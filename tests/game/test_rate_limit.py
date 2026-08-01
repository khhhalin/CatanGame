"""Flood protection: token buckets, abuse escalation, payload caps."""

from game import rate_limit
from game.rate_limit import AbuseTracker, Limit, RateLimiter, payload_too_large


class FakeClock:
    """A clock the test drives by hand, standing in for `time.monotonic`."""

    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_limiter(capacity=3, refill_per_second=1.0, **kwargs):
    clock = FakeClock()
    limiter = RateLimiter(Limit(capacity, refill_per_second), clock=clock, **kwargs)
    return limiter, clock


class TestBurstAndRefusal:
    def test_a_burst_up_to_capacity_is_allowed(self):
        limiter, _ = make_limiter(capacity=3)
        assert [limiter.allow('sid-1') for _ in range(3)] == [True, True, True]

    def test_the_request_after_capacity_is_refused(self):
        limiter, _ = make_limiter(capacity=3)
        for _ in range(3):
            limiter.allow('sid-1')
        assert limiter.allow('sid-1') is False

    def test_a_refusal_costs_nothing(self):
        """Asking during the cooldown must not push recovery further away."""
        limiter, clock = make_limiter(capacity=1, refill_per_second=1.0)
        limiter.allow('sid-1')
        for _ in range(5):
            assert limiter.allow('sid-1') is False
        clock.advance(1.0)
        assert limiter.allow('sid-1') is True

    def test_cost_lets_one_call_spend_several_tokens(self):
        limiter, _ = make_limiter(capacity=3)
        assert limiter.allow('sid-1', cost=3) is True
        assert limiter.allow('sid-1') is False

    def test_a_cost_larger_than_the_bucket_is_refused_outright(self):
        limiter, _ = make_limiter(capacity=3)
        assert limiter.allow('sid-1', cost=4) is False
        assert limiter.tokens_left('sid-1') == 3


class TestRefill:
    def test_tokens_come_back_as_the_clock_advances(self):
        limiter, clock = make_limiter(capacity=3, refill_per_second=1.0)
        for _ in range(3):
            limiter.allow('sid-1')
        clock.advance(2.0)
        assert [limiter.allow('sid-1') for _ in range(3)] == [True, True, False]

    def test_refill_is_fractional_not_windowed(self):
        """Half a refill period is worth half a token, not zero and not one."""
        limiter, clock = make_limiter(capacity=4, refill_per_second=1.0)
        for _ in range(4):
            limiter.allow('sid-1')
        clock.advance(0.5)
        assert limiter.tokens_left('sid-1') == 0.5
        assert limiter.allow('sid-1') is False
        clock.advance(0.5)
        assert limiter.allow('sid-1') is True

    def test_an_idle_bucket_never_exceeds_capacity(self):
        """Otherwise an hour of silence buys an hour's worth of burst."""
        limiter, clock = make_limiter(capacity=3, refill_per_second=1.0)
        limiter.allow('sid-1')
        clock.advance(3600.0)
        assert limiter.tokens_left('sid-1') == 3

    def test_a_clock_that_steps_backwards_grants_nothing(self):
        """Why the clock is monotonic: a wall clock can jump back, and a
        backwards delta read as elapsed time is free requests."""
        limiter, clock = make_limiter(capacity=2, refill_per_second=1.0)
        limiter.allow('sid-1')
        limiter.allow('sid-1')
        clock.advance(-3600.0)
        assert limiter.allow('sid-1') is False
        assert limiter.tokens_left('sid-1') == 0


class TestRetryAfter:
    def test_it_is_zero_while_the_client_is_within_its_budget(self):
        limiter, _ = make_limiter(capacity=3)
        limiter.allow('sid-1')
        assert limiter.retry_after('sid-1') == 0.0

    def test_it_is_positive_once_the_client_is_refused(self):
        limiter, _ = make_limiter(capacity=1, refill_per_second=2.0)
        limiter.allow('sid-1')
        assert limiter.allow('sid-1') is False
        assert limiter.retry_after('sid-1') == 0.5

    def test_it_shrinks_as_the_clock_advances(self):
        limiter, clock = make_limiter(capacity=1, refill_per_second=1.0)
        limiter.allow('sid-1')
        clock.advance(0.25)
        assert limiter.retry_after('sid-1') == 0.75

    def test_an_unknown_key_never_has_to_wait(self):
        limiter, _ = make_limiter()
        assert limiter.retry_after('never-seen') == 0.0


