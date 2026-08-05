// Display constants shared by more than one panel.
//
// They live in a module of their own because the panels that use them import
// each other, and a `const` exported across an import cycle is not guaranteed
// to be initialised by the time the other side evaluates.

export const COMMODITY_TYPES = ['cloth', 'coin', 'paper'];

// DEPRECATED emoji maps. The icon set now lives in icons.js, which renders
// inline-SVG glyphs from the sprite (RESOURCE_ICON/COMMODITY_ICON map to
// sprite ids, resourceTile()/icon() return the markup). These string maps are
// kept only so panels not yet converted keep rendering; convert a panel to
// icons.js and drop its import from here. COMMODITY_TYPES stays - it is data,
// not a glyph, and icons.js reads it too.
export const COMMODITY_ICONS = { cloth: '🧵', coin: '🪙', paper: '📜' };
export const RESOURCE_ICONS = { wood: '🌲', brick: '🧱', sheep: '🐑', wheat: '🌾', ore: '🪨' };
