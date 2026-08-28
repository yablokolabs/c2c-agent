"""Tests for the orchestration logic — the parts C2C owns.

The model transport is stubbed with canned replies. What is under test is not
the model: it is the rules that decide when a rejection counts, what happens
when a reply is unreadable, and what survives a failed revision. Those are
C2C's decisions and they change the passenger's outcome.
"""

import json

import pytest

from c2c.agent import caseworker, pipeline, verifier
from c2c.llm import LLMResult
from c2c.models import Verdict, load_cases

CASES = {c.case_id: c for c in load_cases()}
CASE = CASES["R01"]

GOOD = Verdict(in_scope=True, qualifies=True, cause_class="carrier_controlled", eligible=True,
               compensation_units=420, evidence_sufficient=True, next_action="submit_claim")


class StubLLM:
    """Replays scripted replies in order and records what it was asked."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []
        self.calls = 0
        self.backend = "stub"
        self.model = "stub"

    def complete(self, system, user, max_tokens=4096):
        self.seen.append({"system": system, "user": user})
        self.calls += 1
        text = self.replies.pop(0) if self.replies else '{"verdict": {}}'
        return LLMResult(text=text, model="stub", backend="stub", duration_ms=1)


def verdict_reply(**over):
    body = {**GOOD.model_dump(), **over}
    return json.dumps({"verdict": body})


# --- verifier ---------------------------------------------------------------

def test_rejection_without_cited_evidence_is_downgraded_to_pass():
    llm = StubLLM([json.dumps({
        "decision": "reject", "confidence": "high",
        "findings": [{"field": "compensation_units", "problem": "feels too high", "evidence": ""}],
        "summary": "I would have said less.",
    })])
    report, _ = verifier.run(CASE, GOOD, llm)
    assert report["decision"] == "pass"
    assert report["downgraded"] is True


def test_rejection_with_cited_evidence_stands():
    llm = StubLLM([json.dumps({
        "decision": "reject", "confidence": "high",
        "findings": [{"field": "compensation_units", "problem": "wrong band",
                      "evidence": "S5.1 and D1"}],
        "summary": "Band B, not C.",
    })])
    report, _ = verifier.run(CASE, GOOD, llm)
    assert report["decision"] == "reject"
    assert "downgraded" not in report


def test_unreadable_verifier_fails_open():
    report, _ = verifier.run(CASE, GOOD, StubLLM(["I'm not sure, sorry."]))
    assert report["decision"] == "pass"
    assert report["unreadable"] is True


def test_verifier_never_sees_the_caseworker_transcript():
    """If it inherits the caseworker's working it is a reviewer, not a second
    opinion, and it inherits the caseworker's wrong turns."""
    llm = StubLLM([json.dumps({"decision": "pass", "findings": []})])
    verifier.run(CASE, GOOD, llm)
    sent = llm.seen[0]["user"]
    assert "You called:" not in sent
    assert "list_documents" not in sent
    assert CASE.dossier() in sent


# --- pipeline ---------------------------------------------------------------

def test_a_pass_returns_the_caseworker_verdict_unchanged():
    llm = StubLLM([verdict_reply(), json.dumps({"decision": "pass", "findings": []})])
    got, calls = pipeline.run_case(CASE, llm)
    assert got.compensation_units == 420
    assert len(calls) == 2


def test_a_cited_rejection_triggers_exactly_one_revision():
    llm = StubLLM([
        verdict_reply(compensation_units=750),
        json.dumps({"decision": "reject", "confidence": "high",
                    "findings": [{"field": "compensation_units", "problem": "wrong band",
                                  "evidence": "S5.1"}]}),
        verdict_reply(compensation_units=420),
    ])
    got, _ = pipeline.run_case(CASE, llm)
    assert got.compensation_units == 420
    assert llm.replies == []


def test_the_revision_is_told_what_the_verifier_said():
    llm = StubLLM([
        verdict_reply(compensation_units=750),
        json.dumps({"decision": "reject", "confidence": "high",
                    "findings": [{"field": "compensation_units", "problem": "wrong band",
                                  "evidence": "S5.1"}]}),
        verdict_reply(compensation_units=420),
    ])
    pipeline.run_case(CASE, llm)
    revision_prompt = llm.seen[-1]["user"]
    assert "INDEPENDENT VERIFIER REJECTED" in revision_prompt
    assert "wrong band" in revision_prompt
    assert "S5.1" in revision_prompt


def test_the_caseworker_may_keep_its_answer_against_the_verifier():
    """The verifier is not automatically right, and the revision prompt says so.
    A caseworker that re-affirms must not be overridden."""
    llm = StubLLM([
        verdict_reply(compensation_units=420),
        json.dumps({"decision": "reject", "confidence": "low",
                    "findings": [{"field": "compensation_units", "problem": "maybe band C",
                                  "evidence": "S5.1"}]}),
        verdict_reply(compensation_units=420),
    ])
    got, _ = pipeline.run_case(CASE, llm)
    assert got.compensation_units == 420


def test_a_broken_revision_keeps_the_original_verdict():
    llm = StubLLM([
        verdict_reply(compensation_units=750),
        json.dumps({"decision": "reject", "confidence": "high",
                    "findings": [{"field": "x", "problem": "y", "evidence": "S5.1"}]}),
        "the revision fell over",
    ])
    got, _ = pipeline.run_case(CASE, llm)
    assert got is not None and got.compensation_units == 750


def test_no_caseworker_verdict_means_no_verifier_call():
    llm = StubLLM(["not json at all"] * caseworker.MAX_STEPS)
    got, _ = pipeline.run_case(CASE, llm)
    assert got is None
    assert llm.calls == caseworker.MAX_STEPS


# --- caseworker loop --------------------------------------------------------

def test_tool_results_are_fed_back_into_the_transcript():
    llm = StubLLM([
        json.dumps({"tool": "read_document", "args": {"doc_id": "D3"}, "why": "cause"}),
        verdict_reply(),
        json.dumps({"decision": "pass", "findings": []}),
    ])
    pipeline.run_case(CASE, llm)
    second_turn = llm.seen[1]["user"]
    assert "You called: read_document" in second_turn
    assert "CRW-DUTY" in second_turn


def test_a_non_json_reply_is_retried_not_fatal():
    llm = StubLLM(["sorry, thinking out loud", verdict_reply(),
                   json.dumps({"decision": "pass", "findings": []})])
    got, _ = pipeline.run_case(CASE, llm)
    assert got is not None


def test_the_loop_gives_up_after_max_steps():
    llm = StubLLM([json.dumps({"tool": "list_documents", "args": {}})] * 40)
    got, calls = pipeline.run_case(CASE, llm)
    assert got is None
    assert len(calls) == caseworker.MAX_STEPS


def test_coercion_never_invents_a_value():
    v = caseworker.coerce_verdict({"next_action": "submit_claim", "evidence_sufficient": True,
                                   "compensation_units": None, "stray_key": "ignored"})
    assert v.compensation_units is None
    assert v.duty_of_care_units == 0
    assert not hasattr(v, "stray_key")
