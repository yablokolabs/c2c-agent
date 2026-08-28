# Baseline prompt, v2

The simple, reasonable way to do this task before building an agent: one direct
prompt with the whole policy and the whole case file, asking for the answer.

v2 changes exactly one thing against v1: the field definitions below are now
explicit about what `in_scope` and `eligible` mean. v1 left both underspecified,
and the first baseline run showed four cases failing on that ambiguity alone
rather than on any reasoning error. See FAILURES.md F-002. Nothing else about
the prompt, the policy or the task changed, and the agent's prompts inherit the
same definitions, so the comparison stays fair.

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

Rules for the fields. These are definitions, not suggestions:

- `in_scope` means the claim satisfies every limb of S1.2. It is about the
  claim's admissibility, not its merits.
- `qualifies` means a disruption under Part 2 occurred. A claim can be in scope
  and not qualify.
- `eligible` means **Part 5 compensation is payable and greater than zero**. It
  is not a general judgement about whether the passenger deserves something. A
  passenger owed duty of care but no compensation is `eligible: false`. A
  passenger owed a downgrade reimbursement but no compensation is
  `eligible: false`.
- `compensation_units` is the Part 5 amount after every reduction, in whole
  units. Use `0` when nothing is payable. Use `null` only when the evidence is
  insufficient to compute an amount at all.
- `eligible` and `compensation_units` must agree: `true` with a positive
  amount, `false` with `0`, `null` with `null`.
- Any of `in_scope`, `qualifies` and `eligible` may be `null` where the
  evidence does not settle them.
- `duty_of_care_units` and `downgrade_reimbursement_units` are separate from
  compensation and are never folded into it. Give them as `0` when nothing is
  owed under Part 6 or Part 7.
- `next_action` is the single most appropriate next step.

---

## THE POLICY

{policy}

---

## THE CASE

{dossier}
