/**
 * Catan Board Renderer
 * Renders the Catan board using HTML5 Canvas
 */

// Configuration for the board rendering
const BOARD_CONFIG = {
    hexRadius: 35,       // Size of hexes in pixels
    edgeRadius: 3,       // Not used currently, kept for reference
    clickRadius: 15,     // Pixels to detect clicks on vertices/edges
    colors: {
        // Fallbacks only. The live values come from the CSS custom properties
        // read in readPalette(), so the board follows the page's theme; these
        // are what is drawn if a token is missing or the sheet has not loaded.
        ocean: '#2f6288',
        desert: '#e6d9bb',
        ore: '#8a9bb0',
        wheat: '#e0b64a',
        sheep: '#8fbf4a',
        brick: '#c9663a',
        wood: '#3f8f5a',
        highlight: 'rgba(231, 76, 60, 0.5)',
        border: '#2c3e50',
        text: '#ecf0f1',
        numberCircle: '#ecf0f1',
        numberText: '#2c3e50',
        vertexDefault: 'red',
        edgeDefault: 'red'
    }
};

// The terrain fills and the harbour badges come from the stylesheet. The board
// is a canvas, so nothing here inherits a colour: each one has to be read.
const PALETTE_TOKENS = {
    wood: '--terrain-wood',
    brick: '--terrain-brick',
    sheep: '--terrain-sheep',
    wheat: '--terrain-wheat',
    ore: '--terrain-ore',
    desert: '--terrain-desert',
    // Explorers & Pirates terrains: an undiscovered tile's dark back, and the
    // three v2 terrains a discovery can turn up.
    hidden: '--terrain-hidden',
    gold: '--terrain-gold',
    fish: '--terrain-fish',
    spice: '--terrain-spice',
    portWood: '--res-wood',
    portBrick: '--res-brick',
    portSheep: '--res-sheep',
    portWheat: '--res-wheat',
    portOre: '--res-ore',
    onPort: '--on-resource',
    portGeneric: '--info',
    onGeneric: '--on-status'
};

const PALETTE_FALLBACKS = {
    wood: '#3f8f5a', brick: '#c9663a', sheep: '#8fbf4a', wheat: '#e0b64a',
    ore: '#8a9bb0', desert: '#e6d9bb',
    hidden: '#223247', gold: '#d9a441', fish: '#3f9fb8', spice: '#b5643c',
    portWood: '#2f6b3a', portBrick: '#a4502a', portSheep: '#5c7d26',
    portWheat: '#8a6800', portOre: '#4d5b6b', onPort: '#ffffff',
    portGeneric: '#1a5fb4', onGeneric: '#ffffff'
};

// Reading a custom property forces a style resolve, and this board redraws on
// every pan frame, so the answer is cached until the theme that produced it
// changes. Nothing else can change these values without a theme change.
let palette = null;
let paletteSignature = '';

/**
 * The board's colours, as the stylesheet currently defines them.
 *
 * @returns {object} - Token name to colour string
 */
function readPalette() {
    const root = document.documentElement;
    const prefersDark = window.matchMedia
        && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const signature = `${root.getAttribute('data-theme') || ''}|${prefersDark}`;
    if (palette && signature === paletteSignature) {
        return palette;
    }

    const styles = getComputedStyle(root);
    const next = {};
    for (const name in PALETTE_TOKENS) {
        next[name] = styles.getPropertyValue(PALETTE_TOKENS[name]).trim()
            || PALETTE_FALLBACKS[name];
    }
    // The ocean is deliberately not a token: --board-backdrop is the same dark
    // in both themes, and a light sea around it reads as a rendering fault.
    next.ocean = BOARD_CONFIG.colors.ocean;
    palette = next;
    paletteSignature = signature;
    return palette;
}

// The placement ghost. Fallback colour only: the preview normally carries the
// acting player's own colour, which is what makes "that would be mine" read.
const GHOST_ALLOWED_COLOR = '#ecf0f1';
const GHOST_BLOCKED_COLOR = '#e74c3c';
const GHOST_RING_RADIUS = 14;

// Which part of the board each placement aims at. Listed rather than tested
// one kind at a time: the ghost, the ring and the anchor all have to agree on
// the answer, and three separate `=== 'road'` checks is how they stop agreeing.
// The `progress_` kinds are a progress card being aimed: a Merchant or a Bishop
// lands on a hex, an Inventor on two number tokens, a Diplomat on a road.
const EDGE_GHOST_KINDS = ['road', 'ship', 'ship_move', 'progress_road'];
const HEX_GHOST_KINDS = ['robber', 'pirate', 'progress_hex', 'progress_tokens'];

// Cache of the last computed layout, keyed by board data identity.
// This is a memo of a pure computation, not state that drawing writes to.
let lastLayoutBoardData = null;
let lastLayout = null;

/**
 * Convert cube coordinates to pixel coordinates for rendering.
 * Uses the formula from hex.md:
 *   px = S * √3 * (x / 3 + z / 6)
 *   py = S * 3/2 * (z / 3)
 * 
 * @param {number} x - Cube x coordinate
 * @param {number} y - Cube y coordinate  
 * @param {number} z - Cube z coordinate
 * @param {number} radius - Hex radius for scaling
 * @returns {object} - {x, y} pixel coordinates
 */
function cubeToPixel(x, y, z, radius) {
    const px = radius * Math.sqrt(3) * (x / 3 + z / 6);
    const py = radius * 3/2 * (z / 3);
    return { x: px, y: py };
}

/**
 * Parse a coordinate key string into (x, y, z) tuple.
 * Key format: "x,y,z" e.g., "3,-3,0"
 * 
 * @param {string} key - Coordinate key string
 * @returns {object} - {x, y, z} coordinates
 */
function parseKey(key) {
    const parts = key.split(',').map(Number);
    return { x: parts[0], y: parts[1], z: parts[2] };
}

/**
 * Draw a single hex on the canvas.
 * 
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} centerX - Center x position
 * @param {number} centerY - Center y position
 * @param {number} radius - Hex radius
 * @param {string} color - Fill color
 * @param {number|null} number - Dice number to display
 * @param {boolean} isLand - Whether this is a land hex (not ocean)
 * @param {boolean} isHighlighted - Whether this hex should be highlighted
 */
function drawHex(ctx, centerX, centerY, radius, color, number, isLand, isHighlighted = false,
                terrain = null) {
    hexPath(ctx, centerX, centerY, radius);

    // Highlight glow effect
    if (isHighlighted) {
        ctx.shadowColor = '#f1c40f';
        ctx.shadowBlur = 20;
    }

    // The land fill is a tiled per-terrain pattern; the ocean, which has no
    // pattern, falls back to the flat colour it was already given.
    const pattern = terrain ? getTerrainPattern(ctx, terrain) : null;
    ctx.fillStyle = pattern || color;
    ctx.fill();
    ctx.strokeStyle = isHighlighted ? '#f1c40f' : BOARD_CONFIG.colors.border;
    ctx.lineWidth = isHighlighted ? 4 : 2;
    ctx.stroke();

    // Reset shadow
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;

    if (isLand && number !== null && number !== undefined) {
        drawNumberToken(ctx, centerX, centerY, number, isHighlighted);
    }

    // An undiscovered tile (Explorers & Pirates) shows only its back — a large,
    // faint question mark — until a ship reaches it and it turns face up.
    if (terrain === 'hidden') {
        drawHiddenMark(ctx, centerX, centerY, radius);
    }
}

/**
 * The mark on a face-down, undiscovered tile: a big, faint question mark.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} centerX - Center x
 * @param {number} centerY - Center y
 * @param {number} radius - Hex radius
 */
