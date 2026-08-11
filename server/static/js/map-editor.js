// Map editor — v1.
//
// The server side (parse / validate / instantiate / store / socket events) is
// already shipped. This module is the only missing half: a screen where a
// player paints a hex grid, edits region pools, previews the deal, and saves.
//
// Screen lifecycle
// ─────────────────
// Lobby → Maps button → enterEditor() → #map-editor-screen visible
// Done button / exitEditor() → back to #user-screen
//
// Authored view vs preview
// ─────────────────────────
// While editing, the canvas draws all frame hexes as ocean, tinted by region
// colour (the `overlay` param added to renderBoard). After pressing Preview
// the server deals the map and returns real board data; the canvas then shows
// the dealt terrain. Any edit after that clears previewBoard and returns to
// the authored view.

import {
    editorAddRegionBtn,
    editorBuildingsImportBtn,
    editorBuildingsImportInput,
    editorCanvas,
    editorClearBtn,
    editorDoneBtn,
    editorHarbourCounters,
    editorInspectAnchor,
    editorInspectBtn,
    editorInspectPopover,
    editorMapListEl,
    editorMapNameInput,
    editorNullItem,
    editorPaintBtn,
    editorPreviewBtn,
    editorRadiusSelect,
    editorRegionList,
    editorRegionPopover,
    editorResourcesImportBtn,
    editorResourcesImportInput,
    editorSaveBtn,
    editorSaveConfirmBtn,
    editorSaveCopyBtn,
    editorSavePopover,
    editorScreen,
    editorStatusEl,
    mapsBtn,
    userScreen,
} from './dom.js';
import { showNotice } from './notices.js';
import { togglePopover, openPopover, closePopover } from './popovers.js';
import { emitGame } from './socket.js';
import { viewState } from './state.js';

// ─── constants ───────────────────────────────────────────────────────────────

const REGION_PALETTE = [
    '#8bb26a', '#c9a227', '#6a8eb2', '#b26a8b',
    '#6ab2a0', '#b2916a', '#8a6ab2', '#b26a6a',
];

// `cotton` is a resource no printed box holds, defined server-side (game/tiles.py)
// so a custom map can deal it. It is paintable like any other land tile, takes a
// number token, and can carry a 2:1 harbour — but it is never part of the
// standard mix (STANDARD_MIX gives it 0), so Auto-fill leaves a standard board's
// composition untouched.
const TERRAIN_TYPES = ['wood', 'brick', 'sheep', 'wheat', 'ore', 'cotton', 'desert', 'sea'];
const LAND_TERRAINS = ['wood', 'brick', 'sheep', 'wheat', 'ore', 'cotton', 'desert'];
const RESOURCE_TERRAINS = new Set(['wood', 'brick', 'sheep', 'wheat', 'ore', 'cotton']);

// Explorers & Pirates terrains (map_version 2). Gold takes a number token like a
// resource but is not tradable; a fish shoal and a spice hex take none. Opt-in
// per region, so a v1 map never sees them and stays map_version 1.
const V2_TERRAINS = ['gold', 'fish', 'spice'];
// Everything paintable into a region's pool: the six base land tiles plus the v2
// terrains. `sea` stays out — it is the ocean region's single tile, not a pool
// choice — matching what LAND_TERRAINS meant for the resource checklist.
const POOL_TERRAINS = [...LAND_TERRAINS, ...V2_TERRAINS];
// Tiles the deal must hand a number token: the five base resources and gold.
// Mirrors the server's TOKEN_TERRAINS, and is what the token-count badge checks.
const TOKEN_TERRAINS = new Set([...RESOURCE_TERRAINS, 'gold']);
// A region pool's three deal modes. `shuffled` is the base game; `hidden` deals
// its tiles face-down for ships to discover; `fixed` prints a named tile (and
// its token) on each of the region's hexes. The last two need map_version 2.
const POOL_MODE_LABELS = { shuffled: 'Shuffled', hidden: 'Hidden (discover)', fixed: 'Fixed (printed)' };
// The six sides of a hex a Council-of-Catan dock can sit on.
const HEX_SIDES = [0, 1, 2, 3, 4, 5];

const TOKEN_VALUES = [2, 3, 4, 5, 6, 8, 9, 10, 11, 12];
const HARBOUR_TYPES = ['generic', 'wood', 'brick', 'sheep', 'wheat', 'ore', 'cotton'];

// How much a pool close to the standard 19-hex mix distributes per terrain
// per 19 hexes, used by Auto-fill. `cotton` sits at 0: it is paintable, but the
// standard board deals none, so Auto-fill never changes a base board's mix.
const STANDARD_MIX = { wood: 4, brick: 3, sheep: 4, wheat: 4, ore: 3, cotton: 0, desert: 1, sea: 0 };
const STANDARD_TOKENS = { 2: 1, 3: 2, 4: 2, 5: 2, 6: 2, 8: 2, 9: 2, 10: 2, 11: 2, 12: 1 };

const MAX_UNDO = 30;

// ─── module state ────────────────────────────────────────────────────────────

let mapDoc = newMapDoc();
let tool = 'inspect';           // 'paint' | 'erase' | 'inspect'
let selectedRegionId = null;
let undoStack = [];
let mapList = [];               // last map_list from server
let previewBoard = null;        // board data from map_preview; null = authored view
let screenAbort = null;         // AbortController for screen-scoped listeners
let painting = false;           // pointer is down in paint/erase mode

// ─── default document ────────────────────────────────────────────────────────

function newMapDoc() {
    return {
        id: '',
        name: 'New Map',
        frame: { radius: 4, excluded: [] },
        regions: [
            {
                id: 'mainland',
                name: 'Mainland',
                kind: 'main',
                color: REGION_PALETTE[0],
                hexes: [],
                pool: {
                    mode: 'shuffled',
                    resources: [...LAND_TERRAINS],
                    terrain: {},
                    numbers: [],
                },
            },
            {
                id: 'ocean',
                name: 'Ocean',
                kind: 'sea',
                color: REGION_PALETTE[2],
                hexes: 'remaining',
                pool: { mode: 'shuffled', resources: [], terrain: { sea: 1 }, numbers: [] },
            },
        ],
        harbours: {
            mode: 'bag',
            types: { generic: 4, wood: 1, brick: 1, sheep: 1, wheat: 1, ore: 1 },
        },
    };
}

// ─── frame hex generation ────────────────────────────────────────────────────

function buildFrameHexKeys(radius) {
    // Cube coordinates scaled by 3 (matching the server's coordinate system).
    // A hex is inside the frame when max(|x/3|, |y/3|, |z/3|) <= radius.
    const keys = [];
    const r = radius * 3;
    for (let x = -r; x <= r; x += 3) {
        for (let y = -r; y <= r; y += 3) {
            const z = -x - y;
            if (Math.abs(z) <= r) {
                keys.push(`${x},${y},${z}`);
            }
        }
    }
    // Sort by parsed (x, y, z) — same order as sort_hex_keys on the server.
    keys.sort((a, b) => {
        const [ax, ay, az] = a.split(',').map(Number);
        const [bx, by, bz] = b.split(',').map(Number);
        return ax !== bx ? ax - bx : ay !== by ? ay - by : az - bz;
    });
    return keys;
}

