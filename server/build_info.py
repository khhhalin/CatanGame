"""Which build this process is running, and since when.

Three bugs were reported twice in one day — city walls, discarding commodities,
the progress card deck — and all three had been fixed hours before the report.
Every one of them was a tab left open on an older build. Triage cost a round
trip each time, and none of that time was spent on the game.

So the server knows its own build and says so in every payload the changelog
panel reads. `resolve()` runs once, at import, because the answer cannot change
while the process lives — and a long-lived process on an old build is exactly
the failure this exists to make visible.

Where the answer comes from, in order:

  1. `CATAN_BUILD` — an explicit answer beats every guess. This is what a
     deployment pipeline sets.
  2. `git rev-parse --short HEAD` — true in development, where the tree *is*
     the build.
  3. `BUILD_ID`, a generated file beside the code. A container image has no
     `.git`, so a build step can write the sha here instead.
  4. The newest release in CHANGELOG.md. Coarse — it names the last deploy
     rather than this commit — but it is never wrong about which release the
     player is looking at, and it needs nothing at build time.

Falls through to "unknown" rather than raising: a server that will not start
because it cannot name itself is a far worse outcome than an unnamed server.
"""

import logging
import os
import subprocess
import time

import changelog

logger = logging.getLogger(__name__)

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SERVER_DIR)

# Written by a build step for images that ship without `.git`. Looked for both
# beside the code and at the repo root, because only `server/` is copied into
# the container.
BUILD_ID_FILES = (
    os.path.join(SERVER_DIR, 'BUILD_ID'),
    os.path.join(REPO_ROOT, 'BUILD_ID'),
)

UNKNOWN = 'unknown'

# When this process started, as a Unix timestamp. Read once: it is the process's
# own age, and the panel shows it so "the server has been up since Tuesday" is
# visible rather than inferred.
STARTED_AT = time.time()


def _from_env():
    value = (os.environ.get('CATAN_BUILD') or '').strip()
    return (value, 'env') if value else None


def _from_git():
    """The working tree's HEAD, or None where git cannot answer.

    Every failure mode is None, not an exception: no git binary (a slim image),
    no repository (a copied tree), and a hung git (a network filesystem) all
    mean the same thing here — ask the next source.
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=2, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return (value, 'git') if value else None


def _from_file():
    for path in BUILD_ID_FILES:
        try:
            with open(path) as handle:
                value = handle.read().strip()
        except OSError:
            continue
        if value:
            return value, 'file'
    return None


def _from_changelog():
    try:
        value = changelog.newest_build()
    except changelog.ChangelogError:
        # The changelog handler reports this to the client properly. Here it is
        # merely one exhausted source among four.
        return None
    return (value, 'changelog') if value else None


def resolve():
    """(build id, where it came from). Never raises, never returns empty."""
    for source in (_from_env, _from_git, _from_file, _from_changelog):
        answer = source()
        if answer:
            return answer
    return UNKNOWN, 'none'


_BUILD_ID, _BUILD_SOURCE = resolve()
logger.info("serving build %s (from %s)", _BUILD_ID, _BUILD_SOURCE)


def summary() -> dict:
    """What every payload carries so a tester can name the build they are on."""
    return {
        'id': _BUILD_ID,
        'source': _BUILD_SOURCE,
        'started_at': STARTED_AT,
    }