function drawHiddenMark(ctx, centerX, centerY, radius) {
    ctx.save();
    ctx.fillStyle = 'rgba(232, 240, 248, 0.5)';
    ctx.font = `700 ${Math.round(radius * 0.95)}px "Space Grotesk", system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('?', centerX, centerY + radius * 0.05);
    ctx.restore();
}

/**
 * Trace a pointy-top hexagon, leaving it as the current path.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} centerX - Center x position
 * @param {number} centerY - Center y position
 * @param {number} radius - Hex radius
 */
function hexPath(ctx, centerX, centerY, radius) {
    ctx.beginPath();
    for (let corner = 0; corner < 6; corner += 1) {
        const angle = Math.PI / 3 * corner - Math.PI / 6;
        const x = centerX + radius * Math.cos(angle);
        const y = centerY + radius * Math.sin(angle);
        if (corner === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    }
    ctx.closePath();
}

/* -------------------------------------------------------------------------
 * Terrain patterns
 *
 * Each land hex is filled with a tiled, low-contrast motif in its own terrain
 * colour rather than a flat wash or an image sprite: small pines for the
 * forest, offset brick courses for the hills, dots for the pasture, vertical
 * strokes for the field, a chevron zigzag for the mountains and a sparse
 * stipple for the desert. The motif is a slightly off shade of the same fill,
 * so it reads as texture and never competes with the number token on top.
 *
 * Built once per theme as a CanvasPattern off a small offscreen tile, then
 * handed straight to the hex fill. Two things follow from that:
 *   - The tile carries the terrain colour the stylesheet currently defines, so
 *     the cache is keyed by the same signature readPalette() uses and rebuilds
 *     when the theme flips.
 *   - The tile is drawn supersampled and scaled back down through the pattern
 *     transform, so the motif stays crisp when the board is zoomed in.
 * ---------------------------------------------------------------------- */

// Motif tile, in board units, and how far above one-to-one it is rendered.
// 15 is a shade under half a hex radius: a few tiles fit across a hex without
// the motif turning into noise behind the token.
const PATTERN_TILE = 15;
const PATTERN_SUPERSAMPLE = 3;

// How far the motif shade sits from the terrain fill. Darker in the light
// theme, lighter in the dark one: a strictly darker mark on an already dark
// hex reads as nothing, and the point of the motif is that it is seen.
const PATTERN_LIGHT_SHIFT = -0.22;
const PATTERN_DARK_SHIFT = 0.18;

// Rebuilt whenever the theme signature readPalette() tracks changes.
let terrainPatterns = null;
let terrainPatternSignature = null;

// The resource registry the server sent with the last board (hex_type to
// {name, color, symbol, pattern}). The board's colours and patterns are drawn
// from this; it is empty until the first board arrives, when getHexColor falls
// back to the CSS terrain tokens. `resourceDefsSignature` busts the pattern
// cache when the registry changes (a theme change or an imported file).
let resourceDefs = {};
let resourceDefsSignature = '';

/**
 * Parse a #rgb or #rrggbb colour into its channels.
 *
 * @param {string} hex - Colour string
 * @returns {object|null} - {r, g, b}, or null if it is not a hex colour
 */
function parseHexColor(hex) {
    if (typeof hex !== 'string' || hex[0] !== '#') {
        return null;
    }
    let body = hex.slice(1);
    if (body.length === 3) {
        body = body[0] + body[0] + body[1] + body[1] + body[2] + body[2];
    }
    if (!/^[0-9a-fA-F]{6}$/.test(body)) {
        return null;
    }
    const value = parseInt(body, 16);
    return { r: (value >> 16) & 255, g: (value >> 8) & 255, b: value & 255 };
}

/**
 * A shade of the same colour, mixed toward black (shift < 0) or white (> 0).
 *
 * @param {string} base - Terrain colour
 * @param {number} shift - How far to move, -1..1
 * @returns {string|null} - An rgb() string, or null if base could not be read
 */
function shadeColor(base, shift) {
    const rgb = parseHexColor(base);
    if (!rgb) {
        return null;
    }
    const target = shift < 0 ? 0 : 255;
    const amount = Math.abs(shift);
    const mix = channel => Math.round(channel + (target - channel) * amount);
    return `rgb(${mix(rgb.r)}, ${mix(rgb.g)}, ${mix(rgb.b)})`;
}

/**
 * Stroke a segment given in the 12-unit tile space, scaled by `u`.
 *
 * @param {CanvasRenderingContext2D} ctx - Tile context
 * @param {number} u - Units-to-pixels scale for the tile
 */
function patternLine(ctx, u, x1, y1, x2, y2) {
    ctx.beginPath();
    ctx.moveTo(x1 * u, y1 * u);
    ctx.lineTo(x2 * u, y2 * u);
    ctx.stroke();
}

function patternDot(ctx, u, x, y, r) {
    ctx.beginPath();
    ctx.arc(x * u, y * u, r * u, 0, Math.PI * 2);
    ctx.fill();
}

function patternPolyline(ctx, u, points, close) {
    ctx.beginPath();
    points.forEach(([x, y], index) => {
        if (index === 0) {
            ctx.moveTo(x * u, y * u);
        } else {
            ctx.lineTo(x * u, y * u);
        }
    });
    if (close) {
        ctx.closePath();
    }
    ctx.stroke();
}

// The named pattern styles a resource definition can pick from, each drawn in a
// 12-unit tile scaled by `u` and in the resource's own ink. Once one motif per
// terrain, now one per *style* referenced by id (see server resources.py) — so a
// new resource picks a style rather than needing new code. 'solid' is the absence
// of a style: no motif, just the flat fill (the ocean's look).
const PATTERN_STYLES = {
    pines(ctx, u, ink) {
        ctx.strokeStyle = ink;
        ctx.lineWidth = u;
        patternPolyline(ctx, u, [[6, 2], [9, 8], [3, 8]], true);
        patternPolyline(ctx, u, [[6, 6], [10, 12], [2, 12]], true);
    },

    brick(ctx, u, ink) {
        // Courses of a wall, every other row's joints shifted half a brick.
        ctx.strokeStyle = ink;
        ctx.lineWidth = u * 0.9;
        patternLine(ctx, u, 0, 4, 12, 4);
        patternLine(ctx, u, 0, 10, 12, 10);
        patternLine(ctx, u, 6, 0, 6, 4);
        patternLine(ctx, u, 3, 4, 3, 10);
        patternLine(ctx, u, 9, 4, 9, 10);
        patternLine(ctx, u, 6, 10, 6, 12);
    },

    dots(ctx, u, ink) {
        ctx.fillStyle = ink;
        patternDot(ctx, u, 4, 4, 1.4);
        patternDot(ctx, u, 9, 9, 1.4);
    },

    stripes(ctx, u, ink) {
        // Vertical strokes: a field of standing stalks.
        ctx.strokeStyle = ink;
        ctx.lineWidth = u * 0.9;
        patternLine(ctx, u, 3, 12, 3, 2);
        patternLine(ctx, u, 6, 12, 6, 0);
        patternLine(ctx, u, 9, 12, 9, 2);
    },

    chevron(ctx, u, ink) {
        // Chevrons: the folded ridgeline of a mountain.
        ctx.strokeStyle = ink;
        ctx.lineWidth = u * 0.9;
        patternPolyline(ctx, u, [[0, 8], [3, 4], [6, 8], [9, 4], [12, 8]], false);
    },

    stipple(ctx, u, ink) {
        ctx.fillStyle = ink;
        patternDot(ctx, u, 6, 6, 1);
    }
};

/**
 * Build one CanvasPattern per resource for the current theme.
 *
 * Driven by the server resource registry: each definition names a `color` and a
 * `pattern` style id, and the pattern is drawn in an ink shaded from that colour.
 * A definition whose style is 'solid' (or unknown) gets no pattern — the flat
 * fill, the ocean's look. Keyed by hex_type, which is what a hex carries as its
 * `type` and what getTerrainPattern looks up.
 *
 * @param {CanvasRenderingContext2D} ctx - The board context the patterns fill
 * @param {object} defs - The resource registry (hex_type to definition)
 * @param {object} colors - Terrain colours from readPalette(), a fallback tint
 * @returns {object} - hex_type to CanvasPattern
 */
function buildTerrainPatterns(ctx, defs, colors) {
    const size = PATTERN_TILE * PATTERN_SUPERSAMPLE;
    const unit = size / 12;
    const root = document.documentElement;
    const dark = root.getAttribute('data-theme') === 'dark'
        || (!root.getAttribute('data-theme') && window.matchMedia
            && window.matchMedia('(prefers-color-scheme: dark)').matches);
    const shift = dark ? PATTERN_DARK_SHIFT : PATTERN_LIGHT_SHIFT;
    // Only reached if a resource colour is not a hex string; a translucent ink
    // then reads on either theme, the way the old texture wash did.
    const fallbackInk = dark ? 'rgba(255, 255, 255, 0.16)' : 'rgba(20, 26, 34, 0.20)';

    const patterns = {};
    for (const hexType in defs) {
        const def = defs[hexType];
        const motif = PATTERN_STYLES[def && def.pattern];
        if (!motif) {
            continue;  // 'solid' or an unknown style: flat fill, no motif.
        }
        const base = (def && def.color) || colors[hexType];
        if (!base) {
            continue;
        }
        const ink = shadeColor(base, shift) || fallbackInk;

        const tile = document.createElement('canvas');
        tile.width = size;
        tile.height = size;
        const tileCtx = tile.getContext('2d');
        tileCtx.fillStyle = base;
        tileCtx.fillRect(0, 0, size, size);
        tileCtx.lineCap = 'round';
        tileCtx.lineJoin = 'round';
        motif(tileCtx, unit, ink);

        const pattern = ctx.createPattern(tile, 'repeat');
        // The tile is supersampled, so scale the pattern back to board units;
        // without this the motif tiles PATTERN_SUPERSAMPLE times too large.
        if (pattern && typeof pattern.setTransform === 'function') {
            const scale = 1 / PATTERN_SUPERSAMPLE;
            pattern.setTransform(new DOMMatrix([scale, 0, 0, scale, 0, 0]));
        }
        patterns[hexType] = pattern;
    }
    return patterns;
}

/**
 * The pattern to fill one terrain's hexes with, rebuilt when the theme or the
 * resource registry changes.
 *
 * @param {CanvasRenderingContext2D} ctx - The board context
 * @param {string} terrain - Hex type
 * @returns {CanvasPattern|null} - The terrain's pattern, or null for the ocean
 */
function getTerrainPattern(ctx, terrain) {
    const colors = readPalette();
    const signature = paletteSignature + '|' + resourceDefsSignature;
    if (!terrainPatterns || terrainPatternSignature !== signature) {
        terrainPatterns = buildTerrainPatterns(ctx, resourceDefs, colors);
        terrainPatternSignature = signature;
    }
    return terrainPatterns[terrain] || null;
}

/**
 * A single conifer: a stacked triangle over a trunk.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Base x
 * @param {number} y - Base y
 * @param {number} height - Overall height in pixels
 */
function drawConifer(ctx, x, y, height) {
    const half = height * 0.34;
    ctx.beginPath();
    ctx.moveTo(x, y - height);
    ctx.lineTo(x + half, y - height * 0.35);
    ctx.lineTo(x + half * 0.45, y - height * 0.35);
    ctx.lineTo(x + half * 0.9, y);
    ctx.lineTo(x - half * 0.9, y);
    ctx.lineTo(x - half * 0.45, y - height * 0.35);
    ctx.lineTo(x - half, y - height * 0.35);
    ctx.closePath();
    ctx.fill();
}

/**
 * Draw the geometric symbol for one resource, centred on (x, y).
 *
 * Labels the harbour badges: a harbour is then marked in the same vocabulary
 * as the terrain patterns it trades against, one shape to learn instead of
 * two. Uses the current fill and stroke styles.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Centre x
 * @param {number} y - Centre y
 * @param {number} size - Half-extent in pixels
 * @param {string} resource - 'wood', 'brick', 'sheep', 'wheat', 'ore' or 'desert'
 */
function drawResourceGlyph(ctx, x, y, size, resource) {
    ctx.lineWidth = Math.max(1, size * 0.22);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    if (resource === 'wood') {
        drawConifer(ctx, x, y + size, size * 2);
        return;
    }

    if (resource === 'brick') {
        const width = size * 0.9;
        const height = size * 0.62;
        ctx.fillRect(x - width, y, width * 0.92, height);
        ctx.fillRect(x + width * 0.08, y, width * 0.92, height);
        ctx.fillRect(x - width * 0.46, y - height * 1.15, width * 0.92, height);
        return;
    }

    if (resource === 'ore') {
        // A cut stone. Deliberately not the five-sided outline this started
        // as: that silhouette is a knight's shield, and the two appeared
        // within a hex of each other on the board.
        ctx.beginPath();
        ctx.moveTo(x, y - size);
        ctx.lineTo(x + size * 0.95, y);
        ctx.lineTo(x, y + size);
        ctx.lineTo(x - size * 0.95, y);
        ctx.closePath();
        ctx.fill();
        return;
    }

    if (resource === 'wheat') {
        // An ear of grain: a stalk with three pairs of grains.
        ctx.beginPath();
        ctx.moveTo(x, y + size);
        ctx.lineTo(x, y - size);
        for (let step = 0; step < 3; step += 1) {
            const grainY = y - size + step * size * 0.62;
            ctx.moveTo(x, grainY + size * 0.34);
            ctx.lineTo(x - size * 0.62, grainY);
            ctx.moveTo(x, grainY + size * 0.34);
            ctx.lineTo(x + size * 0.62, grainY);
        }
        ctx.stroke();
        return;
    }

    if (resource === 'sheep') {
        // A sheep in profile: a fleecy body, a head off to one side and two
        // legs. The head is what keeps it from reading as a bush, which is
        // what a bare cluster of discs did next to the forest tiles.
        ctx.beginPath();
        ctx.arc(x - size * 0.45, y - size * 0.1, size * 0.45, 0, Math.PI * 2);
        ctx.arc(x + size * 0.15, y - size * 0.1, size * 0.45, 0, Math.PI * 2);
        ctx.arc(x - size * 0.15, y - size * 0.5, size * 0.42, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(x + size * 0.72, y + size * 0.1, size * 0.3, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(x - size * 0.5, y + size * 0.3);
        ctx.lineTo(x - size * 0.5, y + size * 0.95);
        ctx.moveTo(x + size * 0.2, y + size * 0.3);
        ctx.lineTo(x + size * 0.2, y + size * 0.95);
        ctx.stroke();
        return;
    }

    if (resource === 'desert') {
        // A sun. Drawn without the dune it once sat over: a disc above a
        // single arc is a face, and that is all anyone saw.
        ctx.beginPath();
        ctx.arc(x, y, size * 0.46, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        for (let ray = 0; ray < 8; ray += 1) {
            const angle = ray * Math.PI / 4;
            ctx.moveTo(x + Math.cos(angle) * size * 0.68, y + Math.sin(angle) * size * 0.68);
            ctx.lineTo(x + Math.cos(angle) * size * 0.98, y + Math.sin(angle) * size * 0.98);
        }
        ctx.stroke();
    }
}

/**
 * Draw a number token circle in the center of a hex.
 * 
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} centerX - Center x position
 * @param {number} centerY - Center y position
 * @param {number} number - The dice number (2-12)
 * @param {boolean} isHighlighted - Whether this hex should be highlighted
 */
function drawNumberToken(ctx, centerX, centerY, number, isHighlighted = false) {
    const tokenRadius = 12;

    ctx.beginPath();
    ctx.arc(centerX, centerY, tokenRadius, 0, Math.PI * 2);
    // A self-contained pair rather than theme tokens: the disc sits on six
    // different terrain fills, so its contrast has to come from the disc
    // itself. Near-white under near-black is ~15:1 in either theme.
    ctx.fillStyle = isHighlighted ? '#f1c40f' : BOARD_CONFIG.colors.numberCircle;
    ctx.fill();
    ctx.strokeStyle = isHighlighted ? '#f39c12' : BOARD_CONFIG.colors.border;
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.font = 'bold 14px Arial';
    // 6 and 8 in red is how the tokens are printed, and it is the one piece of
    // colour a player reads at a glance. #a52222 on the disc is 5.9:1, so it
    // is not carrying the information alone either - the digit still says it.
    const isHot = number === 6 || number === 8;
    ctx.fillStyle = isHighlighted
        ? '#2c3e50'
        : (isHot ? '#a52222' : BOARD_CONFIG.colors.numberText);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(number.toString(), centerX, centerY);
}

/**
 * Get the color for a hex type. The server resource registry is the source of
 * truth; the page's terrain tokens are a fallback for a hex the registry does
 * not define (or before any board has loaded).
 *
 * @param {string} hexType - Type of hex (ore, wheat, sheep, brick, wood, desert, ocean)
 * @returns {string} - Hex color code
 */
function getHexColor(hexType) {
    const def = resourceDefs[hexType];
    if (def && def.color) {
        return def.color;
    }
    const colors = readPalette();
    return colors[hexType] || colors.ocean;
}

/**
 * Draw a vertex (test rendering - red dot).
 * 
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - X position
 * @param {number} y - Y position
 */
function drawVertex(ctx, x, y) {
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = BOARD_CONFIG.colors.vertexDefault;
    ctx.fill();
}

/**
 * Draw an edge (test rendering - red line).
 * 
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x1 - Start x
 * @param {number} y1 - Start y
 * @param {number} x2 - End x
 * @param {number} y2 - End y
 */
function drawEdge(ctx, x1, y1, x2, y2) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = BOARD_CONFIG.colors.edgeDefault;
    ctx.lineWidth = 3;
    ctx.stroke();
}

/**
 * Draw the harbour on one coastal edge.
 *
 * One marker per edge, out in the water it faces, with a line back to each of
 * the two intersections it serves. Drawing it from `vertex.port` instead - as
 * this did until harbours moved onto edges - paints the same harbour twice,
 * once at each end, and tells the player nothing about which side it is on.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} pos - Edge geometry {x1, y1, x2, y2, centerX, centerY}
 * @param {object} port - Port info {type: "generic"/"resource", resource: string}
 * @param {object} outward - Unit vector {x, y} pointing from the land to the sea
 */
function drawHarbour(ctx, pos, port, outward) {
    const colors = readPalette();
    const resource = port.type === 'resource' ? port.resource : null;
    const fill = resource
        ? colors[`port${resource.charAt(0).toUpperCase()}${resource.slice(1)}`]
        : colors.portGeneric;
    const ink = resource ? colors.onPort : colors.onGeneric;

    const badgeX = pos.centerX + outward.x * HARBOUR_REACH;
    const badgeY = pos.centerY + outward.y * HARBOUR_REACH;

    ctx.save();

    // Mooring lines to both ends of the edge, so which side of which
    // intersection this harbour serves is never a guess.
    ctx.strokeStyle = fill;
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(pos.x1, pos.y1);
    ctx.lineTo(badgeX, badgeY);
    ctx.moveTo(pos.x2, pos.y2);
    ctx.lineTo(badgeX, badgeY);
    ctx.stroke();

    // The plank, along the coast it belongs to. This is the part that is
    // angled to the water's edge; the label above it stays upright, because a
    // rotated "2:1" on the southern coastline would be upside down.
    ctx.save();
    ctx.translate(pos.centerX + outward.x * 5, pos.centerY + outward.y * 5);
    ctx.rotate(Math.atan2(pos.y2 - pos.y1, pos.x2 - pos.x1));
    ctx.fillStyle = fill;
    ctx.fillRect(-11, -2, 22, 4);
    ctx.restore();

    const width = resource ? 32 : 24;
    const height = 15;
    roundedRectPath(ctx, badgeX - width / 2, badgeY - height / 2, width, height, 4);
    ctx.fillStyle = fill;
    ctx.fill();
    // The badge floats on the open sea, so it carries its own outline rather
    // than relying on the fill contrasting with whatever is behind it.
    ctx.strokeStyle = 'rgba(10, 16, 24, 0.75)';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = ink;
    ctx.strokeStyle = ink;
    if (resource) {
        drawResourceGlyph(ctx, badgeX - width / 2 + 7, badgeY, 4.5, resource);
    }
    ctx.font = 'bold 10px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(resource ? '2:1' : '3:1', badgeX + (resource ? 6 : 0), badgeY + 0.5);

    ctx.restore();
}

// How far out to sea the harbour badge sits, in pixels. Far enough to leave
// the coastal edge free for a road, close enough to still read as attached.
const HARBOUR_REACH = 24;

/**
 * Trace a rounded rectangle, leaving it as the current path.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Left
 * @param {number} y - Top
 * @param {number} width - Width
 * @param {number} height - Height
 * @param {number} radius - Corner radius
 */
function roundedRectPath(ctx, x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.arcTo(x + width, y, x + width, y + height, radius);
    ctx.arcTo(x + width, y + height, x, y + height, radius);
    ctx.arcTo(x, y + height, x, y, radius);
    ctx.arcTo(x, y, x + width, y, radius);
    ctx.closePath();
}

/**
 * Draw a settlement at a vertex position.
 * Settlement appears as a square.
 * 
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - X position
 * @param {number} y - Y position
 * @param {string} playerColor - Color of the player who owns this settlement
 */
function drawSettlement(ctx, x, y, playerColor) {
    const size = 14;
    ctx.fillStyle = playerColor || '#888888';
    ctx.fillRect(x - size/2, y - size/2, size, size);
    ctx.strokeStyle = '#000000';
    ctx.lineWidth = 1;
    ctx.strokeRect(x - size/2, y - size/2, size, size);
}

/**
 * Draw a city at a vertex position.
 * City appears as a triangle.
 * 
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - X position
 * @param {number} y - Y position
 * @param {string} playerColor - Color of the player who owns this city
 */
function drawCity(ctx, x, y, playerColor) {
    const size = 16;
    ctx.fillStyle = playerColor || '#888888';
    ctx.beginPath();
    ctx.moveTo(x, y - size/2);
    ctx.lineTo(x - size/2, y + size/2);
    ctx.lineTo(x + size/2, y + size/2);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#000000';
    ctx.lineWidth = 2;
    ctx.stroke();
}

/* -------------------------------------------------------------------------
 * City walls (Cities & Knights)
 *
 * A wall was buildable and completely invisible: two brick bought a hand-limit
 * bonus that appeared as a number in a panel and nothing on the board at all.
 *
 * Drawn as a rampart standing around the intersection, *under* the city, so
 * the piece it protects is always painted over the top of it and can never be
 * hidden by it. The rampart is open towards the top right, which is exactly
 * where a knight sharing this intersection steps to - so a walled city with a
 * knight on it reads as two pieces, not one collision.
 *
 * Its colours are fixed rather than themed, for the same reason the knight's
 * are: it sits on a player-coloured piece on a terrain fill, and neither of
 * those is under this file's control. A pale halo under a dark outline
 * survives both themes and all six player colours.
 * ---------------------------------------------------------------------- */

// A rampart of straight wall runs between square corner towers. Two earlier
// attempts drew crenellations around a circle; at 36px across, radial teeth on
// a ring read as a cog and not as a fortification at all. Straight runs with
// corners are what says "wall" at this size.
const WALL_RADIUS = 15.5;       // corners; clear of the city's 16px footprint
const WALL_CORNERS = 5;         // four runs of wall between them
const WALL_TOWER = 2.8;         // half a tower; kept small, or five of them
                                // read as five blobs rather than one wall
const WALL_GAP_START = -0.05 * Math.PI;   // just above the right horizontal
const WALL_SWEEP = 1.5 * Math.PI;         // three quarters round, open top right
const WALL_STONE = '#b9c4d0';
const WALL_HALO = '#f4f8fb';
const WALL_OUTLINE = '#0e141b';

// Halo, then outline, then stone: three passes of the same polyline, each
// narrower than the last, which is how a stroked line gets an outline at all.
const WALL_HALO_WIDTH = 9.5;
const WALL_OUTLINE_WIDTH = 7.5;
const WALL_STONE_WIDTH = 5;

/**
 * The corners of the rampart, in order along the wall.
 *
 * @param {number} x - Vertex x
 * @param {number} y - Vertex y
 * @returns {Array<object>} - {x, y, angle} per corner
 */
function wallCorners(x, y) {
    const corners = [];
    for (let index = 0; index < WALL_CORNERS; index += 1) {
        const angle = WALL_GAP_START + WALL_SWEEP * (index / (WALL_CORNERS - 1));
        corners.push({
            x: x + WALL_RADIUS * Math.cos(angle),
            y: y + WALL_RADIUS * Math.sin(angle),
            angle,
        });
    }
    return corners;
}

/**
 * Trace the runs of wall as one open polyline, leaving it as the current path.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Vertex x
 * @param {number} y - Vertex y
 */
function cityWallPath(ctx, x, y) {
    const corners = wallCorners(x, y);
    ctx.beginPath();
    ctx.moveTo(corners[0].x, corners[0].y);
    for (const corner of corners.slice(1)) {
        ctx.lineTo(corner.x, corner.y);
    }
}

/**
 * Trace one square corner tower, square to the wall it stands on.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} corner - One entry from wallCorners
 */
function wallTowerPath(ctx, corner) {
    const along = corner.angle + Math.PI / 2;
    const acrossX = Math.cos(corner.angle);
    const acrossY = Math.sin(corner.angle);
    const alongX = Math.cos(along);
    const alongY = Math.sin(along);

    ctx.beginPath();
    for (const [side, end] of [[1, 1], [1, -1], [-1, -1], [-1, 1]]) {
        const pointX = corner.x + (acrossX * side + alongX * end) * WALL_TOWER;
        const pointY = corner.y + (acrossY * side + alongY * end) * WALL_TOWER;
        if (side === 1 && end === 1) {
            ctx.moveTo(pointX, pointY);
        } else {
            ctx.lineTo(pointX, pointY);
        }
    }
    ctx.closePath();
}

/**
 * Draw the wall protecting one city.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Vertex x
 * @param {number} y - Vertex y
 */
function drawCityWall(ctx, x, y) {
    ctx.save();
    ctx.lineJoin = 'round';
    ctx.lineCap = 'butt';

    // The halo goes down first and widest, so the wall keeps its edge on a dark
    // forest hex and on a pale desert alike.
    for (const [color, width] of [[WALL_HALO, WALL_HALO_WIDTH],
                                  [WALL_OUTLINE, WALL_OUTLINE_WIDTH],
                                  [WALL_STONE, WALL_STONE_WIDTH]]) {
        cityWallPath(ctx, x, y);
        ctx.strokeStyle = color;
        ctx.lineWidth = width;
        ctx.stroke();
    }

    for (const corner of wallCorners(x, y)) {
        wallTowerPath(ctx, corner);
        ctx.fillStyle = WALL_STONE;
        ctx.fill();
        ctx.strokeStyle = WALL_OUTLINE;
        ctx.lineWidth = 1.3;
        ctx.stroke();
    }

    ctx.restore();
}

/* -------------------------------------------------------------------------
 * Knights (Cities & Knights)
 *
 * A knight stands on an intersection, which is also where a settlement or a
 * city stands, so the two cannot both be drawn on the point. The knight moves
 * off it when the intersection is built on and keeps a leader line back to it,
 * which is unambiguous in a way that stacking is not.
 *
 * Rank and activation are drawn as shape, not only colour: rank is one, two or
 * three chevrons, and an inactive knight has a grey body inside its owner's
 * rim where an active one is filled with the owner's colour outright.
 * ---------------------------------------------------------------------- */

const KNIGHT_WIDTH = 16;
const KNIGHT_HEIGHT = 19;
const KNIGHT_OFFSET = 16;       // how far off a built-on vertex a knight steps
const KNIGHT_INACTIVE_BODY = '#93a1b0';
const KNIGHT_OUTLINE = '#0e141b';

/**
 * Draw one knight at a vertex.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} vertexX - Vertex x
 * @param {number} vertexY - Vertex y
 * @param {object} knight - {rank, active} from Knight.to_dict()
 * @param {string} playerColor - Colour of the knight's owner
 * @param {boolean} shareVertex - Whether a building already stands here
 */
function drawKnight(ctx, vertexX, vertexY, knight, playerColor, shareVertex) {
    const owner = playerColor || '#888888';
    const x = shareVertex ? vertexX + KNIGHT_OFFSET : vertexX;
    const y = shareVertex ? vertexY - KNIGHT_OFFSET : vertexY;
    const active = Boolean(knight.active);
    const rank = Math.min(3, Math.max(1, knight.rank || 1));

    ctx.save();
    ctx.lineJoin = 'round';

    if (shareVertex) {
        ctx.strokeStyle = KNIGHT_OUTLINE;
        ctx.lineWidth = 1.5;
        // Started clear of the piece standing here, not at its centre: a
        // leader drawn from the vertex crosses the building it is pointing
        // away from, which is the obscuring this offset exists to avoid.
        ctx.beginPath();
        ctx.moveTo(vertexX + (x - vertexX) * 0.55, vertexY + (y - vertexY) * 0.55);
        ctx.lineTo(x, y);
        ctx.stroke();
    }

    shieldPath(ctx, x, y);
    ctx.fillStyle = active ? owner : KNIGHT_INACTIVE_BODY;
    ctx.fill();
    // The rim is always the owner's colour, so an inactive knight still says
    // whose it is; the body is what says whether it can act.
    ctx.strokeStyle = active ? KNIGHT_OUTLINE : owner;
    ctx.lineWidth = active ? 1.5 : 3;
    ctx.stroke();

    // Chevrons: one for basic, two for strong, three for mighty. Drawn in the
    // colour that contrasts with the body they sit on, not with the theme.
    ctx.strokeStyle = active ? '#ffffff' : KNIGHT_OUTLINE;
    ctx.lineWidth = 1.8;
    ctx.lineCap = 'round';
    const pitch = 4.6;
    const top = y - (rank - 1) * pitch / 2 - 3;
    for (let index = 0; index < rank; index += 1) {
        const chevronY = top + index * pitch;
        ctx.beginPath();
        ctx.moveTo(x - 4, chevronY + 2);
        ctx.lineTo(x, chevronY - 1.4);
        ctx.lineTo(x + 4, chevronY + 2);
        ctx.stroke();
    }

    ctx.restore();
}

/**
 * Trace a knight's shield, centred on (x, y).
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Centre x
 * @param {number} y - Centre y
 */
function shieldPath(ctx, x, y) {
    const halfWidth = KNIGHT_WIDTH / 2;
    const top = y - KNIGHT_HEIGHT / 2;
    const bottom = y + KNIGHT_HEIGHT / 2;
    ctx.beginPath();
    ctx.moveTo(x - halfWidth, top);
    ctx.lineTo(x + halfWidth, top);
    ctx.lineTo(x + halfWidth, y + KNIGHT_HEIGHT * 0.12);
    ctx.quadraticCurveTo(x + halfWidth * 0.85, bottom, x, bottom);
    ctx.quadraticCurveTo(x - halfWidth * 0.85, bottom, x - halfWidth, y + KNIGHT_HEIGHT * 0.12);
    ctx.closePath();
}

/**
 * Draw a road on an edge.
 * Road appears as a thick colored line.
 * 
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x1 - Start x
 * @param {number} y1 - Start y
 * @param {number} x2 - End x
 * @param {number} y2 - End y
 * @param {string} playerColor - Color of the player who owns this road
 */
function drawRoad(ctx, x1, y1, x2, y2, playerColor) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = playerColor || '#888888';
    ctx.lineWidth = 6;
    ctx.stroke();
}

/* -------------------------------------------------------------------------
 * Ships and the pirate (Seafarers)
 *
 * A ship lies on the same Edge object a road would, so the two have to be told
 * apart by *shape*, not by where they are: a coastal side can carry either one,
 * and a player who reads a ship as a road builds the wrong network for three
 * turns before finding out. So a road stays what it always was - one solid bar
 * of the owner's colour - and a ship is a thin lane with a little boat standing
 * on it, hull in the owner's colour under a pale sail.
 *
 * The boat is drawn upright rather than turned along its edge, for the same
 * reason the harbour labels are: a hull rotated onto the southern coastline is
 * upside down, and an upside-down boat reads as debris.
 *
 * Every piece out here sits on open water, whose fill is a fixed dark blue in
 * both themes, but a ship may also lie against a pale desert coast - and its
 * hull is a colour the player picked, which may be either. So each shape
 * carries a pale halo *and* a dark outline rather than one ink chosen for one
 * background; that is separation from anything behind it and from any fill
 * inside it, without a contrast test that could only be right about one of the
 * two.
 * ---------------------------------------------------------------------- */

const SHIP_HALO = 'rgba(246, 249, 252, 0.95)';
const SHIP_OUTLINE = '#0e141b';
// The rulebook's pirate is a black ship. Nothing else on the board is this
// colour, and the robber - a grey block - shares no part of its silhouette.
const PIRATE_HULL = '#15191f';

/**
 * Trace a boat's hull, centred on (x, y).
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Centre x
 * @param {number} y - Waterline y
 * @param {number} scale - Size multiplier, 1 is a player's ship
 */
function hullPath(ctx, x, y, scale) {
    ctx.beginPath();
    ctx.moveTo(x - 9 * scale, y);
    ctx.lineTo(x + 9 * scale, y);
    ctx.lineTo(x + 5.5 * scale, y + 5.5 * scale);
    ctx.lineTo(x - 5.5 * scale, y + 5.5 * scale);
    ctx.closePath();
}

/**
 * Trace a boat's sail, centred on (x, y).
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Mast x
 * @param {number} y - Waterline y
 * @param {number} scale - Size multiplier
 */
function sailPath(ctx, x, y, scale) {
    ctx.beginPath();
    ctx.moveTo(x + 0.8 * scale, y - 11 * scale);
    ctx.lineTo(x + 7.5 * scale, y - 1 * scale);
    ctx.lineTo(x + 0.8 * scale, y - 1 * scale);
    ctx.closePath();
}

/**
 * Draw one boat: mast, sail and hull, haloed and outlined.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Centre x
 * @param {number} y - Waterline y
 * @param {string} hullColor - Fill for the hull
 * @param {string} sailColor - Fill for the sail
 * @param {number} scale - Size multiplier
 */
function drawBoat(ctx, x, y, hullColor, sailColor, scale = 1) {
    const paint = (trace, fill) => {
        trace();
        ctx.strokeStyle = SHIP_HALO;
        ctx.lineWidth = 3.5 * scale;
        ctx.stroke();
        ctx.fillStyle = fill;
        ctx.fill();
        ctx.strokeStyle = SHIP_OUTLINE;
        ctx.lineWidth = 1.2;
        ctx.stroke();
    };

    ctx.save();
    ctx.lineJoin = 'round';
    ctx.setLineDash([]);

    // The mast goes down first so both sails and hull overlap its ends.
    ctx.strokeStyle = SHIP_OUTLINE;
    ctx.lineWidth = 1.8 * scale;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(x, y - 11.5 * scale);
    ctx.lineTo(x, y + 1 * scale);
    ctx.stroke();

    paint(() => sailPath(ctx, x, y, scale), sailColor);
    paint(() => hullPath(ctx, x, y, scale), hullColor);
    ctx.restore();
}

/**
 * Draw a ship on a sea edge.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} pos - Edge geometry {x1, y1, x2, y2, centerX, centerY}
 * @param {string} playerColor - Colour of the ship's owner
 */
function drawShip(ctx, pos, playerColor) {
    const color = playerColor || '#888888';

    ctx.save();
    ctx.lineCap = 'round';
    ctx.setLineDash([]);
    // The shipping lane. Half a road's weight, so even the line alone says
    // which of the two networks this side belongs to.
    ctx.strokeStyle = SHIP_HALO;
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.moveTo(pos.x1, pos.y1);
    ctx.lineTo(pos.x2, pos.y2);
    ctx.stroke();
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(pos.x1, pos.y1);
    ctx.lineTo(pos.x2, pos.y2);
    ctx.stroke();
    ctx.restore();

    drawBoat(ctx, pos.centerX, pos.centerY + 2, color, SHIP_HALO, 1);
}

// The colour a cargo piece reads as, by type: a crew, a settler, a fish haul,
// a spice sack. The two mission tokens borrow their terrain's colour so a haul
// reads as fish and a sack as spice at a glance.
const CARGO_COLORS = {
    crew: '#e8c069',
    settler: '#8fbf4a',
    fish_haul: '#3f9fb8',
    spice_sack: '#b5643c',
};

/**
 * Draw a transport ship's hold above its boat: one pip per small piece (a crew
 * or a spice sack), a double-wide pip for a large one (a settler or a fish haul)
 * that fills the whole hold. Coloured by cargo type, ringed dark so they read
 * over any water.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} pos - Edge position (carries centerX/centerY)
 * @param {Array} cargo - The ship's cargo pieces ({type, size})
 */
function drawCargo(ctx, pos, cargo) {
    const unit = 6;   // a small pip's width
    const gap = 2;
    const height = 5;
    const widths = cargo.map(piece => (piece.size === 'large' ? unit * 2 + gap : unit));
    const total = widths.reduce((sum, w) => sum + w, 0) + gap * (cargo.length - 1);

    let x = pos.centerX - total / 2;
    const y = pos.centerY - 13;

    ctx.save();
    ctx.lineWidth = 1;
    ctx.strokeStyle = SHIP_OUTLINE;
    for (let i = 0; i < cargo.length; i += 1) {
        const w = widths[i];
        ctx.fillStyle = CARGO_COLORS[cargo[i].type] || '#cccccc';
        roundRect(ctx, x, y, w, height, 1.5);
        ctx.fill();
        ctx.stroke();
        x += w + gap;
    }
    ctx.restore();
}

/**
 * Trace a rounded rectangle as the current path.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Left
 * @param {number} y - Top
 * @param {number} w - Width
 * @param {number} h - Height
 * @param {number} r - Corner radius
 */
function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
}

/**
 * Draw the pirate on its sea hex.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} centerX - Hex centre x
 * @param {number} centerY - Hex centre y
 */
function drawPirate(ctx, centerX, centerY) {
    drawBoat(ctx, centerX, centerY + 6, PIRATE_HULL, PIRATE_HULL, 1.45);
}

/* -------------------------------------------------------------------------
 * Explorers & Pirates markers
 *
 * Everything that lives on `board.ep`: each player's own pirate ship, and the
 * three missions' destinations. All are drawn from the ep state onto the hexes,
 * coloured so a lair reads dark, a shoal reads fish, a village reads spice.
 * ------------------------------------------------------------------------- */

/**
 * A player's own pirate ship on its sea hex — a boat in their colour, so it
 * reads apart from the single black Seafarers pirate.
 */
function drawPlayerPirate(ctx, centerX, centerY, color) {
    drawBoat(ctx, centerX, centerY + 6, color || '#888888', SHIP_HALO, 1.4);
}

/**
 * A small disc badge on a hex — a mission token with an optional number on it.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Centre x
 * @param {number} y - Centre y
 * @param {number} r - Badge radius
 * @param {string} fill - Disc colour
 * @param {string|number|null} text - Optional label (a count)
 * @param {string} textColor - Label colour
 */
function drawHexBadge(ctx, x, y, r, fill, text = null, textColor = '#ffffff') {
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = SHIP_OUTLINE;
    ctx.stroke();
    if (text !== null && text !== '') {
        ctx.fillStyle = textColor;
        ctx.font = `700 ${Math.round(r * 1.15)}px "Space Grotesk", system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(text), x, y + r * 0.06);
    }
    ctx.restore();
}

