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
    editorEraseBtn,
    editorHarbourCounters,
    editorInspectBtn,
    editorMapListEl,
    editorMapNameInput,
    editorPaintBtn,
    editorPoolPopover,
    editorPoolTrigger,
    editorPreviewBtn,
    editorRegionSelect,
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
        frame: { radius: 4 },
        regions: [
            {
                id: 'mainland',
                name: 'Mainland',
                kind: 'main',
                color: REGION_PALETTE[0],
                hexes: [],
                pool: { mode: 'shuffled', terrain: {}, numbers: [] },
            },
            {
                id: 'ocean',
                name: 'Ocean',
                kind: 'sea',
                color: REGION_PALETTE[2],
                hexes: 'remaining',
                pool: { mode: 'shuffled', terrain: { sea: 1 }, numbers: [] },
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
    // Minimal boardData the renderer accepts: hexes as ocean, no vertices,
    // edges, players, or robber. Replaced as a new object on every edit so the
    // renderer's identity-based memo always sees a fresh board.
    const hexes = {};
    for (const key of buildFrameHexKeys(radius)) {
        hexes[key] = { type: 'ocean', number: null };
    }
    return { hexes, vertices: {}, edges: {}, players: [], robber_hex: null };
}

// ─── overlay (region tinting) ─────────────────────────────────────────────────

function buildOverlay() {
    const regionOf = {};
    const colors = {};
    for (const region of mapDoc.regions) {
        if (region.hexes === 'remaining') continue;
        colors[region.id] = region.color;
        for (const key of region.hexes) {
            regionOf[key] = region.id;
        }
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
    editorEraseBtn.addEventListener('click', () => setTool('erase'), { signal });
    editorInspectBtn.addEventListener('click', () => setTool('inspect'), { signal });
    editorAddRegionBtn.addEventListener('click', addRegion, { signal });
    editorRegionSelect.addEventListener('change', () => {
        selectedRegionId = editorRegionSelect.value || null;
    }, { signal });
    editorPoolTrigger.addEventListener('click', () => {
        if (selectedRegionId) openPoolPopover(selectedRegionId);
    }, { signal });
    editorPreviewBtn.addEventListener('click', requestPreview, { signal });
    editorSaveBtn.addEventListener('click', () => togglePopover(editorSaveBtn), { signal });
    editorDoneBtn.addEventListener('click', exitEditor, { signal });
    editorSaveConfirmBtn.addEventListener('click', saveMap, { signal });
    editorSaveCopyBtn.addEventListener('click', saveMapAsCopy, { signal });

    // Server events relayed as DOM custom events by net.js.
    document.addEventListener('map-list-updated', onMapListUpdated, { signal });
    document.addEventListener('map-preview-received', onMapPreviewReceived, { signal });

    emitGame('request_maps', null);
    syncToolUI();
    syncRegionSelect();
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
    for (const [btn, t] of [[editorPaintBtn, 'paint'], [editorEraseBtn, 'erase'], [editorInspectBtn, 'inspect']]) {
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
    const key = window.BoardRenderer.findNearestHex(board, e.clientX, e.clientY);
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
    if (!region || region.hexes === 'remaining') return;

    // Remove from whichever region currently holds it.
    for (const r of mapDoc.regions) {
        if (r.hexes !== 'remaining') {
            r.hexes = r.hexes.filter(k => k !== hexKey);
        }
    }
    region.hexes = [...region.hexes, hexKey];

    // Replace mapDoc object to bust the renderer's layout memo.
    mapDoc = { ...mapDoc, regions: mapDoc.regions.map(r => ({ ...r })) };
    previewBoard = null;
    renderEditor();
}

function eraseHex(hexKey) {
    let changed = false;
    for (const r of mapDoc.regions) {
        if (r.hexes !== 'remaining' && r.hexes.includes(hexKey)) {
            r.hexes = r.hexes.filter(k => k !== hexKey);
            changed = true;
        }
    }
    if (!changed) return;
    mapDoc = { ...mapDoc, regions: mapDoc.regions.map(r => ({ ...r })) };
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
    syncRegionSelect();
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
        pool: { mode: 'shuffled', terrain: {}, numbers: [] },
    };
    mapDoc = { ...mapDoc, regions: [...mapDoc.regions, region] };
    selectedRegionId = id;
    syncRegionSelect();
    renderEditor();
}

function syncRegionSelect() {
    editorRegionSelect.innerHTML = '';
    for (const r of mapDoc.regions) {
        const opt = document.createElement('option');
        opt.value = r.id;
        opt.textContent = r.name;
        editorRegionSelect.appendChild(opt);
    }
    if (selectedRegionId) editorRegionSelect.value = selectedRegionId;
    else if (mapDoc.regions.length) {
        selectedRegionId = mapDoc.regions[0].id;
        editorRegionSelect.value = selectedRegionId;
    }
}

// ─── pool popover ─────────────────────────────────────────────────────────────

function openPoolPopover(regionId) {
    const region = mapDoc.regions.find(r => r.id === regionId);
    if (!region) return;
    buildPoolPopover(region);
    togglePopover(editorPoolTrigger);
}

function buildPoolPopover(region) {
    editorPoolPopover.innerHTML = '';

    // Fixed header: region name + kind selector
    const head = document.createElement('div');
    head.className = 'popover-head';
    const headTitle = document.createElement('span');
    headTitle.textContent = region.name;
    head.appendChild(headTitle);
    const kindSelect = document.createElement('select');
    kindSelect.className = 'editor-pool-kind-select';
    for (const k of ['main', 'island', 'sea']) {
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
    head.appendChild(kindSelect);
    editorPoolPopover.appendChild(head);

    // Scrollable body: terrain and token sections side by side
    const body = document.createElement('div');
    body.className = 'popover-body editor-pool-columns';

    // Terrain counters
    const terrainSection = document.createElement('div');
    terrainSection.className = 'editor-pool-section';
    const terrainHead = document.createElement('div');
    terrainHead.className = 'editor-pool-section-head';
    terrainHead.textContent = 'Terrain';
    terrainSection.appendChild(terrainHead);
    for (const terrain of TERRAIN_TYPES) {
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
        });
        inc.addEventListener('click', () => {
            region.pool.terrain[terrain] = (region.pool.terrain[terrain] || 0) + 1;
            count.textContent = String(region.pool.terrain[terrain]);
            mapDoc = { ...mapDoc };
            refreshPoolBadges(region, tilesUsed, tokensBadge);
        });

        row.appendChild(lbl);
        row.appendChild(dec);
        row.appendChild(count);
        row.appendChild(inc);
        terrainSection.appendChild(row);
    }
    body.appendChild(terrainSection);

    // Token counters
    const tokenSection = document.createElement('div');
    tokenSection.className = 'editor-pool-section';
    const tokenHead = document.createElement('div');
    tokenHead.className = 'editor-pool-section-head';
    tokenHead.textContent = 'Tokens';
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
        });
        inc.addEventListener('click', () => {
            region.pool.numbers.push(val);
            tokenCounts[val] = (tokenCounts[val] || 0) + 1;
            cnt.textContent = String(tokenCounts[val]);
            mapDoc = { ...mapDoc };
            refreshPoolBadges(region, tilesUsed, tokensBadge);
        });

        row.appendChild(lbl);
        row.appendChild(dec);
        row.appendChild(cnt);
        row.appendChild(inc);
        tokenSection.appendChild(row);
    }
    body.appendChild(tokenSection);
    editorPoolPopover.appendChild(body);

    // Fixed footer: badges + auto-fill + done
    const footer = document.createElement('div');
    footer.className = 'editor-pool-footer';

    const badges = document.createElement('div');
    badges.className = 'editor-pool-badges';
    const tilesUsed = document.createElement('span');
    tilesUsed.className = 'editor-pool-badge';
    const tokensBadge = document.createElement('span');
    tokensBadge.className = 'editor-pool-badge';
    badges.appendChild(tilesUsed);
    badges.appendChild(tokensBadge);
    footer.appendChild(badges);
    refreshPoolBadges(region, tilesUsed, tokensBadge);

    const autoFill = document.createElement('button');
    autoFill.textContent = 'Auto-fill';
    autoFill.addEventListener('click', () => {
        autoFillPool(region);
        buildPoolPopover(region);
    });
    footer.appendChild(autoFill);

    const done = document.createElement('button');
    done.textContent = 'Done';
    done.addEventListener('click', () => closePopover());
    footer.appendChild(done);

    editorPoolPopover.appendChild(footer);
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

    // Scale the standard 19-hex mix to this region's size.
    const scale = slots / 19;
    const terrain = {};
    let placed = 0;
    for (const [t, count] of Object.entries(STANDARD_MIX)) {
        if (t === 'sea') continue;
        const n = Math.round(count * scale);
        if (n > 0) { terrain[t] = n; placed += n; }
    }
    // Adjust to hit exactly `slots`.
    while (placed < slots) { terrain.wood = (terrain.wood || 0) + 1; placed++; }
    while (placed > slots && terrain.wood > 0) { terrain.wood--; placed--; }

    region.pool.terrain = terrain;

    // Scale the standard token distribution to the non-desert tile count.
    const landTiles = slots - (terrain.desert || 0);
    const tokenScale = landTiles / 18;
    const numbers = [];
    for (const [val, count] of Object.entries(STANDARD_TOKENS)) {
        const n = Math.round(count * tokenScale);
        for (let i = 0; i < n; i++) numbers.push(Number(val));
    }
    // Trim or pad to match land tile count exactly.
    while (numbers.length > landTiles) numbers.pop();
    while (numbers.length < landTiles) numbers.push(5);
    region.pool.numbers = numbers;

    mapDoc = { ...mapDoc };
    renderEditor();
}

