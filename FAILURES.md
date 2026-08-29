# Failure journal

Failures found while building C2C. Includes failures in C2C's own benchmark and
harness, which is where the first three came from — the baseline run's job was
to tell me something, and what it told me first was that my instrument was
faulty.

---

## F-001 — A `null` in one field discarded an otherwise correct verdict

| | |
|---|---|
| **Found** | baseline-v0, case R05 |
| **Commit** | `6471db6` |
| **Evidence** | `trajectories/runs/20260828T171341Z-baseline-v0-d7882c/events.jsonl` |

**Observed.** R05 scored zero on every component. The model had actually
produced a well-formed JSON verdict, and its reasoning on the decisive clause
was correct: it identified that the two segments were on separate booking
references under S2.3 and that the 55-minute delay at FRA fell short of S2.1(b).

**Expected.** A verdict that is wrong about the next action should lose points
for the next action, not for everything.

**Root cause.** `Verdict.in_scope` was typed `bool`, not `Optional[bool]`, while
its siblings `qualifies` and `eligible` were optional. The model answered
`"in_scope": null`, Pydantic rejected the whole object, and `run_case` returned
`None`, which the grader scores as a total loss.

This is not a model failure. It is my schema being stricter than my own ground
truth, which uses `null` for exactly this kind of undetermined field.

**Corrective change.** `in_scope` is now `Optional[bool]`, consistent with the
other determination fields.

**Outcome.** R05 now scores on its merits. It still fails, because it asks for a
boarding pass it does not need, but it fails for a real reason.

**Lesson.** A parse failure and a reasoning failure look identical in an
aggregate score. Any field the ground truth is allowed to leave undetermined
must be a field the schema allows the model to leave undetermined, or the
harness silently converts partial correctness into zero.

---

## F-002 — The primary metric contained a field that carried no information

| | |
|---|---|
| **Found** | baseline-v0, cases R06, R08, R10, R17 |
| **Commit** | `6471db6` |
| **Evidence** | `evaluation/results/baseline-v0--20260828T172034Z.json` |

**Observed.** Four of the five unresolved cases failed on `eligible` and on
nothing else. Every other component was correct in all four.

**Root cause.** Two problems, compounding.

The field was ambiguous. "Eligible" was never defined as eligible *for what*.
In R17 the passenger is owed 320 units of downgrade reimbursement and no Part 5
compensation; answering `true` is a defensible reading of an underspecified
question. Same in R06 and R08, where the claim is a valid claim that the notice
ladder reduces to zero.

Worse, the field was redundant. Checked against ground truth across all 20
cases, `eligible` is exactly `compensation_units > 0`, with `null` mapping to
`null`, in every single case. It carried no information the conjunction did not
already have.

So the third term of a three-term primary metric was measuring how a system
resolved an ambiguity in my own wording, and nothing else.

**Corrective change.** Case Resolution Accuracy is now:

> next action correct **and** compensation correct **and** other entitlements
> correct, where other entitlements means duty of care and downgrade
> reimbursement both correct.

Duty of care and downgrade are genuinely independent of the compensation figure
— R02, R16, R17, R19 all turn on them — and they are money the passenger
actually receives. `eligible` stays as a secondary rate, now defined in the
shared schema as `compensation_units > 0`.

**Re-scored from the saved run, with no new model calls:**

| Definition | Baseline CRA |
|---|---|
| action + compensation + eligible | 0.75 |
| action + compensation + entitlements | **0.90** |

Both numbers are reported. The change was made before the agent existed, and
the baseline is re-run under the new definition so both systems are scored
identically.

**Lesson.** Before trusting a conjunctive metric, check whether its terms are
independent. A term derivable from another term does not make the metric
stricter; it makes it noisier, and it moves the score around for reasons that
have nothing to do with the system under test.

---

## F-003 — The benchmark was nearly saturated by the baseline

| | |
|---|---|
| **Found** | baseline-v0, all cases |
| **Commit** | `6471db6` |
| **Evidence** | `evaluation/results/baseline-v0--20260828T172034Z.json` |

**Observed.** Under the corrected metric the baseline — one direct prompt, no
tools, no verification, no workflow — scores **0.90**. Its only genuine errors
are R05 and R16. Per component: the next action is wrong once in twenty, the
compensation figure is wrong once in twenty.

**Expected.** A benchmark with enough headroom that an agent can demonstrably
improve on the baseline, and enough sensitivity to detect a regression.

**Root cause.** The cases were written to cover the *situations* the brief
requires — cancellation, weather, missed connection, notice, evidence,
rejection, escalation — and not to be *hard*. Coverage and difficulty are
different axes, and I designed for one of them. A modern model handles a
five-document dossier and a two-step ladder in one pass without help.

This is a defect in the instrument, not a happy result. At 0.90 with 20 cases,
one case is 5 points of the metric and the measurement is mostly noise.

**Corrective change.** Eight cases added, `R21` to `R28`, targeting properties
that make single-pass reasoning fail *in general*, rather than cases picked
because a baseline got them wrong:

