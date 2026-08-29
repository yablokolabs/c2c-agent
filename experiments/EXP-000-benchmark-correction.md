# EXP-000 — Correcting the benchmark the baseline exposed

**Git SHA:** `9a65f78`
**Decision:** KEEP

## Hypothesis

None. This is not an experiment on the system; it is a repair of the instrument.
The baseline run was supposed to establish a starting point and instead
established that the measurement was not trustworthy.

## Motivation

The first baseline run reported Case Resolution Accuracy 0.75 on 20 cases. Three
things were wrong with that number, all found by reading the per-case output
rather than the aggregate:

1. One case scored zero on every component because the model answered
   `"in_scope": null` and the schema required a boolean. Its reasoning on the
   decisive clause was correct.
2. Four of the five unresolved cases failed on the `eligible` field and nothing
   else. Checked across all 20 cases, `eligible` is exactly
   `compensation_units > 0` — it carried no information the conjunction did not
   already have, and its wording was ambiguous.
3. With those corrected, the baseline scored 0.90. A benchmark a single prompt
   nearly solves cannot show improvement or detect regression.

Full write-ups in FAILURES.md F-001 through F-004.

## Change

- `Verdict.in_scope` became `Optional[bool]`, consistent with its siblings and
  with the ground truth, which uses `null` for undetermined fields.
- The primary metric's third term changed from `eligible` to entitlements —
  duty of care and downgrade reimbursement, which are independent of the
  compensation figure and are money the passenger receives.
- Prompt `baseline_v2` defines `in_scope`, `qualifies` and `eligible`
  explicitly. `baseline_v1` is kept.
- Policy SHCP v1.1 adds S9.4, making `accept_settlement` reachable. It had been
  a valid output with no case where it was correct.
- Eight cases added, R21 to R28, targeting properties that make single-pass
  reasoning fail generally: a decisive fact buried at document eight of nine,
  two composed reductions at an exact band boundary, an answer that depends on
  noticing an absent document, a scope rule no other case exercises, itemised
  arithmetic with an exclusion and a cap, a rule whose scope is narrower than it
  reads, a conflict the policy does resolve, and a settlement at exactly the
  full entitlement.

## Evaluation

Same harness. The metric change was applied by re-scoring the saved baseline
output with **no new model calls**, which isolates the definition change from
everything else.

## Before

| | |
|---|---|
| Cases | 20 |
| CRA (action + compensation + eligible) | **0.75** |
| Failed | R05, R06, R08, R10, R17 |
| Best constant guess | 0.25 |

## After

| | |
|---|---|
| CRA on the same saved output, entitlements instead of eligible | **0.90** |
| Cases | 28 |
| CRA re-run on 28 cases, `baseline-v1` | **0.68** |
| Failed | R04, R05, R16, R18, R24, R25, R26, R27, R28 |
| Best constant guess over the whole space of constant answers | 0.25 |

## Failed cases

Seven of the nine baseline failures on the 28-case suite are in the new hard
set. The remaining two, R04 and R16, are original cases the baseline had
previously passed — a reminder that a single run is a sample, not a measurement.

## Cost impact

The metric re-score cost nothing. The 28-case baseline re-run cost $1.14 against
$0.91 for the 20-case run.

## Decision

**KEEP.** The corrected 28-case suite with the entitlements metric is the
comparison point for every later experiment. Both the 20-case and 28-case
figures are reported.

## Learning

Two, and the second is the one that generalises.

**Check a conjunctive metric's terms for independence before trusting it.** A
term derivable from another does not make the metric stricter, it makes it
noisier, and the score moves for reasons unrelated to the system under test.

**Write the benchmark to be hard, then check it covers what it must — not the
other way round.** These cases were designed for *coverage* of the situations
the brief listed, and coverage and difficulty are different axes. The result was
a suite that was complete and uninformative, and that only became visible after
the baseline run had already been spent.

There is a real threat to validity in extending a benchmark after seeing a
baseline score. The constraints were fixed in advance: target general difficulty
properties rather than observed baseline errors, author and commit before the
agent existed, keep every original case and result file, and report both sets of
numbers. It is recorded here rather than smoothed over.