/**
 * Draw every Explorers & Pirates marker on `board.ep`: pirate ships, uncaptured
 * lair tokens, fish shoals (number, and a haul token when one sits there), and
 * spice villages (the sacks still on them). A no-op on a table without any ep
 * state.
 */
/**
 * Draw the Fishermen-of-Catan markers on `board.tb`: the production number on
 * each fishing-ground frame tile, so a player can see which sea hexes pay fish
 * and to whom. The lake itself is a plain terrain tile, drawn like any hex. A
 * no-op on a table without the scenario.
 */
function drawFishermenState(ctx, tb, hexPositions, hexRadius) {
    if (!tb) {
        return;
    }
    const badge = hexRadius * 0.3;
    for (const ground of tb.fishing_grounds || []) {
        const pos = hexPositions[ground.hex];
        if (pos) {
            drawHexBadge(ctx, pos.x, pos.y, badge, '#0e3a2a', ground.number, '#dff0f6');
        }
    }
}

function drawEpState(ctx, ep, hexPositions, playerColors, hexRadius) {
    if (!ep) {
        return;
    }
    const badge = hexRadius * 0.3;

    // Each player's own pirate ship on its sea hex.
    for (const [name, hexKey] of Object.entries(ep.pirate_hex || {})) {
        const pos = hexKey && hexPositions[hexKey];
        if (pos) {
            drawPlayerPirate(ctx, pos.x, pos.y, playerColors[name]);
        }
    }

    // Uncaptured pirate lairs: a dark token at the top of the gold field, clear
    // of its number token in the centre.
    for (const [hexKey, lair] of Object.entries(ep.lairs || {})) {
        const pos = hexPositions[hexKey];
        if (pos && !lair.captured) {
            drawHexBadge(ctx, pos.x, pos.y - hexRadius * 0.52, badge, '#6b1a1a');
        }
    }

    // Discovered fish shoals: the placement number in the centre, and a fish
    // token above it while a haul sits on the shoal.
    for (const [hexKey, shoal] of Object.entries(ep.fish_shoals || {})) {
        const pos = hexPositions[hexKey];
        if (!pos) {
            continue;
        }
        drawHexBadge(ctx, pos.x, pos.y, badge, '#0e2733', shoal.number, '#dff0f6');
        if (shoal.haul) {
            drawHexBadge(ctx, pos.x, pos.y - hexRadius * 0.52, badge * 0.8,
                         CARGO_COLORS.fish_haul);
        }
    }

    // Discovered spice villages: the sacks still on the village.
    for (const [hexKey, spice] of Object.entries(ep.spice_hexes || {})) {
        const pos = hexPositions[hexKey];
        if (pos) {
            drawHexBadge(ctx, pos.x, pos.y, badge, CARGO_COLORS.spice_sack,
                         spice.sacks, '#ffffff');
        }
    }
}

