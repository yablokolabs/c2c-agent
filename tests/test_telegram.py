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


def test_the_demo_shows_the_passenger_surface_not_the_http_call():
    """The workflow suspends on a durable promise and does not care what
    resolves it — but a demo that only shows the HTTP call hides the thing the
    passenger actually experiences."""
    import inspect

    from c2c.tools import demo

    src = inspect.getsource(demo)
    assert "format_request" in src and "show_approval_request(st)" in src
    assert src.count("show_approval_request(st)") == 2, (
        "both approval gates should render the passenger's view")


# --- intake over chat -------------------------------------------------------

class IntakeStubHTTP:
    def __init__(self): self.posts = []
    def get(self, url, params=None):
        class R:
            text = "BOOKING QX7T4L"
            def json(_): return {"result": {"file_path": "docs/ticket.txt"}}
        return R()
    def post(self, url, json=None):
        self.posts.append((url, json))
        class R:
            def json(_): return {"ok": True}
        return R()


class IntakeStubLLM:
    backend = model = "stub"
    def __init__(self, reply): self.reply = reply; self.seen = []
    def complete(self, system, user, max_tokens=4096):
        from c2c.llm import LLMResult
        self.seen.append(user)
        return LLMResult(text=self.reply, model="stub", backend="stub", duration_ms=1)


import json as _json

READY = _json.dumps({
    "passenger_name": "A. Mendes", "pnr": "QX7T4L", "narrative": "cancelled",
    "documents": [], "facts": {"what_happened": "cancellation"}, "missing": [],
    "ready": True, "reply": "Got it — I have what I need to start.",
})
NOT_READY = _json.dumps({
    "passenger_name": None, "pnr": None, "narrative": "something went wrong",
    "documents": [], "facts": {"what_happened": "unclear"},
    "missing": ["which flight"], "ready": False, "reply": "Which flight was it?",
})


def _tg(http):
    return Telegram(token="t", chat_id="1", api="http://cp", client=http)


def test_a_passenger_message_becomes_an_intake_record():
    http, llm = IntakeStubHTTP(), IntakeStubLLM(READY)
    out = _tg(http).handle_message("1", "my flight was cancelled", llm=llm)
    assert out["ready"] is True
    assert out["record"]["pnr"] == "QX7T4L"
    assert "my flight was cancelled" in llm.seen[0]


def test_the_passenger_always_gets_a_reply():
    http = IntakeStubHTTP()
    _tg(http).handle_message("1", "help", llm=IntakeStubLLM(READY))
    sent = [p[1]["text"] for p in http.posts if "sendMessage" in p[0]]
    assert any("Got it" in t for t in sent)


def test_an_incomplete_account_is_not_marked_ready():
    out = _tg(IntakeStubHTTP()).handle_message("1", "it was awful", llm=IntakeStubLLM(NOT_READY))
    assert out["ready"] is False
    assert out["record"]["missing"] == ["which flight"]


def test_an_unusable_model_reply_asks_the_passenger_again():
    http = IntakeStubHTTP()
    out = _tg(http).handle_message("1", "???", llm=IntakeStubLLM("no json here"))
    assert out["ready"] is False and out["record"] is None
    sent = [p[1]["text"] for p in http.posts if "sendMessage" in p[0]]
    assert any("didn't follow" in t for t in sent)


def test_the_conversation_accumulates_across_messages():
    http, tg = IntakeStubHTTP(), None
    tg = _tg(http)
    tg.handle_message("1", "my flight was cancelled", llm=IntakeStubLLM(NOT_READY))
    llm2 = IntakeStubLLM(READY)
    tg.handle_message("1", "it was MR414 on 6 March", llm=llm2)
    assert "my flight was cancelled" in llm2.seen[0] and "MR414" in llm2.seen[0]


def test_conversations_are_kept_separate_per_chat():
    tg = _tg(IntakeStubHTTP())
    tg.handle_message("1", "passenger one", llm=IntakeStubLLM(NOT_READY))
    tg.handle_message("2", "passenger two", llm=IntakeStubLLM(NOT_READY))
    assert tg.conversations["1"].messages == ["passenger one"]
    assert tg.conversations["2"].messages == ["passenger two"]


def test_a_text_attachment_is_read_into_the_conversation():
    tg = _tg(IntakeStubHTTP())
    assert "BOOKING QX7T4L" in tg.fetch_file("file-1")


def test_a_non_text_attachment_says_so_rather_than_storing_a_blank():
    """A photo of a boarding pass needs OCR, which is not built. Storing an
    empty document that looks like evidence would be worse than saying so."""
    class PhotoHTTP(IntakeStubHTTP):
        def get(self, url, params=None):
            class R:
                text = ""
                def json(_): return {"result": {"file_path": "photos/pass.jpg"}}
            return R()
    out = _tg(PhotoHTTP()).fetch_file("file-1")
    assert "text attachments only" in out
