// The draggable seam between the board and the right panel.
//
// Dragging the handle writes `--panel-aside` (the right panel's width), clamped
// so the panel can neither vanish nor swallow the board. Keyboard users get the
// same control through the arrow keys, since the handle is a focusable
// separator. Nothing here touches the board: the panel is a flex sibling, so a
// narrower panel simply hands its width back to the board, which re-fits on the
// resize it already listens for.

const MIN_WIDTH = 220;
const MAX_WIDTH = 520;
const KEY_STEP = 24;

const seam = document.getElementById('board-resizer');

/** Read the current panel width in pixels, falling back to the default token. */
function currentWidth() {
    const aside = document.querySelector('.table-aside');
    return aside ? Math.round(aside.getBoundingClientRect().width) : 272;
}

function clamp(width) {
    return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, width));
}

function setWidth(width) {
    document.documentElement.style.setProperty('--panel-aside', `${clamp(width)}px`);
}

if (seam) {
    let dragging = false;

    const onMove = (event) => {
        if (!dragging) {
            return;
        }
        // The panel is anchored to the right edge, so its width grows as the
        // pointer moves left. innerWidth is close enough to the panel's right
        // edge for a resize handle; the clamp keeps it honest either way.
        setWidth(window.innerWidth - event.clientX);
    };

    const stop = () => {
        if (!dragging) {
            return;
        }
        dragging = false;
        seam.classList.remove('dragging');
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', stop);
    };

    seam.addEventListener('pointerdown', (event) => {
        dragging = true;
        seam.classList.add('dragging');
        event.preventDefault();
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', stop);
    });

    // Arrow keys resize from the keyboard. Left widens the panel (it grows
    // leftward), right narrows it - the same direction the drag moves.
    seam.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.preventDefault();
            const delta = event.key === 'ArrowLeft' ? KEY_STEP : -KEY_STEP;
            setWidth(currentWidth() + delta);
        }
    });
}
