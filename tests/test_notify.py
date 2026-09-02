"""The notifier is the passenger's only view of a case that runs for weeks, and
it is also the component most able to do harm by failing loudly."""

import pytest

from c2c.notify import BANNER, STAGES, configured, render, send


def test_every_stage_renders_and_is_banner_stamped():
    fields = dict(pnr="HB1188", case_id="C2C-2026-K7M2P", amount=420,
                  rationale="the record contradicts them",
                  citations="S3.6", ground="56 days of silence", reference="SYN-SPRB-1",
                  offered=210, owed=420, shortfall=210,
                  missing="• booking confirmation\n• boarding pass")
    for stage in STAGES:
        out = render(stage, **fields)
        assert BANNER in out
        assert "{" not in out.replace("{", "", 0) or "}" not in out, f"{stage} has an unfilled field"


def test_an_unknown_stage_is_refused_not_guessed():
    with pytest.raises(KeyError):
        render("made_up_stage")


def test_the_filed_message_names_the_amount_and_the_clock():
    out = render("claim_filed", amount=420, case_id="C2C-2026-K7M2P")
    assert "420 units" in out and "56 days" in out


def test_a_short_offer_states_the_shortfall_rather_than_just_the_offer():
    out = render("offer_short", offered=210, owed=420, shortfall=210, pnr="X")
    assert "210 units" in out and "420" in out and "short" in out


def test_a_full_offer_recommends_accepting():
    assert "accept" in render("offer_full", offered=590, pnr="X").lower()


def test_no_claim_explains_why_rather_than_just_saying_no():
    out = render("assessed_no_claim", pnr="X", rationale="the delay was 3h20m")
    assert "3h20m" in out


def test_an_evidence_request_lists_what_is_missing():
    out = render("evidence_requested", case_id="C2C-2026-XYZ", pnr="X",
                 missing="• booking confirmation\n• boarding pass")
    assert "booking confirmation" in out and "boarding pass" in out
    assert "C2C-2026-XYZ" in out, "the passenger must know which case is asking"
    assert "isn't a claim worth making" not in out


def test_the_evidence_loop_waits_on_a_fresh_promise_each_round():
    """The case waits durably for evidence instead of closing. Each round must
    wait on its own promise (a replay must not re-read a resolved promise and
    spin), and the re-assessment must have a fresh step name (Restate
    deduplicates ctx.run by name — reusing "assess" would hand back the first
    verdict)."""
    import inspect

    from c2c import workflow

    src = inspect.getsource(workflow)
    assert "AWAITING_EVIDENCE" in src
    assert 'ctx.promise(f"evidence_{evidence_round}")' in src
    assert 'ctx.run(f"assess_after_evidence_{evidence_round}"' in src


def test_an_evidence_request_gets_its_own_message_not_a_no_claim():
    """request_evidence must not tell the passenger "there isn't a claim worth
    making" — the agent simply needs more documents, and saying otherwise is
    the silence that kills real claims."""
    import inspect

    from c2c import workflow

    src = inspect.getsource(workflow)
    assert '"request_evidence"' in src and "evidence_requested" in src


def test_send_never_raises_when_unconfigured(capsys, monkeypatch):
    """Pinned to an empty config rather than the ambient one. This test read the
    real environment and started failing the moment a token was added to .env —
    a test whose result depends on the machine it runs on is not a test."""
    import c2c.notify as n

    monkeypatch.setattr(n, "TOKEN", "")
    monkeypatch.setattr(n, "CHAT_ID", "")
    r = n.send("hello")
    assert r["delivered"] is False and r["reason"] == "not configured"
    assert "hello" in capsys.readouterr().out


