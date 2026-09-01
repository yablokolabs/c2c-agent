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
| **Iteration 1 — tools** | Hypothesis: the baseline fails on buried facts, composed arithmetic and absent documents because one pass over a long dossier does not attend evenly. Gave the caseworker `list_documents`, `read_document`, `policy_lookup`, `calculate` and a 10-step loop. Same model, same policy, same dossier. | CRA 0.68 → **0.86** as first measured · `exp1-tools--20260829T070116Z.json` · `EXP-001` | **KEEP the loop, but the +0.18 headline is RETRACTED.** The baseline it beat had six cases auto-zeroed without ever reaching the model (F-008). Worse, the trajectory shows **1.4 tool calls per case** and `calculate` fired **3 times in 28 cases** — on neither of the two cases that fail *because of* arithmetic. Eleven cases used no tool at all. The loop is kept because it is the substrate the verifier needs; the tools are not credited with the gain. |
| **Iteration 2 — verifier** | Hypothesis: an independent second opinion catches arithmetic and rule-scope errors the caseworker commits confidently. Verifier sees the case and the policy but **not** the caseworker's transcript. | baseline **0.82** → **0.93** · `final-v2-merged--20260830T194802Z.json` · `EXP-002` | **KEEP.** The largest measured contribution on the reasoning axis. Isolated by **R16**, a partial settlement that failed under the baseline *and* under tools-only and passes only with the verifier. Gains concentrate in duty of care (0.96 → 1.00) and evidence sufficiency (0.89 → 0.93) while compensation accuracy was already 1.00 and did not move — the signature of a second reader checking arithmetic, not of different reasoning. Costs **3.6× the model calls**. |
| **Iteration 3 — durability** | Different axis entirely. Restate workflow for case state, timers, human approval waits and exactly-once consequential actions. Expectation stated in advance: this improves durability and moves no reasoning metric. | **6/6** scenarios, **0** duplicate consequential actions · `durability--20260829T065338Z.json` · `EXP-003` | **KEEP.** Expectation held. Reported on its own axis, never folded into CRA. |
| **Removed — NanoClaw** | Evaluated as the agent runtime. | reasoning below · `EXP-004` | **REMOVE.** |
| **Removed — NanoClaw** | Evaluated as the agent runtime. | no run; reasoning below · `EXP-004` | **REMOVE.** Its persistent sessions compete with the durable workflow for owning case memory. |
| **Built, not measured — arithmetic enforcement** | A verdict asserting money it never computed is handed back once with the arithmetic it owes. Driven by F-006. | none — budget went to the headline comparison · `EXP-005` | **Recorded as unrun**, with its prediction stated in advance so it can be checked later. |
| **Final** | Baseline against the full agent: tools, a 10-step loop, and an independent verifier with one revision. | **0.82 → 0.93 (+0.11)**, 0 unsupported claims, 0 false escalations, plus **6/6** durability with 0 duplicate consequential actions | **The main contribution was the verifier on the reasoning axis, and deciding where case memory lives on the durability axis.** Read +0.11 as directional: it is three cases, and this project has no valid variance estimate — the one it had was withdrawn in F-008. |

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

---

## Intake memory — within a session, and across a restart

The intake step was re-asking for facts the passenger had already given. Two
axes, two fixes:

| Stage | What was tried, and why | Evidence | Decision / learning |
|---|---|---|---|
| **Intake prompt + reply path** (`62d8abf`, `46f14d9`) | The model was not told it was seeing a continuing conversation, so it could drift back into "I need everything" mid-exchange. The prompt now says the input is the whole conversation so far; the Telegram reply path became state-aware instead of a blank acknowledgment. | regression tests for the exact live exchange: a complete account followed by a reply that no longer asks for name, airline, flight, date and what happened · 182 passed | **KEEP.** Fixed the within-session half. |
| **Restart durability** (`6e57242` working tree) | The persistence half of the same fix was broken: `save_incomplete` wrote the model record instead of the conversation, and `load_incomplete` returned `None` before ever opening the file. A worker restart still made the passenger start from zero. Persist the conversation itself, reload it on `_conversation`, and delete it once the case opens. | new regression test that simulates a worker restart mid-conversation — fails before, passes after · 185 passed | **KEEP.** F-015. A durability fix needs a test that kills the process; the committed "durability" fix had never exercised the read path. |
| **Open only when done asking** (`65fa129`) | The live IN300 exchange showed the real mechanism: the model said ready while its reply asked "was it 2025 or 2026?", the case opened, and the conversation was dropped — so the answer "2026" landed in an empty intake that asked from zero. `ready` now means "done asking" (prompt) and is enforced in the loop (a ready reply containing a question is not ready). The stale host bot that had been serving pre-fix code was killed. | regression test replays the exchange: ready-but-asking keeps the conversation, the answer arrives with full context · 187 passed | **KEEP.** F-016. One boolean gated a destructive transition (opening deletes the conversation); semantics must be exact, enforced in code not just the prompt. |
| **Acknowledge after open** (`9fdd9af`) | Second live test: the account arrived, the case opened (correctly — no question in the reply), and a "?" sent while it was being processed landed in a fresh intake and was interrogated from zero. Opening ends the intake conversation, so any later message must be acknowledged, not re-collected. | regression test replays the two-message batch: one model call total, the follow-up acknowledged · 188 passed | **KEEP.** F-017. The drop at open is now handled at both ends: don't open while asking, and acknowledge anything said afterwards. |
| **Receipt ack before the model call** (`cf8c850`) | A passenger sees nothing for tens of seconds while intake assesses, assumes the bot is dead, and keeps sending messages. Acknowledge each message immediately ("Got it — one moment while I look at this."), then answer substantively. Follow-ups are already handled: accumulated into context pre-open, acknowledged deterministically post-open. | regression test asserts the ack is the first message sent · 189 passed | **KEEP.** The silence was the panic trigger; an expected wait reads differently from a dead bot. |

