// Black or white ink on an arbitrary background, by WCAG contrast.
//
// Its own module because it is pure - no imports at all - and it is the only
// thing the scoreboard rows and the console's build buttons share. Folding it
// into either would make the other import a renderer just to pick an ink.

/**
 * Convert `#rrggbb` to [r, g, b], or null if it is not a hex colour.
 *
 * Player colours reach us from an `<input type="color">`, so they are always
 * this form in practice - but they arrive over the wire from another client,
 * and a caller must not have to trust that.
 *
 * @param {string} hexColor - A `#rrggbb` colour
 * @returns {number[]|null} - Channels 0-255, or null
 */
function parseHexColor(hexColor) {
    const match = /^#([0-9a-f]{6})$/i.exec(String(hexColor).trim());
    if (!match) {
        return null;
    }
    const value = parseInt(match[1], 16);
    return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

/**
 * WCAG relative luminance of an [r, g, b] triple.
 *
 * @param {number[]} rgb - Channels 0-255
 * @returns {number} - Luminance 0-1
 */
function relativeLuminance(rgb) {
    const [r, g, b] = rgb.map(channel => {
        const value = channel / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * WCAG contrast ratio between two [r, g, b] triples, 1 to 21.
 *
 * @param {number[]} first - Channels 0-255
 * @param {number[]} second - Channels 0-255
 * @returns {number} - Ratio, order-independent
 */
function contrastRatio(first, second) {
    const light = Math.max(relativeLuminance(first), relativeLuminance(second));
    const dark = Math.min(relativeLuminance(first), relativeLuminance(second));
    return (light + 0.05) / (dark + 0.05);
}

/**
 * Black or white for text on `hexColor` - whichever a player can actually read.
 *
 * This used to threshold a YIQ brightness average at 0.5 and offer a navy
 * (#2c3e50) as its dark option. Both halves were wrong. YIQ approximates
 * perceived brightness, not WCAG contrast, so the threshold landed on the wrong
 * side for saturated hues; and the navy throws away four points of ratio for no
 * reason, because nothing is more readable on a light fill than black. Together
 * they put white on #e74c3c at 3.82:1 and the navy on #3498db at 3.48:1 - two
 * of the four shipped player colours failing AA on the scoreboard row and the
 * build buttons.
 *
 * Measuring both candidates and taking the winner is exact rather than
 * approximate, and it is the only approach that holds when the colour is
 * arbitrary: these come from a colour picker, so no palette audit can cover
 * them.
 *
 * @param {string} hexColor - Background colour, `#rrggbb`
 * @returns {string} - `#000000` or `#ffffff`
 */
export function getContrastColor(hexColor) {
    const rgb = parseHexColor(hexColor);
    // White on an unreadable colour is no worse than the old behaviour, and a
    // malformed colour must not throw inside a render pass.
    if (!rgb) {
        return '#ffffff';
    }
    const onBlack = contrastRatio(rgb, [0, 0, 0]);
    const onWhite = contrastRatio(rgb, [255, 255, 255]);
    return onBlack >= onWhite ? '#000000' : '#ffffff';
}
