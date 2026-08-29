# EXP-001 — Does a tool-using loop beat a single prompt?

**Git SHA:** `bc4e9b8`
**Decision:** KEEP, with the attribution stated honestly

## Hypothesis

The baseline fails on cases that need attention the single pass does not give:
a decisive fact buried deep in a long dossier, arithmetic that composes across
several reductions, and answers that depend on noticing a document is *absent*.
Giving the caseworker document-level retrieval, clause lookup, exact arithmetic
and more than one step should fix those.

## Motivation

Seven of the baseline's nine failures were in the hard set added in EXP-000,
which was built around exactly those three properties.

## Change

Caseworker gets four tools — `list_documents`, `read_document`, `policy_lookup`,
`calculate` — and up to ten steps, replying with one JSON object per turn that is
either a tool call or a verdict.

Everything else is held constant: same model, same policy, same full dossier,
same output schema and the same field definitions as `baseline_v2`. **No tool
returns a verdict**; they retrieve and compute, and the model decides.

## Evaluation

`python -m c2c.eval.run --system agent-tools --stage exp1-tools`, same 28 cases,
same grader.

## Before / After

| | baseline-v1 | exp1-tools | change |
|---|---|---|---|
| **Case Resolution Accuracy** | 0.68 | **0.86** | **+0.18** |
| Action accuracy | 0.71 | 0.89 | +0.18 |
| Compensation accuracy | 0.79 | 0.93 | +0.14 |
| Evidence sufficiency | 0.71 | 0.89 | +0.18 |
| Duty of care accuracy | 0.75 | 0.93 | +0.18 |
| Unsupported claims | 0 | 0 | 0 |
| False escalations | 0 | 0 | 0 |
| Model calls | 23 | 73 | +50 |
| Wall clock | 395 s | 1050 s | +166% |
| Cost | $1.14 | $2.60 | +$1.46 |

Fixed: R04, R05, R18, R24, R26, R27, R28.
Broken: R03, R08.
Still failing: R16, R25.

## The attribution is weaker than the headline

The trajectory shows what actually happened, and it does not support a clean
claim that the tools caused the gain.

**40 tool calls across 28 cases — 1.4 per case. `calculate` fired 3 times in
28 cases**, despite arithmetic being one of the three properties the hard set
was built around. The model mostly did the arithmetic in its head and mostly did
not look anything up.

Splitting the cases by whether any tool was called at all:

| | n | baseline | exp1 | fixed | broken |
|---|---|---|---|---|---|
| **used no tools** | 11 | 8/11 | 10/11 | 2 | 0 |
| **used tools** | 17 | 11/17 | 14/17 | 5 | 2 |

Eleven cases answered in a single step with no tool call — structurally
identical to what the baseline did — and **two of them flipped from fail to
pass anyway** (R26, R28). Those two cannot be attributed to tools. They are
attributable to the different system prompt, to sampling, or to both.

So of the five net cases behind +0.18, **at most three are even plausibly
attributable to tool use**, which is +0.11 — and with 28 cases, one run per
configuration and no confidence interval, that is close to the noise floor.

The variance control run (`baseline-v1-repeat`) is recorded in the changelog and
puts a number on that noise floor.

## Failed cases

**R03 and R08 regressed** — both cases the baseline got right. R08 is the
easiest case in the suite (25 days notice, no compensation). A system that
gains five cases and loses two, one of them the easiest in the set, is not
behaving like a system that has learned the rule; it is behaving like a system
sampling near a boundary.

R16 and R25 fail in both. Both are duty-of-care arithmetic: R16's partial
settlement and R25's cap-with-an-exclusion. `calculate` existed and was not
called on either.

## Cost impact

+$1.46 per run, 3.2× the model calls, 2.7× the wall clock, for +0.18 nominal.

## Decision

**KEEP.** The direction is right, the failure-mode counters stayed at zero, and
the loop is the substrate the verifier needs. But it is kept as *loop plus
tools*, not as *tools*, because the evidence does not separate them.

## Learning

**Giving an agent a tool is not the same as the agent using it.** The tools were
designed against three specific difficulty properties and were then largely
ignored — most visibly `calculate`, which went unused on both of the two cases
that fail *because of arithmetic*.

The honest reading is that most of the gain here is the multi-step loop and the
prompt, not the retrieval. A cleaner experiment would have run the same prompt
and loop with the tools removed, isolating them properly. That control was not
run, and the attribution is reported as unresolved rather than assumed.

Second lesson, cheaper: a benchmark this size cannot support confident
attribution from one run per configuration. Two of five flips landing in cases
that used no tools is the kind of thing that only shows up if you look at the
trajectory instead of the aggregate.
