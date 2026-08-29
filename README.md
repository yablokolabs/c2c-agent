# C2C — Cancellation to Compensation

**A durable agent that stays with an airline disruption claim until the claim is
actually resolved.**

> The hard part of agentic AI isn't making an agent reason once.
> It's making it reliably stay with a real-world problem until the problem is
> actually resolved.

Everything here is synthetic. No real airline is contacted, no real claim is
submitted, and every legal-looking artifact is stamped
**SYNTHETIC DEMO — NOT FOR SUBMISSION — NOT LEGAL ADVICE**.

---

## Who has this problem

A passenger whose flight was cancelled or badly delayed, who is probably owed
money, and who has a job. Not a lawyer. Someone with a booking reference, a
blurry photo of a departures board, and about forty minutes of patience.

Secondarily, the small claims operations and passenger-rights non-profits who do
this at volume and currently solve it by paying a person to read the same six
documents over and over.

## The bottleneck is the calendar, not the decision

Working out whether a claim is worth anything takes a competent person about
fifteen minutes. Everything after that is where claims die:

| Step | Elapsed | What the passenger must do |
|---|---|---|
| Assess | 15 min | read a policy they have never seen |
| Submit | 20 min | assemble evidence |
| **Wait** | **4–8 weeks** | remember that they are waiting |
| Read the rejection | 10 min | notice it contradicts the airline's own record |
| Challenge | 30 min | know that challenging is even an option |
| **Wait again** | **4 weeks** | remember, again |
| Escalate | 45 min | know the escalation is ripe, and not before |

The work is small. The calendar is enormous. Between the first click and the
money there are two or three multi-week silences, and each one is a place where
a valid claim quietly dies — not because it was wrong, but because nobody was
still holding it.

That is the **persistence gap**: whether you get what the policy says you are
owed depends less on the merits than on whether you have the knowledge, the
time, and the stubbornness to keep coming back for three months.

Full write-up: [`docs/PROBLEM.md`](docs/PROBLEM.md). Why I care:
[`docs/PERSONAL_MOTIVATION.md`](docs/PERSONAL_MOTIVATION.md).

---

## Architecture

**Agents reason. Workflows remember.** Every boundary follows from that.

```
  human ──▶ FastAPI control plane ──▶ Caseworker (4 tools, ≤10 steps)
              :8099                        │
                │                          ▼
                │                    Verifier (independent, can reject)
                ▼
        Restate 1.7.7  ──── ctx.run       exactly-once side effects
        (pre-existing,  ─── ctx.promise   approvals that outlive the process
         SHARED)        ─── ctx.sleep     the 56-day and 28-day clocks
                        ─── ctx.set       state that survives kill -9
                │
                ▼
        Synthetic airline ── audit log of what LANDED, not what was attempted
```

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
[`docs/STACK.md`](docs/STACK.md) ·
[`docs/DECISIONS.md`](docs/DECISIONS.md)

### What is agentic about it

- **Tools, not an oracle.** The caseworker retrieves documents, looks up policy
  clauses and computes. **No tool returns a verdict** — a `check_eligibility()`
  backed by a rules engine would have turned the benchmark into a test of
  whether the agent can call one function.
- **Independent verification.** The verifier gets the case and the policy but
  **not** the caseworker's working, so it is a second opinion rather than a
  reviewer inheriting a wrong turn. It can reject, and a rejection sends the
  case back for one revision. A rejection citing no clause or document is
  downgraded to a pass, because an uncited rejection can talk a correct
  caseworker out of a correct answer.
- **Durable memory outside the agent.** The agent is stateless. The case lives
  in Restate, where it survives `kill -9`, waits days for a human, and cannot
  execute a consequential action twice.
- **Human approval that is enforced, not requested.** Every consequential action
  blocks on a durable promise, and the rejection branch returns before any
  outbound call is reachable.

---

## Results

Two suites, because a system can be good at one and bad at the other, and a
passenger needs both.

### Suite A — reasoning · 28 synthetic cases

Primary metric **Case Resolution Accuracy**: a case counts only when the next
action, the compensation figure, **and** the other entitlements (duty of care,
downgrade) are all correct at once. Same model, same policy, same dossier, same
schema for every system.