/**
 * Draw the merchant: a market stall with a striped awning.
 *
 * A silhouette rather than a letter or an emoji. The board is drawn at whatever
 * scale the viewport allows, and text is unreadable at sizes a shape still
 * reads at - the same reasoning as the robber and the pirate.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Centre x
 * @param {number} y - Centre y
 */
function drawMerchant(ctx, x, y) {
    const width = 16;
    const height = 11;
    const awning = 5;
    const left = x - width / 2;
    const top = y - height / 2;

    ctx.save();
    ctx.strokeStyle = '#221a10';
    ctx.lineWidth = 1;

    ctx.fillStyle = '#f2ead8';
    ctx.fillRect(left, top, width, height);
    ctx.strokeRect(left, top, width, height);

    const stripe = width / 4;
    for (let i = 0; i < 4; i += 1) {
        ctx.fillStyle = i % 2 === 0 ? '#b83227' : '#f2ead8';
        ctx.fillRect(left + i * stripe, top - awning, stripe, awning);
    }
    ctx.strokeRect(left, top - awning, width, awning);
    ctx.restore();
}

// How wide the ring around a choosable intersection is drawn.
const CHOICE_RING_RADIUS = 13;

/**
 * Ring an intersection a pending choice is asking about.
 *
 * Two strokes, dark under bright: an option can stand on any terrain in either
 * theme, and one colour is invisible against at least one of them.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - Vertex x
 * @param {number} y - Vertex y
 */
