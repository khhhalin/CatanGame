"""CHANGELOG.md, parsed into the shape the panel renders.

The file at the repo root is the single source of truth: nothing in the client
holds a copy of an entry, so a line is written once and every tester sees it.

The format is deliberately narrow. A loose Markdown reader in JavaScript would
turn a typo into a panel that renders half a release and says nothing about the
other half — which is exactly the class of silent failure this feature exists to
end. So the shape is small enough to state in full, and it is checked here,
where a violation is a server-side error with a line number on it:

    # Changelog                         <- one H1, first non-blank line
    ...any number of prose lines...     <- the intro, ignored by the panel

    ## 6b28989 — 2026-08-04 19:43       <- build id, an em dash, when it went out

    - **Fixed** [reported] One line.    <- kind, optional marker, one line of text
    - **New** One line.
    - **Known issue** One line.

Rules, all enforced:

  - exactly three kinds — Fixed, New, Known issue;
  - `[reported]` marks an entry that answers something a tester filed. It is
    what tells them what to go and re-test, so it is part of the format rather
    than a turn of phrase inside the text;
  - an entry must belong to a release, and a release must have entries;
  - build ids are unique and releases run newest first, because the panel reads
    "everything above the one I acknowledged" as unread and would otherwise
    badge the wrong entries;
  - nothing else. A line that is neither blank, a release heading nor an entry
    is a mistake, and a silently ignored mistake is an entry a tester never
    reads.
"""

import os
import re

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SERVER_DIR)

# Both, in order: only `server/` is copied into the container image, so a
# deployment that ships the changelog puts it beside the code. CATAN_CHANGELOG
# overrides for anything neither location suits.
SEARCH_PATH = (
    os.environ.get('CATAN_CHANGELOG'),
    os.path.join(REPO_ROOT, 'CHANGELOG.md'),
    os.path.join(SERVER_DIR, 'CHANGELOG.md'),
)

KINDS = {'Fixed': 'fixed', 'New': 'new', 'Known issue': 'known'}

# `unreleased` is the top group before it goes out. It is a legal id so the file
# can be written before the deploy that ships it, but `newest_build` refuses to
# report it as a build — naming a running server "unreleased" would tell a
# tester nothing.
UNRELEASED = 'unreleased'

TITLE_RE = re.compile(r'^# \S')
# A release is named by a version (`v1.4.0` — the deployed identity a tester
# quotes and the only thing a container with no `.git` can show), a git
# short-sha (a dev build, where the tree *is* the build), or `unreleased`
# before it ships. `VERSION` at the repo root is the source of truth for the
# version, and `test_the_version_file_names_the_current_release` refuses to let
# it drift from the newest heading here.
RELEASE_RE = re.compile(
    r'^## (?P<build>v\d+\.\d+\.\d+|[0-9a-f]{7,40}|' + UNRELEASED + r') — '
    r'(?P<when>\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?)$'
)
ENTRY_RE = re.compile(
    r'^- \*\*(?P<kind>Fixed|New|Known issue)\*\*(?P<reported> \[reported\])? (?P<text>\S.*)$'
)

# Long enough for a sentence that says what changed, short enough that it stays
# one line in a floating panel.
MAX_TEXT = 300


class ChangelogError(Exception):
    """The file is not in the format above. Names the line that is wrong."""


def _fail(number, line, why):
    raise ChangelogError(f"CHANGELOG.md line {number}: {why}: {line!r}")


def parse(text: str) -> list:
    """Releases, newest first, or raise ChangelogError.

    Returns `[{'build', 'when', 'entries': [{'kind', 'reported', 'text'}]}]`.
    """
    releases: list[dict] = []
    seen_builds: set[str] = set()
    last_when = None
    in_intro = True
    titled = False

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip():
            continue

        if not titled:
            # A cheap check that this is the changelog at all, rather than some
            # other Markdown file a path landed on.
            if not TITLE_RE.match(line):
                _fail(number, line, "the file must open with an '# ' title")
            titled = True
            continue

        if in_intro and not line.startswith('## ') and not line.startswith('- '):
            # Prose before the first release: the file's own account of how to
            # add to it. Read by whoever edits it, never by the panel.
            continue

        if line.startswith('## '):
            in_intro = False
            match = RELEASE_RE.match(line)
            if not match:
                _fail(number, line,
                      "a release heading must read '## <build id> — <YYYY-MM-DD[ HH:MM]>'")
            build = match.group('build')
            when = match.group('when')
            if build in seen_builds:
                _fail(number, line, f"build {build!r} already has a release")
            if last_when is not None and when > last_when:
                _fail(number, line,
                      f"releases run newest first, and this one is older than {last_when}")
            seen_builds.add(build)
            last_when = when
            releases.append({'build': build, 'when': when, 'entries': []})
            continue

        if line.startswith('- '):
            in_intro = False
            match = ENTRY_RE.match(line)
            if not match:
                _fail(number, line,
                      "an entry must read '- **Fixed|New|Known issue** [reported] <text>'")
            if not releases:
                _fail(number, line, "an entry before any release heading")
            entry_text = match.group('text').strip()
            if len(entry_text) > MAX_TEXT:
                _fail(number, line, f"an entry is longer than {MAX_TEXT} characters")
            releases[-1]['entries'].append({
                'kind': KINDS[match.group('kind')],
                'reported': match.group('reported') is not None,
                'text': entry_text,
            })
            continue

        _fail(number, line, "neither a release heading nor an entry")

    if not releases:
        raise ChangelogError("CHANGELOG.md has no releases in it")

    for release in releases:
        if not release['entries']:
            raise ChangelogError(
                f"CHANGELOG.md: release {release['build']} has no entries"
            )
    return releases


def path() -> str | None:
    """The first changelog on the search path that exists."""
    for candidate in SEARCH_PATH:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


# Keyed by (path, mtime) so an edited changelog is picked up without a restart —
# the whole point of the file is that a tester reads it, and making them wait
# for a deploy to read about a deploy is absurd. Re-reading it on every request
# would put a disk read on a socket event instead.
_CACHE: dict[tuple, list] = {}


def load() -> list:
    """The parsed releases, newest first. Raises ChangelogError on a bad file.

    An empty list means there is no changelog to serve at all — which happens in
    a container image that did not ship the file, and is not an error.
    """
    found = path()
    if found is None:
        return []
    key = (found, os.path.getmtime(found))
    if key not in _CACHE:
        with open(found, encoding='utf-8') as handle:
            _CACHE.clear()
            _CACHE[key] = parse(handle.read())
    return _CACHE[key]


def newest_build() -> str | None:
    """The newest released build, for `build_info`'s last fallback.

    Skips an `unreleased` group at the top: it is a placeholder for work that
    has not gone out, and answering "which build is this server" with the word
    "unreleased" tells a tester nothing they can quote.
    """
    for release in load():
        if release['build'] != UNRELEASED:
            return release['build']
    return None
