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


def test_a_message_is_acknowledged_before_the_model_reply():
    """The intake assessment takes tens of seconds; a passenger who sees
    nothing assumes the bot is dead and keeps sending messages. Receipt must
    be acknowledged immediately, before the model call."""
    http = IntakeStubHTTP()
    _tg(http).handle_message("1", "IN300 was cancelled", llm=IntakeStubLLM(READY))
    sent = [p[1]["text"] for p in http.posts if "sendMessage" in p[0]]
    assert sent[0] == "Got it — one moment while I look at this."
    assert any("Got it — I have what I need" in t for t in sent)


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


def test_ready_while_still_asking_does_not_open_or_reset(tmp_path, monkeypatch):
    """The live failure from the IN300 exchange: the model says ready ("I
    have enough to open a case") but its reply still asks a question ("was it
    23 June 2025 or 2026?"). Opening the case at that point drops the
    conversation, and the passenger's answer lands in a fresh intake that asks
    from zero. A ready record whose reply still asks something must not open.
    """
    from c2c import intake as intake_mod

    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")
    http, tg = IntakeStubHTTP(), None
    tg = _tg(http)
    ready_but_asking = _json.dumps({
        "passenger_name": "Y. Tanaka", "pnr": "IN5540", "narrative": "cancelled",
        "documents": [], "facts": {"what_happened": "cancellation"},
        "missing": ["the year"], "ready": True,
        "reply": "Thanks — I have enough to open a case. Was it 23 June 2025 or 2026?",
    })
    out = tg.handle_message("1", "Flight IN300 was cancelled", llm=IntakeStubLLM(ready_but_asking))
    assert out["ready"] is False, "a ready record that still asks must not open the case"
    # The conversation must survive, so the answer to the question continues it.
    assert tg.conversations["1"].messages == ["Flight IN300 was cancelled"]

    # The answer arrives; the model asks nothing more, so now it opens.
    done = _json.dumps({
        "passenger_name": "Y. Tanaka", "pnr": "IN5540", "narrative": "cancelled in 2026",
        "documents": [], "facts": {"what_happened": "cancellation"},
        "missing": [], "ready": True,
        "reply": "Got it — 2026. I'm opening your case now.",
    })
    llm2 = IntakeStubLLM(done)
    out2 = tg.handle_message("1", "2026", llm=llm2)
    assert out2["ready"] is True
    # And the model saw the whole conversation, not just the latest message.
    assert "Flight IN300 was cancelled" in llm2.seen[0]


def test_a_ready_record_without_a_reply_gets_a_state_aware_fallback(tmp_path, monkeypatch):
    """The fallback path is a method, not a module function; calling it
    unqualified raised NameError on exactly the path it exists for."""
    from c2c import intake as intake_mod

    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")
    http = IntakeStubHTTP()
    out = _tg(http).handle_message("1", "IN300 was cancelled", llm=IntakeStubLLM(_json.dumps({
        "passenger_name": "Y. Tanaka", "pnr": "IN5540", "narrative": "cancelled",
        "documents": [], "facts": {"what_happened": "cancellation",
                                     "flight_number": "IN300"}, "missing": [],
        "ready": True, "reply": "",
    })))
    assert out["ready"] is True
    sent = [p[1]["text"] for p in http.posts if "sendMessage" in p[0]]
    assert any("enough to start your case" in t for t in sent)