<!--RESULTS_TABLE-->

### Suite B — durability · 6 failure-injection scenarios

| Metric | Result |
|---|---|
| Scenarios passed | **6 / 6** |
| Workflow completion | 1.00 |
| Failure recovery | 1.00 |
| State preserved after `kill -9` | 1.00 |
| **Duplicate consequential actions** | **0** |

The load-bearing one is **D06**: SIGKILL the worker inside the submission
window. The carrier received **2 submission attempts** and **1 claim landed** —
the crash genuinely did cause a retry, and the idempotency key, generated inside
a durable step and therefore stable across replay, absorbed it. And **D05**:
when a human refuses, the carrier is called **zero** times, not once and then
reversed.

**The baseline scores nothing here, and that is not reported as a win.** It is a
single prompt with no lifecycle; there is nothing for a crash to interrupt.
Suite B measures whether Restate delivers the invariants it was added for.

Raw results: [`evaluation/results/`](evaluation/results/) — never overwritten,
each carrying its commit, model, backend and prompt digests.

---

## The biggest improvement, and an honest note about it

<!--BIGGEST_IMPROVEMENT-->

---

## Reproducing this

```bash
git clone https://github.com/yablokolabs/c2c-agent.git && cd c2c-agent
make setup
make test        # 76 tests, no model calls, no services
make reproduce   # baseline + agent + comparison
```

Needs Python 3.11+, [uv](https://docs.astral.sh/uv/), and either an
`ANTHROPIC_API_KEY` or a logged-in Claude Code CLI. **No Restate server, no
Docker and no Telegram** for the headline result.

For the durability half: `make up && make failure-tests && make down`.

Full guide with versions, expected output, runtime and measured cost:
[`docs/REPRODUCTION.md`](docs/REPRODUCTION.md).

---

## Trajectories

`trajectories/runs/<run-id>/events.jsonl` is canonical; `trajectory.md` is the
same thing rendered for a human. Every run of every agent is captured: the
instructions, each tool call and what came back, the stated rationale, the
verifier's decision, retries, workflow transitions, human approvals, and the
outcome.

No hidden reasoning is captured — only material a reviewer can audit.

```bash
make trajectories
```

---

## The simulation boundary

| Simulated | Real |
|---|---|
| the carrier and its claims system | the model |
| every passenger, booking and document | the durable workflow engine and its crash semantics |
| the compensation policy (SHCP v1.1) | the injected failures |
| the Synthetic Passenger Rights Body | the audit log the results are measured from |

The policy's thresholds deliberately match no real scheme — not only for the
ground rules, but because a model that could recall the real regulation would
never have to read the document in front of it. Every correct answer here has to
be grounded in the supplied text.

---

## The main failure mode

<!--MAIN_FAILURE-->

---

## Hot take

<!--HOT_TAKE-->

---

## Where everything is

| | |
|---|---|
| Problem and user | [`docs/PROBLEM.md`](docs/PROBLEM.md) |
| Architecture, stack, decisions | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/STACK.md`](docs/STACK.md) · [`docs/DECISIONS.md`](docs/DECISIONS.md) |
| **Improvement changelog** | [`IMPROVEMENT_CHANGELOG.md`](IMPROVEMENT_CHANGELOG.md) |
| Experiments, including removed ones | [`experiments/`](experiments/) |
| **Failure journal** | [`FAILURES.md`](FAILURES.md) |
| Metrics and their weaknesses | [`docs/EVALUATION.md`](docs/EVALUATION.md) · [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) |
| Reproduction | [`docs/REPRODUCTION.md`](docs/REPRODUCTION.md) |
| Demo script | [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) |
| Agent instructions | [`agents/caseworker/SYSTEM_PROMPT.md`](agents/caseworker/SYSTEM_PROMPT.md) · [`agents/verifier/SYSTEM_PROMPT.md`](agents/verifier/SYSTEM_PROMPT.md) |
| The synthetic policy | [`benchmark/POLICY.md`](benchmark/POLICY.md) |
| Hackathon requirement mapping | [`docs/HACKATHON_REQUIREMENTS.md`](docs/HACKATHON_REQUIREMENTS.md) |
| What existed before the competition | [`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md) |