| Case | Difficulty property being tested |
|---|---|
| R21 | decisive fact buried in document 8 of 9, among plausible distractors |
| R22 | two composed reductions plus an exact band boundary |
| R23 | the answer depends on noticing a document that is **not** in the record |
| R24 | a scope rule no other case exercises, behind a strong merits distractor |
| R25 | itemised arithmetic, a non-reimbursable line item, and a cap |
| R26 | a rule whose scope is narrower than it first reads |
| R27 | a conflict the policy **does** resolve, paired against R11 where it does not |
| R28 | an action the policy never made reachable |

These were authored and committed **before** the agent was built and before
either system was run against them, and both systems are scored on the same 28.

**Honesty note.** Adding cases after seeing a baseline score is exactly the
shape of metric-gaming, so the constraints were fixed in advance: target
general difficulty properties rather than observed baseline errors, commit
before running anything, keep every original case, keep the original result
file, and report both the 20-case and 28-case numbers.

**Lesson.** Write the benchmark to be hard, then check it covers what it must.
Doing it the other way round produces a suite that is complete and uninformative,
and you do not find out until you have already spent the baseline run.

---

## F-004 — The policy made one outcome unreachable

| | |
|---|---|
| **Found** | while writing R28 |
| **Commit** | `6471db6` |

**Observed.** `accept_settlement` was a value in the `next_action` enum, was
listed in the consequential-actions set that requires human approval, and was
reachable by no case, because SHCP v1.0 never said when a settlement should be
accepted.

**Root cause.** The enum was written from the shape of the real-world process;
the policy was written from the shape of the entitlement rules. Neither was
checked against the other.

**Corrective change.** SHCP v1.1 adds S9.4: an offer meeting or exceeding the
full entitlement under Parts 5, 6 and 7 should be accepted, and an offer below
it is a partial settlement under S9.3. R28 exercises it.

**Lesson.** Every value a system can output needs a case that makes it the right
answer. An unreachable enum value is dead surface that will eventually be
emitted by accident, at which point nothing in the evaluation can tell you
whether it was correct.

---

## F-005 — Every durable step journalled an un-awaited coroutine

| | |
|---|---|
| **Found** | first durability run |
| **Commit** | `6524105` |
| **Evidence** | `TypeError: Object of type coroutine is not JSON serializable  /  Related command: run [assess]` |

**Observed.** The first workflow invocation wedged in a retry loop. Restate's
service log showed the assess step failing to serialise its result.

**Expected.** `ctx.run("assess", ...)` awaits the async HTTP call and journals
the response.

**Root cause.** `ctx.run` accepts either a sync or an async callable and
distinguishes them with `inspect.iscoroutinefunction`. That returns **False for
a lambda that merely returns a coroutine** — the lambda itself is an ordinary
function. So the SDK treated `lambda: _post(...)` as synchronous, took the
coroutine object as the step's result, and tried to journal it.

Every durable side effect in the workflow was written that way: assess, submit,
challenge, escalate. All four were broken, and none of them had ever run.

**Corrective change.** Real `async def` closures instead of lambdas.

**Outcome.** All six durability scenarios pass.

**Lesson.** An API that accepts "sync or async" is deciding which one you meant
by inspecting your callable, and a lambda hides the thing it inspects. The
symptom appeared three layers away from the cause, in a serialiser.

The wider miss is mine: **there was no test that would have caught this.** The
workflow's durable steps were only ever exercised end to end against a live
Restate server, so a bug in every one of them survived until the first
integration run. The unit tests covered the tools, the simulator and the
orchestration — everything except the layer that turned out to be wrong.

---

## F-006 — The agent was given a calculator and did not use it

| | |
|---|---|
| **Found** | EXP-001, `exp1-tools--20260829T070116Z.json` |
| **Commit** | `bc4e9b8` |
| **Evidence** | `trajectories/runs/20260829T064345Z-exp1-tools-89f2c7/events.jsonl` |

**Observed.** Across 28 cases the caseworker made **40 tool calls in total** —
1.4 per case — and called `calculate` **3 times**. Eleven cases made no tool
call at all and answered in a single step, structurally identical to the
baseline.

Both of the cases still failing after the tool loop, R16 and R25, fail on
duty-of-care arithmetic: a partial settlement, and a receipts total with a
non-reimbursable line and a cap. `calculate` was available on both and called on
neither.

**Expected.** The prompt already says, in its own numbered list: *"Compute, do
not estimate. Reductions compose. Use `calculate` for every arithmetic step,
including sums of receipts and each multiplication."*

**Root cause.** An instruction is a request, not a constraint. The model is
capable of the arithmetic and confident about it, so it does it in its head, and
nothing in the loop notices that a figure was asserted rather than computed.

This also undermines the attribution in EXP-001: an improvement measured on a
system whose tools were mostly unused cannot be credited to the tools.

**Corrective experiment.** EXP-005. A verdict that asserts money without ever
having called `calculate` is handed back once, with the arithmetic it owes.
Narrow deliberately: it fires only when there is money to check and the tool was
never called, at most once per case, and it never supplies or corrects a number.

**Lesson.** **Measure tool use, not just tool availability.** The gap between
"the agent has a calculator" and "the agent uses the calculator on the cases
that need arithmetic" is invisible in an aggregate score and obvious in a
trajectory. Every claim of the form "adding tool X improved the result" should
be checked against how often X was actually called, and on which cases.

And: if a behaviour matters, enforce it in the loop rather than asking for it in
the prompt. The prompt had already asked, in bold, with an example.