// ─── authored-view board data ─────────────────────────────────────────────────

function buildFrameBoardData(radius) {
    // All frame hexes are present so findNearestHex can register clicks on
    // excluded (null) hexes too. The overlay tints them distinctly.
    const hexes = {};
    for (const key of buildFrameHexKeys(radius)) {
        hexes[key] = { type: 'ocean', number: null };
    }
    return { hexes, vertices: {}, edges: {}, players: [], robber_hex: null };
}

// ─── overlay (region tinting) ─────────────────────────────────────────────────

const VOID_COLOR = '#555566';  // dark grey-blue — visually distinct from ocean

function buildOverlay() {
    const regionOf = {};
    const colors = { __void__: VOID_COLOR };
    let remainingRegion = null;
    for (const region of mapDoc.regions) {
        if (region.hexes === 'remaining') {
            remainingRegion = region;
            continue;
        }
        colors[region.id] = region.color;
        for (const key of region.hexes) {
            regionOf[key] = region.id;
        }
    }
    // Assign all unexcluded, unclaimed hexes to the 'remaining' region so they
    // get its colour instead of rendering as a visually distinct untinted ocean.
    if (remainingRegion) {
        colors[remainingRegion.id] = remainingRegion.color;
        const excluded = new Set(mapDoc.frame.excluded || []);
        for (const key of buildFrameHexKeys(mapDoc.frame.radius)) {
            if (!excluded.has(key) && !regionOf[key]) {
                regionOf[key] = remainingRegion.id;
            }
        }
    }
    for (const key of (mapDoc.frame.excluded || [])) {
        regionOf[key] = '__void__';
    }
    return { regionOf, colors };
}

// ─── render ───────────────────────────────────────────────────────────────────

function renderEditor() {
    // Each call replaces the board object — the renderer memoises on identity,
    // so a fresh object always triggers a layout recompute.
    const board = previewBoard ?? buildFrameBoardData(mapDoc.frame.radius);
    const overlay = previewBoard ? null : buildOverlay();
    window.BoardRenderer.render(board, 'editor-canvas', null, null, [], overlay);
    updateStatusStrip();
}

function updateStatusStrip() {
    const allKeys = buildFrameHexKeys(mapDoc.frame.radius);
    const total = allKeys.length;

    const assigned = new Set();
    let problems = 0;
    for (const region of mapDoc.regions) {
        if (region.hexes === 'remaining') continue;
        for (const key of region.hexes) assigned.add(key);
        const slots = region.hexes.length;
        const { tiles, tokenRequired, tokens } = poolCounts(region);
        if (tiles !== slots) problems++;
        if (tokens !== tokenRequired) problems++;
    }
    const unassigned = total - assigned.size;

    const parts = [`${total} hexes`, `${mapDoc.regions.length} regions`];
    if (unassigned > 0) parts.push(`${unassigned} unassigned`);
    if (problems > 0) parts.push(`${problems} pool problem${problems > 1 ? 's' : ''}`);
    if (previewBoard) parts.push('preview');

    editorStatusEl.textContent = parts.join(' · ');
}

// ─── screen enter / exit ──────────────────────────────────────────────────────

export function enterEditor() {
    userScreen.classList.add('hidden');
    editorScreen.classList.remove('hidden');

    screenAbort = new AbortController();
    const { signal } = screenAbort;

    // Camera controls: space+drag pans, wheel zooms — same as the game board.
    window.BoardRenderer.attachCameraControls(editorCanvas, renderEditor);

    // Pointer: paint on drag in paint/erase modes.
    editorCanvas.addEventListener('pointerdown', onPointerDown, { signal });
    editorCanvas.addEventListener('pointermove', onPointerMove, { signal });
    editorCanvas.addEventListener('pointerup', onPointerUp, { signal });
    editorCanvas.addEventListener('pointercancel', onPointerUp, { signal });
    // Click in Inspect mode opens the per-hex metadata popover.
    editorCanvas.addEventListener('click', onCanvasClick, { signal });

    // Keyboard shortcuts.
    document.addEventListener('keydown', onKeyDown, { signal });

    // Toolbar buttons.
    editorClearBtn.addEventListener('click', clearMap, { signal });
    editorPaintBtn.addEventListener('click', () => setTool('paint'), { signal });
    editorInspectBtn.addEventListener('click', () => setTool('inspect'), { signal });
    editorRadiusSelect.addEventListener('change', changeRadius, { signal });
    editorPreviewBtn.addEventListener('click', requestPreview, { signal });
    editorSaveBtn.addEventListener('click', () => togglePopover(editorSaveBtn), { signal });
    editorDoneBtn.addEventListener('click', exitEditor, { signal });
    editorSaveConfirmBtn.addEventListener('click', saveMap, { signal });
    editorSaveCopyBtn.addEventListener('click', saveMapAsCopy, { signal });

    // Registry import: a hidden file input opened by its visible button, the
    // upload half of the Resources/Buildings download links beside them.
    editorResourcesImportBtn.addEventListener(
        'click', () => editorResourcesImportInput.click(), { signal });
    editorResourcesImportInput.addEventListener(
        'change', (event) => importRegistry('resources', event.target), { signal });
    editorBuildingsImportBtn.addEventListener(
        'click', () => editorBuildingsImportInput.click(), { signal });
    editorBuildingsImportInput.addEventListener(
        'change', (event) => importRegistry('buildings', event.target), { signal });
    document.addEventListener('registry-imported', onRegistryImported, { signal });

    // Sidebar.
    editorNullItem.addEventListener('click', () => selectRegion('__null__'), { signal });
    editorAddRegionBtn.addEventListener('click', addRegion, { signal });

    // Server events relayed as DOM custom events by net.js.
    document.addEventListener('map-list-updated', onMapListUpdated, { signal });
    document.addEventListener('map-preview-received', onMapPreviewReceived, { signal });
    document.addEventListener('map-data-received', onMapDataReceived, { signal });

    emitGame('request_maps', null);
    syncToolUI();
    renderSidebar();
    syncRadiusSelect();
    buildHarbourCounters();
    renderEditor();
}

export function exitEditor() {
    screenAbort?.abort();
    screenAbort = null;
    closePopover();
    editorScreen.classList.add('hidden');
    userScreen.classList.remove('hidden');
}

// ─── registry import ──────────────────────────────────────────────────────────

// Read the picked file, parse it here so nothing malformed is ever emitted, and
// send it to the server. Parse failures are shown in the status line rather than
// sent as garbage; the server's ack (registry-imported) or rejection surfaces
// from there. The input is cleared so the same file can be re-picked.
function importRegistry(kind, input) {
    const file = input.files && input.files[0];
    input.value = '';
    if (!file) return;

    const reader = new FileReader();
    reader.onerror = () => {
        editorStatusEl.textContent = `Import failed — could not read ${file.name}`;
    };
    reader.onload = () => {
        let data;
        try {
            data = JSON.parse(reader.result);
        } catch {
            editorStatusEl.textContent = `Import failed — ${file.name} is not valid JSON`;
            return;
        }
        emitGame('import_registry', { kind, data });
    };
    reader.readAsText(file);
}