function drawChoiceRing(ctx, x, y) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, CHOICE_RING_RADIUS, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(10, 16, 24, 0.85)';
    ctx.lineWidth = 6;
    ctx.stroke();
    ctx.strokeStyle = '#ffd54a';
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.restore();
}

/**
 * Compute the full board geometry from board data.
 * Pure: reads only boardData, touches no canvas and no module state, so hit
 * detection works before the first frame has been drawn.
 *
 * @param {object} boardData - Board data from server
 * @returns {object} - {hexPositions, vertexPositions, edgePositions, offsetX, offsetY, width, height}
 */
function computeLayout(boardData) {
    const hexes = boardData.hexes || {};
    const vertices = boardData.vertices || {};
    const edges = boardData.edges || {};
    const hexRadius = BOARD_CONFIG.hexRadius;

    // Calculate canvas size by finding bounding box of all hexes
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

    const hexPositions = {};
    for (const key in hexes) {
        const coords = parseKey(key);
        const pos = cubeToPixel(coords.x, coords.y, coords.z, hexRadius);
        hexPositions[key] = pos;

        minX = Math.min(minX, pos.x - hexRadius);
        maxX = Math.max(maxX, pos.x + hexRadius);
        minY = Math.min(minY, pos.y - hexRadius);
        maxY = Math.max(maxY, pos.y + hexRadius);
    }

    const vertexPositions = {};
    for (const key in vertices) {
        const coords = parseKey(key);
        vertexPositions[key] = cubeToPixel(coords.x, coords.y, coords.z, hexRadius);
    }

    const edgePositions = {};
    for (const key in edges) {
        const vertexKeys = edges[key].neighbors.vertices || [];

        if (vertexKeys.length >= 2) {
            const pos1 = vertexPositions[vertexKeys[0]];
            const pos2 = vertexPositions[vertexKeys[1]];

            if (pos1 && pos2) {
                edgePositions[key] = {
                    x1: pos1.x, y1: pos1.y,
                    x2: pos2.x, y2: pos2.y,
                    centerX: (pos1.x + pos2.x) / 2,
                    centerY: (pos1.y + pos2.y) / 2
                };
            }
        }
    }

    // Breathing room around the bounding box, and nothing more. It used to be
    // `hexRadius + 20`, which on the standard board was about 17% of the
    // layout: `fitToView` scales `width`/`height` down to the viewport, so
    // every padded pixel came straight off the size of the drawn board and the
    // table sat in dead space.
    //
    // 12 is what still has to be reserved. The bounds are hex centres ±
    // hexRadius, which is the circumscribed circle and therefore already
    // covers every corner, every vertex piece and every number token; what it
    // does not cover is the stroke width on the outermost hexes and the ring a
    // pending choice draws around a boundary intersection. Harbour badges reach
    // further than this, but always *inwards* from an ocean hex whose own
    // bounds are in the box already.
    // v2.1: trimmed from 12. The board is the whole greedy region now (no left
    // rail, no console row below it), so `fitToView` fills the far larger area
    // by default; a smaller reserve lets the drawn board reach nearer the edges
    // still. 6 keeps the outermost stroke and the pending-choice ring covered.
    const padding = 6;

    return {
        hexPositions,
        vertexPositions,
        edgePositions,
        offsetX: -minX + padding,
        offsetY: -minY + padding,
        width: maxX - minX + padding * 2,
        height: maxY - minY + padding * 2
    };
}

/**
 * Get the layout for board data, reusing the previous result when the board
 * object has not been replaced.
 *
 * @param {object} boardData - Board data from server
 * @returns {object|null} - Layout object, or null when there is no board yet
 */
function getLayout(boardData) {
    if (!boardData) {
        return null;
    }
    if (boardData !== lastLayoutBoardData) {
        lastLayout = computeLayout(boardData);
        lastLayoutBoardData = boardData;
    }
    return lastLayout;
}

/**
 * Size the drawing buffer for the current device pixel ratio and establish the
 * "one drawing unit is one CSS pixel" convention the hit-tester also assumes.
 *
 * @param {HTMLCanvasElement} canvas - The board canvas
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} cssWidth - Board width in CSS pixels
 * @param {number} cssHeight - Board height in CSS pixels
 */
