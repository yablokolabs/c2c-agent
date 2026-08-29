# Demo script

Five minutes. Runs `make demo` on case R12.

Setup before recording:

```bash
make setup && make up && make demo-reset
```

---

## 0:00 — The problem (40s)

> "I flew Dublin to Paris to Bangalore. The first leg was late, I missed the
> connection, and I lost most of a day in Paris. I did eventually get compensated
> — after months of chasing.
>
> The part that stuck with me is that the reasoning was never the hard bit.
> Working out whether I had a case took a competent person fifteen minutes. What
> took months was the calendar: submit, wait six weeks, get a rejection that
> contradicts the airline's own records, challenge it, wait four more weeks,
> escalate.
>
> Between the first click and the money there are two or three multi-week
> silences, and each one is where a valid claim quietly dies. Not because it was
> wrong. Because nobody was still holding it.
>
> That's the persistence gap, and it's what C2C is for."

## 0:40 — The baseline (30s)

Show `prompts/baseline_v2.md`.

> "The reasonable thing to do first: one prompt. Give the model the whole policy,
> the whole case file, ask for the answer. Not crippled — same model, same
> policy, same output schema as the agent. It just doesn't have tools, doesn't
> verify itself, and can't remember anything past the end of the call."

## 1:10 — The benchmark, and a mistake worth showing (40s)

Show `benchmark/POLICY.md` and one case file.

> "Twenty-eight synthetic cases against an invented policy. The numbers
> deliberately don't match any real scheme, so the model can't answer from
> memory — every correct answer has to be grounded in the document.
>
> The first version of this benchmark was wrong. The baseline scored 0.90 on it,
> which meant it couldn't detect improvement or regression. That's in FAILURES.md
> along with two other defects the baseline run exposed in my own harness."

## 1:50 — One real execution (90s)

Run `make demo`. Talk over it.

**Step 3, the assessment.**

> "The caseworker listed the documents first, then read the operational record,
> then looked up the clauses it was relying on. The carrier said weather. Its own
> log says the crew timed out and both airports were clear. The policy says the
> operational record governs. So: 420 units, challengeable.
>
> An independent verifier then checked that — and it doesn't get the caseworker's
> working, only the case, so it's a second opinion rather than a review."

**Step 3, the stop.**

> "And now it stops. Nothing has been sent. Submitting a claim is consequential,
> so it waits for a human. The workflow is suspended on a durable promise —
> consuming nothing, surviving restarts, and it will sit there for as long as it
> takes."

**Steps 4–6.**

> "I approve. It submits. Weeks pass — here that's one HTTP event. The rejection
> arrives, the agent re-reads it, proposes a challenge, and stops again for a
> second approval."

**Step 7, the audit.**

> "This is the airline's log of what actually landed, not what was attempted.
> That's the measurement, and it's how I can claim exactly-once rather than
> assert it."

## 3:20 — Where it breaks, and holds (60s)

Run `make failure-tests`.

> "Six failure scenarios. The one that matters is D06: kill the worker with
> SIGKILL in the window around the submission.
>
> Look at the numbers — the carrier endpoint received **two** submission
> attempts, and **one** claim landed. The retry did happen. The idempotency key
> is generated inside a durable step, so the replay produced the same key and the
> airline deduplicated it.
>
> And D05: when a human refuses, the carrier is never called at all. Zero
> attempts, not one that got rolled back."

## 4:20 — Results and the honest bit (50s)

Run `make compare`. Show `IMPROVEMENT_CHANGELOG.md`.

> "Baseline against the full agent, same 28 cases.
>
> The changelog has the experiments including the one I removed, and what it
> taught me.
>
> The hot take is the thing I didn't expect. I assumed the reasoning would be the
> hard part and the durability would be plumbing. It was the other way round. A
> single prompt already handles most of these cases. What a single prompt cannot
> do is be there in week six — and that's the part that decides whether a
> passenger gets paid.
>
> If you're building agents for anything that takes longer than one call to
> finish, put your effort where the calendar is, not where the reasoning is."
