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

---

## F-007 — A gateway served a different model, and nothing in the results said so

| | |
|---|---|
| **Found** | reviewing an evening of runs that all looked like ordinary bad results |
| **Commit** | `fbcae5e` (introduced), fixed on `main` |
| **Evidence** | `evaluation/results/baseline-v1--20260830T01*.json`, `.worktrees/fix-llm-backend/` |

**Observed.** After the `claude -p` CLI began refusing calls
(`claude -p exited 1`, 28/28 cases), the harness was pointed at a local gateway
via `ANTHROPIC_BASE_URL=http://127.0.0.1:8082` plus `ANTHROPIC_AUTH_TOKEN`. Runs
started completing again. They also got much worse, and the *baseline* got worse
too:

| Run | Endpoint | CRA | Output tokens/call |
|---|---|---|---|
| baseline-v1 | CLI | **0.68** | 7,990 |
| baseline-v1-repeat | CLI | **0.75** | 7,470 |
| baseline-v1 | gateway | **0.29** | 2,824 |
| baseline-v1 | gateway | **0.36** | 2,744 |

**Expected.** Changing transport should not change the baseline. The baseline
halving is the tell: no change had been made to the baseline at all.

**Root cause.** The gateway (`fcc-server`, "free-claude-code") serves 186 models,
mostly `nvidia_nim/*` open weights. It does **not** carry
`claude-haiku-4-5-20251001` — it has `claude-haiku-4-20250514`,
`claude-3-haiku-20240307` and `claude-3-5-haiku-20241022`, and nothing newer. A
request naming `claude-haiku-4-5-20251001` was answered by something else.

Meanwhile every result file recorded `"model": "claude-haiku-4-5-20251001"`,
because that field logged what was *requested*. **The provenance was
technically true and completely misleading.**

There was a second, quieter half. With `ANTHROPIC_BASE_URL` exported in the
parent shell, the `claude` CLI subprocess inherited it and routed through the
gateway too. So the `cli` backend silently stopped being the CLI backend, which
is why CLI-labelled runs also came back at 0.43 and 0.54 instead of 0.68–0.75.

**Corrective change.**

- Every result now records `model_endpoint` and `first_party_model`. The harness
  prints a warning when calls are not going to Anthropic, and the report refuses
  to compare two runs whose endpoints differ.
- `_cli_env()` strips every `ANTHROPIC_*` variable from the CLI subprocess, so
  the CLI backend is the CLI backend regardless of the parent shell.
- Calls are paced (1s default, `C2C_MIN_CALL_INTERVAL`) across all instances and
  worker threads, since the refusals were load-driven.

**Outcome.** Every gateway-era number is discarded. The valid comparison points
remain the CLI runs: baseline 0.68/0.75, agent-with-tools 0.86.

**Lesson.** **The model field is not provenance; the endpoint is.** Any layer
between the harness and the provider can serve something other than what was
asked for, and it will do so silently while every log line still names the model
you requested.

The diagnostic lesson is sharper. This was first written up, in
`FAILURE_ANALYSIS.md`, as a "verifier resource leak" with a "progressive failure
pattern" — a plausible story built entirely from the shape of the failures, with
no test of the transport itself. **The baseline moving was sitting in the data
the whole time, and the baseline had not been changed.** When a control moves,
stop theorising about the treatment.

And: routing around a rate limit is not free. It converted a loud, obvious
failure into a quiet, plausible one, and cost an evening of runs that all had to
be thrown away.

---

## F-008 — Six cases were never sent to the model, and scored as wrong answers

| | |
|---|---|
| **Found** | `baseline-v2` scoring 0.82 against a "known" baseline of 0.68 |
| **Commit** | `6471db6` (introduced), fixed by `87a9e59` |
| **Evidence** | `evaluation/results/baseline-v1--20260828T173342Z.json` vs `baseline-v2--20260830T092738Z.json` |

**Observed.** The first clean baseline scored **0.82**, far above the 0.68 and
0.75 that had been treated as the comparison point all project. The cause was
not the model:

| Run | CRA | Model calls | Cases that received no model call |
|---|---|---|---|
| baseline-v1 | 0.68 | 23 | **6** — R18, R24, R25, R26, R27, R28 |
| baseline-v1-repeat | 0.75 | 23 | **6** — the same six |
| baseline-v2 | **0.82** | **28** | **0** |
| exp1-tools | 0.86 | 73 | 1 — R25 |