---

## Found while wiring up the Telegram demo — environment issues

Not model findings: these surfaced while taking the finished system from the
development machine to a fresh box for the demo, and each one silently broke
the pipeline rather than failing loudly. They are recorded because a judge
starting from a clean checkout will meet them.

| Symptom | Root cause | Fix | Evidence |
|---|---|---|---|
| The model-reachability check (`claude -p` PONG) **hangs with no output** | A stale **legacy iptables** ruleset (xtables, from an older Docker install) coexists with Docker's nftables rules and has `FORWARD policy DROP` with rules only for the default `docker0` bridge — so the compose network's outbound traffic is silently dropped before NAT. Docker's own rules look fine while the legacy ruleset does the dropping. | Accept the compose bridge in the legacy chains and masquerade its subnet; bridge name and subnet are **derived from the running stack** so the same commands work anywhere. Documented in `REPRODUCTION_GUIDE.md` §4 and `DEMO_SCRIPT_TELEGRAM.md`. | `iptables-legacy -L FORWARD -n -v` shows `policy DROP` and no rule for `br-...`; the legacy MASQUERADE rule for the compose subnet counts 0 packets while the container's `curl` times out. After the fix, the same `curl` returns in ~0.04s. |
| Telegram bot starts, says *listening*, but never replies; logs repeat `poll failed: Network is unreachable` | The `bot` service had **no `~/.claude` OAuth mount** (the `api` service has one), so the intake assessment's `claude -p` call ran unauthenticated and failed after five retries. The poll error is stale log noise from the network issue above; the real failure is `cli backend failed after 5 attempts`. | Add the same `${HOME}/.claude` mounts to the `bot` service as the `api` service has. | Before: `claude auth status` in the bot container reports `loggedIn: false`; after the mount, `true` and the PONG check returns `PONG`. |
| A pasted bot token is rejected with Telegram 404 on every call | The token in `.env` had extra characters appended (a timestamp) — Telegram returns 404 `Not Found` for any token that is not exactly right, and `getUpdates` swallows the 404, so the bot appears healthy while receiving nothing. | Fix the token, then **recreate** the bot container — env vars are read at container start, so editing `.env` alone does nothing until then. | `getMe` returns 404 before, 200 `{"ok":true,...}` after; token length in `.env` went from 54 (corrupted) to 46 (clean). |
| Docs hardcoded a developer's home path | `CLAUDE.md` declared the project root as `/home/azureuser/...` — wrong on any other machine. | Use `./` (relative to the clone); the demo docs now derive the iptables bridge/subnet from docker instead of baking in `br-...` and `172.18.0.0/16`. | `CLAUDE.md` project root now reads `./`. |
| `sudo docker compose` silently breaks the model mounts | The compose file mounts `${HOME}/.claude`. Run under `sudo`, `${HOME}` expands to `/root`, so the `~/.claude` OAuth login never mounts. The bot greets and listens fine, then every model call fails with `cli backend failed after 5 attempts: claude -p exited 1` — and `getUpdates` swallows the error, so it looks healthy while answering nothing. | Run compose with the real home: `sudo HOME=/home/box docker compose ...` — and recreate any container whose mounts point at `/root/.claude`. | `docker inspect` showed `/root/.claude -> /root/.claude`; after the fix, `/home/box/.claude` and `claude -p 'PONG'` returns `PONG` inside the container. |

**What it taught.** Three of these are the same failure class as F-008, at the
environment level: a component that looks healthy while silently doing nothing.
The bot logs *listening* regardless of whether it is authenticated; the
container's network looks fine from the host side while the legacy ruleset
drops its traffic; `getUpdates` swallows Telegram's 404. The reliable check is
the one that asks the remote end — `getMe` for the token, a `curl` from inside
the container for egress, and the PONG call before anything else. That is why
the reproduction guide and the demo script both start by proving the model is
reachable rather than trusting the stack to look up.
