# The problem, and who has it

## Who

A passenger whose flight was cancelled or badly delayed, who is probably owed
money, and who has a job.

Not a lawyer. Not a claims professional. Someone with a booking reference, a
blurry photo of a departures board, and about forty minutes of patience.

Secondarily: the small claims-handling operations and passenger-rights
non-profits who do this work at volume, on thin margins, and who currently
solve it by paying a person to read the same six documents over and over.

## The bottleneck

The bottleneck is not the decision. It is the **persistence**.

Deciding whether a claim is worth anything takes a competent person maybe
fifteen minutes: read the policy, read the documents, apply the ladder, get a
number. That part is genuinely hard to get right — the thresholds are exact,
the reductions compose, and the cause classification turns on details the
airline controls — but it is bounded.

What is not bounded is everything after it:

| Step | Elapsed time | What the passenger has to do |
|---|---|---|
| Assess the claim | 15 min | read a policy they have never seen |
| Submit it | 20 min | assemble evidence, fill a form |
| Wait | **4 to 8 weeks** | remember that they are waiting |
| Read the rejection | 10 min | notice that the stated reason contradicts the operational record |
| Challenge it | 30 min | know that challenging is even an option |
| Wait again | **4 weeks** | remember, again |
| Escalate | 45 min | know the escalation is now ripe, and not before |

The work is small. The **calendar** is enormous. Between the first click and the
money there are two or three multi-week silences, and each one is a place where
a valid claim quietly dies — not because it was wrong, but because nobody was
still holding it.

That is the persistence gap: whether a passenger gets what the policy says they
are owed depends less on the merits than on whether they have the knowledge,
the time, and the stubbornness to keep coming back for three months.

## Why it is worth solving

Two reasons, and the second is the interesting one.

**For the passenger:** the amounts are meaningful (180 to 750 units per person
in this benchmark's synthetic scheme, and comparable in real ones), the process
is winnable, and the failure mode is silent. Nobody tells you your claim died.

**For anyone building agents:** this is a clean instance of a general problem.
The reasoning is a small part of the task. The rest is *staying with it* —
across weeks of wall-clock time, process restarts, duplicate inbound events,
retries, and human approval gates that must hold for days without either
forgetting the case or firing twice.

That is the thesis this project is testing:

> The hard part of agentic AI isn't making an agent reason once.
> It's making it reliably stay with a real-world problem until the problem is
> actually resolved.

Which splits the evaluation into two questions that must be measured
separately, because a system can win one and lose the other:

1. **Does it decide correctly?** — measured by Case Resolution Accuracy over
   the 20-case reasoning benchmark.
2. **Does it stay with the case?** — measured by the durability suite: does
   state survive a crash, does a claim get submitted twice after a retry, does
   a rejected approval stay rejected.

An agent that is right and forgetful is not useful here. Neither is one that is
durable and wrong.

## What "good" looks like for this user

Before running anything, the target was set as:

- **Case Resolution Accuracy above 0.80**, where a case counts only if the
  action, the amount and the eligibility are all correct at once.
- **Zero unsupported claims** — never invent a compensation figure when the
  evidence does not support one. A confidently wrong number is worse than an
  honest "I need your arrival time", because the passenger acts on it.
- **Zero unsupported challenges and zero false escalations** — never send a
  passenger to a regulator on a claim the carrier was right to refuse, and
  never escalate before the clock allows it.
- **Zero duplicate consequential actions** under crash and retry.

The trivial floors are recorded so the primary metric can be read honestly: a
system that always answers "close the case, nothing owed" scores 0.25, and one
that always answers "submit, 420 units" scores 0.10. Anything at or below 0.25
has learned nothing.
