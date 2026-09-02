# Demo script — terminal

*Filming it as a Telegram conversation instead? Use [`DEMO_SCRIPT_TELEGRAM.md`](DEMO_SCRIPT_TELEGRAM.md).*

Five minutes exactly. Timings are cumulative and the beats are budgeted to land
on 5:00 with nothing rushed.

The case is **R18**: an airline blaming a bird strike for a cancellation forty
hours later, while holding two spare aircraft it never used. It is the most
interesting reasoning in the benchmark, because the airline's excuse was
*genuine* — and had expired.

**Before recording:**

```bash
make setup && make up && make demo-reset
```

Two terminals. Left: `make demo`. Right: `make failure-tests`, then `make compare`.

> Step numbers below match what `c2c/tools/demo.py` prints. If you change the
> demo, change this.
>
> Read the numbers off `make compare` on screen rather than reciting them. The
> figures below match the committed result files as of commit `707daa0`.

---

## 0:00 — The problem (35s)

> "I flew Dublin to Paris to Bangalore. The first leg was late, I missed the
> connection, and I lost most of a day in Paris. I did get compensated —
> after months of chasing.
>
> The reasoning was never the hard part. Working out whether I had a case took
> maybe fifteen minutes. What took months was the calendar: submit, wait six
> weeks, get a rejection that contradicts the airline's own records, challenge
> it, wait four more weeks, escalate.
>
> Between the first click and the money there are two or three multi-week
> silences, and each one is where a valid claim quietly dies. Not because it was
> wrong — because nobody was still holding it. That's what C2C is for."

## 0:35 — The baseline (15s)

Show `prompts/baseline_v2.md`.

> "The reasonable first thing: one prompt, whole policy, whole case file. Same
> model and same output schema as the agent — it just has no tools, doesn't
> verify itself, and forgets everything when the call ends."

## 0:50 — The benchmark, and a mistake worth showing (30s)

Show `benchmark/POLICY.md`, then one case file.

> "Twenty-eight synthetic cases against an invented policy. The thresholds match
> no real scheme deliberately, so the model can't answer from memory — every
> correct answer has to come from the document in front of it.
>
> The first version of this benchmark was wrong. The baseline scored 0.90, which
> meant it could detect neither improvement nor regression. That's in
> FAILURES.md, with two other defects the baseline run found in my harness before
> it found anything about the agent."

## 1:20 — One real execution (95s)

**Scroll through the already-completed `make demo` output**, top to bottom.

> Run `make demo` *before* recording. One assessment takes 3.5 minutes at the
> median and the demo does two, so it cannot happen live inside a five-minute
> video. What is on screen is a genuine execution; the trajectory is committed
> alongside it.

**Step 3 — the assessment.** *(The strongest 20 seconds in the video. Slow down.)*

> "The passenger's complaint is one sentence: *they say a bird strike the day
> before means they owe me nothing, even though my flight wasn't until the
> following evening.*
>
> A bird strike genuinely is an extraordinary circumstance. Under this policy the
> airline owes nothing for one. So the obvious answer is: no claim.
>
> Watch what it actually did. It listed the documents, read the operations log,
> and found the timestamps — the bird strike ended at 01:10 on the 22nd, the
> flight was due out at 17:10 on the 23rd. Forty hours. The policy says an
> extraordinary cause reverts to the airline's responsibility if more than twelve
> hours passed and they could have recovered. And one line further down: they
> held two serviceable spare aircraft at Helsinki the whole time and assigned
> neither.
>
> So the excuse was real, and it expired. 420 units. That is not a lookup — it is
> reading a log, doing date arithmetic, and noticing an absence.
>
> An independent verifier then checked it, and it never sees the caseworker's
> working, only the case. A second opinion, not a review that inherits the same
> wrong turn."

**Step 3 — the stop, and what the passenger sees.** *(This is the thesis. Let it
land, and pause on the boxed message.)*

