"""The airline's side of a live case. Without it a Telegram demo stops dead
after 'Filed' — the workflow waits for a response that nothing sends."""

import json

import pytest

from c2c.tools import carrier


def test_the_newest_live_case_is_the_one_picked(tmp_path, monkeypatch):
    """During a demo that is the case just opened. Asking the operator to copy a
    reference off a phone mid-take is a good way to fumble it."""
    monkeypatch.setattr(carrier, "LIVE", tmp_path)
    for i, cid in enumerate(["C2C-2026-AAAAA", "C2C-2026-BBBBB"]):
        p = tmp_path / f"{cid}.json"
        p.write_text(json.dumps({"case_id": cid}))
        import os, time
        os.utime(p, (1000 + i, 1000 + i))
    assert carrier.newest_live_case() == "C2C-2026-BBBBB"


def test_no_live_cases_returns_none_rather_than_guessing(tmp_path, monkeypatch):
    monkeypatch.setattr(carrier, "LIVE", tmp_path)
    assert carrier.newest_live_case() is None


def test_a_refusal_is_the_default_and_carries_a_stated_ground():
    sent = {}
    def fake(case_id, payload, promise): sent.update(payload=payload, promise=promise); return {}
    import c2c.tools.carrier as c
    orig = c.deliver; c.deliver = fake
    try:
        c.main(["--case", "X"])
    finally:
        c.deliver = orig
    assert sent["payload"]["type"] == "rejection"
    assert "extraordinary circumstances" in sent["payload"]["text"]
    assert sent["promise"] == "carrier_response"


def test_a_settlement_carries_the_amount_so_the_agent_can_check_it():
    """S9.4: an offer below the full entitlement is a partial settlement. The
    agent cannot tell without the number."""
    sent = {}
    def fake(case_id, payload, promise): sent.update(payload=payload); return {}
    import c2c.tools.carrier as c
    orig = c.deliver; c.deliver = fake
    try:
        c.main(["--case", "X", "--settle", "210"])
    finally:
        c.deliver = orig
    assert sent["payload"]["type"] == "settlement_offer"
    assert sent["payload"]["amount_units"] == 210


def test_answering_a_challenge_targets_a_different_promise():
    sent = {}
    def fake(case_id, payload, promise): sent.update(promise=promise); return {}
    import c2c.tools.carrier as c
    orig = c.deliver; c.deliver = fake
    try:
        c.main(["--case", "X", "--after-challenge"])
    finally:
        c.deliver = orig
    assert sent["promise"] == "challenge_response"
