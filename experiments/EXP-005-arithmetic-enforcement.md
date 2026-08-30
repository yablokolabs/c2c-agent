# EXP-005 — Enforce the arithmetic tool instead of asking for it

**Git SHA:** `0b7bac4`
**Decision:** BUILT, NOT MEASURED

## Hypothesis

A caseworker that has asserted a compensation figure without ever calling
`calculate` has done the arithmetic in its head. Handing that verdict back once,
with the arithmetic it owes, will fix the duty-of-care cases that fail on
composed reductions and capped receipt totals.

## Motivation

F-006, measured directly from the trajectory. Across 28 cases the caseworker made
**40 tool calls in total** — 1.4 per case — and called `calculate` **three
times**. Both cases still failing after the tool loop, R16 and R25, fail on
arithmetic. `calculate` was available on both and called on neither.

The prompt already said, in its own numbered list, in bold, with an example:
*"Compute, do not estimate. Reductions compose. Use `calculate` for every
arithmetic step, including sums of receipts and each multiplication."*

It read that and did the sums in its head anyway. **An instruction is a request,
not a constraint.**

## Change

`ENFORCE_ARITHMETIC`, off by default, registered as its own evaluation system
(`agent-enforced`) so the A/B is clean. A verdict asserting a non-zero amount
without any `calculate` call is returned once with the arithmetic it owes.

Deliberately narrow:

- fires only when there is money to check **and** the tool was never called;
- fires **at most once** per case, so the loop cannot wedge;
- never supplies or corrects a number — it only makes the agent do the step it
  skipped;
- the prompt for the retry says the figures may well be right, and to change them
  only if the arithmetic says so.

Five tests cover the enforcement path, including that it does not fire when
nothing is owed, does not fire when `calculate` was already used, and cannot fire
twice.

## Evaluation

**Not run.** The backend's sustained-throughput ceiling (F-009) consumed the
available budget on the baseline and the full agent, and an ablation is worth
less than the headline comparison it would be measured against.

## Before / After

Not applicable. The code is written, tested and registered; no number is claimed
for it, and none is implied.

## Decision

**BUILT, NOT MEASURED.** Recorded as an unrun experiment rather than folded into
the results or quietly dropped.

The prediction, stated in advance so it can be checked later: it should fix R25,
which fails on a receipts total with a non-reimbursable line and a 300-unit cap
— three arithmetic steps the model currently performs unaided. It should not move
R07 or R26, which fail on rule scope rather than arithmetic. If it moves those,
the mechanism is not what this experiment claims.

## Learning

Available before running anything: **measure tool use, not tool availability.**
The gap between "the agent has a calculator" and "the agent uses the calculator
on the cases that need arithmetic" is invisible in an aggregate score and obvious
in a trajectory, and it undermined the attribution in EXP-001 entirely.

The design lesson is the one the code encodes: if a behaviour matters, enforce it
in the loop rather than asking for it in the prompt. The prompt had already
asked, in bold, with an example.
