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
    editorCanvas,
    editorDoneBtn,
    editorHarbourCounters,
    editorInspectBtn,
    editorMapListEl,
    editorMapNameInput,
    editorNullItem,
    editorPaintBtn,
    editorPreviewBtn,
    editorRadiusSelect,
    editorRegionList,
    editorRegionPopover,
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
import { togglePopover, closePopover } from './popovers.js';
import { emitGame } from './socket.js';
import { viewState } from './state.js';

// ─── constants ───────────────────────────────────────────────────────────────

const REGION_PALETTE = [
    '#8bb26a', '#c9a227', '#6a8eb2', '#b26a8b',
    '#6ab2a0', '#b2916a', '#8a6ab2', '#b26a6a',
];

const TERRAIN_TYPES = ['wood', 'brick', 'sheep', 'wheat', 'ore', 'desert', 'sea'];
const LAND_TERRAINS = ['wood', 'brick', 'sheep', 'wheat', 'ore', 'desert'];
const RESOURCE_TERRAINS = new Set(['wood', 'brick', 'sheep', 'wheat', 'ore']);
const TOKEN_VALUES = [2, 3, 4, 5, 6, 8, 9, 10, 11, 12];
const HARBOUR_TYPES = ['generic', 'wood', 'brick', 'sheep', 'wheat', 'ore'];

// How much a pool close to the standard 19-hex mix distributes per terrain
// per 19 hexes, used by Auto-fill.
const STANDARD_MIX = { wood: 4, brick: 3, sheep: 4, wheat: 4, ore: 3, desert: 1, sea: 0 };
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
    for (const region of mapDoc.regions) {
        if (region.hexes === 'remaining') continue;
        colors[region.id] = region.color;
        for (const key of region.hexes) {
            regionOf[key] = region.id;
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
        const tiles = Object.values(region.pool.terrain).reduce((s, n) => s + n, 0);
        const tokenRequired = TERRAIN_TYPES.filter(t => RESOURCE_TERRAINS.has(t))
            .reduce((s, t) => s + (region.pool.terrain[t] || 0), 0);
        if (tiles !== slots) problems++;
        if (region.pool.numbers.length !== tokenRequired) problems++;
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

    // Keyboard shortcuts.
    document.addEventListener('keydown', onKeyDown, { signal });

    // Toolbar buttons.
    editorPaintBtn.addEventListener('click', () => setTool('paint'), { signal });
    editorInspectBtn.addEventListener('click', () => setTool('inspect'), { signal });
    editorRadiusSelect.addEventListener('change', changeRadius, { signal });
    editorPreviewBtn.addEventListener('click', requestPreview, { signal });
    editorSaveBtn.addEventListener('click', () => togglePopover(editorSaveBtn), { signal });
    editorDoneBtn.addEventListener('click', exitEditor, { signal });
    editorSaveConfirmBtn.addEventListener('click', saveMap, { signal });
    editorSaveCopyBtn.addEventListener('click', saveMapAsCopy, { signal });

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
    const slots = region.hexes.length;
    const tiles = Object.values(region.pool.terrain).reduce((s, n) => s + n, 0);
    return tiles !== slots;
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
    const fromTerrain = LAND_TERRAINS.filter(t => (region.pool.terrain[t] || 0) > 0);
    if (fromTerrain.length > 0) return fromTerrain;
    return region.kind === 'sea' ? [] : [...LAND_TERRAINS];
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

    // Resources section — checkboxes control what auto-fill distributes
    const resHead = document.createElement('div');
    resHead.className = 'editor-pool-section-head';
    resHead.style.marginTop = 'var(--space-2)';
    resHead.textContent = 'Resources';
    body.appendChild(resHead);

    const resources = inferResources(region);
    const resGrid = document.createElement('div');
    resGrid.className = 'editor-resource-grid';
    for (const t of LAND_TERRAINS) {
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

    if (resources.length > 0) {
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

        const autoFill = document.createElement('button');
        autoFill.textContent = 'Auto-fill';
        autoFill.addEventListener('click', () => {
            autoFillPool(region);
            buildRegionPopover(region);
        });
        footer.appendChild(autoFill);
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
    const tiles = Object.values(region.pool.terrain).reduce((s, n) => s + n, 0);
    const tokenRequired = TERRAIN_TYPES
        .filter(t => RESOURCE_TERRAINS.has(t))
        .reduce((s, t) => s + (region.pool.terrain[t] || 0), 0);
    const tokens = region.pool.numbers.length;

    tilesBadge.textContent = `tiles ${tiles}/${slots}`;
    tilesBadge.classList.toggle('bad', tiles !== slots);
    tokensBadge.textContent = `tokens ${tokens}/${tokenRequired}`;
    tokensBadge.classList.toggle('bad', tokens !== tokenRequired);
}

function autoFillPool(region) {
    if (region.hexes === 'remaining') return;
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

    // Tokens for non-desert, non-sea tiles — scale standard distribution.
    const tokenTiles = slots - (terrain.desert || 0) - (terrain.sea || 0);
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

function mapDocToWire() {
    if (!mapDoc.id) {
        showNotice('Enter a map name first', 'error');
        return null;
    }
    return {
        map_version: 1,
        id: mapDoc.id,
        name: mapDoc.name,
        frame: mapDoc.frame.excluded?.length
            ? { radius: mapDoc.frame.radius, excluded: sortHexKeys([...mapDoc.frame.excluded]) }
            : { radius: mapDoc.frame.radius },
        regions: mapDoc.regions.map(r => {
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
            return {
                id: r.id,
                kind: r.kind,
                color: r.color,
                hexes: r.hexes === 'remaining' ? 'remaining' : sortHexKeys([...r.hexes]),
                pool: { mode: r.pool.mode, terrain, numbers: [...r.pool.numbers] },
            };
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
            const pool = r.pool ? {
                mode: r.pool.mode || 'shuffled',
                terrain: { ...(r.pool.terrain || {}) },
                numbers: [...(r.pool.numbers || [])],
            } : { mode: 'shuffled', terrain: {}, numbers: [] };
            const stub = { kind: r.kind || 'island', pool };
            pool.resources = inferResources(stub);
            return {
                id: r.id,
                name: r.name || r.id,
                kind: r.kind || 'island',
                color: r.color || REGION_PALETTE[0],
                hexes: r.hexes === 'remaining' ? 'remaining'
                     : Array.isArray(r.hexes) ? [...r.hexes] : [],
                pool,
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