def test_incomplete_intake_survives_a_worker_restart(tmp_path, monkeypatch):
    """A passenger mid-conversation is not asked from zero just because the
    Telegram worker restarted. The in-progress conversation is persisted per
    chat before replying, and a fresh process reloads it for the next message.

    This is the restart half of the intake-memory fix: within a running worker
    the conversation accumulates in memory, but a restart must not make the
    passenger repeat everything.
    """
    from c2c import intake as intake_mod
    from c2c.telegram import Telegram

    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")

    # First worker: passenger gives the first half of the account.
    first = Telegram(token="t", chat_id="1", api="http://cp", client=IntakeStubHTTP())
    first.handle_message("1", "my flight was cancelled", llm=IntakeStubLLM(NOT_READY))

    # The worker dies. A brand-new instance has no in-memory state at all.
    restarted = Telegram(token="t", chat_id="1", api="http://cp", client=IntakeStubHTTP())
    llm = IntakeStubLLM(READY)
    restarted.handle_message("1", "it was MR414 on 6 March", llm=llm)

    # The model must have been given the earlier message too — otherwise the
    # passenger is being asked from zero again, which is exactly the failure
    # this regression test exists for.
    assert "my flight was cancelled" in llm.seen[0]
    assert "MR414" in llm.seen[0]


def test_a_complete_live_exchange_does_not_restart_from_zero(tmp_path, monkeypatch):
    """The failure mode described in the live intake: the passenger gives a
    complete account, then the next reply still asks for name, airline, flight,
    date and what happened as if the passenger had said nothing.

    Persistent incomplete intake is written under a writable test directory,
    because the repo's data/ tree is not writable in this environment.
    """
    from c2c import intake as intake_mod
    from c2c.telegram import Telegram

    http = IntakeStubHTTP()
    tg = Telegram(token="t", chat_id="1", api="http://cp", client=http)
    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")

    record_so_far = _json.dumps({
        "passenger_name": "Y. Tanaka",
        "pnr": "IN5540",
        "narrative": "Flight IN300 from Helsinki to Istanbul on 23 June was cancelled. "
                     "Booking IN5540, Y. Tanaka. They told me on the 22nd at 23:40. "
                     "They're blaming a bird strike from the day before and say they owe me nothing.",
        "facts": {"carrier": "Indigo North", "flight_number": "IN300",
                  "route": "Helsinki to Istanbul", "what_happened": "cancellation",
                  "disruption_date": "2026-06-23"},
        "missing": ["the airline's cancellation email, so we can see when they told you"],
        "ready": True,
        "reply": "Got it. I have IN300 Helsinki-Istanbul on 23 June, booking IN5540, "
                 "cancelled by the airline. I have enough to open your case.",
    })
    tg.handle_message("1",
                       "Flight IN300 from Helsinki to Istanbul on 23 June was cancelled. "
                       "Booking IN5540, Y. Tanaka. They told me on the 22nd at 23:40. "
                       "They're blaming a bird strike from the day before and say they owe me nothing.",
                       llm=IntakeStubLLM(record_so_far))
    sent = [p[1]["text"] for p in http.posts if "sendMessage" in p[0]]
    assert any("Got it" in t or "enough to open" in t for t in sent), sent
    assert "Could you tell me your name" not in " ".join(sent)
    assert "name, the airline and flight number" not in " ".join(sent)
    assert "name, booking reference, flight number" not in " ".join(sent)
    assert "Tell me your name" not in " ".join(sent)


def test_opening_a_case_clears_the_persisted_incomplete(tmp_path, monkeypatch):
    """Once a case is opened, the persisted intake conversation is removed —
    otherwise a restart would resurrect the same ready conversation and could
    open a duplicate case.
    """
    from c2c import intake as intake_mod
    from c2c.telegram import Telegram

    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")

    class OpensCase(IntakeStubHTTP):
        def get(self, url, params=None):
            class R:
                def json(_):
                    return {"result": [{"update_id": 1, "message": {
                        "chat": {"id": "9"}, "text": "my flight was cancelled"}}]}
            return R()

        def post(self, url, json=None):
            self.posts.append((url, json))
            class R:
                def json(_):
                    if "from-intake" in url:
                        return {"case_id": "C2C-2026-ABCDE"}
                    return {"ok": True}
            return R()

    class OpensCaseTelegram(Telegram):
        """poll_once drives handle_message without an llm; inject the stub so
        the intake assessment makes no real model call."""
        def handle_message(self, chat_id, text, attachment=None, llm=None):
            return super().handle_message(chat_id, text, attachment, llm=IntakeStubLLM(READY))

    tg = OpensCaseTelegram(token="t", chat_id="1", api="http://cp", client=OpensCase())
    handled = tg.poll_once()
    assert handled == [{"case_id": "C2C-2026-ABCDE", "event": "case opened"}]
    assert "9" not in tg.conversations
    assert not (intake_mod.INCOMPLETE_INTAKE / "9.json").exists()


