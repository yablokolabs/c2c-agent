"""The merge produces the headline number, so its refusals matter more than its
successes. A merge that silently double-counts a case, or quietly drops one, or
combines two different models, would manufacture a result."""

import pytest

from c2c.eval.merge import MergeError, merge
from c2c.models import load_cases

ALL = [c.case_id for c in load_cases()]


def case(cid, resolved=True, calls=1):
    exp = {"next_action": "submit_claim", "compensation_units": 420, "eligible": True,
           "cause_class": "carrier_controlled", "evidence_sufficient": True,
           "duty_of_care_units": 0, "downgrade_reimbursement_units": 0}
    got = dict(exp) if resolved else {**exp, "next_action": "close_no_claim"}
    return {"case_id": cid, "expected": exp, "got": got, "model_calls": calls,
            "flags": {"unsupported_claim": False, "unsupported_challenge": False,
                      "false_escalation": False, "missed_escalation": False}}


def part(cids, stage="p", **over):
    base = {"stage": stage, "system": "agent", "model": "m", "backend": "cli",
            "model_endpoint": "claude-cli", "first_party_model": True,
            "benchmark_digest": "d", "git_sha": "abc", "prompt_provenance": {},
            "timestamp": "2026-08-30T00:00:00+00:00",
            "cases": [case(c) for c in cids],
            "totals": {"model_calls": len(cids), "cost_usd": 1.0, "wall_clock_s": 10,
                       "task_input_tokens": 1, "output_tokens": 1,
                       "harness_overhead_tokens": 1}}
    return {**base, **over}


def test_two_parts_covering_the_benchmark_merge():
    a, b = ALL[:18], ALL[18:]
    out = merge([part(a, "final-v2"), part(b, "final-v2-gap")], "merged")
    assert out["metrics"]["n_cases"] == 28
    assert out["totals"]["cases_without_model_call"] == 0
    assert [p["stage"] for p in out["merged_from"]] == ["final-v2", "final-v2-gap"]


def test_a_case_covered_twice_is_refused():
    """Double-counting a case would let a good run be merged with itself."""
    with pytest.raises(MergeError, match="more than one part"):
        merge([part(ALL[:20]), part(ALL[15:])], "merged")


def test_incomplete_coverage_is_refused():
    with pytest.raises(MergeError, match="do not cover the benchmark"):
        merge([part(ALL[:18]), part(ALL[18:26])], "merged")


def test_different_endpoints_are_refused():
    """A gateway run and a first-party run must never be combined. See F-007."""
    with pytest.raises(MergeError, match="different endpoints"):
        merge([part(ALL[:18]),
               part(ALL[18:], model_endpoint="http://127.0.0.1:8082")], "merged")


def test_different_systems_are_refused():
    with pytest.raises(MergeError, match="disagree on system"):
        merge([part(ALL[:18]), part(ALL[18:], system="baseline")], "merged")


def test_different_models_are_refused():
    with pytest.raises(MergeError, match="disagree on model"):
        merge([part(ALL[:18]), part(ALL[18:], model="other")], "merged")


def test_unreached_cases_are_dropped_not_carried():
    """A case with no model call is not evidence of anything and must not be
    merged in as a failure. Here the second part 'covers' R19 with zero calls,
    so coverage is incomplete and the merge must refuse."""
    a = part(ALL[:18])
    b = part(ALL[18:], stage="gap")
    b["cases"][0]["model_calls"] = 0
    with pytest.raises(MergeError, match="do not cover the benchmark"):
        merge([a, b], "merged")


def test_totals_are_summed_across_parts():
    out = merge([part(ALL[:18]), part(ALL[18:])], "merged")
    assert out["totals"]["model_calls"] == 28
    assert out["totals"]["cost_usd"] == 2.0
