"""The benchmark is an artifact in its own right, so it gets its own tests."""

import json
from pathlib import Path

import pytest

from c2c.eval.metrics import aggregate, score_case
from c2c.models import Verdict, load_cases

CASES = load_cases()


def test_twenty_cases_present():
    assert len(CASES) == 20
    assert {c.case_id for c in CASES} == {f"R{i:02d}" for i in range(1, 21)}


def test_required_coverage():
    """CLAUDE.md names the situations the benchmark has to cover."""
    tags = {t for c in CASES for t in c.tags}
    for required in [
        "eligible_cancellation",
        "weather_extraordinary",
        "operational_disruption",
        "missed_connection",
        "advance_notice",
        "missing_evidence",
        "invalid_rejection",
        "valid_rejection",
        "evidence_request",
        "conflicting_documents",
        "partial_settlement",
        "adversarial",
    ]:
        assert required in tags, f"benchmark does not cover {required}"


def test_no_single_action_dominates():
    """Guard against a benchmark a constant guesser could score well on."""
    from collections import Counter

    counts = Counter(c.ground_truth.next_action for c in CASES)
    assert counts.most_common(1)[0][1] / len(CASES) <= 0.40


def test_ground_truth_is_internally_consistent():
    for c in CASES:
        gt = c.ground_truth
        if not gt.evidence_sufficient:
            assert gt.next_action == "request_evidence", c.case_id
            assert gt.compensation_units is None, c.case_id
            assert gt.missing_evidence, c.case_id
        else:
            assert gt.compensation_units is not None, c.case_id
            assert not gt.missing_evidence, c.case_id
        if gt.eligible is False:
            assert gt.compensation_units == 0, c.case_id
        if gt.eligible is True:
            assert gt.compensation_units and gt.compensation_units > 0, c.case_id
        assert gt.derivation, c.case_id


def test_every_derivation_cites_a_real_policy_clause():
    policy = Path("benchmark/POLICY.md").read_text()
    import re

    cited = {
        m
        for c in CASES
        for step in c.ground_truth.derivation
        for m in re.findall(r"\bS\d+\.\d+(?:\([a-g]\))?", step)
    }
    assert cited, "no clauses cited anywhere"
    for clause in sorted(cited):
        assert f"**{clause}**" in policy, f"derivation cites {clause}, which is not in POLICY.md"


def test_dossier_never_leaks_ground_truth():
    for c in CASES:
        d = c.dossier()
        for step in c.ground_truth.derivation:
            assert step not in d, f"{c.case_id} dossier leaks its derivation"
        assert "ground_truth" not in d


def test_perfect_verdicts_score_one():
    scores = []
    for c in CASES:
        gt = c.ground_truth
        v = Verdict(**{k: getattr(gt, k) for k in Verdict.model_fields if hasattr(gt, k)})
        scores.append(score_case(c, v))
    agg = aggregate(scores)
    assert agg["case_resolution_accuracy"] == 1.0
    assert agg["unsupported_claims"] == 0
    assert agg["false_escalations"] == 0


def test_constant_guesser_scores_poorly():
    """A system that always says 'submit the claim for 420 units' must not
    look good, or the primary metric is not measuring anything."""
    scores = [
        score_case(
            c,
            Verdict(
                in_scope=True,
                eligible=True,
                compensation_units=420,
                evidence_sufficient=True,
                next_action="submit_claim",
            ),
        )
        for c in CASES
    ]
    assert aggregate(scores)["case_resolution_accuracy"] <= 0.10


def test_missing_verdict_scores_zero():
    s = score_case(CASES[0], None)
    assert not s.resolved and not s.action_correct
