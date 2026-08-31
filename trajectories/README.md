# Agent trajectories

*Deliverable 04. Representative trajectories for every agent, with what the agent
did, how its tools responded, and the feedback that shaped its next step.*

Two formats per run, in `runs/<run-id>/`:

| File | What it is |
|---|---|
| `events.jsonl` | canonical. One JSON object per line. |
| `trajectory.md` | the same, rendered for a human. `make trajectories` regenerates it. |

Private chain-of-thought is deliberately **not** captured. What is captured is
what a reviewer needs to audit a decision: the instructions, every tool call and
what came back, the stated rationale, the verifier's decision, retries, workflow
transitions, human checkpoints and the outcome.

---

## Start here

### The agent doing its whole job — `20260830T140743Z-final-v2-470136`

197 events over 28 cases. Caseworker, verifier, and one revision after a
rejection. This is the run behind the headline **0.93**.

### One case, from a real passenger interaction — `20260830T200959Z-live-006d39`

147 events on a single case, driven by `make demo` rather than the benchmark.
Easiest to follow end to end.

### The verifier disagreeing, repeatedly — `20260830T083702Z-final-v1-243cd1`

390 events with **10 verifier rejections and 23 retries**. The messiest run here
and the most informative: it shows the verifier actually pushing back and the
caseworker revising, which the cleaner runs barely exercise.

> This run went through a gateway that served a different model than requested,
> so its *scores* are void — see FAILURES.md **F-007**. The trajectories are
> still a fair record of the interaction pattern, and it is labelled rather than
> quietly dropped.

### The baseline, for contrast — `20260830T091310Z-baseline-v2-58bfd9`

114 events, 28 cases, one model call each. No tools, no verifier, nothing to
show between question and answer. Worth a glance precisely because it is so
short: the difference in shape *is* the difference between the two systems.

---

## Every agent, and where to see it

| Agent | Instructions | Representative run |
|---|---|---|
| **Caseworker** | [`agents/caseworker/SYSTEM_PROMPT.md`](../agents/caseworker/SYSTEM_PROMPT.md) | `final-v2-470136`, any case |
| **Verifier** | [`agents/verifier/SYSTEM_PROMPT.md`](../agents/verifier/SYSTEM_PROMPT.md) | `final-v1-243cd1` — 10 rejections |
| **Intake** | [`agents/intake/SYSTEM_PROMPT.md`](../agents/intake/SYSTEM_PROMPT.md) | `runs/*-intake-*` — created when a passenger messages the bot |
| **Baseline** | [`prompts/baseline_v2.md`](../prompts/baseline_v2.md) | `baseline-v2-58bfd9` |

---

## What a trajectory looks like

From `exp1-tools-89f2c7`, case R21 — the case whose decisive fact is buried in
document eight of nine:

```
start · caseworker
model out · 40172 ms      {"tool": "list_documents", "why": "establish what is on file"}
tool · list_documents
tool result               9 documents on file for R21:
                            D1 [booking_confirmation] …
                            D8 [correspondence] GULFMARK CUSTOMER SERVICE CONTACT NOTE
model out · 64151 ms      {"tool": "read_document", "args": {"doc_id": "D2"},
                           "why": "need the exact timestamp of the cancellation notification"}
```

Every tool call carries the agent's stated reason for making it, which is the
part that shows whether it was reasoning or guessing.

---

## The demo, as artifacts

`demo/` holds one verified end-to-end run: the transcript, the case summary and
the challenge letter the passenger receives, and the airline's audit of what
actually landed.

---

## Honest notes

- **44 run directories.** Most are the benchmark; several are failed or
  contaminated runs kept as evidence for FAILURES.md rather than deleted.
  `evaluation/results/README.md` says which results are valid.
- **The durable workflow emits no trajectory.** Seven declared event types
  (`WORKFLOW_TRANSITION`, `HUMAN_APPROVED`, and others) are never emitted. Case
  state lives in Restate and is readable through `GET /c2c/cases/{id}`, and the
  airline's audit log records what landed — so the evidence exists, but the human
  approval checkpoints are not in these files. See `docs/ARCHITECTURE.md`.
