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
        ocean: '#1a5276',
        desert: '#f4d03f',
        ore: '#7f8c8d',
        wheat: '#f39c12',
        sheep: '#27ae60',
        brick: '#c0392b',
        wood: '#8b4513',
        highlight: 'rgba(231, 76, 60, 0.5)',
        border: '#2c3e50',
        text: '#ecf0f1',
        numberCircle: '#ecf0f1',
        numberText: '#2c3e50',
        vertexDefault: 'red',
        edgeDefault: 'red'
    }
};

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
function drawHex(ctx, centerX, centerY, radius, color, number, isLand, isHighlighted = false) {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
        const angle = Math.PI / 3 * i - Math.PI / 6;
        const x = centerX + radius * Math.cos(angle);
        const y = centerY + radius * Math.sin(angle);
        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    }
    ctx.closePath();
    
    // Highlight glow effect
    if (isHighlighted) {
        ctx.shadowColor = '#f1c40f';
        ctx.shadowBlur = 20;
    }
    
    ctx.fillStyle = color;
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
    ctx.fillStyle = isHighlighted ? '#f1c40f' : BOARD_CONFIG.colors.numberCircle;
    ctx.fill();
    ctx.strokeStyle = isHighlighted ? '#f39c12' : BOARD_CONFIG.colors.border;
    ctx.lineWidth = 1;
    ctx.stroke();
    
    ctx.font = 'bold 14px Arial';
    ctx.fillStyle = isHighlighted ? '#2c3e50' : BOARD_CONFIG.colors.numberText;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(number.toString(), centerX, centerY);
}

/**
 * Get the color for a hex type.
 * 
 * @param {string} hexType - Type of hex (ore, wheat, sheep, brick, wood, desert, ocean)
 * @returns {string} - Hex color code
 */
function getHexColor(hexType) {
    return BOARD_CONFIG.colors[hexType] || BOARD_CONFIG.colors.ocean;
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
 * Draw a port at a vertex position.
 * Port appears as a small harbor icon (anchor shape).
 * 
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} x - X position
 * @param {number} y - Y position
 * @param {object} port - Port info {type: "generic"/"resource", resource: string}
 */
function drawPort(ctx, x, y, port) {
    const size = 10;
    
    // Set color based on port type
    if (port.type === 'generic') {
        ctx.fillStyle = '#3498db'; // Blue for generic 3:1
    } else {
        ctx.fillStyle = '#e67e22'; // Orange for resource-specific 2:1
    }
    
    // Draw anchor shape (circle with cross)
    ctx.beginPath();
    ctx.arc(x, y, size/2, 0, Math.PI * 2);
    ctx.fill();
    
    // Draw inner dot
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
    
    // Draw resource icon if specific port
    if (port.type === 'resource' && port.resource) {
        const resourceIcons = {
            wood: '🌲',
            brick: '🧱',
            sheep: '🐑',
            wheat: '🌾',
            ore: '🪨'
        };
        ctx.font = '8px Arial';
        ctx.fillText(resourceIcons[port.resource] || '', x - 5, y + 12);
    }
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

    const padding = hexRadius + 20;

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
    // The canvas now fills its container and the camera decides what is shown,
    // so the box is set explicitly in both axes. Previously the buffer was the
    // size of the whole board and CSS shrank it, which bitmap-downscaled the
    // board and put an unbounded buffer one big map away from Safari's
    // ~16.7M pixel area cap.
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
let cameraFramed = false;    // has the camera been fitted to a board yet?

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
    clampCamera();
    return true;
}

/**
 * Move the view by a screen-pixel delta. Scale-independent by construction.
 */
function panBy(dxCss, dyCss) {
    camera.x += dxCss;
    camera.y += dyCss;
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
 * Render the Catan board on a canvas.
 *
 * @param {object} boardData - Board data from server
 * @param {string} canvasId - ID of the canvas element
 * @param {number|null} highlightNumber - Optional number to highlight on hexes
 * @returns {object} - Object with canvas and position data for click detection
 */
function renderBoard(boardData, canvasId, highlightNumber = null) {
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

    const hexRadius = BOARD_CONFIG.hexRadius;

    // Build player color lookup from players array
    const playerColors = {};
    for (const player of players) {
        if (player.name && player.color) {
            playerColors[player.name] = player.color;
        }
    }

    const { hexPositions, vertexPositions, edgePositions, offsetX, offsetY, width, height } = getLayout(boardData);
    const hexKeys = Object.keys(hexes);

    // The canvas fills its container; the camera decides which part of the
    // board that shows. Falling back to the board size keeps this working if
    // the canvas is measured before layout has settled.
    const box = canvas.parentElement;
    viewWidth = (box && box.clientWidth) || width;
    viewHeight = (box && box.clientHeight) || height;

    sizeCanvas(canvas, ctx, viewWidth, viewHeight);

    // First board, or a board that outgrew the view: frame it.
    if (!cameraFramed) {
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
        
        drawHex(ctx, pos.x, pos.y, hexRadius - 2, getHexColor(hex.type), hex.number, isLand, isHighlighted);
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

    // Draw ports on vertices
    for (const key in vertices) {
        const vertex = vertices[key];
        const pos = vertexPositions[key];
        
        if (vertex.port) {
            drawPort(ctx, pos.x, pos.y, vertex.port);
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

    ctx.restore();

    return { canvas, hexPositions, vertexPositions };
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
    // Divided by scale so the target stays a constant size on screen: a fixed
    // board-space radius becomes unclickable when zoomed out.
    const radius = BOARD_CONFIG.clickRadius / camera.scale;

    let nearestKey = null;
    let nearestDist = Infinity;
    
    for (const key in vertexPositions) {
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
    const radius = hexRadius * 0.8;
    
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
