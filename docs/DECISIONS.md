# Decisions

Each entry records what was decided, what forced it, and what would reverse it.

---

## D1 — The compensation policy is synthetic, with deliberately non-real numbers

**Decision.** Write `benchmark/POLICY.md` from scratch, with distance bands
(1,200 km / 4,000 km), amounts (180 / 420 / 750 units), a delay threshold of
3h30m, a 12-hour recovery window and a 56-day escalation clock — none of which
match any real scheme.

**Why.** Two reasons, one required and one useful.

Required: the hackathon rules and the project brief both forbid representing
anything here as real law or a real airline's policy.

Useful, and this turned out to matter more: if the policy used real thresholds,
a model could score well by recalling the real regulation rather than by reading
the document in front of it. That would measure the wrong thing. With invented
numbers, every correct answer has to come from grounding in the supplied text.
The benchmark measures document-grounded reasoning, not recall.

**Reverses if.** Nothing plausible. This is load-bearing for the whole
evaluation.

---

## D2 — Ground truth is hand-authored, not computed by a rules engine

**Decision.** Each case's `ground_truth` block is written by hand, with a
`derivation` listing the exact policy clauses that produce it. A test asserts
every cited clause actually exists in `POLICY.md`.

**Why.** The tempting alternative is to write a deterministic policy engine and
use its output as ground truth. That is a trap: the engine would then be
available as an oracle. Any tool the agent could call that returns the answer
turns the benchmark into a test of whether the agent can call one function.

Instead the policy is given to the model as a *document to reason over*, and
tools provide retrieval and arithmetic, never verdicts.

**Reverses if.** The benchmark grows past roughly fifty cases, where
hand-authoring stops being reliable. At that point the right move is a rules
engine used only to *check* hand-authored ground truth for self-consistency,
never to generate it and never exposed to the agent.

---

## D3 — The primary metric is a strict three-way conjunction

**Decision.** Case Resolution Accuracy counts a case only when the next action,
the compensation figure and the eligibility determination are all correct.

**Why.** Each component alone is gameable by guessing the majority class. The
recorded trivial floors make this concrete: always answering "close the case,
nothing owed" scores 0.25 on the primary metric, and always answering "submit,
420 units" scores 0.10. Reporting eligibility accuracy alone would have made
the constant guesser look respectable.

The conjunction also matches what the user needs. A passenger told the right
amount and the wrong action does not get paid.

**Reverses if.** Never for the headline number. Component rates are reported
alongside it precisely so the conjunction can be decomposed when diagnosing.

---

## D4 — Two model backends behind one interface

**Decision.** `c2c/llm.py` speaks to either the Anthropic SDK (when
`ANTHROPIC_API_KEY` is set, or when both `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` are set for local proxy) or the `claude -p` CLI (otherwise).

**Why.** The build host has no API key; see `docs/ENVIRONMENT.md`. Hiding that
and reporting numbers as if they came from the SDK would misreport how the
results were produced. Exposing it as a backend choice means a judge with an
API key runs the documented path, a judge with a Claude subscription runs the
same code through the CLI, and both get comparable numbers.

**Consequence.** The CLI backend adds a fixed harness system prompt that C2C did
not author. Results report `harness_overhead_tokens` separately from
`task_input_tokens` so C2C never takes credit or blame for those tokens.

**Reverses if.** An API key becomes available, in which case `api` becomes the
default automatically and no code changes.

---

## D5 — A fixed system prompt, with the policy inside it

**Decision.** The policy goes in the system prompt, byte-identical across every
call in a run, and the per-case dossier goes in the user turn.

**Why.** Measured, not assumed. With a varying prefix, each CLI call wrote a
fresh prompt cache and cost $0.0162. With a stable prefix, the first call writes
the cache and the rest read it, at $0.0025 — a 6.4x reduction. Since the policy
is the largest constant part of every prompt, putting it in the cached prefix is
free accuracy-wise and large cost-wise.

**Reverses if.** A future agent design needs to vary the policy per case, e.g.
retrieving only the relevant clauses. That trade is worth re-measuring rather
than assuming: fewer tokens per call, but a cache miss on every call.

---

## D6 — Registering additively on the shared Restate server

**Decision.** C2C runs its own SDK service and registers it with the
pre-existing Restate 1.7.7 server rather than starting its own. Every service
it owns is prefixed `C2C`. It never deletes a deployment it did not create.

**Why.** The server was already running and already hosting an unrelated
project's services (`Outreach`, `LeadRegistry`, `ProspectLoop`). Registering a
deployment is additive and does not disturb existing tenants; standing up a
second server, or reinstalling this one, would have risked them.

**Reverses if.** A judge reproducing from a clean environment has no Restate
server, in which case `docs/REPRODUCTION.md` covers starting a throwaway one.
The headline reasoning result does not require Restate at all.
