// What changed, and which build this tab is talking to.
//
// The panel answers two questions, and the second one is the one that saves
// time: a tester who reports a bug we fixed hours ago is almost always on a tab
// they never reloaded. That happened three times in one day. So the build id is
// on the collapsed button, the copyable line is the first thing inside the
// panel, and a server that answers on a different build than this tab loaded
// with says so in an alert.
//
// Nothing here knows an entry. The server parses CHANGELOG.md and validates its
// shape; this renders what it sent, as text nodes - a changelog is arbitrary
// prose from a file, and prose assembled into innerHTML is an injection waiting
// for someone to write a `<` in it.

import { closePopover } from './popovers.js';

const panel = document.getElementById('changelog-panel');
const toggle = document.getElementById('changelog-toggle');
const body = document.getElementById('changelog-body');
const closeBtn = document.getElementById('changelog-close');
const buildLabel = document.getElementById('changelog-build');
const badge = document.getElementById('changelog-badge');
const identityLine = document.getElementById('changelog-line');
const copyBtn = document.getElementById('changelog-copy');
const copiedNote = document.getElementById('changelog-copied');
const staleNote = document.getElementById('changelog-stale');
const releasesDiv = document.getElementById('changelog-releases');

// The build whose entries this tester has already read. Same shape as
// `catan.yoloMode` and `catan.muted`: one key, one browser, never the server's
// business - what one person has read is not a house rule.
const SEEN_STORAGE_KEY = 'catan.changelogSeen';

// A release is identified by both halves: an `unreleased` group keeps its id
// across deploys, so the date is what tells one batch from the next.
const releaseKey = (release) => `${release.build}@${release.when}`;

const KIND_LABELS = { fixed: 'Fixed', new: 'New', known: 'Known issue' };

// When this tab loaded its JavaScript. The pair - server up since X, tab loaded
// at Y - is what makes a stale tab obvious: a tab older than the server's start
// has been through a deploy.
const LOADED_AT = new Date();

// What the server last said about itself, and the first thing it ever said.
// A disagreement between them is the stale tab.
let currentBuild = null;
let loadedBuild = null;
let releases = [];

/**
 * Keep the panel clear of the console.
 *
 * The corner it floats in is above the game console, which carries the build
 * buttons and the dice - the controls a player is using while they read this.
 * Covering them is the mistake two dialogs already had to be fixed for, so the
 * panel is lifted to sit on top of the console rather than over it. In the
 * lobby the console has no box at all and the CSS margin stands.
 *
 * Only `bottom` on a `position: fixed` element is touched, so this can no more
 * reflow the page or move the camera than the popovers can.
 */
function positionPanel() {
    // TEST 6: in game the pill is TOP-anchored (top-left, above the log rail),
    // so pinning `bottom` to clear the console would stretch the fixed element
    // from the top down over the rail. Clear it and let the CSS `bottom: auto`
    // stand. The console-clearing lift is the lobby/bottom-anchored case only.
    if (document.querySelector('#game-screen:not(.hidden)')) {
        panel.style.bottom = '';
        return;
    }
    const console_ = document.getElementById('game-console');
    const box = console_ ? console_.getBoundingClientRect() : null;
    panel.style.bottom = box && box.height > 0
        ? `${Math.round(window.innerHeight - box.top + 8)}px`
        : '';
}

/**
 * Re-place the panel once the browser has laid the page out.
 * `game_started` arrives before the game screen is unhidden, so the console has
 * no box to measure yet and measuring it there would leave the panel where the
 * lobby put it.
 */
function schedulePosition() {
    window.requestAnimationFrame(positionPanel);
}

function storedSeen() {
    try {
        return window.localStorage.getItem(SEEN_STORAGE_KEY);
    } catch (error) {
        // Private mode, or storage disabled. The badge is a nicety; losing it
        // must not cost the panel.
        console.warn('Could not read the changelog marker:', error);
        return null;
    }
}

function rememberSeen(value) {
    try {
        window.localStorage.setItem(SEEN_STORAGE_KEY, value);
    } catch (error) {
        console.warn('Could not save the changelog marker:', error);
    }
}

/**
 * Entries in releases newer than the one this tester acknowledged.
 * Releases arrive newest first and the server has already refused a file that
 * is not in that order, so "newer" is "above the one that matches".
 *
 * @returns {number}
 */
function unreadCount() {
    const seen = storedSeen();
    let count = 0;
    for (const release of releases) {
        if (releaseKey(release) === seen) {
            return count;
        }
        count += release.entries.length;
    }
    return count;
}

function clock(date) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * The one line a tester pastes into a bug report.
 */
function identity() {
    const id = currentBuild?.id || 'unknown';
    const started = currentBuild?.started_at
        ? new Date(currentBuild.started_at * 1000)
        : null;
    const parts = [`Build ${id}`];
    if (started) {
        parts.push(`server up since ${started.toLocaleDateString()} ${clock(started)}`);
    }
    parts.push(`this tab loaded ${clock(LOADED_AT)}`);
    return parts.join(' · ');
}

function renderIdentity() {
    buildLabel.textContent = `build ${currentBuild?.id || '…'}`;
    identityLine.textContent = identity();

    const stale = loadedBuild && currentBuild && loadedBuild !== currentBuild.id;
    staleNote.classList.toggle('hidden', !stale);
    if (stale) {
        staleNote.textContent =
            `This tab was loaded on build ${loadedBuild} and the server is now `
            + `on ${currentBuild.id}. Reload before testing anything else.`;
    }
    panel.classList.toggle('changelog-panel-stale', Boolean(stale));
}