function sizeCanvas(canvas, ctx, cssWidth, cssHeight) {
    const dpr = window.devicePixelRatio || 1;
    const bufferWidth = Math.round(cssWidth * dpr);
    const bufferHeight = Math.round(cssHeight * dpr);

    // Assigning width/height clears the buffer, so only do it on a real change
    if (canvas.width !== bufferWidth || canvas.height !== bufferHeight) {
        canvas.width = bufferWidth;
        canvas.height = bufferHeight;
    }
    // The canvas is `position: absolute; inset: 0` in CSS, which is what keeps
    // its 300x150 intrinsic size out of the layout. The box is still pinned
    // here, in whole CSS pixels, because `inset: 0` resolves against a
    // fractional container (a 540.625px-tall grid track is normal) while the
    // buffer can only be an integer. clientToBoard divides by
    // canvas.width / rect.width, so a box of 540.625 under a 541 buffer puts a
    // 0.07% stretch between what is drawn and what is hit-tested - which is
    // enough to make a click pick the wrong one of two coincident edges.
    canvas.style.width = `${cssWidth}px`;
    canvas.style.height = `${cssHeight}px`;

    // setTransform, not scale: scale would compound on every resize
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

/**
 * Pan/zoom camera mapping board space to the visible viewport.
 *
 * Board space is what computeLayout() produces and what findNearest* compare
 * against, so those never need to know the camera exists. Every value here is
 * in CSS pixels — mixing in buffer pixels would make zoom-to-cursor drift by a
 * factor of devicePixelRatio, which is invisible on a non-retina screen.
 */
const camera = { scale: 1, x: 0, y: 0 };

const MIN_SCALE = 0.25;
const MAX_SCALE = 4;
const EDGE_MARGIN = 80;      // how far the board may be pushed off-screen

// Viewport size in CSS pixels, refreshed every render.
let viewWidth = 0;
let viewHeight = 0;
let lastViewWidth = 0;
let lastViewHeight = 0;
let cameraFramed = false;    // has the camera been fitted to a board yet?
let cameraAdjusted = false;  // has a player zoomed or panned it themselves?

function clampScale(scale) {
    return Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale));
}

/**
 * Keep the board reachable: centre it on any axis where it is smaller than the
 * viewport, otherwise stop it before the last hex leaves the screen.
 */
function clampCamera() {
    if (!lastLayout || !viewWidth || !viewHeight) {
        return;
    }
    const boardW = lastLayout.width * camera.scale;
    const boardH = lastLayout.height * camera.scale;

    if (boardW <= viewWidth) {
        camera.x = (viewWidth - boardW) / 2;
    } else {
        camera.x = Math.min(EDGE_MARGIN, Math.max(viewWidth - boardW - EDGE_MARGIN, camera.x));
    }
    if (boardH <= viewHeight) {
        camera.y = (viewHeight - boardH) / 2;
    } else {
        camera.y = Math.min(EDGE_MARGIN, Math.max(viewHeight - boardH - EDGE_MARGIN, camera.y));
    }
}

/**
 * Frame the whole board in the viewport.
 */
function fitToView() {
    if (!lastLayout || !viewWidth || !viewHeight) {
        return;
    }
    camera.scale = clampScale(Math.min(
        viewWidth / lastLayout.width,
        viewHeight / lastLayout.height
    ));
    camera.x = (viewWidth - lastLayout.width * camera.scale) / 2;
    camera.y = (viewHeight - lastLayout.height * camera.scale) / 2;
    cameraFramed = true;
    // "Fit" hands the camera back to the layout: a later resize may re-fit it.
    cameraAdjusted = false;
}

/**
 * Zoom about a fixed screen point so the board point under it stays put.
 *
 * @param {number} factor - Multiplicative zoom (>1 zooms in)
 * @param {number} cssX - Anchor x in CSS pixels, relative to the canvas box
 * @param {number} cssY - Anchor y in CSS pixels, relative to the canvas box
 */
function zoomAt(factor, cssX, cssY) {
    const next = clampScale(camera.scale * factor);
    if (next === camera.scale) {
        return false;
    }
    // From (cssX - x) / scale === (cssX - x') / next, solved for x'.
    camera.x = cssX - (cssX - camera.x) * (next / camera.scale);
    camera.y = cssY - (cssY - camera.y) * (next / camera.scale);
    camera.scale = next;
    cameraAdjusted = true;
    clampCamera();
    return true;
}

/**
 * Move the view by a screen-pixel delta. Scale-independent by construction.
 */
function panBy(dxCss, dyCss) {
    camera.x += dxCss;
    camera.y += dyCss;
    cameraAdjusted = true;
    clampCamera();
}

function getScale() {
    return camera.scale;
}

/**
 * Convert a client (viewport) position into board drawing coordinates.
 * The buffer is DPR-scaled and CSS may shrink the box (max-width), so both
 * ratios have to be undone before comparing against layout positions.
 *
 * @param {HTMLCanvasElement} canvas - The board canvas
 * @param {number} clientX - Pointer clientX
 * @param {number} clientY - Pointer clientY
 * @returns {object} - {x, y} in drawing coordinates
 */
function clientToBoard(canvas, clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) {
        return { x: 0, y: 0 };
    }

    const dpr = window.devicePixelRatio || 1;
    // Into CSS-pixel space first (the buffer/box ratio guards against a frame
    // where the two disagree during a resize)...
    const cssX = (clientX - rect.left) * (canvas.width / rect.width) / dpr;
    const cssY = (clientY - rect.top) * (canvas.height / rect.height) / dpr;
    // ...then undo the camera, which is the only step findNearest* rely on.
    return {
        x: (cssX - camera.x) / camera.scale,
        y: (cssY - camera.y) / camera.scale
    };
}

/**
 * Convert board drawing coordinates back into client (viewport) position.
 * The exact inverse of clientToBoard, which is what lets an HTML overlay be
 * pinned to a vertex, edge or hex without the overlay knowing the camera.
 *
 * @param {HTMLCanvasElement} canvas - The board canvas
 * @param {number} boardX - X in drawing coordinates
 * @param {number} boardY - Y in drawing coordinates
 * @returns {object} - {x, y} in client coordinates
 */
function boardToClient(canvas, boardX, boardY) {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height || !canvas.width || !canvas.height) {
        return { x: rect.left, y: rect.top };
    }

    const dpr = window.devicePixelRatio || 1;
    const cssX = boardX * camera.scale + camera.x;
    const cssY = boardY * camera.scale + camera.y;
    return {
        x: rect.left + cssX * dpr * rect.width / canvas.width,
        y: rect.top + cssY * dpr * rect.height / canvas.height
    };
}

/**
 * Draw the translucent piece a player is about to commit to.
 *
 * The preview is passed in per frame rather than stored here: drawing that
 * owns state makes the picture depend on the order the draw calls ran.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} layout - Layout from getLayout
 * @param {object} preview - {kind, key, blocked, color}
 */
function drawGhost(ctx, layout, preview) {
    const { vertexPositions, edgePositions, hexPositions } = layout;

    // The origin half of a two-step ship move. Marked on the board rather than
    // in a list, because unlike a knight a ship has no panel row to highlight -
    // the only place a player can see which one they picked up is where it is.
    // A progress card's first target - an Inventor's first number token, a
    // Smith's first knight - is held the same way and marked the same way, so
    // the origin is looked up wherever on the board it belongs.
    const origin = preview.from
        ? edgePositions[preview.from] || hexPositions[preview.from]
            || vertexPositions[preview.from]
        : null;
    if (origin) {
        ctx.save();
        ctx.setLineDash([4, 3]);
        ctx.lineWidth = 2;
        ctx.strokeStyle = preview.color || GHOST_ALLOWED_COLOR;
        ctx.beginPath();
        ctx.arc(
            origin.centerX ?? origin.x, origin.centerY ?? origin.y,
            GHOST_RING_RADIUS, 0, Math.PI * 2
        );
        ctx.stroke();
        ctx.restore();
    }
    if (!preview.key) {
        return;
    }
    // Blocked is a different *shape* as well as a different colour: a player
    // who cannot tell red from green still has to be able to tell "not allowed"
    // from "not a target".
    const color = preview.blocked ? GHOST_BLOCKED_COLOR : (preview.color || GHOST_ALLOWED_COLOR);

    ctx.save();
    ctx.globalAlpha = 0.55;
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 2;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;

    // A dashed ring around the target, whatever the piece is. The piece art is
    // small and half-transparent; the ring is what says "this spot, not the
    // one next to it" at a glance.
    if (!HEX_GHOST_KINDS.includes(preview.kind)) {
        const centre = EDGE_GHOST_KINDS.includes(preview.kind)
            ? edgePositions[preview.key]
            : vertexPositions[preview.key];
        if (centre) {
            ctx.save();
            ctx.globalAlpha = 0.9;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(
                centre.centerX ?? centre.x, centre.centerY ?? centre.y,
                GHOST_RING_RADIUS, 0, Math.PI * 2
            );
            ctx.stroke();
            ctx.restore();
        }
    }

    if (EDGE_GHOST_KINDS.includes(preview.kind)) {
        const pos = edgePositions[preview.key];
        if (pos) {
            ctx.setLineDash([]);
            if (preview.kind === 'road') {
                drawRoad(ctx, pos.x1, pos.y1, pos.x2, pos.y2, color);
            } else if (preview.kind !== 'progress_road') {
                drawShip(ctx, pos, color);
            }
            // A Diplomat takes a road *away*, so the ring above is all it gets:
            // drawing a road over the one being removed would say the opposite.
            ctx.setLineDash([5, 4]);
            markIfBlocked(ctx, preview, pos.centerX, pos.centerY);
        }
    } else if (HEX_GHOST_KINDS.includes(preview.kind)) {
        const pos = hexPositions[preview.key];
        if (pos) {
            const radius = BOARD_CONFIG.hexRadius - 2;
            ctx.beginPath();
            for (let corner = 0; corner < 6; corner += 1) {
                const angle = Math.PI / 3 * corner - Math.PI / 6;
                const x = pos.x + radius * Math.cos(angle);
                const y = pos.y + radius * Math.sin(angle);
                if (corner === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            }
            ctx.closePath();
            ctx.globalAlpha = 0.3;
            ctx.fill();
            ctx.globalAlpha = 0.85;
            ctx.lineWidth = 3;
            ctx.stroke();
            // Which piece is about to sail there, not just which hex: with the
            // pirate in play a 7 offers two different moves and the outlined
            // hex alone looks identical for both.
            if (preview.kind === 'pirate') {
                drawPirate(ctx, pos.x, pos.y);
            }
            markIfBlocked(ctx, preview, pos.x, pos.y);
        }
    } else {
        const pos = vertexPositions[preview.key];
        if (pos) {
            if (preview.kind === 'city') {
                drawCity(ctx, pos.x, pos.y, color);
            } else if (preview.kind === 'settlement') {
                drawSettlement(ctx, pos.x, pos.y, color);
            } else if (preview.kind === 'knight' || preview.kind === 'knight_move') {
                ctx.setLineDash([]);
                shieldPath(ctx, pos.x, pos.y);
                ctx.fill();
                ctx.lineWidth = 2;
                ctx.stroke();
                ctx.setLineDash([5, 4]);
            } else if (preview.kind === 'city_wall') {
                // The piece itself, half-transparent: a player aiming a wall
                // should see the wall, not a generic marker.
                ctx.setLineDash([]);
                cityWallPath(ctx, pos.x, pos.y);
                ctx.lineWidth = 4;
                ctx.stroke();
                for (const corner of wallCorners(pos.x, pos.y)) {
                    wallTowerPath(ctx, corner);
                    ctx.fill();
                }
                ctx.setLineDash([5, 4]);
            } else {
                // Anything without art of its own: a blob says "here" without
                // claiming to be a piece.
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, 9, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }
            markIfBlocked(ctx, preview, pos.x, pos.y);
        }
    }

    ctx.restore();
}

/**
 * Strike a blocked ghost through, so illegal reads as illegal without colour.
 */
function markIfBlocked(ctx, preview, x, y) {
    if (!preview.blocked) {
        return;
    }
    const arm = 11;
    ctx.setLineDash([]);
    ctx.globalAlpha = 0.95;
    ctx.strokeStyle = GHOST_BLOCKED_COLOR;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x - arm, y - arm);
    ctx.lineTo(x + arm, y + arm);
    ctx.moveTo(x + arm, y - arm);
    ctx.lineTo(x - arm, y + arm);
    ctx.stroke();
}

