"""The in-game chat and event log."""

import pytest
from game.event_log import MAX_CHAT_LENGTH, MAX_ENTRIES, EventLog, sanitize_chat


class FakeClock:
    """A clock that only moves when the test says so."""

    def __init__(self, start=1_000_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def tick(self, seconds=1.0):
        self.now += seconds
        return self.now


def make_log(clock=None, max_entries=MAX_ENTRIES):
    return EventLog(clock=clock or FakeClock(), max_entries=max_entries)


class TestEntryShape:
    def test_an_entry_carries_every_field_the_client_renders(self):
        entry = make_log().log('chat', 'hello', player='Alice')
        assert set(entry) == {'id', 'at', 'kind', 'text', 'player', 'details'}

    def test_extra_keywords_land_in_details(self):
        entry = make_log().log('dice', 'Alice rolled 7', player='Alice', total=7)
        assert entry['details'] == {'total': 7}

    def test_details_is_an_empty_dict_when_nothing_is_passed(self):
        assert make_log().log('game', 'The game began')['details'] == {}

    def test_player_is_none_for_a_system_event(self):
        assert make_log().log('game', 'The game began')['player'] is None


class TestIds:
    def test_the_first_entry_is_id_one(self):
        assert make_log().log('game', 'started')['id'] == 1

    def test_ids_increase_by_one(self):
        log = make_log()
        ids = [log.log('chat', str(index))['id'] for index in range(5)]
        assert ids == [1, 2, 3, 4, 5]

    def test_last_id_is_zero_before_anything_is_logged(self):
        assert make_log().last_id == 0

    def test_last_id_tracks_the_newest_entry(self):
        log = make_log()
        log.log('chat', 'a')
        log.log('chat', 'b')
        assert log.last_id == 2

    def test_ids_keep_climbing_after_the_cap_evicts(self):
        """Eviction must not recycle ids, or `since` would replay old entries."""
        log = make_log(max_entries=3)
        for index in range(5):
            log.log('chat', str(index))
        assert log.last_id == 5
        assert [entry['id'] for entry in log.recent()] == [3, 4, 5]


class TestTimestamps:
    def test_the_injected_clock_is_used(self):
        clock = FakeClock(start=1_700_000_000.0)
        assert make_log(clock).log('chat', 'hi')['at'] == 1_700_000_000.0

    def test_each_entry_is_stamped_when_it_is_logged(self):
        clock = FakeClock(start=100.0)
        log = make_log(clock)
        first = log.log('chat', 'first')
        clock.tick(30)
        second = log.log('chat', 'second')
        assert (first['at'], second['at']) == (100.0, 130.0)

    def test_the_timestamp_is_a_float(self):
        assert isinstance(make_log().log('chat', 'hi')['at'], float)


class TestBound:
    def test_the_cap_evicts_the_oldest_entries(self):
        log = make_log(max_entries=3)
        for index in range(6):
            log.log('chat', f'message {index}')
        assert [entry['text'] for entry in log.recent()] == [
            'message 3', 'message 4', 'message 5',
        ]

    def test_the_log_never_grows_past_its_cap(self):
        log = make_log(max_entries=10)
        for index in range(500):
            log.log('dice', str(index))
        assert len(log.recent(limit=1000)) == 10


class TestRecent:
    def test_it_returns_everything_when_the_log_is_short(self):
        log = make_log()
        log.log('chat', 'only one')
        assert len(log.recent()) == 1

    def test_it_returns_the_newest_entries_not_the_oldest(self):
        log = make_log()
        for index in range(10):
            log.log('chat', str(index))
        assert [entry['text'] for entry in log.recent(limit=3)] == ['7', '8', '9']

    def test_it_stays_in_chronological_order(self):
        log = make_log()
        for index in range(10):
            log.log('chat', str(index))
        ids = [entry['id'] for entry in log.recent(limit=4)]
        assert ids == sorted(ids)

    def test_a_limit_of_zero_returns_nothing(self):
        log = make_log()
        log.log('chat', 'hi')
        assert log.recent(limit=0) == []


class TestSince:
    def test_it_returns_only_newer_entries(self):
        log = make_log()
        for index in range(5):
            log.log('chat', str(index))
        assert [entry['text'] for entry in log.since(3)] == ['3', '4']

    def test_zero_returns_the_whole_log(self):
        log = make_log()
        for index in range(3):
            log.log('chat', str(index))
        assert len(log.since(0)) == 3

    def test_a_caught_up_client_gets_nothing(self):
        log = make_log()
        log.log('chat', 'hi')
        assert log.since(log.last_id) == []

    def test_an_id_from_the_future_returns_nothing(self):
        log = make_log()
        log.log('chat', 'hi')
        assert log.since(9999) == []

    def test_it_stays_in_chronological_order(self):
        log = make_log()
        for index in range(6):
            log.log('chat', str(index))
        ids = [entry['id'] for entry in log.since(2)]
        assert ids == sorted(ids)


class TestKinds:
    def test_every_documented_kind_is_accepted(self):
        from game import event_log

        log = make_log()
        for kind in event_log.KINDS:
            assert log.log(kind, 'fine')['kind'] == kind

    def test_an_unknown_kind_is_rejected(self):
        """Documented behaviour: raise, because a bad kind is a caller bug."""
        with pytest.raises(ValueError):
            make_log().log('shenanigans', 'nope')

    def test_a_rejected_kind_logs_nothing(self):
        log = make_log()
        with pytest.raises(ValueError):
            log.log('shenanigans', 'nope')
        assert log.recent() == []
        assert log.last_id == 0


class TestSanitizeChat:
    def test_it_trims_surrounding_whitespace(self):
        assert sanitize_chat('  hello  ') == 'hello'

    def test_it_collapses_runs_of_whitespace(self):
        assert sanitize_chat('trade   me    wood') == 'trade me wood'

    def test_it_collapses_newlines_that_would_take_over_the_panel(self):
        assert sanitize_chat('one\n\n\ntwo') == 'one two'

    def test_an_empty_message_is_rejected(self):
        with pytest.raises(ValueError):
            sanitize_chat('')

    def test_a_whitespace_only_message_is_rejected(self):
        with pytest.raises(ValueError):
            sanitize_chat('   \n\t  ')

    def test_a_message_at_the_cap_is_accepted(self):
        text = 'a' * MAX_CHAT_LENGTH
        assert sanitize_chat(text) == text

    def test_a_message_over_the_cap_is_rejected(self):
        with pytest.raises(ValueError):
            sanitize_chat('a' * (MAX_CHAT_LENGTH + 1))

    def test_a_non_string_is_rejected(self):
        with pytest.raises(ValueError):
            sanitize_chat({'text': 'hi'})

    def test_markup_is_left_alone_for_the_renderer_to_escape(self):
        """Escaping here would double-escape whatever the client does."""
        assert sanitize_chat('<script>alert(1)</script>') == '<script>alert(1)</script>'
