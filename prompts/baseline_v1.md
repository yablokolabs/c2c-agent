# Baseline prompt, v1

The simple, reasonable way to do this task before building an agent: one direct
prompt with the whole policy and the whole case file, asking for the answer.

No tools, no retrieval, no verification, no workflow, no memory. Same model,
same policy, same cases and same output schema as the agent, so the comparison
is fair. It is not deliberately weakened: it is given everything it needs in
one go, which is what a competent person would do first.

---

You are assessing a passenger's airline disruption compensation claim.

Apply the policy below. It is the only authority. It is a synthetic policy
written for this exercise; its thresholds and amounts differ from every real
compensation scheme, so do not substitute anything you know about real
regulations.

Work out, for the case you are given:

- whether the claim is in scope,
- whether the disruption qualifies,
- whether the cause was carrier-controlled or extraordinary,
- whether compensation is payable and how much,
- what duty of care and downgrade reimbursement, if any, is owed,
- whether the evidence on file is sufficient to decide,
- what the passenger should do next.

Reply with a single JSON object and nothing else:

```json
{
  "in_scope": true,
  "qualifies": true,
  "cause_class": "carrier_controlled | extraordinary | unknown",
  "eligible": true,
  "compensation_units": 420,
  "duty_of_care_units": 0,
  "downgrade_reimbursement_units": 0,
  "evidence_sufficient": true,
  "missing_evidence": [],
  "next_action": "submit_claim | request_evidence | challenge_rejection | escalate | accept_settlement | await_carrier | close_no_claim",
  "policy_citations": ["S2.1(a)", "S5.1"],
  "rationale": "two or three sentences stating why"
}
```

Rules for the fields:

- `compensation_units` is the Part 5 amount after every reduction, in whole
  units. Use `0` when nothing is payable. Use `null` only when the evidence is
  insufficient to compute an amount at all.
- `qualifies` and `eligible` may be `null` where the evidence does not settle
  them.
- `duty_of_care_units` and `downgrade_reimbursement_units` are separate from
  compensation and are never folded into it.
- `next_action` is the single most appropriate next step.

---

## THE POLICY

{policy}

---

## THE CASE

{dossier}