def test_a_follow_up_after_the_case_opens_is_acknowledged_not_interrogated(tmp_path, monkeypatch):
    """The passenger sent '?' while the account was being processed: the case
    opened, the intake conversation was dropped, and the '?' landed in a fresh
    intake that asked from zero ("which airline and flight…"). Once a case is
    open for a chat, further messages are acknowledged deterministically — no
    model call, no interrogation.
    """
    from c2c import intake as intake_mod
    from c2c.telegram import Telegram

    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")

    class TwoUpdates(IntakeStubHTTP):
        def get(self, url, params=None):
            class R:
                def json(_):
                    return {"result": [
                        {"update_id": 1, "message": {"chat": {"id": "9"}, "text": (
                            "Flight IN300 from Helsinki to Istanbul on 23 June 2026 was "
                            "cancelled. Booking IN5540, Y. Tanaka. They told me on the "
                            "22nd at 23:40. They're blaming a bird strike and say they "
                            "owe me nothing.")}},
                        {"update_id": 2, "message": {"chat": {"id": "9"}, "text": "?"}},
                    ]}
            return R()

        def post(self, url, json=None):
            self.posts.append((url, json))
            class R:
                def json(_):
                    if "from-intake" in url:
                        return {"case_id": "C2C-2026-ABCDE"}
                    return {"ok": True}
            return R()

    class CountingLLM(IntakeStubLLM):
        def __init__(self):
            super().__init__(READY)
            self.calls = 0

        def complete(self, system, user, max_tokens=4096):
            self.calls += 1
            return super().complete(system, user, max_tokens)

    class TestBot(Telegram):
        llm = None

        def handle_message(self, chat_id, text, attachment=None, llm=None):
            if self.llm is None:
                self.llm = CountingLLM()
            return super().handle_message(chat_id, text, attachment, llm=self.llm)

    tg = TestBot(token="t", chat_id="1", api="http://cp", client=TwoUpdates())
    handled = tg.poll_once()
    assert {"case_id": "C2C-2026-ABCDE", "event": "case opened"} in handled
    assert any(h.get("event") == "acknowledged" for h in handled)
    assert tg.llm.calls == 1, "the follow-up must not make a model call"
    sent = [p[1]["text"] for p in tg.http.posts if "sendMessage" in p[0]]
    assert any("case C2C-2026-ABCDE is open" in t for t in sent)
    assert not any("which airline" in t or "tell me what happened" in t.lower() for t in sent)


