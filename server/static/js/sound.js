// The game's small noises: a cue when a piece goes down, and the one that says
// a turn has become yours.
//
// Synthesised with the Web Audio API rather than shipped as files. Six pieces
// need six cues, and six samples would be six binaries in the repo, six
// licences to answer for, and - because they would all be recorded the same way
// - six sounds a player still could not tell apart. An envelope over one or two
// oscillators is a few lines each and each one can be given a shape of its own.
//
// Everything here is deliberately quiet and under a quarter of a second. A
// sound on every placement is a sound several times a turn, and the alternative
// to short and quiet is muted forever.

// Personal preference, this browser only, exactly like `catan.yoloMode`: it
// changes nothing anyone else can see, so it never goes near the server or the
// rules registry.
import { muteToggle, turnSound } from './dom.js';

const MUTE_STORAGE_KEY = 'catan.muted';

// Peak gain of a cue. Two of these can land in the same payload - a road and a
// settlement in one setup step - so the ceiling has to leave room for both.
const PEAK = 0.07;

/**
 * How each piece sounds.
 *
 * `tones` are played in sequence: {freq, at, dur, type, glide}. `glide` bends
 * the pitch to another frequency over the tone's life, which is what makes a
 * ship read as a ship and not as a shorter road.
 */
const CUES = {
    // A tap: one short low block, the least intrusive of the six because roads
    // are the piece that goes down most often.
    road: { tones: [{ freq: 196, dur: 0.09, type: 'triangle' }] },
    // Two rising notes - something was founded.
    settlement: {
        tones: [
            { freq: 440, dur: 0.09, type: 'sine' },
            { freq: 659, at: 0.08, dur: 0.12, type: 'sine' }
        ]
    },
    // The settlement's two notes with a third on top: a city is an upgrade of
    // one, and it sounds like one.
    city: {
        tones: [
            { freq: 440, dur: 0.09, type: 'sine' },
            { freq: 659, at: 0.08, dur: 0.09, type: 'sine' },
            { freq: 880, at: 0.16, dur: 0.14, type: 'sine' }
        ]
    },
    // A rising whistle over water.
    ship: {
        tones: [{ freq: 330, dur: 0.2, type: 'sine', glide: 520 }]
    },
    // Metal: a sawtooth with a hard edge, falling.
    knight: {
        tones: [{ freq: 320, dur: 0.16, type: 'sawtooth', glide: 180 }]
    },
    // Stone: low, blunt, gone immediately.
    city_wall: {
        tones: [{ freq: 110, dur: 0.14, type: 'square', glide: 70 }]
    }
};

// The pieces this watches for, in the order a payload is read. Each names how
// to count how many of them are on the board; a count that has gone up is a
// piece that has just been placed, whoever placed it.
const WATCHED = [
    { kind: 'city', count: (board) => sumOver(board.players, p => (p.cities || []).length) },
    {
        kind: 'settlement',
        count: (board) => sumOver(board.players, p => (p.settlements || []).length)
    },
    { kind: 'road', count: (board) => sumOver(board.players, p => (p.roads || []).length) },
    { kind: 'ship', count: (board) => sumOver(board.players, p => (p.ships || []).length) },
    {
        kind: 'knight',
        count: (board) => sumOver(
            Object.values(board.cities_knights?.knights || {}), list => list.length
        )
    },
    {
        kind: 'city_wall',
        count: (board) => sumOver(
            Object.values(board.cities_knights?.city_walls || {}), walls => walls
        )
    }
];

/**
 * @param {Array} items
 * @param {Function} of - What to add up for each item
 * @returns {number}
 */
function sumOver(items, of) {
    return (items || []).reduce((total, item) => total + (of(item) || 0), 0);
}

/**
 * Whether the player has asked for less of everything.
 * Used only to pick the *starting* setting: a stored preference always wins.
 */
function prefersReducedMotion() {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
}

/**
 * The stored preference, or - with nothing stored - reduced motion as a hint.
 *
 * A browser with storage denied gets the quiet half of that, the way YOLO mode
 * gets the safe half of its own default.
 *
 * @returns {boolean}
 */
