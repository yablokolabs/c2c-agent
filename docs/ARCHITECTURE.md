# Architecture

```
                        ┌──────────────────────────────┐
   Telegram / curl ────▶│  FastAPI control plane :8099 │
   (human approvals)    │  /c2c/*                      │
                        └───────┬──────────────┬───────┘
                                │              │
                    starts,     │              │  runs the agent
                    approves,   │              │  on demand
                    reads state │              ▼
                                │      ┌───────────────────┐
                                │      │  Caseworker       │
                                │      │  tools:           │
                                │      │   list_documents  │
                                │      │   read_document   │
                                │      │   policy_lookup   │
                                │      │   calculate       │
                                │      └────────┬──────────┘
                                │               │ verdict
                                │               ▼
                                │      ┌───────────────────┐
                                │      │  Verifier         │
                                │      │  pass / reject    │──┐
                                │      └───────────────────┘  │ one
                                │               ▲             │ revision
                                │               └─────────────┘
                                ▼
              ┌──────────────────────────────────────────┐
              │  Restate 1.7.7  (pre-existing, SHARED)   │
              │  admin :9070   ingress :8080             │
              │                                          │
              │   C2CCase  (Workflow, key = case_id)     │
              │     ctx.run      durable side effects    │
              │     ctx.promise  human approval waits    │
              │     ctx.sleep    56-day / 28-day clocks  │
              │     ctx.set      case state              │
              │                                          │
              │   (also hosts an unrelated project's     │
              │    Outreach / LeadRegistry / ProspectLoop)│
              └───────────────────┬──────────────────────┘
                                  │ HTTP, with an
                                  │ idempotency key
                                  ▼
                        ┌──────────────────────────────┐
                        │  Synthetic airline  :8099    │
                        │  /airline/*                  │
                        │   claims, challenges,        │
                        │   escalations                │
                        │   audit log of what LANDED   │
                        │   failure injection          │
                        └──────────────────────────────┘
```

C2C's SDK service listens on **:9095** and is what Restate calls back into.

## The organising principle

**Agents reason. Workflows remember.**

Every component boundary follows from it.

| Component | Owns | Explicitly does not own |
|---|---|---|
| Claude | the reasoning | any state |
| Caseworker / Verifier | one case's assessment, now | what happened last week |
| FastAPI | HTTP, and being the surface humans and the workflow talk to | case state, decisions |
| Restate | case state, timers, approval waits, exactly-once execution | any judgement about a claim |
| Airline simulator | the external world, and the audit log that measures it | anything C2C asserts about itself |

The temptation this resists is putting case state in the control plane, because
that is where the HTTP handlers are. Then a FastAPI restart loses a case, and a
retry submits a claim twice. Restate exists precisely so that neither is
possible, and giving it that job is the point of using it.

## The two evaluation axes, and why they are separate

The system is measured twice, because it can be good at one and bad at the
other, and a passenger needs both.

**Reasoning — 28 cases, single-turn.** Does it reach the right conclusion?
Baseline and agent get the same model, the same policy, the same dossier and the
same output schema. The agent additionally gets tools and a verifier. Primary
metric: Case Resolution Accuracy.

**Durability — 6 scenarios, failure injection.** Does it stay with the case?
503s, worker kills, duplicate events, duplicate approvals, a rejected approval,
and a crash in the window around a consequential side effect. Ground truth is
the airline's audit log of actions that actually landed.

The baseline scores nothing on the durability suite. That is not a win for the
agent and is not reported as one: the baseline is a single prompt and has no
lifecycle to be durable about. What the durability suite measures is whether the
Restate layer delivers the invariants it was added for, not whether an agent
beats a prompt.

## Request flow, one case end to end

1. `POST /c2c/cases/R12/open` starts the `C2CCase` workflow keyed `R12`.
   Opening it twice attaches to the same workflow rather than starting a second.
2. The workflow's `assess` step calls back to `POST /c2c/assess`, which runs the
   caseworker and the verifier. `ctx.run` means a crash here retries, and a
   success here is never re-run.
3. The verdict names a consequential action, so the workflow sets state
   `AWAITING_APPROVAL` and suspends on `ctx.promise("approval")`. It consumes
   nothing while waiting. This can last days.
4. A human answers via `POST /c2c/cases/R12/approve`. A refusal returns before
   any side effect is reachable.
5. On approval, `ctx.uuid()` inside a durable step produces a replay-stable
   idempotency key, and the claim goes to the airline under that key. A retry
   presents the same key and the airline deduplicates it.
6. The workflow waits on whichever comes first: the carrier's reply, or
   `ctx.sleep(56 days)`. On silence it proposes escalation, which needs its own
   approval.
7. A rejection goes back through assessment, then a challenge, then a 28-day
   clock, then escalation.

## What was deliberately not built

- **A rules engine for the policy.** It would have become an oracle the agent
  could call instead of reading the policy. See `docs/DECISIONS.md` D2.
- **A database.** Restate holds the case state. Adding Postgres would mean two
  sources of truth and a synchronisation bug waiting to happen.
- **A second Restate server.** The existing one is shared; C2C registers
  additively and never touches another tenant's deployment.
- **Separate containers for the control plane and the airline.** They are
  separate concerns, not separate deployments, and the failure suite restarts
  the whole process anyway.
