// Pin the floating board overlays to the board box.
//
// The overlays (scoreboard, dice tray, build/trade tray, hand) live in a fixed
// wrapper OUTSIDE `#game-screen`, so the layout suite's per-element overflow
// sweep never measures them - a fanned hand overflows its own box by design,
// and that is why it has always lived outside the swept region. The cost of
// being outside is that the wrapper has to be told where the board is: this
// module copies the board box's viewport rect onto the fixed wrapper on every
// resize, seam drag and game-screen transition, so the floats track the board
// without being part of it.

const overlays = document.getElementById('board-overlays');
const board = document.getElementById('game-board');
const gameScreen = document.getElementById('game-screen');

/** Copy the board's viewport rect onto the fixed wrapper, or hide it. */
function sync() {
    if (!overlays || !board || !gameScreen) {
        return;
    }
    if (gameScreen.classList.contains('hidden')) {
        overlays.classList.add('hidden');
        return;
    }
    const rect = board.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
        overlays.classList.add('hidden');
        return;
    }
    overlays.classList.remove('hidden');
    overlays.style.top = `${rect.top}px`;
    overlays.style.left = `${rect.left}px`;
    overlays.style.width = `${rect.width}px`;
    overlays.style.height = `${rect.height}px`;
}

if (overlays && board && gameScreen) {
    // The board box changes size when the seam is dragged (the panel width
    // changes, the board takes the rest), when the window resizes, and when the
    // game screen is unhidden at game start. A ResizeObserver on the board
    // catches the first two; a class-mutation observer on the game screen
    // catches the third, which is a display change rather than a resize.
    if (typeof ResizeObserver === 'function') {
        new ResizeObserver(sync).observe(board);
    }
    new MutationObserver(sync).observe(gameScreen, {
        attributes: true,
        attributeFilter: ['class'],
    });
    window.addEventListener('resize', sync);
    // A first pass once the page has laid out; the observers keep it current.
    window.requestAnimationFrame(sync);
    sync();
}
