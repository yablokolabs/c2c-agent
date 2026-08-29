# EXP-003 — Does Restate deliver the durability invariants?

**Git SHA:** `bc4e9b8`
**Decision:** KEEP

## Hypothesis

A durable workflow engine holding case state, timers and approval waits will
satisfy five invariants that an agent alone cannot:

1. a claim is not submitted twice because of a retry
2. an escalation does not execute twice
3. an action a human rejected never executes
4. a restart does not lose case state
5. a duplicate external event does not duplicate a side effect

And the expectation stated in advance: **this will improve durability without
improving reasoning accuracy at all.** They are different axes. If durability
had turned out to move the reasoning metric, that would have meant something was
wrong with the isolation.

## Motivation

The project's thesis is that the hard part is staying with a problem, not
reasoning about it once. That is only a thesis until the invariants are
measured, and measuring them requires being able to break things on purpose.

## Change

`C2CCase`, a Restate workflow keyed by `case_id`, registered additively on the
shared Restate 1.7.7 server. Each feature is load-bearing for one invariant:

| Feature | Invariant |
|---|---|
| workflow key = `case_id` | a duplicate intake cannot start a second lifecycle |
| `ctx.run` | a side effect that succeeded is never re-executed on replay |
| `ctx.uuid()` inside a durable step | idempotency keys are replay-stable, so a retry reuses the key |
| `ctx.promise` | a human approval outlives the process and resolves once |
| the approval branch returning before any call | a rejected action is unreachable |
| `ctx.sleep` | the 56-day and 28-day policy clocks survive restarts |
| `ctx.set` | case state survives `kill -9` |

Plus a synthetic airline whose audit log distinguishes actions **attempted**
from actions that **landed**. That distinction is the whole measurement: without
it, exactly-once is an assertion rather than a result.

## Evaluation

Six failure-injection scenarios, `python -m c2c.eval.durability`. The assess
step points at a stub returning a fixed verdict, so model sampling does not add
variance to a measurement about crash recovery.

## Before

Not applicable. There was no lifecycle to be durable about before this, and
the baseline has none either. Reporting "baseline 0/6" would be comparing a
system to the absence of one.

## After

`evaluation/results/durability--20260829T065338Z.json`

| Metric | Result |
|---|---|
| Scenarios passed | **6/6** |
| Workflow completion | 1.00 |
| Failure recovery | 1.00 |
| State preserved | 1.00 |
| **Duplicate consequential actions** | **0** |

The two that carry the weight:

**D01 — carrier API answers 503 three times.** The carrier endpoint was called
**4 times**: three rejected, one succeeding. One submission landed. The scenario
asserts the call count, so a run where the injection silently failed to fire
cannot pass by accident.

**D06 — worker SIGKILLed inside the submission window.** The carrier received
**2 submission attempts** and **1 landed**. This is the important number: the
crash genuinely did cause a second attempt, and the replay-stable idempotency
key absorbed it. Had it shown 1 attempt, the kill would have missed the window
and the scenario would have proved nothing.

**D05 — a human refuses.** The carrier endpoint was called **0 times**. Not one
call that was later reversed: the rejection branch returns before any side
effect is reachable.

## Failed cases

None. Two harness bugs were found and fixed along the way, both real:

- `ctx.run` inspects its callable with `iscoroutinefunction`, which is `False`
  for a lambda that merely returns a coroutine. Every durable HTTP step was
  journalling an un-awaited coroutine. Replaced with real `async def` closures.
- A no-argument Restate handler rejects a request body, so `status()` returned
  400 to every caller.

Both were found by reading the service log rather than by a test, which is
recorded as a gap: there is no test that would have caught either.

## Cost impact

Zero model calls. ~25 seconds wall clock for the suite.

## Decision

**KEEP.** Every invariant the component was added for is measured and holds, and
the measurement is grounded in an external audit log rather than in C2C's own
claims about itself.

## Learning

The expectation held: **durability moved no reasoning metric, and that is a
result, not a disappointment.** They are separate axes and the evaluation
reports them separately.

The more useful lesson is about instrumentation. The first version of D01 passed
while proving nothing: a 503 raises before the audit entry is written, so the
retries were invisible and the scenario would have passed identically if the
injection had never fired. Asserting the *carrier-side call count* turned it from
a test that could only confirm into a test that could fail. A failure-injection
test that cannot detect its own injection failing is not evidence.
