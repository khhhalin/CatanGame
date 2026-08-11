// The icon set. One source for every glyph the panels draw.
//
// The page ships an inline SVG sprite (see the <symbol> block at the top of
// index.html). Every icon on screen is a `<use href="#i-...">` into that
// sprite - no emoji, no per-panel SVG. This module maps the game's concepts
// (a resource, a commodity, an award) onto the sprite ids and hands back the
// markup, so a panel never types a sprite id or a class name by hand.
//
// ============================ HOW TO CALL ============================
//
//   import { icon, resourceTile, statusIcon,
//            RESOURCE_ICON, COMMODITY_ICON, STATUS_ICON, SPRITE_IDS } from './icons.js';
//
//   icon(spriteId, opts?) -> string
//       A bare `<svg class="icon">…</svg>` for one sprite id ('i-wood', or
//       '#i-wood', or a full key via the maps below). Monochrome, inherits
//       `color` (currentColor). Use for the line icons - pieces, awards.
//         opts.label   accessible name. Given -> role="img" + aria-label +
//                      <title>; omitted -> aria-hidden="true" (decorative,
//                      the meaning is carried by adjacent text). Pass a label
//                      whenever the icon is the ONLY carrier of meaning.
//         opts.cls     extra class(es) on the <svg>, appended after "icon".
//
//   resourceTile(key, opts?) -> string
//       The filled coloured tile for a resource or commodity you hold:
//       `<span class="tile t-wood"><svg class="icon">…</svg></span>`. `key` is
//       a resource ('wood'..'ore') or commodity ('cloth'|'coin'|'paper').
//       Same opts as icon(); the label goes on the inner <svg>.
//
//   statusIcon(concept, opts?) -> string
//       icon() for an award/piece/counter concept via STATUS_ICON, e.g.
//       statusIcon('longest_road', {label: 'Longest Road'}).
//
// The design rule these encode: FILLED COLOURED TILES are things a player
// holds (resources, commodities) - always resourceTile(); MONOCHROME LINE
// ICONS are facts about a player (pieces, roads, awards, counters) - icon()
// or statusIcon(). Do not put an award in a tile or a resource on a bare icon.
//
// The maps are exported so a panel can build its own markup when a helper does
// not fit - but the sprite id and the tile class must come from here, never a
// literal, so a renamed glyph is renamed in one place.
// =====================================================================

import { COMMODITY_TYPES } from './constants.js';
import { getBoard } from './state.js';

/** Resource -> sprite id. The five base resources, board order. */
export const RESOURCE_ICON = {
    wood: 'i-wood',
    brick: 'i-brick',
    sheep: 'i-sheep',
    wheat: 'i-wheat',
    ore: 'i-ore',
};

/** Commodity -> sprite id (Cities & Knights). */
export const COMMODITY_ICON = {
    cloth: 'i-cloth',
    coin: 'i-coin',
    paper: 'i-paper',
};

// The tile variant class for each holdable. Kept beside the id maps so the two
// never drift: a resource has both a glyph and a tile colour, and both are
// named here. Matches the `.t-*` classes in style.css.
const TILE_CLASS = {
    wood: 't-wood', brick: 't-brick', sheep: 't-sheep', wheat: 't-wheat', ore: 't-ore',
    cloth: 't-cloth', coin: 't-coin', paper: 't-paper',
};

// The display name for each base holdable. A resource a map introduced (cotton)
// has no entry here and takes its name from the registry the server sent.
const CARD_NAME = {
    wood: 'Wood', brick: 'Brick', sheep: 'Sheep', wheat: 'Wheat', ore: 'Ore',
    cloth: 'Cloth', coin: 'Coin', paper: 'Paper',
};

// The resource registry travels with every board payload, keyed by hex_type
// (a resource id). It is the source of truth for a resource with no built-in
// glyph, colour or name here — the base five and the commodities keep their
// hardcoded ids and theme-aware token classes, so their look never changes.
function resourceDef(key) {
    const defs = getBoard() && getBoard().resources;
    return defs ? defs[key] : undefined;
}

/**
 * The display name for a resource or commodity: the hardcoded name for a base
 * card, the registry name for one a map introduced (cotton), the id as a last
 * resort.
 *
 * @param {string} key
 * @returns {string}
 */
export function resourceName(key) {
    if (CARD_NAME[key]) {
        return CARD_NAME[key];
    }
    const def = resourceDef(key);
    return (def && def.name) || key;
}

/**
 * The `.t-*` tile-colour class for a card, or '' for one with no built-in class
 * (a map's own resource, which colours itself inline from the registry instead).
 *
 * @param {string} key
 * @returns {string}
 */
export function resourceTileClass(key) {
    return TILE_CLASS[key] || '';
}

/**
 * The `--tile` fill for a resource that has no theme-aware token class — its
 * registry colour — or null for the base five and commodities, which fill
 * themselves through their `.t-*` class and must not be given an inline colour
 * (that would drop their light/dark theming). Cotton returns its cream.
 *
 * @param {string} key
 * @returns {?string}
 */
export function customTileFill(key) {
    if (TILE_CLASS[key]) {
        return null;
    }
    const def = resourceDef(key);
    return (def && def.color) || null;
}