function onRegistryImported(event) {
    const { kind, count } = event.detail || {};
    const label = kind === 'buildings' ? 'building' : 'resource';
    editorStatusEl.textContent =
        `Imported ${count} ${label} definition${count === 1 ? '' : 's'}`;
}

// ─── tool management ──────────────────────────────────────────────────────────

function setTool(t) {
    tool = t;
    syncToolUI();
}

function syncToolUI() {
    for (const [btn, t] of [[editorPaintBtn, 'paint'], [editorInspectBtn, 'inspect']]) {
        btn.setAttribute('aria-pressed', String(tool === t));
    }
    editorCanvas.dataset.tool = tool;
}

// ─── pointer handling ─────────────────────────────────────────────────────────

function onPointerDown(e) {
    if (tool === 'inspect') return;
    if (e.button !== 0) return;
    painting = true;
    pushUndo();
    applyToolAt(e);
}

function onPointerMove(e) {
    if (!painting) return;
    if (window.BoardRenderer.wasPanning()) return;
    applyToolAt(e);
}

function onPointerUp() {
    painting = false;
}

function applyToolAt(e) {
    const board = previewBoard ?? buildFrameBoardData(mapDoc.frame.radius);
    const pos = window.BoardRenderer.clientToBoard(editorCanvas, e.clientX, e.clientY);
    const key = window.BoardRenderer.findNearestHex(board, pos.x, pos.y);
    if (!key) return;
    if (tool === 'paint' && selectedRegionId) {
        paintHex(key);
    } else if (tool === 'erase') {
        eraseHex(key);
    }
}

function onCanvasClick(e) {
    // Inspect is the only click tool; paint/erase work on pointerdown/drag. A
    // drag that panned the camera is not a hex pick.
    if (tool !== 'inspect') return;
    if (window.BoardRenderer.wasPanning && window.BoardRenderer.wasPanning()) return;
    const board = previewBoard ?? buildFrameBoardData(mapDoc.frame.radius);
    const pos = window.BoardRenderer.clientToBoard(editorCanvas, e.clientX, e.clientY);
    const key = window.BoardRenderer.findNearestHex(board, pos.x, pos.y);
    if (!key) return;
    openInspectPopover(key, e.clientX, e.clientY);
}

// ─── hex assignment ───────────────────────────────────────────────────────────

function paintHex(hexKey) {
    if (!selectedRegionId) return;
    const region = mapDoc.regions.find(r => r.id === selectedRegionId);
    if (!region) return;

    // Remove from whichever explicit region currently holds it.
    for (const r of mapDoc.regions) {
        if (r.hexes !== 'remaining') {
            r.hexes = r.hexes.filter(k => k !== hexKey);
        }
    }
    // If the target region is explicit, add the hex.
    // If it uses 'remaining', removing it from all other explicit regions is
    // enough — 'remaining' auto-claims everything not explicitly assigned.
    if (region.hexes !== 'remaining') {
        region.hexes = [...region.hexes, hexKey];
    }

    // Un-exclude so the hex re-enters the frame.
    const newExcluded = (mapDoc.frame.excluded || []).filter(k => k !== hexKey);

    mapDoc = {
        ...mapDoc,
        frame: { ...mapDoc.frame, excluded: newExcluded },
        regions: mapDoc.regions.map(r => ({ ...r })),
    };
    previewBoard = null;
    renderEditor();
}

function eraseHex(hexKey) {
    // Remove from any explicit region.
    for (const r of mapDoc.regions) {
        if (r.hexes !== 'remaining') {
            r.hexes = r.hexes.filter(k => k !== hexKey);
        }
    }
    // Mark as excluded (null tile) unless it is already.
    const excluded = mapDoc.frame.excluded || [];
    const newExcluded = excluded.includes(hexKey) ? excluded : [...excluded, hexKey];
    mapDoc = {
        ...mapDoc,
        frame: { ...mapDoc.frame, excluded: newExcluded },
        regions: mapDoc.regions.map(r => ({ ...r })),
    };
    previewBoard = null;
    renderEditor();
}

// ─── undo ─────────────────────────────────────────────────────────────────────

function pushUndo() {
    undoStack.push(JSON.stringify(mapDoc));
    if (undoStack.length > MAX_UNDO) undoStack.shift();
}

function undo() {
    if (!undoStack.length) return;
    mapDoc = JSON.parse(undoStack.pop());
    previewBoard = null;
    renderSidebar();
    syncRadiusSelect();
    renderEditor();
}

// ─── region management ────────────────────────────────────────────────────────

function addRegion() {
    const id = `region-${Date.now()}`;
    const colorIdx = mapDoc.regions.length % REGION_PALETTE.length;
    const region = {
        id,
        name: `Region ${mapDoc.regions.length + 1}`,
        kind: 'island',
        color: REGION_PALETTE[colorIdx],
        hexes: [],
        pool: {
            mode: 'shuffled',
            resources: [...LAND_TERRAINS],
            terrain: {},
            numbers: [],
        },
    };
    mapDoc = { ...mapDoc, regions: [...mapDoc.regions, region] };
    selectedRegionId = id;
    setTool('paint');
    renderSidebar();
    syncRadiusSelect();
    renderEditor();
}

function syncRadiusSelect() {
    editorRadiusSelect.value = String(mapDoc.frame.radius);
}

function changeRadius() {
    const newRadius = parseInt(editorRadiusSelect.value, 10);
    if (newRadius === mapDoc.frame.radius) return;

    // Prune hexes and excluded entries that fall outside the new frame.
    const allKeys = new Set(buildFrameHexKeys(newRadius));
    const newExcluded = (mapDoc.frame.excluded || []).filter(k => allKeys.has(k));
    const newRegions = mapDoc.regions.map(r => {
        if (r.hexes === 'remaining') return { ...r };
        return { ...r, hexes: r.hexes.filter(k => allKeys.has(k)) };
    });

    mapDoc = {
        ...mapDoc,
        frame: { ...mapDoc.frame, radius: newRadius, excluded: newExcluded },
        regions: newRegions,
    };
    previewBoard = null;
    renderEditor();
}

function regionHasProblem(region) {
    if (region.hexes === 'remaining') return false;
    return poolCounts(region).tiles !== region.hexes.length;
}

function renderSidebar() {
    editorRegionList.innerHTML = '';

    editorNullItem.classList.toggle('active', selectedRegionId === '__null__');

    for (const region of mapDoc.regions) {
        const item = document.createElement('div');
        item.className = 'editor-region-item' + (selectedRegionId === region.id ? ' active' : '');
        item.dataset.region = region.id;

        const swatch = document.createElement('span');
        swatch.className = 'editor-region-swatch';
        swatch.style.background = region.color;

        const name = document.createElement('span');
        name.className = 'editor-region-name';
        name.textContent = region.name;

        item.appendChild(swatch);
        item.appendChild(name);

        if (regionHasProblem(region)) {
            const warn = document.createElement('span');
            warn.className = 'editor-region-warn';
            warn.textContent = '!';
            warn.title = 'Tile count does not match hex count — open ⚙ and Auto-fill';
            item.appendChild(warn);
        }

        const gear = document.createElement('button');
        gear.className = 'editor-region-gear';
        gear.textContent = '⚙';
        gear.setAttribute('aria-label', `Settings for ${region.name}`);
        gear.setAttribute('aria-controls', 'editor-region-popover');
        gear.addEventListener('click', (e) => {
            e.stopPropagation();
            openRegionPopover(region, gear);
        });

        item.appendChild(gear);
        item.addEventListener('click', () => selectRegion(region.id));
        editorRegionList.appendChild(item);
    }
}