class TestKeyIsolation:
    def test_one_key_exhausting_its_bucket_does_not_touch_another(self):
        limiter, _ = make_limiter(capacity=2)
        limiter.allow('sid-1')
        limiter.allow('sid-1')
        assert limiter.allow('sid-1') is False
        assert limiter.allow('sid-2') is True

    def test_a_socket_and_a_player_budget_can_share_one_limiter(self):
        """Part II wants per-socket and per-player limits; the key carries the
        distinction, so one instance enforces both."""
        limiter, _ = make_limiter(capacity=1)
        assert limiter.allow('sid:abc') is True
        assert limiter.allow('player:Alice') is True
        assert limiter.allow('sid:abc') is False


class TestEventLimits:
    def test_joining_is_tighter_than_an_ordinary_game_action(self):
        assert rate_limit.limit_for('join').capacity < rate_limit.DEFAULT_LIMIT.capacity
        join_rate = rate_limit.limit_for('join').refill_per_second
        assert join_rate < rate_limit.DEFAULT_LIMIT.refill_per_second

    def test_resync_events_are_cheaper_for_the_client_than_for_us(self):
        for event in ('refresh_board', 'request_state', 'request_log'):
            limit = rate_limit.limit_for(event)
            assert limit.refill_per_second < rate_limit.DEFAULT_LIMIT.refill_per_second

    def test_chat_allows_a_conversation_but_not_a_flood(self):
        chat = rate_limit.limit_for('chat_message')
        assert 20 <= chat.refill_per_second * 60 <= 60, "roughly 20-60 messages a minute"

    def test_an_ordinary_game_action_is_unlisted_and_gets_the_default(self):
        assert rate_limit.limit_for('place_settlement') == rate_limit.DEFAULT_LIMIT

    def test_an_event_nobody_has_written_yet_still_has_a_finite_limit(self):
        limit = rate_limit.limit_for('an_event_from_the_future')
        assert limit == rate_limit.DEFAULT_LIMIT
        assert limit.capacity < float('inf')

    def test_the_per_call_limit_overrides_the_constructor_default(self):
        limiter, _ = make_limiter(capacity=100)
        tight = rate_limit.limit_for('start_game')
        for _ in range(int(tight.capacity)):
            assert limiter.allow('sid-1:start_game', limit=tight) is True
        assert limiter.allow('sid-1:start_game', limit=tight) is False

    def test_two_events_on_one_socket_have_independent_budgets(self):
        limiter, _ = make_limiter()
        join = rate_limit.limit_for('join')
        for _ in range(int(join.capacity)):
            limiter.allow('sid-1:join', limit=join)
        assert limiter.allow('sid-1:join', limit=join) is False
        assert limiter.allow('sid-1:roll_dice') is True


class TestForgetting:
    def test_forget_clears_a_key_so_a_new_socket_starts_fresh(self):
        limiter, _ = make_limiter(capacity=1)
        limiter.allow('sid-1')
        assert limiter.allow('sid-1') is False
        limiter.forget('sid-1')
        assert limiter.allow('sid-1') is True

    def test_forgetting_an_unknown_key_is_harmless(self):
        limiter, _ = make_limiter()
        limiter.forget('never-seen')

    def test_pruning_reclaims_keys_nobody_has_used(self):
        limiter, clock = make_limiter(idle_ttl=60.0)
        limiter.allow('sid-1')
        clock.advance(61.0)
        assert limiter.prune() == 1

    def test_pruning_keeps_keys_that_are_still_active(self):
        limiter, clock = make_limiter(idle_ttl=60.0)
        limiter.allow('sid-1')
        clock.advance(61.0)
        limiter.allow('sid-2')
        assert limiter.prune() == 1
        assert limiter.tokens_left('sid-2') < limiter.tokens_left('sid-1')

    def test_the_table_sweeps_itself_without_an_explicit_prune(self):
        """A long-running server must not accumulate a bucket per socket."""
        limiter, clock = make_limiter(idle_ttl=60.0, sweep_every=4)
        limiter.allow('gone-1')
        limiter.allow('gone-2')
        clock.advance(61.0)
        for _ in range(4):
            limiter.allow('still-here')
        assert limiter.tokens_left('gone-1') == limiter._limit.capacity
        assert len(limiter._buckets) == 2, "the two idle keys were swept on access"