> "And now it stops. Nothing has been sent. Submitting a claim is consequential,
> so it waits for a human — suspended on a durable promise, consuming nothing,
> surviving restarts, for as long as it takes.
>
> And this is what actually reaches the passenger. Not a dashboard they have to
> remember to open — a message, weeks after they last thought about this, with
> the amount, the reasoning, the clauses it rests on, and two buttons. That is
> the whole interaction. They are not managing a case; they are answering a
> question."

**Steps 4–6.**

> "I approve. It submits. Weeks pass — here that's one HTTP event. Indigo North
> comes back and refuses, citing the bird strike. The agent re-reads that against
> the same log, holds its position, proposes a challenge, and stops again for a
> second approval."

**Step 7 — what the passenger receives.** *(Let this breathe.)*

> "This is the output that matters. Not JSON — a plain-language summary of where
> they stand, and a challenge letter they could put their name to, clauses cited,
> documents listed.
>
> Generated deterministically from the verdict, no second model call, so the
> figure in the letter cannot drift from the one that was assessed and approved.
> Every page stamped SYNTHETIC DEMO."

**Step 8 — the audit.**

> "The airline's log of what actually *landed*, not what was attempted. That
> distinction is the measurement — it's how I can say exactly-once instead of
> asserting it."

## 2:55 — Where it breaks, and holds (50s)

Run `make failure-tests`. Host topology only — never while the dockerized
deployment is up: the suite SIGKILLs every process on the host whose command
line matches `c2c.restate_service`, and host `/proc` includes the live
workflow container's service. That is F-024; the dockerized form is
REPRODUCTION_GUIDE §6.

> "Six failure scenarios, no model calls. The one that matters is D06: SIGKILL
> the worker in the window around the submission.
>
> Read the numbers — the carrier received **two** submission attempts, and
> **one** claim landed. The retry genuinely happened. The idempotency key is
> generated inside a durable step, so the replay produced the same key and the
> airline deduplicated it. If that said one attempt, the kill missed its window
> and the test proved nothing.
>
> And D05: when a human refuses, the carrier is called **zero** times. Not once
> and rolled back — never called."

## 3:45 — Results, the changelog, and what I removed (55s)

Run `make compare`. Show `IMPROVEMENT_CHANGELOG.md`.

> "Baseline **0.82**, full agent **0.93**, same 28 cases, same model.
>
> R18, the case you just watched, is one the baseline gets wrong — and how it
> gets it wrong is the interesting part. It found the same reasoning: the
> twelve-hour rule, the forty hours, the unused spare aircraft. Same 420 units.
> Then it asked for a boarding pass it didn't need and answered *request
> evidence* instead of *submit the claim*.
>
> It had the answer and talked itself out of acting on it. That is what the
> verifier is for.
>
> The changelog has every iteration. Two I'd rather show than hide.
>
> First, the tools. I measured 1.4 tool calls per case, and `calculate` fired
> three times in twenty-eight cases — on neither of the two cases that fail
> *because of* arithmetic. So I can't honestly credit the improvement to the
> tools, and the changelog says exactly that.
>
> Second, the experiment I removed: NanoClaw, as the agent runtime. Its whole
> value is persistent agent sessions — and that's precisely the state I'm arguing
> belongs in the durable workflow, not in the runtime. Two systems both claiming
> to remember the case isn't redundancy, it's a sync bug waiting for a crash. So
> the biggest contribution wasn't a component I added. It was deciding where
> memory lives, and being strict about it."

## 4:40 — Hot take (20s)

> "I assumed reasoning was the hard part and durability was plumbing. It was the
> other way round.
>
> And the sharpest lesson came from a bug. When rate limits hit, I routed through
> a gateway. Runs completed again — and got worse. The tell was that the
> *baseline* fell from 0.82 to 0.29, and I hadn't touched the baseline. The
> gateway didn't carry the model I was asking for, and every result file still
> said it did, because that field logged what was *requested*.
>
> The model field is not provenance. The endpoint is. And when a control moves
> and you haven't touched the control, stop theorising about the treatment."