function selectRegion(regionId) {
    if (regionId === '__null__') {
        selectedRegionId = '__null__';
        setTool('erase');
    } else {
        selectedRegionId = regionId;
        setTool('paint');
    }
    renderSidebar();
}

function inferResources(region) {
    if (Array.isArray(region.pool.resources)) return [...region.pool.resources];
    const fromTerrain = POOL_TERRAINS.filter(t => (region.pool.terrain[t] || 0) > 0);
    if (fromTerrain.length > 0) return fromTerrain;
    return region.kind === 'sea' ? [] : [...LAND_TERRAINS];
}

// A region's deal mode, defaulting to shuffled for a v1 document.
function poolMode(region) {
    return region.pool.mode || 'shuffled';
}

// The tile and token tallies a pool contributes. A fixed pool reads them off its
// per-hex placements; the others off the terrain and number multisets. Kept in
// one place so the sidebar, the status strip and the popover badges agree.
function poolCounts(region) {
    if (poolMode(region) === 'fixed') {
        const placements = Object.values(region.pool.placements || {}).filter(Boolean);
        const placed = placements.filter(p => p.terrain);
        const tokenRequired = placed.filter(p => TOKEN_TERRAINS.has(p.terrain)).length;
        const tokens = placed.filter(p => TOKEN_TERRAINS.has(p.terrain) && p.number != null).length;
        return { tiles: placed.length, tokenRequired, tokens };
    }
    const tiles = Object.values(region.pool.terrain).reduce((s, n) => s + n, 0);
    const tokenRequired = [...TOKEN_TERRAINS].reduce((s, t) => s + (region.pool.terrain[t] || 0), 0);
    return { tiles, tokenRequired, tokens: region.pool.numbers.length };
}

// A hex's per-hex metadata for a region, created empty on first touch.
function hexMetaOf(region, hexKey) {
    if (!region.meta) region.meta = {};
    if (!region.meta[hexKey]) region.meta[hexKey] = { docks: [], village: false };
    return region.meta[hexKey];
}

// Drop a hex's metadata once it carries nothing, so an untouched hex never
// serialises an empty entry.
function pruneHexMeta(region, hexKey) {
    const meta = region.meta?.[hexKey];
    if (meta && meta.docks.length === 0 && !meta.village) {
        delete region.meta[hexKey];
    }
}

// The region that owns a hex: the explicit one holding it, else the 'remaining'
// region, else null for an excluded (void) hex.
function regionOwning(hexKey) {
    let remaining = null;
    for (const region of mapDoc.regions) {
        if (region.hexes === 'remaining') { remaining = region; continue; }
        if (region.hexes.includes(hexKey)) return region;
    }
    if ((mapDoc.frame.excluded || []).includes(hexKey)) return null;
    return remaining;
}

// ─── region settings popover ──────────────────────────────────────────────────

const DEFAULT_REGION_IDS = new Set(['mainland', 'ocean']);

function openRegionPopover(region, gear) {
    buildRegionPopover(region);
    togglePopover(gear);
}