class TestAbuseTracker:
    def test_the_first_violation_does_not_warrant_a_disconnect(self):
        tracker = AbuseTracker(threshold=3, clock=FakeClock())
        assert tracker.record_violation('sid-1') == 1
        assert tracker.should_disconnect('sid-1') is False

    def test_repeated_violations_reach_the_threshold(self):
        tracker = AbuseTracker(threshold=3, clock=FakeClock())
        for _ in range(3):
            tracker.record_violation('sid-1')
        assert tracker.should_disconnect('sid-1') is True

    def test_violations_are_counted_per_key(self):
        tracker = AbuseTracker(threshold=2, clock=FakeClock())
        tracker.record_violation('sid-1')
        tracker.record_violation('sid-1')
        assert tracker.should_disconnect('sid-2') is False

    def test_old_violations_decay_so_a_bad_minute_is_not_permanent(self):
        clock = FakeClock()
        tracker = AbuseTracker(threshold=3, violation_ttl=60.0, clock=clock)
        tracker.record_violation('sid-1')
        tracker.record_violation('sid-1')
        clock.advance(61.0)
        assert tracker.record_violation('sid-1') == 1
        assert tracker.should_disconnect('sid-1') is False

    def test_a_sustained_attack_still_trips_despite_the_decay(self):
        clock = FakeClock()
        tracker = AbuseTracker(threshold=5, violation_ttl=60.0, clock=clock)
        for _ in range(5):
            clock.advance(1.0)
            tracker.record_violation('sid-1')
        assert tracker.should_disconnect('sid-1') is True

    def test_forget_clears_the_history_on_disconnect(self):
        tracker = AbuseTracker(threshold=2, clock=FakeClock())
        tracker.record_violation('sid-1')
        tracker.record_violation('sid-1')
        tracker.forget('sid-1')
        assert tracker.violations('sid-1') == 0

    def test_pruning_drops_keys_whose_violations_all_expired(self):
        clock = FakeClock()
        tracker = AbuseTracker(violation_ttl=60.0, clock=clock)
        tracker.record_violation('sid-1')
        clock.advance(61.0)
        assert tracker.prune() == 1
        assert tracker.violations('sid-1') == 0

    def test_a_refused_client_escalates_from_throttled_to_disconnected(self):
        """The two pieces together: keep asking after a refusal and you are cut
        off rather than throttled forever."""
        limiter, _ = make_limiter(capacity=1, refill_per_second=0.1)
        tracker = AbuseTracker(threshold=3, clock=FakeClock())
        limiter.allow('sid-1')
        for _ in range(3):
            if not limiter.allow('sid-1'):
                tracker.record_violation('sid-1')
        assert tracker.should_disconnect('sid-1') is True


class TestPayloadSizeGuard:
    def test_an_ordinary_payload_passes(self):
        assert payload_too_large({'vertex': 14}, 1024) is False

    def test_an_oversized_string_is_rejected(self):
        assert payload_too_large({'text': 'x' * 5000}, 1024) is True

    def test_a_long_list_is_rejected(self):
        assert payload_too_large({'ids': list(range(5000))}, 1024) is True

    def test_deep_nesting_is_rejected_without_recursing_through_it(self):
        payload = {}
        cursor = payload
        for _ in range(50):
            cursor['next'] = {}
            cursor = cursor['next']
        assert payload_too_large(payload, 1024) is True

    def test_the_default_cap_is_finite_and_generous(self):
        assert payload_too_large({'text': 'hello'}) is False
        assert payload_too_large({'text': 'x' * (rate_limit.MAX_PAYLOAD_BYTES + 1)}) is True

    def test_size_is_measured_in_bytes_not_characters(self):
        """Multi-byte text must not slip past a byte cap by being short."""
        assert payload_too_large({'t': 'ą' * 40}, 50) is True
