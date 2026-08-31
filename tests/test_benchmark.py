"""The benchmark is an artifact in its own right, so it gets its own tests."""

import json
from pathlib import Path

import pytest

from c2c.eval.metrics import aggregate, score_case
from c2c.models import Verdict, load_cases

CASES = load_cases()


def test_all_cases_present_and_contiguous():
    assert len(CASES) == 28
    assert {c.case_id for c in CASES} == {f"R{i:02d}" for i in range(1, 29)}


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


def test_no_constant_guess_scores_well():
    """The strongest possible constant answer must still score badly, or the
    primary metric is not measuring anything. This searches the whole space of
    constant answers rather than checking one hand-picked guess."""
    actions = {c.ground_truth.next_action for c in CASES}
    amounts = {c.ground_truth.compensation_units for c in CASES}
    doc_amounts = {c.ground_truth.duty_of_care_units for c in CASES}
    best = 0.0
    for action in actions:
        for amount in amounts:
            for doc in doc_amounts:
                agg = aggregate([
                    score_case(c, Verdict(
                        compensation_units=amount,
                        duty_of_care_units=doc,
                        evidence_sufficient=True,
                        next_action=action,
                    ))
                    for c in CASES
                ])
                best = max(best, agg["case_resolution_accuracy"])
    assert best <= 0.30, f"best constant guess scores {best}, benchmark is too guessable"


def test_missing_verdict_scores_zero():
    s = score_case(CASES[0], None)
    assert not s.resolved and not s.action_correct


def test_a_dropped_case_is_visible_not_just_scored():
    """A case the model never saw is not a case it got wrong. The grader cannot
    tell them apart, so the harness has to surface the count. See F-008."""
    import inspect

    from c2c.eval import run

    src = inspect.getsource(run.main)
    assert "cases_without_model_call" in src
    assert "never reached the model" in src, "a dropped case must produce a visible warning"


def test_a_benchmark_case_without_ground_truth_is_refused(tmp_path):
    """ground_truth is optional on the model so live intake cases can exist
    without a fabricated one — but a *benchmark* case missing it must fail
    loudly rather than score as unresolvable."""
    import json

    from c2c.models import load_cases as load

    good = json.loads((Path("benchmark/cases") / "R01.json").read_text())
    good.pop("ground_truth")
    (tmp_path / "R01.json").write_text(json.dumps(good))
    with pytest.raises(ValueError, match="without ground truth"):
        load(tmp_path)


def test_a_live_case_may_have_no_ground_truth():
    from c2c.models import Case, Document

    c = Case(case_id="LIVE-1", title="from a passenger", difficulty="medium", tags=["live"],
             passenger={"name": "A. Passenger", "pnr": "ABC123"},
             narrative="my flight was cancelled",
             documents=[Document(doc_id="D1", type="booking_confirmation", content="...")])
    assert c.ground_truth is None
    assert "my flight was cancelled" in c.dossier()