def test_evidence_for_an_open_case_is_recorded_not_acked(tmp_path, monkeypatch):
    """A case that asked for evidence stays open and waiting; the passenger's
    next message is evidence, not chatter — it goes to the case file and the
    workflow is told to re-assess on the round it is actually waiting for.
    No model call; no interrogation.
    """
    from c2c import intake as intake_mod
    from c2c.telegram import Telegram

    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")

    class Stub(IntakeStubHTTP):
        def get(self, url, params=None):
            class R:
                def json(_):
                    if "getUpdates" in url:
                        return {"result": [
                            {"update_id": 1, "message": {"chat": {"id": "9"}, "text": (
                                "Flight IN300 from Helsinki to Istanbul was cancelled. "
                                "Booking IN5540, Y. Tanaka.")}},
                            {"update_id": 2, "message": {"chat": {"id": "9"}, "text": (
                                "here is my boarding pass: IN300 23JUN")}},
                        ]}
                    if "/c2c/cases/" in url:
                        return {"state": "AWAITING_EVIDENCE", "evidence_round": 2}
                    return {"result": {"file_path": "docs/ticket.txt"}}
            return R()

        def post(self, url, json=None):
            self.posts.append((url, json))
            class R:
                def json(_):
                    if "from-intake" in url:
                        return {"case_id": "C2C-2026-EVID1"}
                    return {"ok": True}
            return R()

    class CountingLLM(IntakeStubLLM):
        def __init__(self):
            super().__init__(READY)
            self.calls = 0

        def complete(self, system, user, max_tokens=4096):
            self.calls += 1
            return super().complete(system, user, max_tokens)

    class TestBot(Telegram):
        llm = None

        def handle_message(self, chat_id, text, attachment=None, llm=None):
            if self.llm is None:
                self.llm = CountingLLM()
            return super().handle_message(chat_id, text, attachment, llm=self.llm)

    http = Stub()
    tg = TestBot(token="t", chat_id="1", api="http://cp", client=http)
    handled = tg.poll_once()
    assert any(h.get("event") == "case opened" for h in handled)
    assert any(h.get("event") == "evidence recorded" for h in handled)
    assert tg.llm.calls == 1, "recording evidence must not call the model"
    evidence_calls = [p for p in http.posts if p[0].endswith("/evidence")]
    assert len(evidence_calls) == 1
    assert evidence_calls[0][1]["round"] == 2, "must resolve the round the workflow waits on"
    docs = evidence_calls[0][1]["documents"]
    assert any("boarding pass: IN300" in d["content"] for d in docs)
    sent = [p[1]["text"] for p in http.posts if "sendMessage" in p[0]]
    assert any("added that to your case" in t for t in sent)
    assert not any("which airline" in t or "tell me what happened" in t.lower() for t in sent)


def test_evidence_document_as_first_message_in_batch_does_not_crash(tmp_path, monkeypatch):
    """The evidence branch must work when the document is the first (or only)
    message in a poll batch. Before the fix, `attachment` was extracted *after*
    the opened-case branch, so it was unbound exactly there: the first message
    in a batch for an open case crashed with UnboundLocalError and the
    passenger's documents were dropped (F-021).
    """
    from c2c import intake as intake_mod
    from c2c.telegram import Telegram

    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")

    class Stub(IntakeStubHTTP):
        def get(self, url, params=None):
            class R:
                def json(_):
                    if "getUpdates" in url:
                        return {"result": [{"update_id": 7, "message": {
                            "chat": {"id": "42"},
                            "document": {"file_id": "FILE42",
                                          "file_name": "boarding_pass.txt"},
                            "caption": "here is my boarding pass",
                        }}]}
                    if "/c2c/cases/" in url:
                        return {"state": "AWAITING_EVIDENCE", "evidence_round": 0}
                    return {"result": {"file_path": "docs/boarding_pass.txt"}}
            return R()

        def post(self, url, json=None):
            self.posts.append((url, json))
            class R:
                def json(_):
                    return {"ok": True}
            return R()

    http = Stub()
    tg = Telegram(token="t", chat_id="1", api="http://cp", client=http)
    tg.opened_cases["42"] = "C2C-2026-F021"
    handled = tg.poll_once()
    assert any(h.get("event") == "evidence recorded" for h in handled)
    evidence_calls = [p for p in http.posts if p[0].endswith("/evidence")]
    assert len(evidence_calls) == 1
    docs = evidence_calls[0][1]["documents"]
    contents = "\n".join(d.get("content", "") for d in docs)
    assert "boarding_pass.txt" in contents, "the document text must reach the case file"
    assert "here is my boarding pass" in contents, "the caption is evidence too"


