# Improvement changelog

The story of how C2C got from a single prompt to the final system, with the
evidence behind each step and the things that did not work.

Primary metric throughout: **Case Resolution Accuracy (CRA)** — a case counts
only when the next action, the compensation figure and the other entitlements
(duty of care, downgrade) are all correct at once. Definition and the reason it
changed once are in `docs/EVALUATION.md` and FAILURES.md F-002.

Reference floors on the 28-case suite, so the numbers can be read honestly:

| | CRA |
|---|---|
| Best possible constant answer, searched over the whole space | **0.25** |
| Always "submit the claim, 420 units" | 0.10 |

Anything at or below 0.25 has learned nothing.

---

## The table

| Stage | What was tried, and why | Evidence | Decision / learning |
|---|---|---|---|
| **Baseline v0** | One direct prompt, whole policy, whole case file, no tools, no verification. 20 cases. | CRA **0.75** · `baseline-v0--20260828T172034Z.json` | Established a starting point, and immediately exposed three defects in the benchmark itself. |
| **Benchmark correction** | The baseline run's first finding was that the instrument was faulty: a required field discarded a well-formed verdict; the metric's third term was fully redundant; and the suite was near-saturated at 0.90. Fixed the schema, replaced the redundant term with entitlements, added 8 harder cases. | Re-scored with no new calls: **0.75 → 0.90** on the same output. Then **0.68** on 28 cases. · `EXP-000` | **KEEP.** Coverage and difficulty are different axes; designing for the first produced a suite that was complete and uninformative. |
| **Baseline v1** | The corrected baseline. Same prompt shape, 28 cases, entitlements metric. This is the comparison point. | CRA **0.68** · `baseline-v1--20260828T173342Z.json` | The number every later stage is measured against. |
| **Iteration 1 — tools** | Hypothesis: the baseline fails on buried facts, composed arithmetic and absent documents because one pass over a long dossier does not attend evenly. Gave the caseworker `list_documents`, `read_document`, `policy_lookup`, `calculate` and a 10-step loop. Same model, same policy, same dossier. | see below · `EXP-001` | see below |
| **Iteration 2 — verifier** | Hypothesis: an independent second opinion catches arithmetic and rule-scope errors the caseworker commits confidently. Verifier sees the case and the policy but **not** the caseworker's transcript. | see below · `EXP-002` | see below |
| **Iteration 3 — durability** | Different axis entirely. Restate workflow for case state, timers, human approval waits and exactly-once consequential actions. Expectation stated in advance: this improves durability and moves no reasoning metric. | **6/6** scenarios, **0** duplicate consequential actions · `durability--20260829T065338Z.json` · `EXP-003` | **KEEP.** Expectation held. Reported on its own axis, never folded into CRA. |
| **Removed — NanoClaw** | Evaluated as the agent runtime. | reasoning below · `EXP-004` | **REMOVE.** |
| **Final** | see below | | |

---

## Iteration 3 in detail — the durability suite

This is the one the project's thesis rests on, so the numbers are here rather
than only in the experiment file.

| Scenario | Injected failure | Result |
|---|---|---|
| D01 | carrier API answers 503 three times | carrier called **4×** (3 rejected, 1 succeeded), **1** submission landed |
| D02 | worker `SIGKILL`ed while awaiting approval | state and verdict survived, **1** submission landed |
| D03 | the same carrier rejection delivered twice | second delivery absorbed, **1** challenge landed |
| D04 | human approves twice | second approval absorbed, **1** submission landed |
| D05 | human rejects | carrier called **0 times** — not one call later reversed |
| D06 | worker `SIGKILL`ed inside the submission window | carrier received **2 attempts**, **1** landed |

D06 is the load-bearing one. The crash genuinely caused a second submission
attempt; the idempotency key, generated inside a durable step and therefore
stable across replay, made the second a no-op. Had it shown one attempt, the
kill would have missed the window and the scenario would have proved nothing.

D01's first version passed while proving nothing, because a 503 raises before
the audit entry is written and the retries were invisible. It now asserts the
carrier-side call count. A failure-injection test that cannot detect its own
injection failing is not evidence.

---

## Removed — NanoClaw as the agent runtime

**What was tried.** NanoClaw (upstream `nanocoai/nanoclaw`, commit `a099c71f`)
was on the host and was the obvious candidate for the agent runtime: isolated
containers per agent, persistent sessions, chat-channel bindings.

**Why it was removed.** Its central value is *persistent agent sessions* — an
agent that remembers across invocations. That is exactly the state this project
argues belongs in the workflow, not in the agent runtime. Adopting it would have
produced two systems each claiming to remember the case, which is the
architecture the whole project exists to argue against. Its container logs are
also ephemeral, and durable trajectories are a deliverable, so C2C's own recorder
was needed regardless.

**What it taught.** The question "where does the memory live?" is a real
architectural fork, not a detail. A runtime that remembers and a workflow that
remembers are not complementary; they compete, and the one that loses becomes a
cache that drifts. Picking one and being strict about it made every later
boundary obvious — which is why FastAPI holds no case state either.

**Decision: REMOVE**, with the reason recorded rather than the component quietly
omitted. See `docs/STACK.md`.
