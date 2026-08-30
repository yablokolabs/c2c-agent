# Demo script

Five minutes, on case R12. Timings are cumulative.

**Before recording:**

```bash
make setup && make up && make demo-reset
```

Have two terminals ready. Left: `make demo` output. Right: for
`make failure-tests` and `make compare`.

> The step numbers below match what `c2c/tools/demo.py` actually prints. If you
> change the demo, change this.

---

## 0:00 — The problem (40s)

> "I flew Dublin to Paris to Bangalore. The first leg was late, I missed the
> connection, and I lost most of a day in Paris. I did get compensated
> eventually — after months of chasing.
>
> What stuck with me is that the reasoning was never the hard part. Working out
> whether I had a case took maybe fifteen minutes. What took months was the
> calendar: submit, wait six weeks, get a rejection that contradicts the
> airline's own records, challenge it, wait four more weeks, escalate.
>
> Between the first click and the money there are two or three multi-week
> silences, and each one is where a valid claim quietly dies. Not because it was
> wrong. Because nobody was still holding it.
>
> That's the persistence gap. That's what C2C is for."

## 0:40 — The baseline (25s)

Show `prompts/baseline_v2.md`.

> "The reasonable first thing: one prompt. Whole policy, whole case file, ask for
> the answer. Not crippled — same model, same policy, same output schema as the
> agent. It just has no tools, doesn't verify itself, and forgets everything the
> moment the call ends."

## 1:05 — The benchmark, and a mistake worth showing (35s)

Show `benchmark/POLICY.md`, then one case file.

> "Twenty-eight synthetic cases against an invented policy. The numbers
> deliberately match no real scheme, so the model can't answer from memory —
> every correct answer has to come from the document in front of it.
>
> The first version of this benchmark was wrong. The baseline scored 0.90 on it,
> which meant it could detect neither improvement nor regression. That's in
> FAILURES.md, along with two other defects the baseline run found in my own
> harness before it found anything about the agent."

## 1:40 — One real execution (100s)

Run `make demo`. Talk over it.

**Step 3 — the assessment.**

> "The caseworker listed the documents first, then read the operational record,
> then looked up the clauses it was relying on. The carrier said weather. Its own
> log says the crew timed out and both airports were clear. The policy says the
> operational record governs. So: 420 units, and the rejection is challengeable.
>
> An independent verifier then checked that — and it never sees the caseworker's
> working, only the case, so it's a second opinion rather than a review that
> inherits the same wrong turn."

**Step 3 — the stop.**

> "And now it stops. Nothing has been sent. Submitting a claim is consequential,
> so it waits for a human. The workflow is suspended on a durable promise —
> consuming nothing, surviving restarts, and it will sit there as long as it
> takes."

**Steps 4–6.**

> "I approve. It submits. Weeks pass — here that's one HTTP event. The rejection
> arrives, the agent re-reads it, proposes a challenge, and stops again for a
> second approval."

**Step 7 — what the passenger actually receives.** *(Let this one breathe.)*

> "And this is the output that matters. Not JSON — a plain-language summary of
> where they stand, and a challenge letter they could put their name to, with
> the clauses cited and the documents listed.
>
> It's generated deterministically from the verdict, with no second model call,
> so the figure in the letter cannot drift from the figure that was assessed and
> approved. And every page is stamped SYNTHETIC DEMO, not for submission."

**Step 8 — the audit.**

> "This is the airline's log of what actually *landed*, not what was attempted.
> That distinction is the measurement — it's how I can say exactly-once rather
> than just assert it."

## 3:20 — Where it breaks, and holds (55s)

Run `make failure-tests` in the right-hand terminal.

> "Six failure scenarios, no model calls. The one that matters is D06: SIGKILL
> the worker in the window around the submission.
>
> Read the numbers — the carrier received **two** submission attempts, and
> **one** claim landed. The retry genuinely happened. The idempotency key is
> generated inside a durable step, so the replay produced the same key and the
> airline deduplicated it. If that said one attempt, the kill missed the window
> and the test proved nothing.
>
> And D05: when a human refuses, the carrier is called **zero** times. Not once
> and then rolled back — never called."

## 4:15 — Results, and the honest bit (45s)

Run `make compare`. Show `IMPROVEMENT_CHANGELOG.md`.

> "Baseline against the full agent, same 28 cases, same model.
>
> Two things I'd rather show than hide. First, I re-ran the *identical* baseline
> and it moved by 0.07 — that's the noise floor, and any claim smaller than it
> is not a result.
>
> Second, the tools. I measured 1.4 tool calls per case, and `calculate` fired
> three times in twenty-eight cases — including on neither of the two cases that
> fail *because of* arithmetic. Eleven cases used no tools at all. So I can't
> honestly credit the improvement to the tools, and the changelog says so."

## 5:00 — Hot take (20s)

> "The thing I got wrong: I assumed reasoning was the hard part and durability
> was plumbing. It was the other way round.
>
> And the sharpest lesson came from a bug. When rate limits hit, I routed through
> a gateway. Runs completed again — and got worse. The tell was that the
> *baseline* fell from 0.68 to 0.29, and I hadn't touched the baseline. The
> gateway didn't carry the model I was asking for, and every result file still
> said it did, because that field logged what was *requested*.
>
> So: the model field is not provenance, the endpoint is. And when a control
> moves and you haven't touched the control, stop theorising about the treatment.
> Every result now records where the call actually went."
