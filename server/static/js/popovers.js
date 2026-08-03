// Folded detail panels.
//
// The owner's rule for this screen is that nothing scrolls and nothing is
// clipped: the board, the hand, the scoreboard, the build buttons and the log
// are all on screen at once, and every other subject collapses to a chip that
// states its headline numbers. Pressing the chip raises the detail.
//
// Two properties are load-bearing and neither is negotiable:
//
//   - A popover is `position: fixed` and placed from JavaScript. It is
//     therefore outside every flow on the page, so opening or closing one
//     cannot reflow the rail, cannot resize the board box, and cannot move the
//     camera under a click a player has already begun.
//   - Exactly one is open at a time. Two overlapping popovers on a 15rem rail
//     are unreadable, and the second one is always the one the player wanted.

// Clear of the anchor, and of the viewport edge it would otherwise hang over.
const ANCHOR_GAP = 6;
const VIEWPORT_MARGIN = 8;

// The chip (or tab) that opened whatever is currently up, or null.
let openTrigger = null;

/**
 * The panel a trigger controls.
 *
 * @param {HTMLElement} trigger - Element carrying `aria-controls`
 * @returns {HTMLElement|null}
 */
function panelFor(trigger) {
    const id = trigger?.getAttribute('aria-controls');
    return id ? document.getElementById(id) : null;
}

/**
 * Pin a popover beside its trigger, inside the viewport.
 *
 * Preferred position is to the right of the rail chip, top-aligned with it;
 * a popover that would hang off the bottom or the right is pulled back rather
 * than allowed to introduce a scrollbar - a scrollbar here is the exact defect
 * this whole layout exists to remove.
 *
 * @param {HTMLElement} panel - The popover
 * @param {HTMLElement} trigger - What opened it
 */
function place(panel, trigger) {
    const anchor = trigger.getBoundingClientRect();

    // Measured after it is displayed but before it is painted at its final
    // spot, so `hidden` has to be off by the time this runs.
    const width = panel.offsetWidth;
    const height = panel.offsetHeight;

    let left = anchor.right + ANCHOR_GAP;
    if (left + width > window.innerWidth - VIEWPORT_MARGIN) {
        // No room to the right: hang it off the left edge of the anchor instead
        left = anchor.left - ANCHOR_GAP - width;
    }
    left = Math.max(VIEWPORT_MARGIN, Math.min(left, window.innerWidth - width - VIEWPORT_MARGIN));

    let top = anchor.top;
    top = Math.max(VIEWPORT_MARGIN, Math.min(top, window.innerHeight - height - VIEWPORT_MARGIN));

    panel.style.left = `${Math.round(left)}px`;
    panel.style.top = `${Math.round(top)}px`;
}

/**
 * Close whatever is open. Safe to call when nothing is.
 */
export function closePopover() {
    if (!openTrigger) {
        return;
    }
    const panel = panelFor(openTrigger);
    panel?.classList.add('hidden');
    openTrigger.setAttribute('aria-expanded', 'false');
    openTrigger = null;
}

/**
 * Whether a given trigger's popover is the one currently up.
 *
 * @param {HTMLElement} trigger
 * @returns {boolean}
 */
export function isOpen(trigger) {
    return openTrigger === trigger;
}

/**
 * Raise a trigger's popover, closing any other.
 *
 * @param {HTMLElement} trigger - Element carrying `aria-controls`
 */
export function openPopover(trigger) {
    const panel = panelFor(trigger);
    if (!panel) {
        return;
    }
    closePopover();
    panel.classList.remove('hidden');
    trigger.setAttribute('aria-expanded', 'true');
    openTrigger = trigger;
    place(panel, trigger);
}

/**
 * Open a trigger's popover, or close it if it is already the one showing.
 *
 * @param {HTMLElement} trigger - Element carrying `aria-controls`
 */
export function togglePopover(trigger) {
    if (isOpen(trigger)) {
        closePopover();
        return;
    }
    openPopover(trigger);
}

/**
 * Keep an open popover beside its chip after a re-render changed its height.
 * The chips restate their numbers on every board payload, so the anchor moves.
 */
export function repositionPopover() {
    if (!openTrigger) {
        return;
    }
    const panel = panelFor(openTrigger);
    if (panel) {
        place(panel, openTrigger);
    }
}

// The chips. Registered once here rather than per-panel: every fold in the
// template is a `.fold-chip` with `aria-controls`, so a fold added later needs
// no JavaScript at all.
document.querySelectorAll('.fold-chip[aria-controls]').forEach(chip => {
    chip.addEventListener('click', () => togglePopover(chip));
});

document.querySelectorAll('[data-close-popover]').forEach(button => {
    button.addEventListener('click', closePopover);
});

// `pointerdown` rather than `click`, and deliberately without
// `preventDefault`: a tap outside dismisses the popover AND still reaches
// whatever it landed on, so dismissing never costs the player a board click.
document.addEventListener('pointerdown', (event) => {
    if (!openTrigger) {
        return;
    }
    const panel = panelFor(openTrigger);
    if (panel?.contains(event.target) || openTrigger.contains(event.target)) {
        return;
    }
    closePopover();
});

document.addEventListener('keydown', (event) => {
    // Escape also cancels a pending board placement; the popover is the
    // shallower of the two, so it goes first and stops there.
    if (event.key === 'Escape' && openTrigger) {
        const trigger = openTrigger;
        closePopover();
        trigger.focus();
        event.stopPropagation();
    }
}, true);

// A popover is pinned in viewport coordinates, so a resize strands it.
window.addEventListener('resize', closePopover);
