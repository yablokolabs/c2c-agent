# C2C — Claude Code Project Instructions

## Project

C2C — Cancellation to Compensation

A durable AI agent for airline disruption compensation cases.

Core thesis:

> The hard part of agentic AI isn't making an agent reason once.
> It's making it reliably stay with a real-world problem until the
> problem is actually resolved.

Project root:

`/home/azureuser/yablokolabs/c2c-agent`

The official hackathon brief is:

`./micro1_First_Hackathon97ce7c5.pdf`

Always treat that PDF as the authoritative competition specification.

---

# Core Stack

Expected stack:

- Python
- Claude
- NanoClaw
- FastAPI
- Pydantic
- Restate
- Docker / Docker Compose
- Telegram
- pytest
- synthetic airline simulator
- structured JSONL trajectory recorder
- Git/GitHub

Each component must have a clear responsibility.

## Responsibility boundaries

### Claude
Reasoning/model.

### NanoClaw
Agent runtime and tool use.

### FastAPI
HTTP/control plane.

### Restate
Durable workflow execution and authoritative long-running case state.

### Docker
Reproducibility, isolation and controlled failure injection.

### Telegram
Human interaction surface.

### Synthetic airline simulator
Controlled external environment.

### Python evaluation harness
Benchmarking and empirical evidence.

### Git/GitHub
Development and experiment provenance.

Architectural principle:

**Agents reason. Workflows remember.**

Do not make NanoClaw or FastAPI the authoritative durable workflow
state store when Restate should own that responsibility.

---

# Existing Environment

Host:

- Ubuntu 24.04.4 LTS
- x86_64
- Azure VM
- Docker 29.1.3
- Claude Code 2.1.250

Restate is already running locally and port 9070 is exposed.

DO NOT reinstall, destroy or replace the existing Restate deployment.

Before integrating with it:

- inspect its version
- inspect containers/processes
- inspect ports
- determine correct SDK/service connectivity
- document findings

Do not assume 9070 is the correct endpoint for every Restate
interaction.

---

# Hackathon Development Method

This project must be built experimentally.

Always use:

OBSERVE FAILURE
→ FORM HYPOTHESIS
→ IMPLEMENT CHANGE
→ RUN SAME EVALUATION
→ SAVE RESULTS
→ DOCUMENT
→ COMMIT
→ KEEP / REVISE / REMOVE

Do not optimize for making the project look successful.

Never fabricate improvement.

If an experiment reduces performance, record that result.

If a component provides no measurable or architectural value, consider
removing it.

---

# Baseline

Build and run a fair baseline before evaluating the final agent.

The baseline must use:

- the same synthetic compensation policy
- the same benchmark cases
- preferably the same underlying model

but without:

- tool-enabled agent orchestration
- independent verifier
- durable workflow
- workflow memory
- Restate advantages

Do not intentionally cripple the baseline.

Primary metric:

**Case Resolution Accuracy**

Secondary metrics should include:

- eligibility accuracy
- compensation accuracy
- unsupported claims
- unsupported rejection challenges
- evidence sufficiency
- false escalation
- workflow completion
- failure recovery
- duplicate consequential actions
- runtime
- model calls
- tokens
- approximate cost where measurable

Metric definitions must be established before final evaluation.

---

# Benchmark

Use a deterministic synthetic compensation policy.

Never represent it as the actual law or policy of any airline.

Clearly label:

**C2C Synthetic Hackathon Compensation Policy**

Benchmark should contain at least 15 cases, preferably around 20.

Include:

- eligible cancellation
- weather/extraordinary circumstances
- operational disruption
- missed connection
- advance notice
- missing evidence
- invalid rejection
- valid rejection
- additional evidence request
- duplicate event
- timeout
- worker crash
- conflicting documents
- partial settlement
- eventual resolution
- ambiguous/adversarial case

Every benchmark case needs machine-readable ground truth.

---

# Synthetic World Only

All passengers, airlines, claims, external responses, payments and
legal/escalation actions used in the demo must be synthetic.

Do not:

- contact real airlines
- submit real claims
- submit legal documents
- contact courts
- impersonate passengers
- use real passenger PII in benchmark data

Consequential actions require explicit human approval.

Examples:

- submit claim
- send follow-up
- challenge rejection
- escalate
- accept settlement