/**
 * Render the Catan board on a canvas.
 *
 * @param {object} boardData - Board data from server
 * @param {string} canvasId - ID of the canvas element
 * @param {number|null} highlightNumber - Optional number to highlight on hexes
 * @param {object|null} preview - Placement ghost {kind, key, blocked, color}
 * @param {Array<string>} choiceKeys - Intersections this player is being asked
 *                                     to choose between, ringed on the board
 * @returns {object} - Object with canvas and position data for click detection
 */
function renderBoard(boardData, canvasId, highlightNumber = null, preview = null,
                     choiceKeys = [], overlay = null) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.error('Canvas not found:', canvasId);
        return;
    }

    const ctx = canvas.getContext('2d');
    const hexes = boardData.hexes || {};
    const vertices = boardData.vertices || {};
    const edges = boardData.edges || {};
    const players = boardData.players || [];

    // The resource registry travels with every server board. Adopt it so hex
    // colours, patterns and glyphs draw from it; a client-built board (the map
    // editor's authored frame) omits it and keeps the CSS-token fallback.
    if (boardData.resources) {
        resourceDefs = boardData.resources;
        const signature = JSON.stringify(boardData.resources);
        if (signature !== resourceDefsSignature) {
            resourceDefsSignature = signature;
        }
    }

    const hexRadius = BOARD_CONFIG.hexRadius;

    // Build player color lookup from players array
    const playerColors = {};
    for (const player of players) {
        if (player.name && player.color) {
            playerColors[player.name] = player.color;
        }
    }

    const layout = getLayout(boardData);
    const { hexPositions, vertexPositions, edgePositions, offsetX, offsetY, width, height } = layout;
    const hexKeys = Object.keys(hexes);

    // The canvas fills its container; the camera decides which part of the
    // board that shows. Falling back to the board size keeps this working if
    // the canvas is measured before layout has settled.
    const box = canvas.parentElement;
    viewWidth = (box && box.clientWidth) || width;
    viewHeight = (box && box.clientHeight) || height;

    sizeCanvas(canvas, ctx, viewWidth, viewHeight);

    // First board, or a viewport that changed shape under a camera nobody has
    // touched: frame it. Without the second case the board is framed once, on
    // whatever box existed before the console had finished wrapping, and stays
    // clipped for the rest of the game. A camera the player has zoomed or
    // panned is theirs and is only ever clamped.
    const viewChanged = viewWidth !== lastViewWidth || viewHeight !== lastViewHeight;
    lastViewWidth = viewWidth;
    lastViewHeight = viewHeight;

    if (!cameraFramed || (viewChanged && !cameraAdjusted)) {
        fitToView();
    } else {
        clampCamera();
    }

    // Clear the viewport, not the board — with a camera the two differ, and
    // clearing the board size leaves smears once the board is larger.
    ctx.clearRect(0, 0, viewWidth, viewHeight);

    // save/restore so the camera can never compound across frames
    ctx.save();
    ctx.translate(camera.x, camera.y);
    ctx.scale(camera.scale, camera.scale);
    ctx.translate(offsetX, offsetY);

    // Draw all hexes
    for (const key of hexKeys) {
        const hex = hexes[key];
        const pos = hexPositions[key];
        const isLand = hex.type !== 'ocean';
        const isHighlighted = highlightNumber !== null && hex.number === highlightNumber;
        const regionId = overlay?.regionOf?.[key];
        const hexColor = regionId
            ? (overlay.colors[regionId] ?? getHexColor(hex.type))
            : getHexColor(hex.type);
        drawHex(ctx, pos.x, pos.y, hexRadius - 2, hexColor, hex.number, isLand,
                isHighlighted, hex.type);
    }
    
    // Draw robber if present
    if (boardData.robber_hex && hexPositions[boardData.robber_hex]) {
        const robberPos = hexPositions[boardData.robber_hex];
        const robberSize = 8;
        // Draw in bottom-left corner of hex
        const robberX = robberPos.x - hexRadius * 0.5;
        const robberY = robberPos.y + hexRadius * 0.4;
        
        ctx.fillStyle = '#555555';
        ctx.fillRect(robberX - robberSize/2, robberY - robberSize/2, robberSize, robberSize);
        ctx.strokeStyle = '#000000';
        ctx.lineWidth = 1;
        ctx.strokeRect(robberX - robberSize/2, robberY - robberSize/2, robberSize, robberSize);
    }

    // The pirate. Null until somebody first moves it, so an untouched table
    // with the rule on shows nothing at all.
    if (boardData.pirate_hex && hexPositions[boardData.pirate_hex]) {
        const piratePos = hexPositions[boardData.pirate_hex];
        drawPirate(ctx, piratePos.x, piratePos.y);
    }

    // The merchant. Null until somebody plays the card; it is worth a victory
    // point to whoever holds it, so where it stands has to be on the board and
    // not only in the log line that announced it.
    if (boardData.merchant_hex && hexPositions[boardData.merchant_hex]) {
        const merchantPos = hexPositions[boardData.merchant_hex];
        drawMerchant(ctx, merchantPos.x + hexRadius * 0.5, merchantPos.y + hexRadius * 0.4);
    }


    // Draw roads first so buildings appear on top
    // Note: Empty edges are not drawn (only clickable)
    for (const key in edges) {
        const edge = edges[key];
        const pos = edgePositions[key];

        if (pos && edge.road) {
            const playerColor = playerColors[edge.road.player] || null;
            drawRoad(ctx, pos.x1, pos.y1, pos.x2, pos.y2, playerColor);
        }
    }

    // Harbours belong to coastal edges. `vertex.port` mirrors the same harbour
    // onto both of its intersections for compatibility, so drawing from there
    // draws every harbour twice - 18 markers for the 9 in the box.
    for (const key in edges) {
        const edge = edges[key];
        const pos = edgePositions[key];

        if (pos && edge.port) {
            drawHarbour(ctx, pos, edge.port, seawardFrom(edge, pos, hexPositions));
        }
    }

    // Ships after the harbours: a harbour badge is fixed furniture that sits
    // out in the water, and a player's own piece is what has to win where the
    // two overlap. The badge still reads - its plank and mooring lines are on
    // the coast, clear of any sea edge.
    for (const key in edges) {
        const edge = edges[key];
        const pos = edgePositions[key];

        if (pos && edge.ship) {
            drawShip(ctx, pos, playerColors[edge.ship.player] || null);
            // A transport ship (Explorers & Pirates) carries a hold; show what
            // is in it as a little row of pips above the boat.
            if (edge.ship.kind === 'transport' && edge.ship.cargo?.length) {
                drawCargo(ctx, pos, edge.ship.cargo);
            }
        }
    }

    // Walls before the buildings: a wall stands around the city it protects, so
    // the city is painted over it and cannot be obscured by it.
    const wallsByPlayer = (boardData.cities_knights || {}).city_wall_vertices || {};
    for (const owner in wallsByPlayer) {
        for (const vertexKey of wallsByPlayer[owner]) {
            const pos = vertexPositions[vertexKey];
            if (pos) {
                drawCityWall(ctx, pos.x, pos.y);
            }
        }
    }

    // Draw buildings on top of roads
    for (const key in vertices) {
        const vertex = vertices[key];
        const pos = vertexPositions[key];

        if (vertex.building) {
            const playerColor = playerColors[vertex.building.player] || null;
            if (vertex.building.type === 'settlement') {
                drawSettlement(ctx, pos.x, pos.y, playerColor);
            } else if (vertex.building.type === 'city') {
                drawCity(ctx, pos.x, pos.y, playerColor);
            }
        }
    }

    // Knights last of the pieces: they step off a built-on intersection, so
    // they have to know what is already standing there.
    const knightsByPlayer = (boardData.cities_knights || {}).knights || {};
    for (const owner in knightsByPlayer) {
        const playerColor = playerColors[owner] || null;
        for (const knight of knightsByPlayer[owner]) {
            const pos = vertexPositions[knight.vertex];
            if (!pos) {
                continue;
            }
            const occupied = Boolean((vertices[knight.vertex] || {}).building);
            drawKnight(ctx, pos.x, pos.y, knight, playerColor, occupied);
        }
    }

    // Explorers & Pirates markers on the hexes: each player's pirate ship, and
    // the three missions' destinations (lair tokens, fish shoals, spice
    // villages). Over the tiles and buildings, under the choice ring and ghost.
    drawEpState(ctx, boardData.ep, hexPositions, playerColors, hexRadius);

    // The Fishermen of Catan fishing-ground numbers on their frame tiles.
    drawFishermenState(ctx, boardData.tb, hexPositions, hexRadius);

    // The intersections a pending choice is asking about. Over the pieces,
    // because the thing being chosen is usually one of them.
    for (const key of choiceKeys || []) {
        const pos = vertexPositions[key];
        if (pos) {
            drawChoiceRing(ctx, pos.x, pos.y);
        }
    }

    // Last, so the ghost is never hidden under a piece already on the board
    // `from` alone is a ship picked up and not yet aimed, which still has to be
    // shown or the player cannot see what they are holding.
    if (preview && (preview.key || preview.from)) {
        drawGhost(ctx, layout, preview);
    }

    ctx.restore();

    return { canvas, hexPositions, vertexPositions };
}

/**
 * The direction from the island out to the open water, for a coastal edge.
 *
 * A coastal edge lists exactly one hex as a neighbour - the ocean ring carries
 * no vertices or edges of its own - so the land side is simply the side that
 * hex is on. The fallback keeps a marker pointing somewhere sane if a payload
 * ever arrives without the neighbour list.
 *
 * @param {object} edge - Edge data from the server
 * @param {object} pos - Edge geometry from the layout
 * @param {object} hexPositions - Hex key to {x, y}
 * @returns {object} - Unit vector {x, y}
 */
function seawardFrom(edge, pos, hexPositions) {
    const landKeys = (edge.neighbors || {}).hexes || [];
    let sumX = 0;
    let sumY = 0;
    let counted = 0;
    for (const key of landKeys) {
        const land = hexPositions[key];
        if (land) {
            sumX += land.x;
            sumY += land.y;
            counted += 1;
        }
    }
    if (!counted) {
        return { x: 0, y: -1 };
    }

    const dx = pos.centerX - sumX / counted;
    const dy = pos.centerY - sumY / counted;
    const length = Math.hypot(dx, dy) || 1;
    return { x: dx / length, y: dy / length };
}

