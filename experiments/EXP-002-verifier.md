# EXP-002 — Does an independent verifier earn its cost?

**Git SHA:** `24c35e2` (built), measured at `final-v2`
**Decision:** KEEP

## Hypothesis

A second model, given the same case and the same policy but **not** the
caseworker's working, will catch arithmetic and rule-scope errors that the
caseworker commits confidently — and will do so without manufacturing errors in
verdicts that were already right.

The second half is the risk. A verifier that rejects on preference costs a
revision round and can talk a correct caseworker out of a correct answer.

## Motivation

After the tool loop, the remaining failures clustered on duty-of-care arithmetic
— a partial settlement (R16) and a receipts total with an exclusion and a cap
(R25). Those are exactly the errors a fresh reader with the same policy should
catch, because they need no context beyond the case file.

## Change

A verifier that receives the case and the policy, works the case out itself, then
compares against the caseworker's verdict. On rejection the case goes back for
**one** revision, carrying the verifier's findings.

Two constraints, both aimed at the second half of the hypothesis:

- a rejection citing no clause and no document is **downgraded to a pass**,
  because an uncited rejection is a preference;
- an unreadable verifier **fails open**, because one that cannot state a decision
  has not found anything.

The verifier never sees the caseworker's transcript. Sharing it would make it a
reviewer of one chain of reasoning rather than a second opinion on the case, and
it would inherit any wrong turn.

## Evaluation

28 cases, same model, same policy, same dossiers, same grader, same first-party
endpoint as the baseline.

## Before / After

| | baseline-v2 | final-v2 (merged) | change |
|---|---|---|---|
| **Case Resolution Accuracy** | 0.82 | **0.93** | **+0.11** |
| Action accuracy | 0.86 | 0.93 | +0.07 |
| Compensation accuracy | 1.00 | 1.00 | 0 |
| **Duty of care accuracy** | 0.96 | **1.00** | +0.04 |
| **Evidence sufficiency** | 0.89 | **0.93** | +0.04 |
| Unsupported claims | 0 | **0** | 0 |
| Unsupported challenges | 0 | **0** | 0 |
| False escalations | 0 | **0** | 0 |
| Model calls | 28 | 102 | **3.6x** |
| Cost | $1.37 | $3.77 | **2.8x** |

Fixed: R01, R04, R05, R16, R18. Broken: R07, R26.

## The evidence that isolates the verifier

**R16 is the case that carries this experiment.** A partial settlement: the
carrier paid duty of care and refused compensation on a weather ground its own
operations log contradicts. It requires noticing S9.3, applying S3.6, and getting
two separate money figures right.

It failed under the baseline. It failed under tools-only (`exp1-tools`, where it
was one of only two remaining failures). It **passes** with the verifier.

The metric shape agrees: the gains are concentrated in duty of care (0.96 → 1.00)
and evidence sufficiency (0.89 → 0.93), while compensation accuracy was already
1.00 in both and did not move. That is the signature of a second reader checking
arithmetic and re-reading a clause, not of a system reasoning differently.

## Failed cases

**R07 and R26 regressed** — both cases the baseline got right.

R26 is the interesting one: denied boarding with a 4h20m arrival delay, where
S5.4's taper looks applicable and is not, because it is confined to claims
qualifying under S2.1(b) and this one qualifies under S2.1(c). A verifier
"correcting" a correct caseworker toward the more obvious reading is precisely
the failure mode the downgrade-and-fail-open guards were built to limit, and they
did not catch this one because the rejection *did* cite a clause — the wrong one.

Two regressions against five fixes is a net win and a real cost.

## Cost impact

+$2.40 per run, 3.6x the model calls, 7.4x the wall clock. Per case that is about
$0.13 against $0.05. For a claim worth 420 units, the cost is not the constraint;
for a claims operation running thousands, it would be.

## Decision

**KEEP.** It is the largest measured contribution on the reasoning axis, the
failure-mode counters stayed at zero, and R16 is direct evidence that it fixes
something tools alone did not.

## Learning

**Independence is the active ingredient, not review.** The verifier's value came
from being made to reach its own conclusion before seeing the caseworker's — a
reviewer handed the working would likely have agreed with it, since the working
is persuasive and internally consistent. That is a cheap design decision with a
large effect, and it is the opposite of what "add a checking step" usually means.

The honest counterweight: **+0.11 is three cases and this project has no valid
variance estimate.** The one it had was withdrawn in F-008. The direction is
supported by a mechanism (R16, and the metric shape), which is worth more here
than the magnitude.