**Expected.** 28 cases, 28 verdicts, or a loud failure.

**Root cause.** Under concurrent load the CLI began refusing calls. `LLM.complete`
retried three times and then raised; the harness caught the exception per case,
recorded an `ERROR` event, and moved on with `verdict=None`. `score_case` scores
a missing verdict as wrong on every component — which is correct for a model that
answered badly, and completely wrong for a case that was never asked.

So six cases, five of them the hard ones added in EXP-000, were **auto-zeroed
without ever reaching the model**, and the aggregate reported it as reasoning
failure.

**Consequences, stated plainly.**

- **The headline "+0.18 from tools" is retracted.** It compared a baseline denied
  six of the hardest cases against an agent that answered 27 of 28. On comparable
  footing it is roughly **+0.04**, about one case. EXP-001 carries the retraction.
- **The "0.07 noise floor" is withdrawn.** Both v1 runs dropped the *identical*
  six cases, which is deterministic, not sampling. It measured a harness failure
  rate. There is currently **no variance estimate** for this benchmark.

**Corrective change.** The pacing and subprocess isolation added for F-007
(`87a9e59`) removed the refusals as a side effect: `baseline-v2` is the first run
in which all 28 cases received a model call. All three systems are being
re-measured on that harness.

Still outstanding: the harness should **refuse to report an aggregate** when any
case failed to reach the model, rather than folding it into the score. A dropped
case and a wrong answer must not be summed into one number.

**Lesson.** **A missing answer is not a wrong answer, and an aggregate that
cannot tell them apart will quietly report infrastructure as capability.**

This is the same mistake as F-001, at a larger scale. There, one `null` field
turned a good verdict into a zero. Here, a refused call turned six unasked
questions into six failures. Both times the score moved for a reason that had
nothing to do with reasoning, and both times it looked entirely plausible —
0.68 for a single-prompt baseline is exactly what one would expect.

The tell was available and unread: `model_calls: 23` for a 28-case run was
printed in every result file and in the run summary from the very first
evaluation.

---

## F-009 — The CLI dies silently under load, and the retry policy made it worse

| | |
|---|---|
| **Found** | `final-v2` scoring 0.07 on 16 model calls for 28 cases |
| **Commit** | fixed after `956b359` |
| **Evidence** | `evaluation/results/final-v2--20260830T094122Z.json` |

**Observed.** The clean baseline had just completed all 28 cases without a single
error. The full agent, on the same harness, same pacing and same worker count,
managed **16 model calls across 28 cases** and produced 25 errors, every one of
them:

```
LLMError('cli backend failed after 3 attempts: claude -p exited 1: ')
```

Note the empty message after the colon. **The CLI exited non-zero having written
nothing to stdout and nothing to stderr.** A single identical call issued by hand
two minutes after the run finished returned `PONG` and exit 0.

**Expected.** Either the calls succeed, or they fail with a reason.

**Root cause, in two parts.**

The far side intermittently drops calls under sustained load and reports nothing
about it. The agent makes three to four calls per case against the baseline's
one, so it presents roughly four times the load for the same worker count — which
is why the baseline sailed through and the agent did not.

The second part is mine. The retry policy was 3 attempts with `2**attempt`
backoff: 1 second, then 2. For a load symptom that is close to useless — all
three attempts land inside the window where the far side is still unhappy, and
the case is abandoned about three seconds after the first refusal.

**Corrective change.** Silent exits are now their own exception type with their
own backoff curve — 8s, 16s, 32s, 64s, capped at 90 — while ordinary errors keep
failing fast at 1s and 2s. Default attempts raised from 3 to 5. An error that
names a real cause should not hold a worker for a minute; an error that names
nothing should not be retried in one second.

**Lesson.** **An empty error message is itself a signal, and worth branching on.**
The absence of any output distinguished a transient load symptom from a genuine
failure, and both were being handled by the same impatient policy.

The wider point is about test coverage of *load*. Everything about this system
was validated at one call per case. The agent's call pattern is four times
denser, and nothing in the test suite exercises that, because the tests
deliberately make no model calls. The first time the dense pattern ran against a
real backend, it fell over — and it fell over in a way that looked exactly like
bad reasoning in the aggregate score, which is F-008's lesson arriving a second
time.