/**
 * Calculate distance from a point to a line segment.
 * Used for edge click detection.
 * 
 * @param {number} px - Point x
 * @param {number} py - Point y
 * @param {number} x1 - Line start x
 * @param {number} y1 - Line start y
 * @param {number} x2 - Line end x
 * @param {number} y2 - Line end y
 * @returns {number} - Distance from point to line segment
 */
function pointToLineDistance(px, py, x1, y1, x2, y2) {
    const A = px - x1;
    const B = py - y1;
    const C = x2 - x1;
    const D = y2 - y1;
    
    const dot = A * C + B * D;
    const lenSq = C * C + D * D;
    
    let param = -1;
    if (lenSq !== 0) {
        param = dot / lenSq;
    }
    
    let xx, yy;
    
    if (param < 0) {
        xx = x1;
        yy = y1;
    } else if (param > 1) {
        xx = x2;
        yy = y2;
    } else {
        xx = x1 + param * C;
        yy = y1 + param * D;
    }
    
    const dx = px - xx;
    const dy = py - yy;
    
    return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Find the nearest vertex to a click position.
 *
 * @param {object} boardData - Board data from server
 * @param {number} clickX - Click x position in drawing coordinates
 * @param {number} clickY - Click y position in drawing coordinates
 * @returns {string|null} - Vertex key if found, null otherwise
 */
function findNearestVertex(boardData, clickX, clickY) {
    const layout = getLayout(boardData);
    if (!layout) {
        return null;
    }

    const { vertexPositions, offsetX, offsetY } = layout;
    const vertices = boardData.vertices || {};
    // Divided by scale so the target stays a constant size on screen: a fixed
    // board-space radius becomes unclickable when zoomed out.
    const radius = BOARD_CONFIG.clickRadius / camera.scale;

    let nearestKey = null;
    let nearestDist = Infinity;

    for (const key in vertexPositions) {
        // Open water is not a place. With ships on, the graph is grown to cover
        // the ocean ring, so most of the vertices in the payload are out at
        // sea; the server lists only *land* hexes as a vertex's neighbours, so
        // an empty list is exactly "no hex meets here". No piece may ever stand
        // on one - the engine refuses every attempt - and offering one as a
        // target is a click a player can only be told off for. In a base game
        // the ocean carries no vertices at all, so this excludes nothing.
        if (!(vertices[key]?.neighbors?.hexes || []).length) {
            continue;
        }
        const pos = vertexPositions[key];
        // Adjust for canvas offset
        const adjX = pos.x + offsetX;
        const adjY = pos.y + offsetY;
        
        const dist = Math.sqrt(Math.pow(clickX - adjX, 2) + Math.pow(clickY - adjY, 2));

        if (dist < radius && dist < nearestDist) {
            nearestDist = dist;
            nearestKey = key;
        }
    }
    
    return nearestKey;
}

/**
 * Find the nearest hex to a click position.
 *
 * @param {object} boardData - Board data from server
 * @param {number} clickX - Click x position in drawing coordinates
 * @param {number} clickY - Click y position in drawing coordinates
 * @returns {string|null} - Hex key if found, null otherwise
 */
function findNearestHex(boardData, clickX, clickY) {
    const layout = getLayout(boardData);
    if (!layout) {
        return null;
    }

    const { hexPositions, offsetX, offsetY } = layout;
    const hexRadius = BOARD_CONFIG.hexRadius;
    const radius = (hexRadius * 0.8) / camera.scale;
    
    let nearestKey = null;
    let nearestDist = Infinity;
    
    for (const key in hexPositions) {
        const pos = hexPositions[key];
        // Adjust for canvas offset
        const adjX = pos.x + offsetX;
        const adjY = pos.y + offsetY;
        
        const dist = Math.sqrt(Math.pow(clickX - adjX, 2) + Math.pow(clickY - adjY, 2));

        if (dist < radius && dist < nearestDist) {
            nearestDist = dist;
            nearestKey = key;
        }
    }
    
    return nearestKey;
}

/**
 * Find the nearest edge to a click position.
 *
 * @param {object} boardData - Board data from server
 * @param {number} clickX - Click x position in drawing coordinates
 * @param {number} clickY - Click y position in drawing coordinates
 * @returns {string|null} - Edge key if found, null otherwise
 */
function findNearestEdge(boardData, clickX, clickY) {
    const layout = getLayout(boardData);
    if (!layout) {
        return null;
    }

    const { edgePositions, offsetX, offsetY } = layout;
    // Divided by scale so the target stays a constant size on screen: a fixed
    // board-space radius becomes unclickable when zoomed out.
    const radius = BOARD_CONFIG.clickRadius / camera.scale;
    
    let nearestKey = null;
    let nearestDist = Infinity;
    
    for (const key in edgePositions) {
        const edge = edgePositions[key];
        
        // Calculate distance from click to edge line
        const clickAdjX = clickX - offsetX;
        const clickAdjY = clickY - offsetY;
        
        const dist = pointToLineDistance(
            clickAdjX, clickAdjY,
            edge.x1, edge.y1,
            edge.x2, edge.y2
        );
        
        if (dist < radius && dist < nearestDist) {
            nearestDist = dist;
            nearestKey = key;
        }
    }

    return nearestKey;
}

/* -------------------------------------------------------------------------
 * Zoom and pan input
 *
 * These live here rather than in client.js because the camera lives here: the
 * renderer and the hit-tester must share exactly one coordinate convention,
 * and splitting ownership is how placements end up off by the pan offset.
 *
 * Nothing below draws. Handlers mutate the camera and ask for a redraw, so a
 * burst of pointermove events between two frames collapses into one render.
 * ---------------------------------------------------------------------- */

// Set by client.js so a camera change schedules a frame on its rAF loop.
let requestRedraw = () => {};

const TAP_MOVE_LIMIT = 10;   // px of movement before a gesture becomes a pan

const activePointers = new Map();
let panning = false;
let pinchDistance = 0;
let gestureRect = null;      // cached at gesture start: rect reads force layout

function canvasPoint(canvas, clientX, clientY) {
    const rect = gestureRect || canvas.getBoundingClientRect();
    return { x: clientX - rect.left, y: clientY - rect.top };
}

/**
 * Wire zoom and pan to a canvas. Safe to call more than once.
 *
 * @param {HTMLCanvasElement} canvas - The board canvas
 * @param {Function} onChange - Called after the camera moves (mark dirty)
 */
function attachCameraControls(canvas, onChange) {
    if (!canvas || canvas.dataset.cameraBound === 'true') {
        return;
    }
    canvas.dataset.cameraBound = 'true';
    requestRedraw = onChange || (() => {});

    // The drawing buffer is derived from the box, so the box is what has to be
    // watched. A window `resize` listener misses every reason this box changes
    // without the window doing so - a panel appearing, the console wrapping,
    // the rail widening for Cities & Knights.
    if (window.ResizeObserver && canvas.parentElement) {
        new ResizeObserver(() => requestRedraw()).observe(canvas.parentElement);
    }

    // passive: false or preventDefault is a no-op and the *page* zooms instead
    canvas.addEventListener('wheel', (event) => {
        if (event.cancelable !== false) {
            event.preventDefault();
        }
        let dy = event.deltaY;
        // Firefox reports lines, Edge a flat 100; normalise to pixels
        if (event.deltaMode === 1) {
            dy *= 16;
        } else if (event.deltaMode === 2) {
            dy *= 100;
        }
        dy = Math.sign(dy) * Math.min(24, Math.abs(dy));

        // A trackpad pinch arrives as ctrl+wheel with much smaller deltas
        const speed = event.ctrlKey ? 8 : 2.5;
        const factor = dy <= 0
            ? 1 - (speed * dy) / 100
            : 1 / (1 + (speed * dy) / 100);

        gestureRect = canvas.getBoundingClientRect();
        const point = canvasPoint(canvas, event.clientX, event.clientY);
        gestureRect = null;
        if (zoomAt(factor, point.x, point.y)) {
            requestRedraw();
        }
    }, { passive: false });

    canvas.addEventListener('pointerdown', (event) => {
        activePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        gestureRect = canvas.getBoundingClientRect();
        if (activePointers.size === 2) {
            const [a, b] = [...activePointers.values()];
            pinchDistance = Math.hypot(a.x - b.x, a.y - b.y);
        }
    });

    canvas.addEventListener('pointermove', (event) => {
        const cached = activePointers.get(event.pointerId);
        if (!cached) {
            return;
        }
        const dx = event.clientX - cached.x;
        const dy = event.clientY - cached.y;

        if (activePointers.size === 2) {
            cached.x = event.clientX;
            cached.y = event.clientY;
            const [a, b] = [...activePointers.values()];
            const distance = Math.hypot(a.x - b.x, a.y - b.y);
            if (pinchDistance > 0 && distance > 0) {
                const mid = canvasPoint(canvas, (a.x + b.x) / 2, (a.y + b.y) / 2);
                if (zoomAt(distance / pinchDistance, mid.x, mid.y)) {
                    requestRedraw();
                }
            }
            pinchDistance = distance;
            return;
        }

        if (activePointers.size !== 1) {
            return;
        }
        if (!panning && (Math.abs(dx) > TAP_MOVE_LIMIT || Math.abs(dy) > TAP_MOVE_LIMIT)) {
            panning = true;
            canvas.classList.add('panning');
        }
        if (panning) {
            cached.x = event.clientX;
            cached.y = event.clientY;
            panBy(dx, dy);
            requestRedraw();
        }
    });

    const endPointer = (event) => {
        activePointers.delete(event.pointerId);
        if (activePointers.size < 2) {
            pinchDistance = 0;
        }
        if (activePointers.size === 0) {
            panning = false;
            gestureRect = null;
            canvas.classList.remove('panning');
        }
    };
    canvas.addEventListener('pointerup', endPointer);
    canvas.addEventListener('pointercancel', endPointer);

    // The canvas is already tabindex="0"; these keys were unbound.
    canvas.addEventListener('keydown', (event) => {
        const step = event.shiftKey ? 160 : 60;
        let handled = true;
        switch (event.key) {
            case '+': case '=':
                zoomAt(1.2, viewWidth / 2, viewHeight / 2); break;
            case '-': case '_':
                zoomAt(1 / 1.2, viewWidth / 2, viewHeight / 2); break;
            case '0':
                fitToView(); break;
            case 'ArrowLeft':  panBy(step, 0); break;
            case 'ArrowRight': panBy(-step, 0); break;
            case 'ArrowUp':    panBy(0, step); break;
            case 'ArrowDown':  panBy(0, -step); break;
            default: handled = false;
        }
        if (handled) {
            event.preventDefault();
            requestRedraw();
        }
    });
}

/**
 * Whether the last gesture was a pan, so client.js can skip placing a piece.
 */
function wasPanning() {
    return panning;
}

// Export for use in client.js
window.BoardRenderer = {
    render: renderBoard,
    computeLayout: computeLayout,
    clientToBoard: clientToBoard,
    boardToClient: boardToClient,
    findNearestVertex: findNearestVertex,
    findNearestEdge: findNearestEdge,
    findNearestHex: findNearestHex,
    attachCameraControls: attachCameraControls,
    zoomAt: zoomAt,
    panBy: panBy,
    fitToView: fitToView,
    getScale: getScale,
    wasPanning: wasPanning
};
