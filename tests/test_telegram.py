"""The adapter holds no state and makes no decisions, so what is testable is the
translation: does a tap become the right approval, and does a malformed one
become nothing at all."""

import pytest

from c2c.telegram import Telegram, format_request, keyboard, parse_callback

STATE = {
    "pending_action": "challenge_rejection",
    "verdict": {"compensation_units": 420, "duty_of_care_units": 0,
                "downgrade_reimbursement_units": 0, "cause_class": "carrier_controlled",
                "policy_citations": ["S3.6", "S9.1(a)"],
                "rationale": "The carrier cited weather; its own log records crew out of hours."},
}


def test_message_carries_what_a_person_needs_to_decide():
    msg = format_request("R12", STATE)
    assert "R12" in msg
    assert "Challenge the carrier's rejection" in msg
    assert "420 units" in msg
    assert "S3.6" in msg
    assert "crew out of hours" in msg


def test_message_is_stamped_synthetic():
    assert "SYNTHETIC DEMO" in format_request("R12", STATE)


def test_message_omits_amounts_that_are_zero():
    msg = format_request("R12", STATE)
    assert "Duty of care" not in msg and "Downgrade" not in msg


def test_keyboard_routes_to_the_right_promise():
    kb = keyboard("R12", "challenge_rejection")
    data = [b["callback_data"] for b in kb["inline_keyboard"][0]]
    assert data == ["ok|R12|challenge_approval", "no|R12|challenge_approval"]
    assert keyboard("R15", "escalate")["inline_keyboard"][0][0]["callback_data"] \
        == "ok|R15|escalation_approval"


def test_callback_parses_both_answers():
    assert parse_callback("ok|R12|approval") == {
        "case_id": "R12", "approved": True, "promise": "approval"}
    assert parse_callback("no|R12|approval")["approved"] is False


@pytest.mark.parametrize("bad", ["", "ok|R12", "maybe|R12|approval", "ok||approval",
                                 "ok|R12|", "ok|R12|approval|extra", None])
def test_a_malformed_callback_approves_nothing(bad):
    """A garbled callback must never be guessed at into an approval."""
    assert parse_callback(bad) is None


class StubHTTP:
    def __init__(self, updates): self.updates = updates; self.posts = []
    def get(self, url, params=None):
        class R:
            def json(_): return {"result": self.updates}
        return R()
    def post(self, url, json=None):
        self.posts.append((url, json))
        class R:
            def json(_): return {"accepted": True}
        return R()


def test_a_tap_resolves_the_right_promise_on_the_right_case():
    http = StubHTTP([{"update_id": 1,
                      "callback_query": {"id": "c1", "data": "ok|R12|challenge_approval"}}])
    handled = Telegram(token="t", chat_id="1", api="http://cp", client=http).poll_once()
    assert len(handled) == 1
    approve_calls = [p for p in http.posts if "/approve" in p[0]]
    assert approve_calls[0][0] == "http://cp/c2c/cases/R12/approve"
    assert approve_calls[0][1]["approved"] is True
    assert approve_calls[0][1]["promise"] == "challenge_approval"


def test_a_malformed_tap_reaches_the_control_plane_not_at_all():
    http = StubHTTP([{"update_id": 1, "callback_query": {"id": "c1", "data": "garbage"}}])
    assert Telegram(token="t", chat_id="1", api="http://cp", client=http).poll_once() == []
    assert not [p for p in http.posts if "/approve" in p[0]]


def test_updates_are_not_replayed():
    http = StubHTTP([{"update_id": 7, "callback_query": {"id": "c1", "data": "ok|R12|approval"}}])
    tg = Telegram(token="t", chat_id="1", api="http://cp", client=http)
    tg.poll_once()
    assert tg.offset == 8
