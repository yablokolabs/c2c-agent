"""The simulator is the instrument that measures duplicate side effects, so it
has to be correct about deduplication before anything measured with it means
anything."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from c2c.simulator import BANNER, WORLD, router

app = FastAPI()
app.include_router(router)


@pytest.fixture()
def client():
    WORLD.reset()
    with TestClient(app) as c:
        yield c


SUBMISSION = {"case_id": "R01", "passenger": "A. Mendes", "pnr": "QX7T4L",
              "compensation_units": 420, "summary": "crew shortage"}


def test_submission_returns_a_claim_and_is_banner_stamped(client):
    r = client.post("/airline/claims", json=SUBMISSION, headers={"Idempotency-Key": "k1"})
    assert r.status_code == 201
    body = r.json()
    assert body["banner"] == BANNER
    assert body["claim_id"].startswith("SYN-CLM-")
    assert body["deduplicated"] is False


def test_same_key_twice_lands_once(client):
    a = client.post("/airline/claims", json=SUBMISSION, headers={"Idempotency-Key": "k1"}).json()
    b = client.post("/airline/claims", json=SUBMISSION, headers={"Idempotency-Key": "k1"}).json()
    assert b["deduplicated"] is True
    assert a["claim_id"] == b["claim_id"]
    assert WORLD.count("submit_claim", "R01") == 1


def test_different_keys_are_two_real_submissions(client):
    client.post("/airline/claims", json=SUBMISSION, headers={"Idempotency-Key": "k1"})
    client.post("/airline/claims", json=SUBMISSION, headers={"Idempotency-Key": "k2"})
    assert WORLD.count("submit_claim", "R01") == 2


def test_audit_distinguishes_attempts_from_effects(client):
    for _ in range(3):
        client.post("/airline/claims", json=SUBMISSION, headers={"Idempotency-Key": "k1"})
    a = client.get("/airline/_admin/audit").json()
    assert len(a["entries"]) == 3
    assert len(a["effective"]) == 1


def test_injected_503_fires_the_configured_number_of_times(client):
    client.post("/airline/_admin/inject", json={"injection": "503", "times": 2})
    assert client.post("/airline/claims", json=SUBMISSION,
                       headers={"Idempotency-Key": "k1"}).status_code == 503
    assert client.post("/airline/claims", json=SUBMISSION,
                       headers={"Idempotency-Key": "k1"}).status_code == 503
    assert client.post("/airline/claims", json=SUBMISSION,
                       headers={"Idempotency-Key": "k1"}).status_code == 201


def test_a_failed_call_leaves_no_effect_behind(client):
    client.post("/airline/_admin/inject", json={"injection": "503", "times": 1})
    client.post("/airline/claims", json=SUBMISSION, headers={"Idempotency-Key": "k1"})
    assert WORLD.count("submit_claim", "R01") == 0


def test_escalation_is_deduplicated_too(client):
    for _ in range(2):
        client.post("/airline/escalations", params={"case_id": "R15"},
                    headers={"Idempotency-Key": "esc-1"})
    assert WORLD.count("escalate", "R15") == 1


def test_scripted_response_is_delivered_on_advance(client):
    client.post("/airline/_admin/script", json={
        "case_id": "R01",
        "on_submit": {"type": "rejection", "text": "extraordinary circumstances"},
    })
    claim = client.post("/airline/claims", json=SUBMISSION,
                        headers={"Idempotency-Key": "k1"}).json()
    r = client.post(f"/airline/claims/{claim['claim_id']}/_advance").json()
    assert r["advanced"] is True
    assert r["response"]["type"] == "rejection"


def test_reset_clears_everything(client):
    client.post("/airline/claims", json=SUBMISSION, headers={"Idempotency-Key": "k1"})
    client.post("/airline/_admin/reset")
    assert client.get("/airline/_admin/audit").json()["entries"] == []
