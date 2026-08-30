# Demo script

Five minutes exactly. Timings are cumulative and the beats are budgeted to land
on 5:00 with nothing rushed.

**Before recording:**

```bash
make setup && make up && make demo-reset
```

Two terminals. Left: `make demo`. Right: `make failure-tests`, then `make compare`.

> Step numbers below match what `c2c/tools/demo.py` prints. If you change the
> demo, change this.
>
> The numbers in the 3:45 beat are marked `[[ ]]`. Read them off `make compare`
> — do not recite them from memory, and do not record until they are filled in.

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

Run `make demo`.

**Step 3 — the assessment.**

> "It listed the documents, read the operational record, then looked up the
> clauses it was relying on. The carrier said weather. Its own log says the crew
> timed out and both airports were clear. The policy says the operational record
> governs. So: 420 units, and the rejection is challengeable.
>
> An independent verifier then checked that — and it never sees the caseworker's
> working, only the case. A second opinion, not a review that inherits the same
> wrong turn."

**Step 3 — the stop.** *(This is the thesis. Let it land.)*

> "And now it stops. Nothing has been sent. Submitting a claim is consequential,
> so it waits for a human — suspended on a durable promise, consuming nothing,
> surviving restarts, for as long as it takes."

**Steps 4–6.**

> "I approve. It submits. Weeks pass — here that's one HTTP event. The rejection
> arrives, the agent re-reads it, proposes a challenge, stops again."

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

Run `make failure-tests`.

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

> "Baseline `[[0.82]]`, full agent `[[ ]]`, same 28 cases, same model.
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