Any legal-looking artifact must clearly state:

**SYNTHETIC DEMO**
**NOT FOR SUBMISSION**
**NOT LEGAL ADVICE**

Never generate something presented as an official court-issued notice.

---

# Agent Design

Prefer two intelligent agents unless evaluation proves additional
agents useful.

## Caseworker

Responsible for:

- evidence analysis
- missing evidence identification
- policy lookup
- eligibility assessment
- compensation assessment
- claim preparation
- airline response analysis
- follow-up
- rejection challenge
- escalation draft
- next-action recommendation

## Verifier

Independently verifies consequential conclusions including:

- eligibility
- compensation
- evidence sufficiency
- rejection challenge
- escalation
- contradictions
- unsupported assertions

Verifier must be capable of rejecting a Caseworker decision.

Avoid unnecessary agent swarms.

---

# Restate

Use Restate purposefully for:

- durable workflows
- retries
- timers
- suspension/resumption
- external events
- human approval waits
- crash recovery
- idempotency
- prevention of duplicate side effects

Important invariants:

- claim must not be submitted twice because of retry
- escalation must not execute twice
- rejected human action must not execute
- restart must not lose case state
- duplicate external events must not duplicate side effects

Restate improving durability without improving reasoning accuracy is a
valid experimental result.

Record those metrics separately.

---

# NanoClaw

NanoClaw is the agent runtime, not the authoritative case database.

Before integration:

- inspect the current upstream version
- record exact version/commit
- document installation/configuration
- document session persistence
- document relevant logs
- export normalized trajectories separately

Do not rely solely on ephemeral Docker/container logs for hackathon
trajectories.

---

# Trajectories

Maintain structured trajectories from the beginning.

Canonical format:

`trajectories/runs/<run-id>/events.jsonl`

Useful fields:

- timestamp
- run_id
- case_id
- agent
- event_type
- workflow_state
- tool
- input
- output
- duration_ms
- success
- git_sha

Useful event types:

- USER_INPUT
- AGENT_START
- MODEL_REQUEST
- MODEL_RESPONSE
- TOOL_CALL
- TOOL_RESULT
- VERIFIER_REQUEST
- VERIFIER_PASS
- VERIFIER_REJECT
- WORKFLOW_TRANSITION
- WORKFLOW_SUSPEND
- WORKFLOW_RESUME
- EXTERNAL_EVENT
- RETRY
- ERROR
- HUMAN_APPROVAL_REQUIRED
- HUMAN_APPROVED
- HUMAN_REJECTED
- FINAL_DECISION

Also generate judge-readable Markdown trajectories.

Do NOT attempt to save private chain-of-thought or hidden model
reasoning.

Instead preserve:

- prompts
- instructions
- explicit decision rationale
- tool calls
- tool responses
- verifier decisions
- retries
- errors
- workflow transitions
- approvals
- outcomes

---

# Prompt Provenance

Important prompts must be version controlled.

Maintain:

agents/caseworker/SYSTEM_PROMPT.md
agents/verifier/SYSTEM_PROMPT.md

and prompt versions under:

prompts/

Never silently change a meaningful evaluation or agent prompt.

Benchmark outputs should identify the Git SHA and prompt/config version.

---

# Experiments

Maintain:

`experiments/`

Each meaningful experiment must record:

## Hypothesis
## Motivation
## Change
## Evaluation
## Before
## After
## Failed cases
## Cost impact
## Decision
## Learning
## Git SHA

Decision must be one of:

KEEP
REVISE
REMOVE

Never delete evidence of failed experiments.

---

# Improvement Changelog

Maintain continuously:

`IMPROVEMENT_CHANGELOG.md`

Do not reconstruct it only at the end.

For every meaningful evaluated change record:

- stage
- hypothesis
- change
- primary metric
- secondary metrics
- cost
- decision
- evidence
- Git SHA

---

# Failure Journal

Maintain:

`FAILURES.md`

Record important failures with IDs.

Include:

- observed behavior
- expected behavior
- affected case
- evidence
- root cause
- corrective experiment
- outcome
- lesson
- Git SHA

Failures are part of the submission evidence.

---

# Git Discipline

Git history is part of the experimental record.

Use small meaningful commits.

Do not:

- rewrite genuine experiment history
- squash meaningful benchmark stages before submission
- fabricate earlier commits
- modify old results to make later stages appear stronger

Good examples:

chore: initialize C2C hackathon project
docs: define problem and user
eval: add synthetic policy and benchmark
baseline: implement direct model baseline
results: record baseline evaluation
agent: add structured evidence extraction
verify: add independent verifier
workflow: add Restate durability
test: add failure injection
runtime: integrate NanoClaw
channel: add Telegram
results: record final benchmark

Use milestone tags when genuine:

baseline-v0
evidence-v1
agent-v2
verified-v3
durable-v4
final-v1

Evaluation outputs should record:

- timestamp
- Git SHA
- stage
- model
- benchmark version
- prompt/config version

Never overwrite historical evaluation outputs.

---

# Documentation

Maintain at minimum:

README.md
docs/HACKATHON_REQUIREMENTS.md
docs/PROBLEM.md
docs/PERSONAL_MOTIVATION.md
docs/ARCHITECTURE.md
docs/STACK.md
docs/DECISIONS.md
docs/ENVIRONMENT.md
docs/EVALUATION.md
docs/DEMO_SCRIPT.md
docs/RECORDING.md
docs/LIMITATIONS.md
IMPROVEMENT_CHANGELOG.md
FAILURES.md

The four items the brief asks to be submitted are named the way the brief
names them, so a judge does not have to hunt:

REPRODUCTION_GUIDE.md      deliverable 02, the reproduction guide
trajectories/README.md     deliverable 04, the agent trajectories

The reproduction guide replaces what was previously `docs/REPRODUCTION.md`,
`REPRODUCE_AND_RECORD.md` and `FROM_SCRATCH.md` — three overlapping documents
where the brief asks for one. Recording guidance was never part of that
deliverable and lives in `docs/RECORDING.md` beside the script.

README should be optimized for judges and explain quickly:

- who has the problem
- why it matters
- architecture
- what is agentic
- baseline vs final
- biggest improvement
- reproduction
- trajectories
- simulation boundary
- main failure
- hot take

---

# Reproducibility

Target commands:

make setup
make up
make down
make test

make baseline
make evaluate
make compare

make demo
make demo-reset
make demo-advance

make failure-tests
make trajectories
make reproduce

A judge should be able to run evaluation without Telegram.

Test final reproduction from a clean clone.

---

# Evaluation Results

Persist raw results under:

evaluation/results/

Never overwrite old runs.

Every run must contain enough metadata to reproduce it.

Do not fabricate missing token/cost information.

If unavailable, state that it could not be measured.

---

# Failure Injection

Implement reproducible tests for:

- airline API 503
- timeout
- worker crash
- FastAPI restart
- NanoClaw restart
- duplicate external event
- duplicate approval
- agent error
- crash around consequential side effect

Measure:

- recovery
- preserved state
- duplicate actions
- correct final outcome

---

# Keep the Stack Small

Do not add unless a demonstrated need exists:

- Kubernetes
- Kafka
- ClickHouse
- Redis
- PostgreSQL
- vector database
- React frontend
- voice
- WhatsApp
- Slack
- unnecessary MCP infrastructure
- large multi-agent swarms

Every major component must answer:

**What user problem, hackathon requirement, or measured failure does
this solve?**

---

# Personal Motivation

The project was inspired by the creator's experience on a
Dublin → Paris → Bangalore journey where a delayed first leg caused a
missed connection and a substantially longer wait in Paris.

The creator later pursued compensation through repeated follow-up and
formal escalation and recalls eventually receiving a substantial
refund.

Treat this only as motivation.

Do not use the anecdotal historical refund as benchmark ground truth.

Do not generalize from this anecdote to claims about airline behavior.

The project investigates the broader "persistence gap":

valid outcomes may depend partly on whether the passenger has the
knowledge, time and persistence to pursue the process.

---

# Development Reporting

After each meaningful stage report:

STAGE
HYPOTHESIS
IMPLEMENTATION
RESULT
FAILURES
DECISION
GIT SHA
ARTIFACTS
NEXT EXPERIMENT

Do not report only "done".

---

# Final Rule

The project is judged on evidence, not architectural complexity.

Always prefer:

real experiment
+
saved result
+
documented failure
+
clear Git history

over an unsupported claim that the architecture is better.