function buildRegionPopover(region) {
    editorRegionPopover.innerHTML = '';

    // Head: name input
    const head = document.createElement('div');
    head.className = 'popover-head';
    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.value = region.name;
    nameInput.maxLength = 32;
    nameInput.style.flex = '1';
    nameInput.addEventListener('input', () => {
        region.name = nameInput.value;
        mapDoc = { ...mapDoc };
        renderSidebar();
    });
    head.appendChild(nameInput);
    editorRegionPopover.appendChild(head);

    // Scrollable body
    const body = document.createElement('div');
    body.className = 'popover-body';

    // Color row
    const colorRow = document.createElement('div');
    colorRow.className = 'editor-rp-row';
    const colorLbl = document.createElement('span');
    colorLbl.className = 'editor-rp-label';
    colorLbl.textContent = 'Color';
    const swatches = document.createElement('div');
    swatches.className = 'editor-color-swatches';
    for (const c of REGION_PALETTE) {
        const sw = document.createElement('button');
        sw.className = 'editor-color-swatch' + (region.color === c ? ' active' : '');
        sw.style.background = c;
        sw.title = c;
        sw.addEventListener('click', () => {
            region.color = c;
            mapDoc = { ...mapDoc };
            renderSidebar();
            buildRegionPopover(region);
        });
        swatches.appendChild(sw);
    }
    colorRow.appendChild(colorLbl);
    colorRow.appendChild(swatches);
    body.appendChild(colorRow);

    // Kind row
    const kindRow = document.createElement('div');
    kindRow.className = 'editor-rp-row';
    const kindLbl = document.createElement('span');
    kindLbl.className = 'editor-rp-label';
    kindLbl.textContent = 'Kind';
    const kindSelect = document.createElement('select');
    for (const k of ['main', 'island', 'sea', 'fog']) {
        const opt = document.createElement('option');
        opt.value = k;
        opt.textContent = k;
        if (region.kind === k) opt.selected = true;
        kindSelect.appendChild(opt);
    }
    kindSelect.addEventListener('change', () => {
        region.kind = kindSelect.value;
        mapDoc = { ...mapDoc };
    });
    kindRow.appendChild(kindLbl);
    kindRow.appendChild(kindSelect);
    body.appendChild(kindRow);

    // Deal-mode row — shuffled (base), hidden (discover by ship) or fixed
    // (printed per hex). The last two lift the map to version 2 on save.
    const modeRow = document.createElement('div');
    modeRow.className = 'editor-rp-row';
    const modeLbl = document.createElement('span');
    modeLbl.className = 'editor-rp-label';
    modeLbl.textContent = 'Deal';
    const modeSelect = document.createElement('select');
    for (const m of Object.keys(POOL_MODE_LABELS)) {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = POOL_MODE_LABELS[m];
        if (poolMode(region) === m) opt.selected = true;
        modeSelect.appendChild(opt);
    }
    modeSelect.addEventListener('change', () => {
        region.pool.mode = modeSelect.value;
        if (region.pool.mode === 'fixed' && !region.pool.placements) {
            region.pool.placements = {};
        }
        mapDoc = { ...mapDoc };
        buildRegionPopover(region);   // the terrain/token columns switch on mode
        renderSidebar();
    });
    modeRow.appendChild(modeLbl);
    modeRow.appendChild(modeSelect);
    body.appendChild(modeRow);

    // Resources section — checkboxes control what auto-fill distributes
    const resHead = document.createElement('div');
    resHead.className = 'editor-pool-section-head';
    resHead.style.marginTop = 'var(--space-2)';
    resHead.textContent = 'Resources';
    body.appendChild(resHead);

    const resources = inferResources(region);
    const resGrid = document.createElement('div');
    resGrid.className = 'editor-resource-grid';
    for (const t of POOL_TERRAINS) {
        const lbl = document.createElement('label');
        lbl.className = 'editor-resource-check';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = resources.includes(t);
        cb.addEventListener('change', () => {
            const cur = inferResources(region);
            region.pool.resources = cb.checked
                ? [...cur, t]
                : cur.filter(r => r !== t);
            mapDoc = { ...mapDoc };
            buildRegionPopover(region);   // rebuild in-place; popover stays open
            renderSidebar();
        });
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(t));
        resGrid.appendChild(lbl);
    }
    body.appendChild(resGrid);

    // Terrain + Token columns: only shown when region has at least one resource.
    // A no-resource region (ocean) needs no tile or token settings.
    const tilesUsed = document.createElement('span');
    tilesUsed.className = 'editor-pool-badge';
    const tokensBadge = document.createElement('span');
    tokensBadge.className = 'editor-pool-badge';

    // A fixed pool has no counts to distribute — each hex names its own tile in
    // the Inspect tool — so it shows a hint in place of the terrain/token columns.
    if (poolMode(region) === 'fixed') {
        const hint = document.createElement('div');
        hint.className = 'editor-pool-hint';
        hint.textContent = 'Fixed pool: pick the Inspect tool, then click each hex to set its tile and number.';
        body.appendChild(hint);
    } else if (resources.length > 0) {
        const columns = document.createElement('div');
        columns.className = 'editor-pool-columns';
        columns.style.marginTop = 'var(--space-2)';

        // Terrain counters — only the checked resources, one per row
        const terrainSection = document.createElement('div');
        terrainSection.className = 'editor-pool-section';
        const terrainHead = document.createElement('div');
        terrainHead.className = 'editor-pool-section-head';
        terrainHead.textContent = 'Terrain pool';
        terrainSection.appendChild(terrainHead);
        for (const terrain of resources) {
            const row = document.createElement('div');
            row.className = 'editor-pool-row';
            const lbl = document.createElement('label');
            lbl.textContent = terrain;
            const dec = document.createElement('button');
            dec.textContent = '−';
            const count = document.createElement('span');
            count.className = 'count';
            count.textContent = String(region.pool.terrain[terrain] || 0);
            const inc = document.createElement('button');
            inc.textContent = '+';
            dec.addEventListener('click', () => {
                const cur = region.pool.terrain[terrain] || 0;
                if (cur <= 0) return;
                if (cur === 1) delete region.pool.terrain[terrain];
                else region.pool.terrain[terrain] = cur - 1;
                count.textContent = String(region.pool.terrain[terrain] || 0);
                mapDoc = { ...mapDoc };
                refreshPoolBadges(region, tilesUsed, tokensBadge);
                updateStatusStrip();
            });
            inc.addEventListener('click', () => {
                region.pool.terrain[terrain] = (region.pool.terrain[terrain] || 0) + 1;
                count.textContent = String(region.pool.terrain[terrain]);
                mapDoc = { ...mapDoc };
                refreshPoolBadges(region, tilesUsed, tokensBadge);
                updateStatusStrip();
            });
            row.appendChild(lbl);
            row.appendChild(dec);
            row.appendChild(count);
            row.appendChild(inc);
            terrainSection.appendChild(row);
        }
        columns.appendChild(terrainSection);

        // Token counters
        const tokenSection = document.createElement('div');
        tokenSection.className = 'editor-pool-section';
        const tokenHead = document.createElement('div');
        tokenHead.className = 'editor-pool-section-head';
        tokenHead.textContent = 'Token pool';
        tokenSection.appendChild(tokenHead);
        const tokenCounts = {};
        for (const v of region.pool.numbers) tokenCounts[v] = (tokenCounts[v] || 0) + 1;
        for (const val of TOKEN_VALUES) {
            const row = document.createElement('div');
            row.className = 'editor-pool-row';
            const lbl = document.createElement('label');
            lbl.textContent = String(val);
            const dec = document.createElement('button');
            dec.textContent = '−';
            const cnt = document.createElement('span');
            cnt.className = 'count';
            cnt.textContent = String(tokenCounts[val] || 0);
            const inc = document.createElement('button');
            inc.textContent = '+';
            dec.addEventListener('click', () => {
                const idx = region.pool.numbers.indexOf(val);
                if (idx === -1) return;
                region.pool.numbers.splice(idx, 1);
                tokenCounts[val] = (tokenCounts[val] || 1) - 1;
                cnt.textContent = String(tokenCounts[val] || 0);
                mapDoc = { ...mapDoc };
                refreshPoolBadges(region, tilesUsed, tokensBadge);
                updateStatusStrip();
            });
            inc.addEventListener('click', () => {
                region.pool.numbers.push(val);
                tokenCounts[val] = (tokenCounts[val] || 0) + 1;
                cnt.textContent = String(tokenCounts[val]);
                mapDoc = { ...mapDoc };
                refreshPoolBadges(region, tilesUsed, tokensBadge);
                updateStatusStrip();
            });
            row.appendChild(lbl);
            row.appendChild(dec);
            row.appendChild(cnt);
            row.appendChild(inc);
            tokenSection.appendChild(row);
        }
        columns.appendChild(tokenSection);
        body.appendChild(columns);
    }
    editorRegionPopover.appendChild(body);

    // Footer: badges (only when resources exist) + auto-fill + delete + close
    const footer = document.createElement('div');
    footer.className = 'editor-pool-footer';

    if (resources.length > 0) {
        const badges = document.createElement('div');
        badges.className = 'editor-pool-badges';
        badges.appendChild(tilesUsed);
        badges.appendChild(tokensBadge);
        footer.appendChild(badges);
        refreshPoolBadges(region, tilesUsed, tokensBadge);

        // Auto-fill distributes a shuffled/hidden pool; a fixed one is placed by
        // hand, so it offers no button to fill.
        if (poolMode(region) !== 'fixed') {
            const autoFill = document.createElement('button');
            autoFill.textContent = 'Auto-fill';
            autoFill.addEventListener('click', () => {
                autoFillPool(region);
                buildRegionPopover(region);
            });
            footer.appendChild(autoFill);
        }
    }

    if (!DEFAULT_REGION_IDS.has(region.id)) {
        const delBtn = document.createElement('button');
        delBtn.textContent = 'Delete';
        delBtn.dataset.confirm = '0';
        delBtn.addEventListener('click', () => {
            if (delBtn.dataset.confirm !== '1') {
                delBtn.textContent = 'Sure?';
                delBtn.dataset.confirm = '1';
                return;
            }
            mapDoc = { ...mapDoc, regions: mapDoc.regions.filter(r => r.id !== region.id) };
            if (selectedRegionId === region.id) selectedRegionId = mapDoc.regions[0]?.id ?? null;
            renderSidebar();
            renderEditor();
            closePopover();
        });
        footer.appendChild(delBtn);
    }

    const done = document.createElement('button');
    done.textContent = 'Done';
    done.addEventListener('click', closePopover);
    footer.appendChild(done);

    editorRegionPopover.appendChild(footer);
}

function refreshPoolBadges(region, tilesBadge, tokensBadge) {
    const slots = region.hexes === 'remaining' ? 0 : region.hexes.length;
    const { tiles, tokenRequired, tokens } = poolCounts(region);

    tilesBadge.textContent = `tiles ${tiles}/${slots}`;
    tilesBadge.classList.toggle('bad', tiles !== slots);
    tokensBadge.textContent = `tokens ${tokens}/${tokenRequired}`;
    tokensBadge.classList.toggle('bad', tokens !== tokenRequired);
}