function renderBadge() {
    const unread = releases.length ? unreadCount() : 0;
    badge.textContent = unread > 99 ? '99+' : String(unread);
    badge.classList.toggle('hidden', unread === 0);
    // The badge is decoration; this is the part a screen reader gets.
    toggle.setAttribute(
        'aria-label',
        unread
            ? `What changed - build ${currentBuild?.id || 'unknown'}, ${unread} new entries`
            : `What changed - build ${currentBuild?.id || 'unknown'}`,
    );
}

function entryRow(entry) {
    const row = document.createElement('li');
    row.className = `changelog-entry changelog-entry-${entry.kind}`;

    const kind = document.createElement('span');
    kind.className = 'changelog-kind';
    kind.textContent = KIND_LABELS[entry.kind] || entry.kind;
    row.appendChild(kind);

    const text = document.createElement('span');
    text.className = 'changelog-text';
    text.textContent = entry.text;
    row.appendChild(text);

    if (entry.reported) {
        // Which entries answer something a tester filed is the whole reason
        // they read this: it is the list of what to go and re-test. Inside the
        // sentence rather than beside it - as a column of its own it took a
        // third of the width off every line it was on.
        const tag = document.createElement('span');
        tag.className = 'changelog-reported';
        tag.textContent = 'you reported this';
        text.append(' ', tag);
    }
    return row;
}

function renderReleases(error) {
    releasesDiv.replaceChildren();

    if (error) {
        const note = document.createElement('p');
        note.className = 'changelog-error';
        note.textContent = `The server could not read its changelog: ${error}`;
        releasesDiv.appendChild(note);
        return;
    }
    if (!releases.length) {
        const note = document.createElement('p');
        note.className = 'changelog-empty';
        note.textContent = 'This server is not serving a changelog.';
        releasesDiv.appendChild(note);
        return;
    }

    releases.forEach((release, index) => {
        const section = document.createElement('section');
        section.className = 'changelog-release';

        const heading = document.createElement('h3');
        heading.className = 'changelog-release-head';
        const name = document.createElement('span');
        name.className = 'changelog-release-build';
        name.textContent = release.build;
        const when = document.createElement('span');
        when.className = 'changelog-release-when';
        when.textContent = release.when;
        heading.append(name, when);
        if (index === 0) {
            const latest = document.createElement('span');
            latest.className = 'changelog-latest';
            latest.textContent = 'newest';
            heading.appendChild(latest);
        }
        section.appendChild(heading);

        const list = document.createElement('ul');
        list.className = 'changelog-entries';
        release.entries.forEach(entry => list.appendChild(entryRow(entry)));
        section.appendChild(list);

        releasesDiv.appendChild(section);
    });
}

/**
 * Record the build a payload came from.
 * Called for every board and state payload, not only for the changelog reply:
 * a tab that has been open across a deploy learns it from the next board it is
 * sent, which is sooner than the tester thinks to open this panel.
 *
 * @param {object} build - `{id, source, started_at}` from the server
 */
export function noteBuild(build) {
    if (!build || typeof build.id !== 'string') {
        return;
    }
    currentBuild = build;
    if (loadedBuild === null) {
        loadedBuild = build.id;
    }
    renderIdentity();
    renderBadge();
    schedulePosition();
}

/**
 * Render the server's changelog reply.
 *
 * @param {object} payload - `{build, releases, error}`
 */
export function renderChangelog(payload) {
    if (!payload || typeof payload !== 'object') {
        console.warn('Ignoring malformed changelog payload:', payload);
        return;
    }
    releases = Array.isArray(payload.releases) ? payload.releases : [];
    noteBuild(payload.build);
    renderReleases(payload.error);
    renderBadge();
}

/**
 * Whether the panel is open. `aria-expanded` is the single answer - a local
 * flag beside it is a second one waiting to disagree.
 */
function isChangelogOpen() {
    return toggle.getAttribute('aria-expanded') === 'true';
}

function openPanel() {
    // A rail popover and this panel would otherwise both be up, and on a 1366
    // screen they overlap. The popovers already enforce one-at-a-time among
    // themselves; this joins that rule rather than inventing a second one.
    closePopover();
    positionPanel();
    body.classList.remove('hidden');
    toggle.setAttribute('aria-expanded', 'true');
    // Reading it is the acknowledgement. Marking on close instead would leave
    // the badge up for anyone who reads and then navigates away.
    if (releases.length) {
        rememberSeen(releaseKey(releases[0]));
    }
    renderBadge();
}

function closePanel(restoreFocus = false) {
    body.classList.add('hidden');
    toggle.setAttribute('aria-expanded', 'false');
    copiedNote.textContent = '';
    if (restoreFocus) {
        // Focus is inside the panel that is about to be display:none'd; left
        // there the browser drops it on the body and the next Tab starts again
        // at the top of the page.
        toggle.focus();
    }
}

toggle.addEventListener('click', () => {
    if (isChangelogOpen()) {
        closePanel();
    } else {
        openPanel();
    }
});

closeBtn.addEventListener('click', () => closePanel(true));

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && isChangelogOpen()) {
        closePanel(true);
    }
});

copyBtn.addEventListener('click', async () => {
    const line = identity();
    try {
        await navigator.clipboard.writeText(line);
        copiedNote.textContent = 'Copied. Paste it into the report.';
    } catch (error) {
        // Clipboard access is refused on an insecure origin and in some
        // browsers without a permission. Selecting the line is the fallback,
        // so the tester can still copy it by hand.
        console.warn('Could not copy the build line:', error);
        const range = document.createRange();
        range.selectNodeContents(identityLine);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        copiedNote.textContent = 'Selected - press Ctrl+C to copy.';
    }
});

window.addEventListener('resize', positionPanel);

renderIdentity();
renderBadge();
positionPanel();
