"""The artifact is what the user actually receives, so the things that must
never be wrong are: the amounts must match the verdict, and it must always be
unmistakably synthetic."""

import pytest

from c2c.artifact import BANNER, case_summary, claim_letter
from c2c.models import Verdict, load_cases

CASES = {c.case_id: c for c in load_cases()}


def v(**over):
    base = dict(in_scope=True, qualifies=True, cause_class="carrier_controlled", eligible=True,
                compensation_units=420, duty_of_care_units=0, downgrade_reimbursement_units=0,
                evidence_sufficient=True, next_action="submit_claim",
                policy_citations=["S3.2(b)", "S5.1"],
                rationale="The crew timed out, which the policy puts within the airline's control.")
    return Verdict(**{**base, **over})


@pytest.mark.parametrize("render", [case_summary, claim_letter])
def test_every_artifact_is_stamped_synthetic(render):
    assert BANNER in render(CASES["R01"], v())


def test_the_letter_says_it_must_not_be_sent_to_a_real_airline():
    assert "must not be sent" in claim_letter(CASES["R01"], v())


def test_amounts_come_from_the_verdict_and_are_totalled():
    out = case_summary(CASES["R02"], v(compensation_units=0, eligible=False,
                                       duty_of_care_units=240))
    assert "240 units" in out
    assert "meals and accommodation" in out


def test_the_total_adds_every_head_of_claim():
    out = claim_letter(CASES["R28"], v(compensation_units=420, duty_of_care_units=170,
                                       next_action="accept_settlement"))
    assert "Total: 590 units" in out


def test_an_evidence_request_names_what_is_missing_and_gives_no_figure():
    out = case_summary(CASES["R09"], v(
        compensation_units=None, eligible=None, evidence_sufficient=False,
        next_action="request_evidence",
        missing_evidence=["S8.1(c) evidence of the actual arrival time at DOH"]))
    assert "not going to invent one" in out
    assert "actual arrival time at DOH" in out
    assert "420" not in out


def test_a_dead_end_case_says_so_plainly():
    out = case_summary(CASES["R13"], v(compensation_units=0, eligible=False,
                                       next_action="close_no_claim"))
    assert "nothing is payable" in out
    assert "nothing to claim" in out.lower()


def test_a_challenge_reads_as_a_challenge_not_a_fresh_claim():
    out = claim_letter(CASES["R12"], v(next_action="challenge_rejection"))
    assert "challenge your rejection" in out
    assert "Challenge to your rejection" in out


def test_the_letter_lists_the_documents_on_file():
    out = claim_letter(CASES["R21"], v())
    for d in CASES["R21"].documents:
        assert d.doc_id in out


def test_the_summary_promises_approval_before_anything_is_sent():
    assert "without your explicit approval" in case_summary(CASES["R01"], v())