// ─── per-hex inspect popover (docks, village, fixed placement) ─────────────────

function openInspectPopover(hexKey, x, y) {
    const region = regionOwning(hexKey);
    if (region === null) {
        showNotice('Paint this hex into a region before setting its tile or docks', 'info');
        return;
    }
    buildInspectPopover(hexKey, region);
    // Pin the zero-size anchor to the click so the shared placer sits the popover
    // beside the hex the player actually pressed.
    editorInspectAnchor.style.left = `${Math.round(x)}px`;
    editorInspectAnchor.style.top = `${Math.round(y)}px`;
    openPopover(editorInspectAnchor);
}

function buildInspectPopover(hexKey, region) {
    editorInspectPopover.innerHTML = '';

    const head = document.createElement('div');
    head.className = 'popover-head';
    const title = document.createElement('span');
    title.style.flex = '1';
    title.textContent = `Hex ${hexKey} · ${region.name}`;
    head.appendChild(title);
    editorInspectPopover.appendChild(head);

    const body = document.createElement('div');
    body.className = 'popover-body';

    // Fixed pools print a named tile (and its number) on this hex.
    if (poolMode(region) === 'fixed') {
        body.appendChild(buildFixedPlacementSection(hexKey, region));
    }

    // Docks — a Council-of-Catan sea hex carries a dock on any of its six sides.
    const docksHead = document.createElement('div');
    docksHead.className = 'editor-pool-section-head';
    docksHead.textContent = 'Docks (Council of Catan)';
    body.appendChild(docksHead);

    const docksGrid = document.createElement('div');
    docksGrid.className = 'editor-resource-grid';
    for (const side of HEX_SIDES) {
        const lbl = document.createElement('label');
        lbl.className = 'editor-resource-check';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = (region.meta?.[hexKey]?.docks || []).includes(side);
        cb.addEventListener('change', () => {
            const meta = hexMetaOf(region, hexKey);
            meta.docks = cb.checked
                ? [...new Set([...meta.docks, side])]
                : meta.docks.filter(s => s !== side);
            afterMetaChange(region, hexKey);
        });
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(`Side ${side}`));
        docksGrid.appendChild(lbl);
    }
    body.appendChild(docksGrid);

    // Village — a spice-scenario advantage tile.
    const villageRow = document.createElement('label');
    villageRow.className = 'editor-resource-check';
    villageRow.style.marginTop = 'var(--space-2)';
    const villageCb = document.createElement('input');
    villageCb.type = 'checkbox';
    villageCb.checked = !!region.meta?.[hexKey]?.village;
    villageCb.addEventListener('change', () => {
        hexMetaOf(region, hexKey).village = villageCb.checked;
        afterMetaChange(region, hexKey);
    });
    villageRow.appendChild(villageCb);
    villageRow.appendChild(document.createTextNode('Village'));
    body.appendChild(villageRow);

    editorInspectPopover.appendChild(body);

    const footer = document.createElement('div');
    footer.className = 'editor-pool-footer';
    const done = document.createElement('button');
    done.textContent = 'Done';
    done.addEventListener('click', () => closePopover());
    footer.appendChild(done);
    editorInspectPopover.appendChild(footer);
}

function buildFixedPlacementSection(hexKey, region) {
    const section = document.createElement('div');

    const head = document.createElement('div');
    head.className = 'editor-pool-section-head';
    head.textContent = 'Tile';
    section.appendChild(head);

    const placement = region.pool.placements[hexKey] || { terrain: '', number: null };

    const terrainRow = document.createElement('div');
    terrainRow.className = 'editor-rp-row';
    const terrainLbl = document.createElement('span');
    terrainLbl.className = 'editor-rp-label';
    terrainLbl.textContent = 'Terrain';
    const terrainSelect = document.createElement('select');
    const none = document.createElement('option');
    none.value = '';
    none.textContent = '(none)';
    terrainSelect.appendChild(none);
    // The region's checked resources bound what may be placed here.
    for (const t of inferResources(region)) {
        const opt = document.createElement('option');
        opt.value = t;
        opt.textContent = t;
        if (placement.terrain === t) opt.selected = true;
        terrainSelect.appendChild(opt);
    }
    terrainSelect.value = placement.terrain || '';
    terrainSelect.addEventListener('change', () => {
        const terrain = terrainSelect.value;
        if (!terrain) {
            delete region.pool.placements[hexKey];
        } else {
            const keepNumber = TOKEN_TERRAINS.has(terrain) ? placement.number ?? null : null;
            region.pool.placements[hexKey] = { terrain, number: keepNumber };
        }
        afterPlacementChange(region);
        buildInspectPopover(hexKey, region);   // number row appears/disappears
    });
    terrainRow.appendChild(terrainLbl);
    terrainRow.appendChild(terrainSelect);
    section.appendChild(terrainRow);

    // A number is printed only for a tile that takes one.
    if (placement.terrain && TOKEN_TERRAINS.has(placement.terrain)) {
        const numberRow = document.createElement('div');
        numberRow.className = 'editor-rp-row';
        const numberLbl = document.createElement('span');
        numberLbl.className = 'editor-rp-label';
        numberLbl.textContent = 'Number';
        const numberSelect = document.createElement('select');
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = '—';
        numberSelect.appendChild(blank);
        for (const val of TOKEN_VALUES) {
            const opt = document.createElement('option');
            opt.value = String(val);
            opt.textContent = String(val);
            if (placement.number === val) opt.selected = true;
            numberSelect.appendChild(opt);
        }
        numberSelect.value = placement.number != null ? String(placement.number) : '';
        numberSelect.addEventListener('change', () => {
            region.pool.placements[hexKey].number =
                numberSelect.value ? Number(numberSelect.value) : null;
            afterPlacementChange(region);
        });
        numberRow.appendChild(numberLbl);
        numberRow.appendChild(numberSelect);
        section.appendChild(numberRow);
    }

    return section;
}

function afterMetaChange(region, hexKey) {
    pruneHexMeta(region, hexKey);
    mapDoc = { ...mapDoc };
}

function afterPlacementChange(region) {
    mapDoc = { ...mapDoc };
    renderSidebar();
    updateStatusStrip();
}

function autoFillPool(region) {
    if (region.hexes === 'remaining') return;
    // A fixed pool is placed hex by hex in the Inspect tool; there is nothing to
    // distribute, so auto-fill leaves it alone.
    if (poolMode(region) === 'fixed') return;
    const slots = region.hexes.length;
    if (slots === 0) return;

    const resources = inferResources(region);
    if (resources.length === 0) {
        region.pool.terrain = {};
        region.pool.numbers = [];
        mapDoc = { ...mapDoc };
        renderEditor();
        return;
    }

    // Distribute equally across enabled resources, then handle the remainder.
    const base = Math.floor(slots / resources.length);
    const remainder = slots % resources.length;
    const terrain = {};
    for (let i = 0; i < resources.length; i++) {
        terrain[resources[i]] = base + (i < remainder ? 1 : 0);
    }

    region.pool.terrain = terrain;

    // Tokens only for tiles that take one (the base resources and gold), scaling
    // the standard distribution; desert, sea, fish and spice take none.
    const tokenTiles = resources.filter(t => TOKEN_TERRAINS.has(t))
        .reduce((s, t) => s + (terrain[t] || 0), 0);
    const tokenScale = tokenTiles / 18;
    const numbers = [];
    for (const [val, count] of Object.entries(STANDARD_TOKENS)) {
        const n = Math.round(count * tokenScale);
        for (let i = 0; i < n; i++) numbers.push(Number(val));
    }
    while (numbers.length > tokenTiles) numbers.pop();
    while (numbers.length < tokenTiles) numbers.push(5);
    region.pool.numbers = numbers;

    mapDoc = { ...mapDoc };
    renderSidebar();
    renderEditor();
}

