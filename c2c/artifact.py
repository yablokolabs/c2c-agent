"""The thing the passenger actually receives.

A verdict is JSON. A passenger cannot send JSON to an airline. This renders the
assessment into the two documents a person actually needs: a plain-language
explanation of where they stand, and a claim they could put their name to.

Deterministic templating, no model call. The reasoning already happened; asking
a model to also write the letter would add a place for it to introduce a figure
that contradicts the verdict.

Every artifact carries the synthetic banner. Nothing here is legal advice and
nothing is for submission to a real carrier.
"""

from __future__ import annotations

from datetime import date

from c2c.models import Case, Verdict

BANNER = "SYNTHETIC DEMO — NOT FOR SUBMISSION — NOT LEGAL ADVICE"

ACTION_HEADLINE = {
    "submit_claim": "You have a claim worth making.",
    "request_evidence": "Almost there — a few things are missing.",
    "challenge_rejection": "The airline's refusal does not hold up. Challenge it.",
    "escalate": "The airline has run out of road. Take it to the regulator.",
    "accept_settlement": "The offer on the table is the full amount. Take it.",
    "await_carrier": "Your claim is with the airline. It is too early to escalate.",
    "close_no_claim": "On these facts there is nothing to claim.",
}

ACTION_NEXT = {
    "submit_claim": "Send the claim below to the airline, then expect to wait. "
                    "Under this policy they have 56 days before silence alone lets you escalate.",
    "request_evidence": "Send us the items listed and we will finish the assessment. "
                        "We are not guessing at a figure without them.",
    "challenge_rejection": "Send the challenge below. If they maintain the refusal, or say "
                           "nothing for 28 days, escalation becomes available.",
    "escalate": "We will lodge this with the Synthetic Passenger Rights Body once you approve.",
    "accept_settlement": "Confirm and we will accept on your behalf.",
    "await_carrier": "Nothing to do. We are holding the case and will act the moment the "
                     "clock runs out or the airline replies.",
    "close_no_claim": "No further action. The reasoning is above so you can check it yourself.",
}


def _money(units: int | None) -> str:
    return "not yet determined" if units is None else f"{units:,} units"


def case_summary(case: Case, v: Verdict) -> str:
    """Plain language. What a passenger reads first."""
    p = case.passenger
    lines = [
        f"# Your claim — booking {p['pnr']}",
        "",
        f"**{ACTION_HEADLINE.get(v.next_action, v.next_action)}**",
        "",
        "## Where you stand",
        "",
    ]

    total = (v.compensation_units or 0) + v.duty_of_care_units + v.downgrade_reimbursement_units
    if v.evidence_sufficient and total > 0:
        lines += [f"We assess that you are owed **{_money(total)}** in total:", ""]
        if v.compensation_units:
            lines.append(f"- **{_money(v.compensation_units)}** compensation for the disruption")
        if v.duty_of_care_units:
            lines.append(f"- **{_money(v.duty_of_care_units)}** for meals and accommodation")
        if v.downgrade_reimbursement_units:
            lines.append(f"- **{_money(v.downgrade_reimbursement_units)}** for the cabin downgrade")
        lines.append("")
    elif not v.evidence_sufficient:
        lines += [
            "We cannot put a figure on this yet, and we are not going to invent one. "
            "Here is what is missing:", "",
        ]
        lines += [f"- {m}" for m in v.missing_evidence] or ["- (unspecified)"]
        lines.append("")
    else:
        lines += ["On these facts, nothing is payable.", ""]

    lines += ["## Why", "", v.rationale or "(no rationale recorded)", ""]
    if v.policy_citations:
        lines += [
            "This rests on " + ", ".join(f"**{c}**" for c in v.policy_citations)
            + " of the C2C Synthetic Hackathon Compensation Policy.",
            "",
        ]
    if v.cause_class != "unknown":
        readable = "within the airline's control" if v.cause_class == "carrier_controlled" \
            else "an extraordinary circumstance"
        lines += [f"We classify the cause as **{readable}**.", ""]

    lines += [
        "## What happens next",
        "",
        ACTION_NEXT.get(v.next_action, ""),
        "",
        "Nothing is sent on your behalf without your explicit approval, every time.",
        "",
        "---",
        "",
        f"*{BANNER}*",
    ]
    return "\n".join(lines)


def claim_letter(case: Case, v: Verdict) -> str:
    """The document that would go to the carrier, if this were real."""
    p = case.passenger
    carrier = next(
        (line.split("Carrier:")[1].strip() for d in case.documents
         for line in d.content.splitlines() if "Carrier:" in line),
        "the carrier",
    )
    is_challenge = v.next_action == "challenge_rejection"
    subject = ("Challenge to your rejection of a compensation claim"
               if is_challenge else "Claim for compensation and expenses")

    lines = [
        f"**{BANNER}**", "",
        "---", "",
        f"**To:** {carrier}",
        f"**From:** {p['name']}",
        f"**Booking reference:** {p['pnr']}",
        f"**Date:** {date.today():%d %B %Y}",
        f"**Subject:** {subject}", "",
        "---", "",
    ]

    if is_challenge:
        lines += [
            "I am writing to challenge your rejection of my claim under booking "
            f"{p['pnr']}.", "",
            "Your decision rests on a ground that the operational record you hold does not "
            "support. The relevant documents are on file and are listed below.", "",
        ]
    else:
        lines += [
            f"I am claiming compensation and expenses in respect of booking {p['pnr']}.", "",
        ]

    # The passenger's own account, quoted rather than paraphrased. Rewriting it
    # would need a model call and would put words in their mouth.
    quoted = "\n".join(f"> {line}" for line in case.narrative.strip().splitlines())
    lines += ["**The disruption, in my own words**", "", quoted, "",
              "**What I am claiming**", ""]
    if v.compensation_units:
        lines.append(f"- Compensation: **{_money(v.compensation_units)}**")
    if v.duty_of_care_units:
        lines.append(f"- Duty of care, against the receipts enclosed: "
                     f"**{_money(v.duty_of_care_units)}**")
    if v.downgrade_reimbursement_units:
        lines.append(f"- Downgrade reimbursement: **{_money(v.downgrade_reimbursement_units)}**")
    total = (v.compensation_units or 0) + v.duty_of_care_units + v.downgrade_reimbursement_units
    lines += ["", f"**Total: {_money(total)}**", "", "**On what basis**", "",
              v.rationale or "(no rationale recorded)", ""]
    if v.policy_citations:
        lines += ["The provisions relied on are "
                  + ", ".join(f"**{c}**" for c in v.policy_citations) + ".", ""]

    lines += ["**Documents on file**", ""]
    lines += [f"- {d.doc_id} — {d.type.replace('_', ' ')}" for d in case.documents]
    lines += [
        "",
        "I look forward to your response.", "",
        p["name"], "",
        "---", "",
        f"**{BANNER}**", "",
        "This document was produced by an automated system against an invented "
        "compensation policy, for a demonstration. It is not legal advice, it is not "
        "addressed to any real airline, and it must not be sent to one.",
    ]
    return "\n".join(lines)
