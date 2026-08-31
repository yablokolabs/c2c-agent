# Hackathon requirements, and where each one is met

Mapped against `micro1_First_Hackathon97ce7c5.pdf`.

## The four questions

| | Where |
|---|---|
| **Who has this problem?** | `docs/PROBLEM.md` — a passenger who is probably owed money and has a job; secondarily the small claims operations that do this at volume. |
| **What bottleneck makes it worth solving?** | `docs/PROBLEM.md` — the work is small, the calendar is enormous. Two or three multi-week silences, each one where a valid claim quietly dies. |
| **Does the agent solve it well?** | `docs/EVALUATION.md`, `IMPROVEMENT_CHANGELOG.md`, `evaluation/results/`. Two suites, fair baseline, results reported including where they are flat. |
| **Can another person reproduce the result?** | `REPRODUCTION_GUIDE.md`. The headline result needs no Restate, no Docker and no Telegram. |

## Judging criteria

| Criterion | Where |
|---|---|
| Problem & user value (15) | `docs/PROBLEM.md`, `docs/PERSONAL_MOTIVATION.md` |
| Agent solution & engineering (30) | `docs/ARCHITECTURE.md`, `docs/STACK.md`, `docs/DECISIONS.md`, `agents/*/SYSTEM_PROMPT.md` |
| End-to-end quality (20) | `make demo`, `docs/DEMO_SCRIPT.md`, the claim artifacts the workflow produces |
| Measured improvement (15) | `IMPROVEMENT_CHANGELOG.md`, `experiments/`, `evaluation/results/` |
| Reproducibility (15) | `REPRODUCTION_GUIDE.md`, `Makefile`, `make reproduce` |
| Hot take / insights (5) | `README.md`, and `FAILURES.md` for what produced it |

## Ground rules

| Rule | How it is met |
|---|---|
| 01 — build with what you know | Python, FastAPI, Pydantic, pytest. Restate and NanoClaw were new and are documented as such. |
| 02 — make clear what existed before | `docs/ENVIRONMENT.md` has a "what existed before the competition" section: the Restate server and its unrelated tenants, the NanoClaw checkout, the Claude Code CLI. Everything in this repository was built for the hackathon. |
| 03 — licences and service terms | Restate (BSL), NanoClaw (MIT, inspected but not adopted), Anthropic models via an authenticated first-party client. No scraping, no circumvention. |
| 04 — consequential actions sandboxed, with human approval before the action | Every consequential action blocks on `ctx.promise("approval")` and the rejection branch returns before any call is reachable — measured by D05, where the carrier endpoint was called **0 times**. The "carrier" is an in-memory simulator with no outbound network. |
| 05 — a qualified human reviewer in the loop | Approval is required per action, per case. The agent's output is a recommendation with citations, never an executed decision. |
| 06 — legal and ethical use case | Helping a passenger claim what a policy says they are owed. No adversarial use, no scraping, no impersonation. |
| 07 — data you may share | Everything is synthetic and in the repository. No real passenger, airline, claim or regulator. Names and booking references are invented. |
| 08 — credentials out of the submission | No keys in the repository. Model access is by environment variable or an already-authenticated CLI. `.gitignore` covers `.env`. |
| 09 — every claim tied to evidence | Every number in the README and the changelog names the result file it came from. Metrics that could not be measured are `null` with a note, never estimated. |
| 10 — judges can run it | `make reproduce`. |

## Deliverables

| Deliverable | Where |
|---|---|
| 01 — solution code and improvement changelog | this repository; `IMPROVEMENT_CHANGELOG.md`; agent instructions in `agents/*/SYSTEM_PROMPT.md` and `prompts/` |
| 02 — reproduction guide | `REPRODUCTION_GUIDE.md`, with versions, commands, expected output, runtime and measured cost |
| 03 — solution video | `docs/DEMO_SCRIPT.md` is the script; the recording is submitted separately |
| 04 — agent trajectories | `trajectories/runs/<run-id>/events.jsonl` and `trajectory.md`, one per run, for every agent |

## The simulation boundary

Everything outside C2C is simulated, and the boundary is drawn at the HTTP call
to `/airline/*`:

- **Simulated:** the carrier, its claims system, its responses, its settlements,
  the Synthetic Passenger Rights Body, and every passenger, booking and document.
- **Real:** the model, the durable workflow engine and its crash semantics, the
  failures injected into the simulator, and the audit log the results are
  measured from.

No real airline is contacted. No real claim is submitted. No legal document is
sent anywhere. Every artifact that looks legal-ish carries
**SYNTHETIC DEMO — NOT FOR SUBMISSION — NOT LEGAL ADVICE**, and nothing is ever
presented as an official notice from a court or regulator.