// ─── preview ──────────────────────────────────────────────────────────────────

function requestPreview() {
    const problems = mapDoc.regions.filter(r => regionHasProblem(r));
    if (problems.length > 0) {
        const names = problems.map(r => r.name).join(', ');
        if (confirm(`Auto-fill ${names} before previewing?\n\nTile counts don't match hex counts — the preview will fail without this.`)) {
            for (const r of problems) autoFillPool(r);
            renderSidebar();
        }
    }
    const wire = mapDocToWire();
    if (!wire) return;
    emitGame('preview_map', { map: wire });
}

function onMapDataReceived(e) {
    const { map, builtin } = e.detail || {};
    if (!map) return;
    if (builtin) {
        duplicateMap(map);
    } else {
        loadMap(map);
    }
}

function onMapPreviewReceived(e) {
    const { board, warnings } = e.detail || {};
    if (!board) return;
    previewBoard = board;
    if (warnings?.length) {
        showNotice(warnings.map(w => w.message).join('; '), 'info');
    }
    renderEditor();
}

// ─── save / load ──────────────────────────────────────────────────────────────

function saveMap() {
    const name = editorMapNameInput.value.trim();
    if (name) mapDoc.name = name;
    if (!mapDoc.id) mapDoc.id = slugify(mapDoc.name);
    const wire = mapDocToWire();
    if (!wire) return;
    emitGame('save_map', { map: wire });
    closePopover();
}

function saveMapAsCopy() {
    const name = `${editorMapNameInput.value.trim() || mapDoc.name} copy`;
    mapDoc = { ...mapDoc, id: slugify(name), name };
    editorMapNameInput.value = name;
    saveMap();
}

function clearMap() {
    pushUndo();
    mapDoc = newMapDoc();
    previewBoard = null;
    undoStack = [];
    selectedRegionId = mapDoc.regions[0]?.id ?? null;
    editorMapNameInput.value = mapDoc.name;
    renderSidebar();
    syncRadiusSelect();
    buildHarbourCounters();
    renderEditor();
}

function loadMap(mapData) {
    // mapData is an entry from the server's map_list.
    try {
        mapDoc = serverMapToDoc(mapData);
    } catch {
        showNotice('Could not load map', 'error');
        return;
    }
    previewBoard = null;
    undoStack = [];
    selectedRegionId = mapDoc.regions[0]?.id ?? null;
    editorMapNameInput.value = mapDoc.name;
    renderSidebar();
    syncRadiusSelect();
    buildHarbourCounters();
    renderEditor();
    closePopover();
}

function onMapListUpdated() {
    mapList = viewState.server.mapList || [];
    rebuildMapList();
    renderSidebar();
    syncRadiusSelect();
}

function rebuildMapList() {
    editorMapListEl.innerHTML = '';
    for (const m of mapList) {
        const li = document.createElement('li');
        li.className = 'editor-map-entry';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'map-name';
        nameSpan.textContent = m.name || m.id;
        li.appendChild(nameSpan);

        if (m.builtin) {
            const tag = document.createElement('span');
            tag.className = 'map-builtin';
            tag.textContent = 'built-in';
            li.appendChild(tag);
        }

        const loadBtn = document.createElement('button');
        loadBtn.textContent = 'Load';
        loadBtn.addEventListener('click', () => {
            // map_list entries are summaries only (no regions/frame/pool).
            // Request the full definition from the server before loading.
            emitGame('request_map', { id: m.id });
        });
        li.appendChild(loadBtn);

        if (!m.builtin) {
            const dupBtn = document.createElement('button');
            dupBtn.textContent = 'Dup';
            dupBtn.addEventListener('click', () => duplicateMap(m));
            li.appendChild(dupBtn);

            const delBtn = document.createElement('button');
            delBtn.textContent = 'Delete';
            delBtn.dataset.confirm = '0';
            delBtn.addEventListener('click', () => {
                if (delBtn.dataset.confirm !== '1') {
                    delBtn.textContent = 'Confirm?';
                    delBtn.dataset.confirm = '1';
                    return;
                }
                emitGame('delete_map', { id: m.id, confirm: true });
                delBtn.textContent = 'Delete';
                delBtn.dataset.confirm = '0';
            });
            li.appendChild(delBtn);
        }

        editorMapListEl.appendChild(li);
    }
}

function loadOrDuplicate(m) {
    // The server's map_list entry carries enough for preview but not the full
    // region/pool data. For v1 we synthesise a minimal doc from what we have
    // and let the user preview to fill in the rest.
    duplicateMap(m);
}

function duplicateMap(m) {
    // Build a doc from the list entry. Built-in maps return their full
    // definition in the list (the server serialises them that way).
    mapDoc = {
        id: '',
        name: `${m.name || m.id} copy`,
        frame: { radius: m.frame?.radius || 4, excluded: Array.isArray(m.frame?.excluded) ? [...m.frame.excluded] : [] },
        regions: (m.regions || []).map(r => {
            const pool = r.pool
                ? { ...r.pool, terrain: { ...(r.pool.terrain || {}) }, numbers: [...(r.pool.numbers || [])] }
                : { mode: 'shuffled', terrain: {}, numbers: [] };
            const stub = { kind: r.kind || 'island', pool };
            pool.resources = inferResources(stub);
            return {
                ...r,
                color: r.color || REGION_PALETTE[0],
                hexes: Array.isArray(r.hexes) ? [...r.hexes] : r.hexes,
                pool,
            };
        }),
        harbours: m.harbours ? { ...m.harbours, types: { ...(m.harbours.types || {}) } }
                             : { mode: 'bag', types: { generic: 4, wood: 1, brick: 1, sheep: 1, wheat: 1, ore: 1 } },
    };
    previewBoard = null;
    undoStack = [];
    selectedRegionId = mapDoc.regions[0]?.id ?? null;
    editorMapNameInput.value = mapDoc.name;
    renderSidebar();
    syncRadiusSelect();
    buildHarbourCounters();
    renderEditor();
    closePopover();
}

// ─── harbours ─────────────────────────────────────────────────────────────────