def test_the_opened_case_mapping_survives_a_bot_restart(tmp_path, monkeypatch):
    """A passenger who sends a follow-up after a bot restart must not be asked
    from zero again — and their evidence must land on the open case, not a
    duplicate. The chat -> case mapping is persisted.
    """
    from c2c import intake as intake_mod
    from c2c.telegram import Telegram

    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")
    monkeypatch.setattr("c2c.telegram.OPENED_CASES_FILE", tmp_path / "opened_cases.json")

    class Stub(IntakeStubHTTP):
        def get(self, url, params=None):
            class R:
                def json(_):
                    if "getUpdates" in url:
                        return {"result": [{"update_id": 1, "message": {
                            "chat": {"id": "9"}, "text": "IN300 was cancelled, IN5540"}}]}
                    if "/c2c/cases/" in url:
                        return {"state": "AWAITING_CARRIER"}
                    return {"result": {"file_path": "docs/ticket.txt"}}
            return R()

        def post(self, url, json=None):
            self.posts.append((url, json))
            class R:
                def json(_):
                    if "from-intake" in url:
                        return {"case_id": "C2C-2026-KEEP1"}
                    return {"ok": True}
            return R()

    class StubLLM(IntakeStubLLM):
        backend = model = "stub"

    class TestBot(Telegram):
        def handle_message(self, chat_id, text, attachment=None, llm=None):
            return super().handle_message(chat_id, text, attachment, llm=StubLLM(READY))

    first = TestBot(token="t", chat_id="1", api="http://cp", client=Stub())
    assert any(h.get("event") == "case opened" for h in first.poll_once())
    assert (tmp_path / "opened_cases.json").exists()

    # The bot dies. A brand-new instance has no in-memory state.
    restarted = TestBot(token="t", chat_id="1", api="http://cp", client=Stub())
    # Re-run the same update: the mapping must have been reloaded from disk.
    assert restarted.opened_cases.get("9") == "C2C-2026-KEEP1"
    handled = restarted.poll_once()
    assert any(h.get("event") == "acknowledged" for h in handled)
    assert not any(h.get("event") == "case opened" for h in handled), (
        "a restarted bot must not open a duplicate case")


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


def _updates_http(text):
    class Updates(IntakeStubHTTP):
        def get(self, url, params=None):
            class R:
                def json(_):
                    return {"result": [{"update_id": 1,
                                        "message": {"chat": {"id": "9"}, "text": text}}]}
            return R()
    return Updates()


@pytest.mark.parametrize("opener", ["/start", "hi", "Hello", "  hey  "])
def test_a_first_message_gets_an_introduction_not_an_interrogation(opener):
    from c2c.telegram import GREETING

    http = _updates_http(opener)
    assert _tg(http).poll_once() == [{"case_id": "-", "event": "greeted"}]
    sent = [p[1]["text"] for p in http.posts if "sendMessage" in p[0]]
    assert sent == [GREETING]


def test_an_opener_does_not_become_part_of_the_case_narrative():
    """'hi' is not an account of a flight disruption."""
    http = _updates_http("/start")
    tg = _tg(http)
    tg.poll_once()
    assert "9" not in tg.conversations


def test_an_opener_discards_any_persisted_incomplete(tmp_path, monkeypatch):
    """A passenger who resets with /start means a fresh start: the persisted
    incomplete conversation must go too, or a later restart would resurrect
    the account they explicitly reset."""
    from c2c import intake as intake_mod

    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")
    path = intake_mod.INCOMPLETE_INTAKE / "9.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{\"messages\": [\"old account\"]}")

    http = _updates_http("/start")
    _tg(http).poll_once()
    assert not path.exists()


def test_the_greeting_says_what_it_does_and_what_it_will_not_do():
    from c2c.telegram import GREETING

    assert "I'm C2C" in GREETING
    assert "won't guess" in GREETING.replace("’", "'")
    assert "without asking you first" in GREETING
    assert "SYNTHETIC DEMO" in GREETING