def test_send_never_raises_on_a_transport_failure(monkeypatch):
    """A dead notifier must not stall a claim. The workflow sends from inside a
    durable step, and a step that raises is retried — parking the case."""
    import c2c.notify as n

    monkeypatch.setattr(n, "TOKEN", "t")
    monkeypatch.setattr(n, "CHAT_ID", "1")
    monkeypatch.setattr(n.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    r = n.send("hello")
    assert r["delivered"] is False and "down" in r["reason"]


def test_configured_needs_both_a_token_and_a_chat(monkeypatch):
    import c2c.notify as n

    monkeypatch.setattr(n, "TOKEN", "t"); monkeypatch.setattr(n, "CHAT_ID", "")
    assert not n.configured()
    monkeypatch.setattr(n, "CHAT_ID", "1")
    assert n.configured()


def test_notifications_are_sent_from_inside_a_durable_step():
    """A replay after a crash must not re-send a message the passenger has
    already read. Being told twice that your claim was filed is a small harm;
    being told twice that you have been paid is not."""
    import inspect

    from c2c import workflow

    src = inspect.getsource(workflow._tell)
    assert 'ctx.run(f"notify_{stage}"' in src, "notifications must go through ctx.run"
    assert "max_attempts=" in src, "a notifier outage must not park a claim"


def test_delivery_retries_a_transient_failure_then_succeeds(monkeypatch):
    """F-027: notify.send never raises, so ctx.run's exception-driven retries
    can never see a refused delivery — a one-off blip used to swallow the
    message while the step recorded success. The step itself must retry."""
    import asyncio

    from c2c import workflow

    async def no_sleep(_):  # keep the test fast
        return None
    monkeypatch.setattr(workflow.asyncio, "sleep", no_sleep)

    calls = []

    def send_once() -> dict:
        calls.append(1)
        return {"delivered": False} if len(calls) == 1 else {"delivered": True}

    result = asyncio.run(workflow._deliver_notify("test", send_once))
    assert result["delivered"] is True
    assert len(calls) == 2, "the transient failure should have been retried"


def test_delivery_that_keeps_failing_is_logged_and_reported(capsys, monkeypatch):
    import asyncio

    from c2c import workflow

    async def no_sleep(_):
        return None
    monkeypatch.setattr(workflow.asyncio, "sleep", no_sleep)

    result = asyncio.run(workflow._deliver_notify(
        "test", lambda: {"delivered": False, "reason": "chat not found"}))
    assert result["delivered"] is False
    out = capsys.readouterr().out
    assert "NOT delivered after" in out, "a lost message must be loud, not silent"


def test_a_failed_delivery_is_recorded_not_silently_accepted():
    """F-027: the workflow must not record a refused delivery as a successful
    step. The tell checks what notify.send actually reported and writes the
    failure into case state, where status() can surface it."""
    import inspect

    from c2c import workflow

    src = inspect.getsource(workflow._tell)
    assert "_deliver_notify" in src
    assert 'result.get("delivered")' in src
    assert "ctx.set(\"notify_failure\"" in src
    status_src = inspect.getsource(workflow.status)
    assert "notify_failure" in status_src


def test_every_workflow_transition_that_matters_tells_the_passenger():
    import inspect

    from c2c import workflow

    src = inspect.getsource(workflow)
    for stage in ("case_opened", "claim_filed", "carrier_replied", "challenge_sent",
                  "challenge_refused", "challenge_settled", "escalated", "resolved",
                  "offer_short", "closed_by_human"):
        assert f'"{stage}"' in src, f"the workflow never tells the passenger about {stage}"


def test_the_challenge_outcome_is_told_not_silent():
    """Before F-025 the workflow moved to RESOLVED_AFTER_CHALLENGE and said
    nothing, so a case that finished its whole arc was indistinguishable, from
    the passenger's seat, from one that was forgotten. The tell must sit on the
    challenge-reply path itself, not somewhere unreachable."""
    import inspect

    from c2c import workflow

    src = inspect.getsource(workflow)
    reply_branch = src[src.index('ctx.set("challenge_reply", after)'):]
    assert 'await _tell(ctx, "challenge_refused"' in reply_branch
    assert 'await _tell(ctx, "challenge_settled"' in reply_branch
    assert 'pending_action=None' in reply_branch, "a resolved case should not keep a pending action"


def test_the_challenge_resolution_messages_carry_the_outcome():
    out = render("challenge_refused", pnr="X", case_id="C2C-2026-K7M2P")
    assert "holding the refusal" in out and "C2C-2026-K7M2P" in out
    out = render("challenge_settled", pnr="X", case_id="C2C-2026-K7M2P", amount="420 units")
    assert "420 units" in out and "C2C-2026-K7M2P" in out


def test_a_rejected_send_reports_telegrams_own_reason(monkeypatch):
    """Swallowing the description turned 'chat not found' -- a five-second fix --
    into an opaque 400."""
    import c2c.notify as n

    class R:
        status_code = 400
        def json(self): return {"ok": False, "description": "Bad Request: chat not found"}

    monkeypatch.setattr(n, "TOKEN", "t"); monkeypatch.setattr(n, "CHAT_ID", "1")
    monkeypatch.setattr(n.httpx, "post", lambda *a, **k: R())
    r = n.send("hello")
    assert r["delivered"] is False and "chat not found" in r["reason"]


def test_send_carries_the_approval_buttons_when_given(monkeypatch):
    import c2c.notify as n

    class R:
        status_code = 200
        def json(self): return {"ok": True}

    sent = {}
    def fake_post(url, json=None, timeout=15):
        sent.update(json or {})
        return R()

    monkeypatch.setattr(n, "TOKEN", "t"); monkeypatch.setattr(n, "CHAT_ID", "1")
    monkeypatch.setattr(n.httpx, "post", fake_post)
    n.send("approve?", reply_markup={"inline_keyboard": [[{"text": "Approve"}]]})
    assert "reply_markup" in sent and "inline_keyboard" in sent["reply_markup"]


def test_every_approval_gate_sends_the_request_with_buttons():
    """A case that suspends on a human approval must ask the passenger where
    they already are — the buttons are what let the tap become the approval.
    Without this the case waits silently at AWAITING_APPROVAL forever."""
    import inspect

    from c2c import workflow

    src = inspect.getsource(workflow)
    assert src.count("_ask_approval(") >= 3, "all three approval gates must ask"
    assert "reply_markup=markup" in src
    assert 'ctx.promise("approval")' in src and 'ctx.promise("challenge_approval")' in src \
        and 'ctx.promise("escalation_approval")' in src


def test_the_opening_message_gives_a_reference_the_passenger_can_quote():
    out = render("case_opened", case_id="C2C-2026-K7M2P")
    assert "C2C-2026-K7M2P" in out


def test_a_case_reference_avoids_ambiguous_characters():
    """It is read off a phone and typed into an email weeks later."""
    from c2c.intake import new_reference

    for _ in range(50):
        tail = new_reference().split("-")[-1]
        assert not (set(tail) & set("O0I1")), f"ambiguous characters in {tail}"
        assert len(tail) == 5
