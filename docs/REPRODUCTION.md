# Reproduction guide

Written for someone starting from nothing.

The headline reasoning result needs **no Restate server, no Docker and no
Telegram**. The durability result needs a Restate server, and the guide covers
starting a throwaway one.

---

## 1. What you need

| | |
|---|---|
| OS | Linux or macOS. Developed on Ubuntu 24.04.4, x86_64. |
| Python | 3.11+ (3.12.3 used here) |
| [uv](https://docs.astral.sh/uv/) | 0.12.5+ — `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Model access | either an `ANTHROPIC_API_KEY`, **or** an authenticated Claude Code CLI |
| Disk | under 50 MB |

No database, no message broker, no cluster.

### Model access, either way

C2C picks a backend automatically:

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # -> uses the Anthropic SDK. Preferred.
```

If that variable is unset, it shells out to `claude -p` instead, which needs the
Claude Code CLI installed and logged in. That is what this host had, and it is
how every result in `evaluation/results/` was produced. Force either with
`C2C_LLM_BACKEND=api` or `C2C_LLM_BACKEND=cli`.

The two backends are not perfectly comparable: the CLI adds a fixed harness
system prompt C2C did not author. Results report
`harness_overhead_tokens` separately from `task_input_tokens` for that reason.

---

## 2. Setup

```bash
git clone https://github.com/yablokolabs/c2c-agent.git
cd c2c-agent
make setup
```

Expect:

```
c2c 0.1.0
model backend: api        (or: cli)
```

Then the tests, which make no model calls and need no services:

```bash
make test
```

Expect `59 passed` in under a second. These cover the benchmark's own integrity
(every ground-truth derivation cites a clause that exists; no constant answer
scores above 0.30), the tools, the simulator's deduplication, and the
orchestration rules.

---

## 3. The headline result

```bash
make baseline    # ~7 minutes, ~$1.20
make evaluate    # ~25 minutes, ~$6
make compare
```

Or all of it, including the tests, in one go:

```bash
make reproduce
```

### What you should see

`make compare` prints a table. The numbers from the recorded run are in
`docs/EVALUATION.md` and the raw files are in `evaluation/results/`. Yours will
be close but **not identical** — the model is sampled, not deterministic. Expect
Case Resolution Accuracy within roughly ±0.07 of the recorded figures across
28 cases, and the ordering (agent above baseline) to hold.

If your baseline and agent come out within 0.04 of each other, that is inside
the noise for a 28-case suite. Run each twice before concluding anything.

### Cost and runtime, measured

| Command | Model calls | Wall clock | Cost (cli backend) |
|---|---|---|---|
| `make test` | 0 | 0.3 s | $0 |
| `make baseline` | 28–30 | ~7 min | ~$1.14 |
| `make evaluate-tools` | ~120 | ~25 min | see the result file |
| `make evaluate` | ~150 | ~30 min | see the result file |
| `make failure-tests` | 0 | ~25 s | $0 |

Costs are what the backend itself reported, recorded per run in
`evaluation/results/*.json` under `totals`. Where a backend does not report cost,
the field is `null` and the run says so rather than estimating.

Runs go in parallel across 6 workers by default (`--workers`). The first case
runs alone so the cached prompt prefix is established before the rest fan out;
without that every worker pays the cache write, which measurably raised cost.

---

## 4. The durability result

This half needs a Restate server. Two paths.

### If you already have one

C2C registers **additively** and never removes a deployment it did not create.

```bash
make restate-check      # records the server's existing tenants on first run
make up                 # control plane :8099, C2C SDK service :9095, registers C2CCase
make failure-tests      # ~25 seconds
make down
```

`make restate-check` fails loudly if any pre-existing service has gone missing.
Run it before and after.

### If you do not

```bash
npx --yes @restatedev/restate-server           # admin :9070, ingress :8080
```

in one terminal, then `make up failure-tests down` in another.

`make restate-deregister` removes only C2C's own deployment and leaves
everything else alone.

### What you should see

```
scenarios passed              6/6
workflow completion           1.00
failure recovery              1.00
state preserved               1.00
duplicate consequential acts  0
```

The two scenarios worth reading in the result file are **D01** — the carrier
endpoint should be called 4 times, three answered 503 and one succeeding — and
**D06**, where killing the worker inside the submission window should produce
2 attempts at the carrier and 1 landed submission. If D06 shows 1 attempt, the
kill missed the window and the scenario proved nothing; re-run it.

The durability suite points the workflow's assess step at a stub returning a
fixed verdict, set through `C2C_CONTROL_PLANE`. What is under test is the
workflow, and model sampling would only add variance to a measurement about
crash recovery.

---

## 5. The demo

```bash
make up
make demo
```

Walks case R12 through assessment, a human approval, submission, a carrier
rejection arriving as an external event, and a challenge — printing what
actually reached the carrier at the end. `docs/DEMO_SCRIPT.md` is the narrated
version.

---

## 6. Data

Everything is synthetic and in the repository. There is no external data to
fetch and no outbound network call to any real service.

- `benchmark/POLICY.md` — the invented compensation policy, SHCP v1.1
- `benchmark/cases/R01..R28.json` — cases, documents and hand-authored ground truth
- the airline in `c2c/simulator.py` is in-memory and resets between scenarios

No real passenger data, no real airline, no real claim, no real regulator.

---

## 7. Reading the output

| Path | What it is |
|---|---|
| `evaluation/results/<stage>--<timestamp>.json` | every run, never overwritten |
| `trajectories/runs/<run-id>/events.jsonl` | canonical trajectory |
| `trajectories/runs/<run-id>/trajectory.md` | the same, readable |
| `evaluation/restate-tenants-baseline.json` | the shared server's other tenants |

Each result file carries the commit, the model, the backend, the digest of the
benchmark, and the digest of every prompt that shaped it. To tie a number back
to the exact instructions that produced it:

```bash
python -c "import json;d=json.load(open('evaluation/results/final-v1--....json'));print(d['git_sha'],d['prompt_provenance'])"
```

```bash
make trajectories    # re-render every recorded run as Markdown
```

---

## 8. If something goes wrong

| Symptom | Cause |
|---|---|
| `model backend: cli` but calls fail | the Claude Code CLI is not logged in. `claude` once, interactively. |
| every case scores 0 | the backend is erroring. Check one case: `python -m c2c.eval.run --system baseline --stage debug --cases R01` |
| `make up` says no Restate server | nothing on :9070. See section 4. |
| `Address already in use` on 9095 | `C2C_RESTATE_SERVICE_PORT=9096 make up` |
| durability scenarios time out | the C2C SDK service is registered at a stale address. `make restate-register`. |
| a workflow id is rejected as already used | Restate keeps workflow ids for a retention period. The suite tags ids per run; the demo does not, so `make demo` twice in a day needs `C2C_DEMO_CASE=R16`. |