function readMutePreference() {
    try {
        const stored = window.localStorage.getItem(MUTE_STORAGE_KEY);
        if (stored === '1' || stored === '0') {
            return stored === '1';
        }
    } catch {
        return true;
    }
    return prefersReducedMotion();
}

let muted = readMutePreference();

/**
 * Whether sound is currently off.
 */
export function isMuted() {
    return muted;
}

/**
 * Turn sound on or off, and remember it for this browser.
 *
 * @param {boolean} value - True to silence everything
 */
export function setMuted(value) {
    muted = Boolean(value);
    try {
        window.localStorage.setItem(MUTE_STORAGE_KEY, muted ? '1' : '0');
    } catch {
        // Private mode or storage disabled: the setting still applies to this
        // page, it just will not outlive it.
    }
}

// One context for the page, built on the first sound rather than at load: a
// context created before the player has interacted starts suspended, and some
// browsers count that against the page.
let audioContext = null;

/**
 * The audio context, or null where the browser has none.
 */
function context() {
    if (audioContext) {
        return audioContext;
    }
    // Read off `window` at call time rather than at import, so a test can
    // stand in front of it.
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) {
        return null;
    }
    try {
        audioContext = new Ctor();
    } catch {
        return null;
    }
    return audioContext;
}

/**
 * Play one named cue, or nothing at all when sound is off.
 *
 * Silent by policy before the player's first interaction - a browser suspends
 * the context until then. That is left alone deliberately: resuming it behind
 * their back is exactly what the policy exists to stop.
 *
 * @param {string} name - Key into CUES
 */
export function playCue(name) {
    const cue = CUES[name];
    if (muted || !cue) {
        return;
    }
    const ctx = context();
    if (!ctx) {
        return;
    }

    const now = ctx.currentTime;
    cue.tones.forEach(tone => {
        const start = now + (tone.at || 0);
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();

        oscillator.type = tone.type || 'sine';
        oscillator.frequency.setValueAtTime(tone.freq, start);
        if (tone.glide) {
            oscillator.frequency.exponentialRampToValueAtTime(tone.glide, start + tone.dur);
        }

        // A plain on/off would click. Ramping both ends is what makes a 90ms
        // blip sound like a note rather than a fault.
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(PEAK, start + 0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + tone.dur);

        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.start(start);
        oscillator.stop(start + tone.dur + 0.02);
    });
}

/**
 * The one sound this game already had: your turn has begun.
 *
 * A sample rather than a cue, and left that way - it is the sound players know.
 * It goes through here so that the mute toggle silences everything, which was
 * the whole complaint: a sound on every placement with no way to turn it off.
 */
export function playTurnSound() {
    if (muted) {
        return;
    }
    turnSound.play().catch(error => console.log('Could not play sound:', error));
}

// How many of each piece were on the board when it was last looked at. Null
// means nothing has been seen yet - the first payload of a game is the state to
// start from, not six placements to announce.
let placedCounts = null;

/**
 * Sound whatever this payload says has just been placed.
 *
 * Driven off the board payload rather than off the click, so a piece somebody
 * else put down is heard too - which is the point: the tester wanted to know
 * that something happened, and most of what happens is not theirs.
 *
 * @param {object} board - The board payload that has just arrived
 */
export function notePlacements(board) {
    if (!board || !board.players) {
        return;
    }

    const counts = {};
    WATCHED.forEach(piece => {
        counts[piece.kind] = piece.count(board);
    });

    if (placedCounts === null) {
        placedCounts = counts;
        return;
    }

    // At most one cue per payload. A city upgrade is a city built and a
    // settlement returned in the same breath, and a turn that ends with three
    // roads down would otherwise be three overlapping blips.
    const placed = WATCHED.find(piece => counts[piece.kind] > placedCounts[piece.kind]);
    placedCounts = counts;
    if (placed) {
        playCue(placed.kind);
    }
}

/**
 * Forget what was on the board. Called when a game ends or a new one starts, so
 * the first payload of the next one is a baseline and not a fanfare.
 */
export function forgetPlacements() {
    placedCounts = null;
}

// The toggle in the console, wired here so everything about sound is in one
// file - the same shape as the YOLO toggle, which placement.js owns.
if (muteToggle) {
    muteToggle.checked = muted;
    muteToggle.addEventListener('change', () => {
        setMuted(muteToggle.checked);
    });
}