// ─── preview ──────────────────────────────────────────────────────────────────

function requestPreview() {
    const wire = mapDocToWire();
    if (!wire) return;
    emitGame('preview_map', { map: wire });
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
    syncRegionSelect();
    buildHarbourCounters();
    renderEditor();
    closePopover();
}

function onMapListUpdated() {
    mapList = viewState.server.mapList || [];
    rebuildMapList();
    syncRegionSelect();
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
            // The list entry has id/name but not the full definition; we need
            // to request the full map. Use read_map via a preview with seed to
            // get the format — but simpler: the editor can emit request_maps
            // and we already have the map data if the store returns it.
            // For v1 builtins the definition IS in the list; for user maps
            // we duplicate to get a full copy.
            if (m.builtin) {
                duplicateMap(m);
            } else {
                // Load from a full definition if available, otherwise duplicate.
                loadOrDuplicate(m);
            }
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
        frame: m.frame || { radius: 4 },
        regions: (m.regions || []).map(r => ({
            ...r,
            color: r.color || REGION_PALETTE[0],
            hexes: Array.isArray(r.hexes) ? [...r.hexes] : r.hexes,
            pool: r.pool ? { ...r.pool, numbers: [...(r.pool.numbers || [])] } : { mode: 'shuffled', terrain: {}, numbers: [] },
        })),
        harbours: m.harbours ? { ...m.harbours, types: { ...(m.harbours.types || {}) } }
                             : { mode: 'bag', types: { generic: 4, wood: 1, brick: 1, sheep: 1, wheat: 1, ore: 1 } },
    };
    previewBoard = null;
    undoStack = [];
    selectedRegionId = mapDoc.regions[0]?.id ?? null;
    editorMapNameInput.value = mapDoc.name;
    syncRegionSelect();
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
        frame: { radius: mapDoc.frame.radius },
        regions: mapDoc.regions.map(r => ({
            id: r.id,
            kind: r.kind,
            color: r.color,
            hexes: r.hexes === 'remaining' ? 'remaining' : sortHexKeys([...r.hexes]),
            pool: {
                mode: r.pool.mode,
                terrain: { ...r.pool.terrain },
                numbers: [...r.pool.numbers],
            },
        })),
        harbours: { mode: mapDoc.harbours.mode, types: { ...mapDoc.harbours.types } },
    };
}

function serverMapToDoc(m) {
    return {
        id: m.id || '',
        name: m.name || m.id,
        frame: m.frame || { radius: 4 },
        regions: (m.regions || []).map(r => ({
            id: r.id,
            name: r.name || r.id,
            kind: r.kind || 'island',
            color: r.color || REGION_PALETTE[0],
            hexes: r.hexes === 'remaining' ? 'remaining'
                 : Array.isArray(r.hexes) ? [...r.hexes] : [],
            pool: r.pool ? {
                mode: r.pool.mode || 'shuffled',
                terrain: { ...(r.pool.terrain || {}) },
                numbers: [...(r.pool.numbers || [])],
            } : { mode: 'shuffled', terrain: {}, numbers: [] },
        })),
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
    if (e.key === 'e' || e.key === 'E') { setTool('erase'); return; }
    if (e.key === 'i' || e.key === 'I') { setTool('inspect'); return; }

    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= 9 && mapDoc.regions[n - 1]) {
        selectedRegionId = mapDoc.regions[n - 1].id;
        editorRegionSelect.value = selectedRegionId;
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