/**
 * Award, piece and counter concepts -> sprite id. Keyed by what the panels
 * mean, not by the glyph: the scoreboard asks for `longest_road`, not a route.
 * `leader` and `crown` are the same title; `resource`/`progress`/`commodity`
 * are the hand counters the scoreboard shows.
 */
export const STATUS_ICON = {
    crown: 'i-crown',
    leader: 'i-crown',            // "X leads" - same glyph as crown
    longest_road: 'i-route',
    largest_army: 'i-shield',
    harbormaster: 'i-anchor',
    merchant: 'i-shop',
    settlement: 'i-house',
    city: 'i-city',
    road: 'i-road',
    route: 'i-route',
    ship: 'i-ship',
    knight: 'i-sword',
    city_wall: 'i-wall',
    island: 'i-island',
    hand: 'i-hand',              // resource-cards-in-hand counter
    resource: 'i-hand',         // alias: the scoreboard's resource_count chip
    dev: 'i-dev',
    progress: 'i-dev',          // progress cards are a dev-card variant
    // The three progress decks, lettered so which deck a card came from - the
    // fact its colour used to carry - is not lost when a specific card is shown.
    progress_trade: 'i-dev-trade',
    progress_politics: 'i-dev-politics',
    progress_science: 'i-dev-science',
    metropolis: 'i-metropolis',  // a distinct piece, not a plain city
    // A commodity hand-count has no glyph of its own in the set - coin is the
    // set's stand-in for "a commodity". A panel showing a specific commodity
    // should prefer resourceTile('cloth'|'coin'|'paper') instead.
    commodity: 'i-coin',
};

/**
 * Every sprite id defined in the index.html sprite, derived from the maps
 * above so a test can pin the sprite against what the module actually asks
 * for. Deduplicated and in definition order.
 */
export const SPRITE_IDS = [
    ...Object.values(RESOURCE_ICON),
    ...Object.values(COMMODITY_ICON),
    'i-crown', 'i-shield', 'i-sword', 'i-anchor', 'i-shop',
    'i-house', 'i-city', 'i-road', 'i-route', 'i-ship',
    'i-wall', 'i-island', 'i-hand', 'i-dev',
    'i-dev-trade', 'i-dev-politics', 'i-dev-science', 'i-metropolis',
].filter((id, index, all) => all.indexOf(id) === index);

function escapeAttr(text) {
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function resolveSpriteId(key) {
    if (key.startsWith('#')) {
        return key.slice(1);
    }
    if (key.startsWith('i-')) {
        return key;
    }
    // A concept key: resource, then commodity, then status.
    const mapped = RESOURCE_ICON[key] || COMMODITY_ICON[key] || STATUS_ICON[key];
    if (mapped) {
        return mapped;
    }
    // A resource a map introduced (cotton) has no built-in glyph: take the
    // sprite id from its registry symbol (`cloth` -> `i-cloth`).
    const def = resourceDef(key);
    if (def && def.symbol) {
        return `i-${def.symbol}`;
    }
    return key;
}

/**
 * Markup for one sprite glyph. See the header for opts.
 *
 * @param {string} key - sprite id ('i-wood'/'#i-wood') or a concept the maps know.
 * @param {{label?: string, cls?: string}} [opts]
 * @returns {string}
 */
export function icon(key, opts = {}) {
    const id = resolveSpriteId(key);
    const cls = opts.cls ? `icon ${opts.cls}` : 'icon';
    if (opts.label) {
        const label = escapeAttr(opts.label);
        return `<svg class="${cls}" role="img" aria-label="${label}">`
            + `<title>${label}</title><use href="#${id}"></use></svg>`;
    }
    return `<svg class="${cls}" aria-hidden="true"><use href="#${id}"></use></svg>`;
}

/**
 * The filled coloured tile for a held resource or commodity. See the header.
 *
 * @param {string} key - 'wood'..'ore' or 'cloth'|'coin'|'paper'.
 * @param {{label?: string, cls?: string, tileCls?: string}} [opts]
 *        `tileCls` adds a class to the tile span - e.g. 'tile-sm' for the
 *        compact variant a dense strip needs.
 * @returns {string}
 */
export function resourceTile(key, opts = {}) {
    const tile = TILE_CLASS[key] || '';
    const extra = opts.tileCls ? ` ${opts.tileCls}` : '';
    const id = RESOURCE_ICON[key] || COMMODITY_ICON[key] || key;
    // A resource with no `.t-*` token (a map's own, e.g. cotton) is filled from
    // its registry colour inline; the base five and commodities keep their
    // theme-aware class and take no inline style, so their look is untouched.
    const fill = customTileFill(key);
    const style = fill ? ` style="--tile: ${escapeAttr(fill)}"` : '';
    return `<span class="tile ${tile}${extra}"${style}>${icon(id, opts)}</span>`;
}

/**
 * icon() for an award/piece/counter concept.
 *
 * @param {string} concept - a STATUS_ICON key.
 * @param {{label?: string, cls?: string}} [opts]
 * @returns {string}
 */
export function statusIcon(concept, opts = {}) {
    return icon(STATUS_ICON[concept] || concept, opts);
}

// COMMODITY_TYPES is imported so a consumer can iterate commodities and this
// module's use of it keeps the dependency honest; re-exported for panels that
// already reach here for icons.
export { COMMODITY_TYPES };
