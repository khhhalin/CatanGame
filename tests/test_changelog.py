"""The changelog the testers read, and the build id they quote back.

Two failures are worth catching here, and they are the reason the format is
checked server-side at all:

  - an entry written in a shape the panel cannot render. A loose parser would
    drop it silently, and a fix nobody is told about is a fix that gets
    reported again - which is the exact cost this feature exists to remove;
  - a server that cannot say which build it is. Everything else in the panel is
    reading material; the build id is the half that saves a triage round.

`test_the_real_changelog_parses` is the one that will actually fail one day: it
runs the shipped CHANGELOG.md through the shipped parser, so a typo in an entry
is a red test rather than a blank panel in front of a tester.
"""

import os
import subprocess

import build_info
import changelog
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GOOD = """# Changelog

Prose before the first release is the file's own instructions.

## 6b28989 — 2026-08-04 19:43

- **Fixed** [reported] A hand of commodities can pay what a 7 asks for.
- **New** Cloth, coin and paper can be offered in a trade.
- **Known issue** Island points cannot score on a built-in board.

## aeb9ca1 — 2026-08-04 11:16

- **Fixed** A tie leaves the Longest Road with its holder.
"""


class TestTheFormatTheServerWillServe:
    """What the panel renders, and what it refuses to render."""

    def test_releases_come_back_newest_first_with_their_entries(self):
        releases = changelog.parse(GOOD)

        assert [release['build'] for release in releases] == ['6b28989', 'aeb9ca1']
        assert releases[0]['when'] == '2026-08-04 19:43'
        assert releases[0]['entries'] == [
            {'kind': 'fixed', 'reported': True,
             'text': 'A hand of commodities can pay what a 7 asks for.'},
            {'kind': 'new', 'reported': False,
             'text': 'Cloth, coin and paper can be offered in a trade.'},
            {'kind': 'known', 'reported': False,
             'text': 'Island points cannot score on a built-in board.'},
        ]

    @pytest.mark.parametrize("broken,why", [
        ("## 6b28989 — 2026-08-04 19:43\n\n- **Improved** Something.\n",
         "a kind that is not one of the three"),
        ("## 6b28989 — 2026-08-04 19:43\n\n- Something happened.\n",
         "an entry with no kind at all"),
        ("## 6b28989\n\n- **Fixed** Something.\n",
         "a release heading with no date"),
        ("- **Fixed** Something.\n",
         "an entry before any release"),
        ("## 6b28989 — 2026-08-04 19:43\n",
         "a release with no entries"),
        ("## 6b28989 — 2026-08-04 11:16\n\n- **Fixed** One.\n"
         "\n## aeb9ca1 — 2026-08-04 19:43\n\n- **Fixed** Two.\n",
         "releases that are not newest first"),
        ("## 6b28989 — 2026-08-04 19:43\n\n- **Fixed** One.\n"
         "\n## 6b28989 — 2026-08-04 11:16\n\n- **Fixed** Two.\n",
         "the same build twice"),
        ("## 6b28989 — 2026-08-04 19:43\n\n- **Fixed** One.\n\nA loose line.\n",
         "a line that is neither a heading nor an entry"),
    ])
    def test_a_malformed_file_is_refused_rather_than_half_read(self, broken, why):
        """Every one of these renders as something in a loose reader.

        A dropped entry is worse than a visible error: the tester is told
        nothing and re-files the bug it described.
        """
        with pytest.raises(changelog.ChangelogError):
            changelog.parse("# Changelog\n\n" + broken)

    def test_a_file_that_is_not_the_changelog_is_refused(self):
        with pytest.raises(changelog.ChangelogError):
            changelog.parse("Some other document entirely.\n")

    def test_the_real_changelog_parses(self):
        """The shipped file, through the shipped parser.

        Asserted against the file itself and never against a copy of it: a test
        holding its own sample proves only that the sample is well formed.
        """
        with open(os.path.join(REPO_ROOT, 'CHANGELOG.md'), encoding='utf-8') as handle:
            releases = changelog.parse(handle.read())

        assert releases, "CHANGELOG.md has no releases"
        # Known issues are half the point - a tester who knows the island
        # points cannot score on a built-in board does not file it.
        kinds = {entry['kind'] for release in releases for entry in release['entries']}
        assert kinds == {'fixed', 'new', 'known'}
        # And at least one entry says it answers something a tester filed,
        # which is what tells them what to go and re-test.
        assert any(entry['reported']
                   for release in releases for entry in release['entries'])