function buildHarbourCounters() {
    editorHarbourCounters.innerHTML = '';
    for (const type of HARBOUR_TYPES) {
        const row = document.createElement('div');
        row.className = 'editor-harbour-row';

        const lbl = document.createElement('label');
        lbl.textContent = type;

        const dec = document.createElement('button');
        dec.textContent = '−';
        const cnt = document.createElement('span');
        cnt.className = 'count';
        cnt.textContent = String(mapDoc.harbours.types[type] || 0);
        const inc = document.createElement('button');
        inc.textContent = '+';

        dec.addEventListener('click', () => {
            const cur = mapDoc.harbours.types[type] || 0;
            if (cur <= 0) return;
            mapDoc.harbours.types[type] = cur - 1;
            cnt.textContent = String(mapDoc.harbours.types[type]);
        });
        inc.addEventListener('click', () => {
            mapDoc.harbours.types[type] = (mapDoc.harbours.types[type] || 0) + 1;
            cnt.textContent = String(mapDoc.harbours.types[type]);
        });

        row.appendChild(lbl);
        row.appendChild(dec);
        row.appendChild(cnt);
        row.appendChild(inc);
        editorHarbourCounters.appendChild(row);
    }
}

// ─── wire serialisation ───────────────────────────────────────────────────────

// The map is version 2 the moment it uses anything the base format cannot carry:
// a non-shuffled pool, an Explorers & Pirates terrain, or per-hex metadata.
// Otherwise it stays version 1 and means exactly what it always did.
function mapVersion() {
    for (const r of mapDoc.regions) {
        if (poolMode(r) !== 'shuffled') return 2;
        if (r.meta && Object.keys(metaToWire(r)).length) return 2;
        if (Object.keys(r.pool.terrain || {}).some(t => V2_TERRAINS.includes(t))) return 2;
    }
    return 1;
}

// A region's per-hex metadata as the server reads it: a hex maps to its docks
// and/or village, and a hex with neither is left out entirely.
function metaToWire(region) {
    const out = {};
    for (const [key, m] of Object.entries(region.meta || {})) {
        const entry = {};
        if (m.docks?.length) entry.docks = [...m.docks].sort((a, b) => a - b);
        if (m.village) entry.village = true;
        if (Object.keys(entry).length) out[key] = entry;
    }
    return out;
}

// A fixed pool's placements as the server reads them: each hex names its tile,
// and prints a number only when the tile takes one.
function placementsToWire(region) {
    const out = {};
    for (const [key, p] of Object.entries(region.pool.placements || {})) {
        if (!p || !p.terrain) continue;
        const spec = { terrain: p.terrain };
        if (TOKEN_TERRAINS.has(p.terrain) && p.number != null) spec.number = p.number;
        out[key] = spec;
    }
    return out;
}

function poolToWire(r) {
    if (poolMode(r) === 'fixed') {
        return { mode: 'fixed', placements: placementsToWire(r) };
    }
    let terrain;
    if (r.hexes === 'remaining') {
        // Compute exact remaining count so the server pool-size check passes.
        const allKeys = buildFrameHexKeys(mapDoc.frame.radius);
        const excluded = new Set(mapDoc.frame.excluded || []);
        const explicit = new Set(
            mapDoc.regions.filter(o => o.hexes !== 'remaining')
                          .flatMap(o => o.hexes)
        );
        const remaining = allKeys.filter(k => !excluded.has(k) && !explicit.has(k)).length;
        terrain = { sea: remaining };
    } else {
        terrain = { ...r.pool.terrain };
    }
    return { mode: poolMode(r), terrain, numbers: [...r.pool.numbers] };
}

function mapDocToWire() {
    if (!mapDoc.id) {
        showNotice('Enter a map name first', 'error');
        return null;
    }
    return {
        map_version: mapVersion(),
        id: mapDoc.id,
        name: mapDoc.name,
        frame: mapDoc.frame.excluded?.length
            ? { radius: mapDoc.frame.radius, excluded: sortHexKeys([...mapDoc.frame.excluded]) }
            : { radius: mapDoc.frame.radius },
        regions: mapDoc.regions.map(r => {
            const wire = {
                id: r.id,
                kind: r.kind,
                color: r.color,
                hexes: r.hexes === 'remaining' ? 'remaining' : sortHexKeys([...r.hexes]),
                pool: poolToWire(r),
            };
            const meta = metaToWire(r);
            if (Object.keys(meta).length) wire.meta = meta;
            return wire;
        }),
        harbours: { mode: mapDoc.harbours.mode, types: { ...mapDoc.harbours.types } },
    };
}

function serverMapToDoc(m) {
    return {
        id: m.id || '',
        name: m.name || m.id,
        frame: { radius: m.frame?.radius || 4, excluded: Array.isArray(m.frame?.excluded) ? [...m.frame.excluded] : [] },
        regions: (m.regions || []).map(r => {
            const raw = r.pool || {};
            const mode = raw.mode || 'shuffled';
            let pool;
            if (mode === 'fixed') {
                const placements = {};
                for (const [key, spec] of Object.entries(raw.placements || {})) {
                    placements[key] = { terrain: spec.terrain, number: spec.number ?? null };
                }
                pool = { mode, terrain: {}, numbers: [], placements };
                // The allowed placement terrains come from what was placed, so a
                // reloaded fixed pool still offers gold/fish/spice in its dropdown.
                const placed = [...new Set(Object.values(placements).map(p => p.terrain).filter(Boolean))];
                pool.resources = placed.length ? placed : [...LAND_TERRAINS];
            } else {
                pool = {
                    mode,
                    terrain: { ...(raw.terrain || {}) },
                    numbers: [...(raw.numbers || [])],
                };
                pool.resources = inferResources({ kind: r.kind || 'island', pool });
            }
            const meta = {};
            for (const [key, spec] of Object.entries(r.meta || {})) {
                meta[key] = {
                    docks: Array.isArray(spec.docks) ? [...spec.docks] : [],
                    village: !!spec.village,
                };
            }
            return {
                id: r.id,
                name: r.name || r.id,
                kind: r.kind || 'island',
                color: r.color || REGION_PALETTE[0],
                hexes: r.hexes === 'remaining' ? 'remaining'
                     : Array.isArray(r.hexes) ? [...r.hexes] : [],
                pool,
                meta,
            };
        }),
        harbours: m.harbours ? {
            mode: m.harbours.mode || 'bag',
            types: { ...(m.harbours.types || {}) },
        } : { mode: 'bag', types: { generic: 4, wood: 1, brick: 1, sheep: 1, wheat: 1, ore: 1 } },
    };
}

// ─── keyboard ─────────────────────────────────────────────────────────────────

function onKeyDown(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

    if (e.ctrlKey && e.key === 'z') { e.preventDefault(); undo(); return; }
    if (e.key === 'p' || e.key === 'P') { setTool('paint'); return; }
    if (e.key === 'e' || e.key === 'E') { selectRegion('__null__'); return; }
    if (e.key === 'i' || e.key === 'I') { setTool('inspect'); return; }

    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= 9 && mapDoc.regions[n - 1]) {
        selectRegion(mapDoc.regions[n - 1].id);
    }
}

// ─── Maps lobby button (wired here, called from lobby.js) ─────────────────────

export function initMapsButton() {
    mapsBtn.addEventListener('click', () => {
        if (viewState.server.rules?.locked) return;
        enterEditor();
    });
}

// ─── utilities ────────────────────────────────────────────────────────────────

function slugify(name) {
    return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48) || `map-${Date.now()}`;
}

function sortHexKeys(keys) {
    return keys.sort((a, b) => {
        const [ax, ay, az] = a.split(',').map(Number);
        const [bx, by, bz] = b.split(',').map(Number);
        return ax !== bx ? ax - bx : ay !== by ? ay - by : az - bz;
    });
}
