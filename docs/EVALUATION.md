# Evaluation

Two suites, measured separately, because a system can be good at one and bad at
the other and a passenger needs both.

---

## Suite A — reasoning

28 synthetic cases, single-turn. Same model, same policy, same dossier, same
output schema for every system. `benchmark/cases/R01..R28.json`.

### Primary metric — Case Resolution Accuracy

A case counts as **resolved** only when all three are correct at once:

1. `next_action` — what the passenger should do next
2. `compensation_units` — the Part 5 figure, including correctly returning
   `null` where the evidence cannot settle it
3. **other entitlements** — `duty_of_care_units` and
   `downgrade_reimbursement_units` both correct

No partial credit. A case with the right amount and the wrong action does not
get the passenger paid.

**The third term changed once, before the agent existed.** It was originally
the eligibility flag. Checked across every case, that flag is exactly
`compensation_units > 0`, so it added noise to the conjunction rather than
strictness, and four of the first baseline's five failures were on it alone.
Entitlements are independent of the compensation figure and are money the
passenger receives. Full account in FAILURES.md F-002; both numbers are
reported.

### Reference floors

Read the primary metric against these, not against zero.

| | CRA |
|---|---|
| Best constant answer, searched over every (action, amount, duty-of-care) triple | **0.25** |
| Always "submit the claim, 420 units" | 0.10 |

A test in `tests/test_benchmark.py` asserts no constant answer exceeds 0.30, so
the suite cannot silently drift into being guessable.

### Secondary metrics

| Metric | What it catches |
|---|---|
| action accuracy | the recommendation alone |
| compensation accuracy | the figure alone |
| eligibility accuracy | retained as a rate after being dropped from the primary |
| cause classification accuracy | carrier-controlled vs extraordinary |
| evidence sufficiency accuracy | knowing when it cannot decide |
| duty of care accuracy | Part 6 |
| downgrade accuracy | Part 7 |
| **unsupported claims** | a compensation figure asserted where the evidence supports none. The worst failure mode here: the passenger acts on it. |
| **unsupported rejection challenges** | challenging or escalating where the carrier was right |
| **false escalations** | escalating before the policy's clock allows it |
| missed escalations | failing to escalate when it is ripe |
| model calls, wall clock, tokens, cost | what it takes to run |

Tokens are split into `task_input_tokens` and `harness_overhead_tokens`, because
the CLI backend adds a system prompt C2C did not author and should not claim.

### What "good" looked like, fixed before running anything

From `docs/PROBLEM.md`, written before the first evaluation:

- CRA above 0.80
- zero unsupported claims
- zero unsupported challenges and zero false escalations
- zero duplicate consequential actions under crash and retry

---

## Suite B — durability

Six failure-injection scenarios, no model calls.
`python -m c2c.eval.durability`.

| Metric | Definition |
|---|---|
| workflow completion | reached the expected state after the injected failure |
| failure recovery | made progress after the failure rather than wedging |
| state preservation | case state and verdict survived a `kill -9` |
| **duplicate consequential actions** | actions that **landed** at the carrier beyond the one intended |

Ground truth is the synthetic airline's audit log, which separates actions
*attempted* from actions that *landed*. That separation is the measurement:
without it, exactly-once is an assertion.

### The baseline scores nothing here, and that is not reported as a win

The baseline is a single prompt with no lifecycle, so there is nothing for a
crash to interrupt. Suite B measures whether Restate delivers the invariants it
was added for — not whether an agent beats a prompt.

---

## Fairness

What both systems get, identically:

- the same model (`claude-haiku-4-5-20251001`) and the same backend
- the same policy document, in a cached system prompt
- the same full case dossier — every document, the passenger's account, the
  carrier response
- the same output schema with the same field definitions
- the same grader

What the agent gets extra, and nothing else: four tools, up to ten steps, and an
independent verifier with one revision round.

The baseline is not weakened. It is given everything it needs in one call, which
is what a competent person would do first. Its prompt is version-controlled at
`prompts/baseline_v2.md`.

---

## Provenance

Every result file records the commit, the model, the backend, the digest of the
28 case files, the digest of every prompt, the Python version and the trajectory
run id. Result files are never overwritten — the harness raises rather than
clobber one.

```bash
python -c "import json;d=json.load(open('evaluation/results/final-v1--....json'));print(d['git_sha'],d['prompt_provenance'])"
```

## Known weaknesses

Stated in full in `docs/LIMITATIONS.md`. The three that matter most when reading
any number here:

- **28 cases means one case is 3.6 points.** Differences under about 0.07 are
  not distinguishable from sampling noise, and every configuration was run once.
  No figure in this repository carries a confidence interval.
- **Ground truth is one author's reading**, with no inter-annotator agreement
  measured, so the metric's ceiling is unknown. Some scored error may be
  disagreement.
- **The benchmark was extended after the first baseline run.** Handled with
  pre-committed constraints and both sets of numbers reported, but it remains a
  threat to validity.
