# Stack

Every component answers one question: **what user problem, hackathon
requirement, or measured failure does this solve?** Anything that could not
answer it is in the last section.

| Component | Version | Why it is here |
|---|---|---|
| Python | 3.12.3 | host default |
| Claude (Haiku 4.5) | `claude-haiku-4-5-20251001` | the reasoning, for both baseline and agent |
| Claude Code CLI | 2.1.250 | model transport, because this host has no API key |
| Pydantic | 2.13.5 | one verdict schema shared by baseline, agent, verifier and grader |
| FastAPI | 0.115+ | HTTP control plane and the synthetic airline |
| Restate | 1.7.7 (pre-existing) | durable case state, timers, approval waits, exactly-once execution |
| restate-sdk | 1.0.4 | Python bindings for the above |
| hypercorn | latest | Restate calls its SDK endpoints over HTTP/2 bidi; uvicorn does not serve it |
| httpx | 0.27+ | the workflow's calls to the control plane and the airline |
| pytest | 8.3+ | 59 tests over the benchmark, tools, simulator and orchestration |
| uv | 0.12.5 | reproducible environment from `pyproject.toml` |
| Git / GitHub | — | the experimental record |

## Responsibility boundaries

**Claude** reasons. It holds no state and is never asked to remember anything
between cases.

**The caseworker and verifier** are the two agents. Two, not five. A third
agent was considered — a dedicated evidence extractor — and rejected before
building, because the caseworker's `read_document` tool already gives per
document attention and an extra agent would have added a hop and a serialisation
boundary for no hypothesis anyone could state.

**FastAPI** owns HTTP. It is the surface humans, the workflow and the demo all
talk to. It deliberately holds no case state: if it did, restarting it would
lose a case, which is the exact failure Restate is here to prevent.

**Restate** owns everything that has to survive a process dying. Case state,
the 56-day and 28-day policy clocks, human approval waits that last days, and
exactly-once execution of consequential actions. It decides nothing about a
claim.

**The synthetic airline** is the controlled external world, and more usefully it
is the *instrument*: its audit log distinguishes actions attempted from actions
that landed, which is how "the claim was submitted exactly once" is measured
rather than asserted.

**The evaluation harness** produces the evidence. It is separate from the
systems it measures and scores both identically.

## Restate: which feature, which invariant

Restate is the largest dependency, so it owes the clearest account. Each feature
maps to a named invariant from the project brief, and each is exercised by a
scenario in the durability suite.

| Restate feature | Invariant | Scenario |
|---|---|---|
| workflow keyed by `case_id` | a duplicate intake cannot start a second lifecycle | D03, D04 |
| `ctx.run` | a side effect that succeeded is never re-executed on replay | D01, D06 |
| `ctx.uuid()` in a durable step | idempotency keys are replay-stable, so a retry reuses the key | D01, D06 |
| `ctx.promise` | a human approval outlives the process, and resolves once | D02, D03, D04 |
| approval branch before any call | a rejected action never executes | D05 |
| `ctx.sleep` | the 56-day and 28-day clocks survive restarts | exercised by the demo |
| `ctx.set` | case state survives `kill -9` | D02 |

If the durability suite had shown these invariants holding without Restate, or
Restate failing to deliver them, that would be recorded as such. The results are
in `evaluation/results/durability--*.json`.

## NanoClaw

Present on the host at `~/yablokolabs/nanoclaw`, upstream
`github.com/nanocoai/nanoclaw` at commit `a099c71f` (container claude-code
2.1.238, agent SDK 0.3.238). **Pre-existing; not built for this hackathon.**

It was evaluated as the agent runtime and **not adopted**. The reason is
recorded rather than glossed: NanoClaw's value is running agents in isolated
containers with persistent sessions and chat-channel bindings. C2C's agents are
stateless single-case functions — the session state that NanoClaw would persist
is exactly the state this project argues belongs in Restate, not in an agent
runtime. Adopting it would have meant two systems claiming to remember the case,
which is the architecture this project exists to argue against.

Its container logs are also ephemeral, and the brief requires durable
trajectories, so trajectories are exported by C2C's own recorder either way.

This is a component removed for a stated reason, not one that failed. See
`IMPROVEMENT_CHANGELOG.md`.

## Telegram

The human approval surface. Consequential actions block on
`ctx.promise("approval")`, and something has to answer that promise.

The workflow does not care what does. The approval arrives as
`POST /c2c/cases/{id}/approve`, which a Telegram bot, a curl command or a web
form can all send. The evaluation and the durability suite use HTTP directly, so
**a judge can reproduce every result without Telegram**, which is a requirement
in `REPRODUCTION_GUIDE.md`.

## Deliberately not used

| Not used | Why |
|---|---|
| PostgreSQL / Redis | Restate holds case state. A second store means two sources of truth. |
| Kafka | there is no stream. Carrier responses arrive as HTTP events. |
| a vector database | the policy is 1,800 words and fits in a cached prompt. Retrieval over it would add a failure mode and remove none. |
| a rules engine for the policy | it would become an oracle the agent could call instead of reading the policy. `docs/DECISIONS.md` D2. |
| Kubernetes | two processes. |
| a React frontend | the user surface is a chat approval and a claim document, neither of which needs one. |
| large multi-agent swarms | two agents, each with a stated job. A third was considered and rejected above. |
