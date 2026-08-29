# EXP-004 — NanoClaw as the agent runtime

**Git SHA:** `bc4e9b8`
**Decision:** REMOVE

## Hypothesis

NanoClaw, as a purpose-built agent runtime with container isolation and
persistent sessions, would be a better home for the caseworker and verifier than
plain Python functions called from the control plane.

## Motivation

It was already on the host, it is the runtime the project brief names, and it
solves problems C2C would otherwise solve badly: sandboxing an agent that runs
untrusted-ish content, and keeping session state between invocations.

## Version inspected

```
~/yablokolabs/nanoclaw
upstream github.com/nanocoai/nanoclaw
commit a099c71f  ("chore(container): bump claude-code to 2.1.238 and agent SDK to 0.3.238")
```

Pre-existing on the host. Not built for this hackathon.

## Change

None was made. The evaluation happened before integration and the conclusion was
not to integrate.

## Evaluation

Read against the responsibility boundaries the project had already committed to,
specifically **agents reason, workflows remember**.

## Findings

**The persistent-session feature is the problem, not the benefit.** NanoClaw's
central value is that an agent remembers across invocations. C2C's whole
argument is that a case's memory belongs in the durable workflow, where it
survives a `kill -9`, resolves approvals that outlive the process, and enforces
exactly-once execution. Two systems both claiming to remember the case is not
redundancy; it is a synchronisation bug waiting for a crash, and whichever loses
becomes a cache that drifts.

**The isolation is real, and is not needed here.** C2C's agents read synthetic
documents from the repository and call four tools, one of which is arithmetic
with an AST allowlist. There is no untrusted code path for a container to
contain.

**The logs are ephemeral.** Durable trajectories are a deliverable. C2C's own
JSONL recorder was needed regardless, so NanoClaw would have added a second,
weaker trajectory source rather than replacing the need for one.

**The cost is real.** A container per agent invocation, on a benchmark that
makes roughly 150 model calls per run, against a control plane that currently
calls a Python function.

## Before / After

Not applicable. Nothing was measured because nothing was built. This is recorded
as a rejected design rather than a measured regression, and it is labelled as
such rather than presented as an experiment that produced numbers.

## Cost impact

Zero, which is the point.

## Decision

**REMOVE.** Recorded in `docs/STACK.md` with the reason, rather than the
component quietly omitted from the stack list.

## Learning

"Where does the memory live?" is an architectural fork, not a detail. Once it
was answered — the workflow, not the runtime, not the control plane — several
later decisions stopped being decisions: FastAPI holds no case state, the
caseworker takes a case and returns a verdict with nothing carried between
calls, and there is no database.

The generalisable form: when two components both offer to remember something,
picking one and being strict about it is worth more than the features of either.
A component that duplicates an invariant you have already assigned elsewhere is
a liability even when it is good.