class TestTheServerCanNameItsOwnBuild:
    """The half of the panel that saves a round of triage."""

    def test_the_build_id_is_this_checkout(self):
        """In development the tree is the build, so git is the answer."""
        head = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()

        assert build_info.summary()['id'] == head

    def test_an_explicit_build_beats_the_working_tree(self, monkeypatch):
        """What a deployment sets is the truth, whatever git happens to say."""
        monkeypatch.setenv('CATAN_BUILD', 'deployed-42')
        assert build_info.resolve() == ('deployed-42', 'env')

    def test_a_tree_with_no_git_falls_back_to_the_changelog(self, monkeypatch, tmp_path):
        """The container case: no `.git`, no git binary, and it must still answer.

        Falling back rather than raising is deliberate. A server that refuses to
        start because it cannot name itself is a far worse outcome than one that
        names itself coarsely.
        """
        monkeypatch.delenv('CATAN_BUILD', raising=False)
        # An empty PATH is the honest version of "there is no git here": it
        # takes the binary away rather than mocking the function that calls it.
        monkeypatch.setenv('PATH', str(tmp_path))
        monkeypatch.setattr(build_info, 'BUILD_ID_FILES', ())

        build, source = build_info.resolve()
        assert source == 'changelog'
        assert build == changelog.newest_build()

    def test_a_generated_file_answers_when_git_cannot(self, monkeypatch, tmp_path):
        """What a build step writes into an image that ships without `.git`."""
        generated = tmp_path / 'BUILD_ID'
        generated.write_text('a1b2c3d\n')
        monkeypatch.delenv('CATAN_BUILD', raising=False)
        monkeypatch.setenv('PATH', str(tmp_path))
        monkeypatch.setattr(build_info, 'BUILD_ID_FILES', (str(generated),))

        assert build_info.resolve() == ('a1b2c3d', 'file')

    def test_nothing_at_all_is_still_an_answer(self, monkeypatch, tmp_path):
        monkeypatch.delenv('CATAN_BUILD', raising=False)
        monkeypatch.setenv('PATH', str(tmp_path))
        monkeypatch.setattr(build_info, 'BUILD_ID_FILES', ())
        monkeypatch.setattr(changelog, 'SEARCH_PATH', ())
        changelog._CACHE.clear()

        assert build_info.resolve() == ('unknown', 'none')


class TestWhatTheClientIsSent:
    """The panel is drawn from this and holds no entry of its own."""

    def test_the_reply_carries_the_build_and_the_releases(self, socket_app):
        from extensions import socketio

        client = socketio.test_client(socket_app)
        client.get_received()
        client.emit('request_changelog')

        reply = next(m for m in client.get_received() if m['name'] == 'changelog')
        payload = reply['args'][0]

        assert payload['build']['id'] == build_info.summary()['id']
        assert payload['build']['started_at'] > 0
        assert payload['releases'] == changelog.load()
        client.disconnect()

    def test_a_broken_changelog_still_answers_with_the_build(
        self, socket_app, monkeypatch, tmp_path
    ):
        """A typo in the file must not cost a tester the build id.

        The two halves are independent on purpose: which build am I on is the
        question that costs a triage round when it goes unanswered, and it does
        not depend on the file parsing.
        """
        broken = tmp_path / 'CHANGELOG.md'
        broken.write_text("# Changelog\n\n- **Improved** not a kind\n")
        monkeypatch.setattr(changelog, 'SEARCH_PATH', (str(broken),))
        changelog._CACHE.clear()

        from extensions import socketio

        client = socketio.test_client(socket_app)
        client.get_received()
        client.emit('request_changelog')

        payload = next(m for m in client.get_received()
                       if m['name'] == 'changelog')['args'][0]
        assert payload['releases'] == []
        assert 'line 3' in payload['error']
        assert payload['build']['id'] == build_info.summary()['id']
        client.disconnect()
