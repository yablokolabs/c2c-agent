"""Metric definitions for the C2C benchmark.

Fixed before any system was evaluated. Every metric below is computed
identically for the baseline and for the agent.

PRIMARY METRIC — Case Resolution Accuracy (CRA)
    A case counts as resolved only if the system got all three of the things a
    passenger actually needs right, at once:
      1. the recommended next action,
      2. the compensation figure (including correctly declining to give one),
      3. the eligibility determination.
    Partial credit is not given, because a case handled with the right action
    and the wrong amount is still a case handled wrongly.

The three-way conjunction is deliberate. Any of the components on its own is
easy to score well on by guessing the majority class, and a passenger is not
helped by a system that is right about eligibility and wrong about what to do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from c2c.models import Case, Verdict


@dataclass
class CaseScore:
    case_id: str
    resolved: bool
    action_correct: bool
    compensation_correct: bool
    eligibility_correct: bool
    cause_correct: bool
    evidence_correct: bool
    duty_of_care_correct: bool
    downgrade_correct: bool
    unsupported_claim: bool
    unsupported_challenge: bool
    false_escalation: bool
    missed_escalation: bool
    expected: dict = field(default_factory=dict)
    got: dict = field(default_factory=dict)


def score_case(case: Case, v: Optional[Verdict]) -> CaseScore:
    """Score one verdict. A missing or unparseable verdict scores zero on
    everything and is counted as an unsupported claim only if it is absent,
    never as a correct abstention."""
    gt = case.ground_truth

    if v is None:
        return CaseScore(
            case_id=case.case_id,
            resolved=False,
            action_correct=False,
            compensation_correct=False,
            eligibility_correct=False,
            cause_correct=False,
            evidence_correct=False,
            duty_of_care_correct=False,
            downgrade_correct=False,
            unsupported_claim=False,
            unsupported_challenge=False,
            false_escalation=False,
            missed_escalation=gt.next_action == "escalate",
            expected=gt.model_dump(),
            got={"error": "no parseable verdict"},
        )

    action_correct = v.next_action == gt.next_action
    compensation_correct = v.compensation_units == gt.compensation_units
    eligibility_correct = v.eligible == gt.eligible

    # An unsupported claim is a number asserted where the evidence does not
    # support one. Ground truth marks those cases with a null amount.
    unsupported_claim = gt.compensation_units is None and v.compensation_units is not None

    # Challenging or escalating against a case where the carrier was right, or
    # where there is nothing to challenge.
    challenge_actions = {"challenge_rejection", "escalate"}
    gt_challengeable = gt.next_action in challenge_actions
    unsupported_challenge = v.next_action in challenge_actions and not gt_challengeable

    false_escalation = v.next_action == "escalate" and gt.next_action != "escalate"
    missed_escalation = gt.next_action == "escalate" and v.next_action != "escalate"

    return CaseScore(
        case_id=case.case_id,
        resolved=action_correct and compensation_correct and eligibility_correct,
        action_correct=action_correct,
        compensation_correct=compensation_correct,
        eligibility_correct=eligibility_correct,
        cause_correct=v.cause_class == gt.cause_class,
        evidence_correct=v.evidence_sufficient == gt.evidence_sufficient,
        duty_of_care_correct=v.duty_of_care_units == gt.duty_of_care_units,
        downgrade_correct=v.downgrade_reimbursement_units == gt.downgrade_reimbursement_units,
        unsupported_claim=unsupported_claim,
        unsupported_challenge=unsupported_challenge,
        false_escalation=false_escalation,
        missed_escalation=missed_escalation,
        expected={
            "next_action": gt.next_action,
            "compensation_units": gt.compensation_units,
            "eligible": gt.eligible,
            "cause_class": gt.cause_class,
            "evidence_sufficient": gt.evidence_sufficient,
            "duty_of_care_units": gt.duty_of_care_units,
            "downgrade_reimbursement_units": gt.downgrade_reimbursement_units,
        },
        got={
            "next_action": v.next_action,
            "compensation_units": v.compensation_units,
            "eligible": v.eligible,
            "cause_class": v.cause_class,
            "evidence_sufficient": v.evidence_sufficient,
            "duty_of_care_units": v.duty_of_care_units,
            "downgrade_reimbursement_units": v.downgrade_reimbursement_units,
        },
    )


def aggregate(scores: list[CaseScore]) -> dict:
    n = len(scores)
    if n == 0:
        raise ValueError("no scores to aggregate")

    def rate(attr: str) -> float:
        return round(sum(getattr(s, attr) for s in scores) / n, 4)

    def count(attr: str) -> int:
        return sum(getattr(s, attr) for s in scores)

    return {
        "n_cases": n,
        "case_resolution_accuracy": rate("resolved"),
        "action_accuracy": rate("action_correct"),
        "compensation_accuracy": rate("compensation_correct"),
        "eligibility_accuracy": rate("eligibility_correct"),
        "cause_accuracy": rate("cause_correct"),
        "evidence_sufficiency_accuracy": rate("evidence_correct"),
        "duty_of_care_accuracy": rate("duty_of_care_correct"),
        "downgrade_accuracy": rate("downgrade_correct"),
        "unsupported_claims": count("unsupported_claim"),
        "unsupported_rejection_challenges": count("unsupported_challenge"),
        "false_escalations": count("false_escalation"),
        "missed_escalations": count("missed_escalation"),
        "failed_cases": [s.case_id for s in scores if not s.resolved],
    }
