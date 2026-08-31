"""Intake is the only part of C2C that talks to a passenger in prose, and the
only place a fabricated detail could enter the system unchallenged."""

import json

import pytest

from c2c.intake import DOC_TYPES, Intake, load_live, save, to_case, understand
from c2c.llm import LLMResult


class StubLLM:
    def __init__(self, reply):
        self.reply, self.seen = reply, []
        self.backend = self.model = "stub"

    def complete(self, system, user, max_tokens=4096):
        self.seen.append({"system": system, "user": user})
        return LLMResult(text=self.reply, model="stub", backend="stub", duration_ms=1)


RECORD = {
    "passenger_name": "A. Mendes", "pnr": "QX7T4L",
    "narrative": "Flight from Lisbon to Vienna was cancelled three days before departure.",
    "documents": [{"doc_id": "D1", "type": "booking_confirmation", "content": "BOOKING QX7T4L"}],
    "facts": {"carrier": "Meridian Air", "what_happened": "cancellation"},
    "missing": ["The airline's cancellation email, so we can see when they told you"],
    "ready": True, "reply": "Got it — I have your booking. I still need the email.",
}


def test_the_conversation_and_attachments_both_reach_the_model():
    llm = StubLLM(json.dumps(RECORD))
    understand(Intake(messages=["cancelled!"], attachments=[("t.txt", "BOOKING QX7T4L")]), llm)
    sent = llm.seen[0]["user"]
    assert "cancelled!" in sent and "BOOKING QX7T4L" in sent


def test_an_unusable_reply_returns_none_rather_than_a_default():
    assert understand(Intake(messages=["hi"]), StubLLM("I'm not sure what you mean")) is None
    assert understand(Intake(messages=["hi"]), StubLLM('{"unrelated": 1}')) is None


def test_a_live_case_carries_no_ground_truth():
    """Inventing an expected answer for a real passenger's case would corrupt
    the one thing the benchmark guarantees."""
    assert to_case(RECORD).ground_truth is None


def test_the_case_keeps_the_passenger_and_booking():
    c = to_case(RECORD)
    assert c.passenger["name"] == "A. Mendes" and c.passenger["pnr"] == "QX7T4L"
    assert "Lisbon to Vienna" in c.narrative


def test_missing_identity_becomes_unknown_not_a_plausible_invention():
    c = to_case({**RECORD, "passenger_name": None, "pnr": None})
    assert c.passenger["name"] == "Unknown" and c.passenger["pnr"] == "UNKNOWN"


def test_an_unrecognised_document_type_degrades_to_a_statement():
    c = to_case({**RECORD, "documents": [{"doc_id": "D1", "type": "invented_type", "content": "x"}]})
    assert c.documents[0].type == "passenger_statement"
    assert all(d.type in DOC_TYPES for d in c.documents)


def test_a_case_with_no_documents_still_carries_the_passengers_account():
    c = to_case({**RECORD, "documents": []})
    assert len(c.documents) == 1
    assert "Lisbon to Vienna" in c.documents[0].content


def test_empty_documents_are_dropped_not_stored_blank():
    c = to_case({**RECORD, "documents": [{"doc_id": "D1", "type": "receipts", "content": ""},
                                         {"doc_id": "D2", "type": "receipts", "content": "ok"}]})
    assert [d.doc_id for d in c.documents] == ["D2"]


def test_a_live_case_survives_the_process_that_received_it(tmp_path):
    c = to_case(RECORD, case_id="LIVE-TEST1")
    save(c, tmp_path)
    back = load_live(tmp_path)
    assert back["LIVE-TEST1"].passenger["pnr"] == "QX7T4L"
    assert back["LIVE-TEST1"].ground_truth is None


def test_one_corrupt_file_does_not_hide_the_others(tmp_path):
    save(to_case(RECORD, case_id="LIVE-OK"), tmp_path)
    (tmp_path / "broken.json").write_text("{not json")
    assert list(load_live(tmp_path)) == ["LIVE-OK"]


def test_intake_never_mentions_the_policy_or_an_amount():
    """It organises; it does not assess. If it starts estimating, the caseworker
    inherits a number nobody derived."""
    from c2c.intake import system_prompt

    p = system_prompt().lower()
    assert "do not assess" in p
    assert "never invent" in p


def test_intake_records_a_trajectory_like_every_other_agent(tmp_path):
    """The brief asks for representative trajectories for *every* agent. Intake
    is also the only one that sees a passenger's own words, which makes it the
    one most worth being able to audit."""
    from c2c.trajectory import Recorder

    rec = Recorder.open("test", root=tmp_path)
    understand(Intake(messages=["cancelled"]), StubLLM(json.dumps(RECORD)), rec=rec)
    kinds = [e["event_type"] for e in rec.read()]
    assert kinds == ["AGENT_START", "USER_INPUT", "MODEL_RESPONSE", "FINAL_DECISION"]
    assert all(e["agent"] == "intake" for e in rec.read())


def test_an_unusable_intake_reply_is_recorded_as_an_error(tmp_path):
    from c2c.trajectory import Recorder

    rec = Recorder.open("test", root=tmp_path)
    assert understand(Intake(messages=["?"]), StubLLM("not json"), rec=rec) is None
    assert "ERROR" in [e["event_type"] for e in rec.read()]
