"""The notifier is the passenger's only view of a case that runs for weeks, and
it is also the component most able to do harm by failing loudly."""

import pytest

from c2c.notify import BANNER, STAGES, configured, render, send


def test_every_stage_renders_and_is_banner_stamped():
    fields = dict(pnr="HB1188", amount=420, rationale="the record contradicts them",
                  citations="S3.6", ground="56 days of silence", reference="SYN-SPRB-1",
                  offered=210, owed=420, shortfall=210)
    for stage in STAGES:
        out = render(stage, **fields)
        assert BANNER in out
        assert "{" not in out.replace("{", "", 0) or "}" not in out, f"{stage} has an unfilled field"


def test_an_unknown_stage_is_refused_not_guessed():
    with pytest.raises(KeyError):
        render("made_up_stage")


def test_the_filed_message_names_the_amount_and_the_clock():
    out = render("claim_filed", amount=420)
    assert "420 units" in out and "56 days" in out


def test_a_short_offer_states_the_shortfall_rather_than_just_the_offer():
    out = render("offer_short", offered=210, owed=420, shortfall=210, pnr="X")
    assert "210 units" in out and "420" in out and "short" in out


def test_a_full_offer_recommends_accepting():
    assert "accept" in render("offer_full", offered=590, pnr="X").lower()


def test_no_claim_explains_why_rather_than_just_saying_no():
    out = render("assessed_no_claim", pnr="X", rationale="the delay was 3h20m")
    assert "3h20m" in out


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


def test_every_workflow_transition_that_matters_tells_the_passenger():
    import inspect

    from c2c import workflow

    src = inspect.getsource(workflow)
    for stage in ("case_opened", "claim_filed", "carrier_replied", "challenge_sent",
                  "escalated", "resolved", "offer_short", "closed_by_human"):
        assert f'"{stage}"' in src, f"the workflow never tells the passenger about {stage}"


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
