# Reproduce and record

Everything below was run on this machine and the outputs are real. Where a step
is fragile, the failure mode and the retry are stated rather than assumed away.

---

## 1. Exact branch and commit

| | |
|---|---|
| Repository | `https://github.com/yablokolabs/c2c-agent` |
| Branch | `main` |
| Commit | `707daa0240f2db9cb32d30f0b529b78adfa46b96` (`707daa0`) |
| Remote | in sync — local `main` == `origin/main` |
| Tags | `baseline-v0`, `evidence-v1`, `agent-v2`, `durable-v4` |

```bash
git clone https://github.com/yablokolabs/c2c-agent.git
cd c2c-agent
git checkout 707daa0
```

---

## 2. Prerequisites and environment

| Component | Version used | Required |
|---|---|---|
| Python | 3.12.3 | 3.11+ |
| uv | 0.12.5 | any recent |
| Claude Code CLI | 2.1.251 | only for the `cli` backend |
| Restate server | 1.7.7 | only for the demo and durability suite |

### Environment variables

| Variable | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | selects the `api` backend. **The documented path.** |
| `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` | selects `api` against a gateway — see the warning below |
| `C2C_LLM_BACKEND` | forces `api` or `cli` |
| `C2C_MIN_CALL_INTERVAL` | seconds between calls, default `1.0` |
| `C2C_CLOCK_SCALE` | compresses the 56-day / 28-day policy clocks |

> **Do not point this at a gateway without checking what it serves.** A local
> proxy was used during development; it did not carry
> `claude-haiku-4-5-20251001` and answered with something else while every result
> file still recorded the requested model. The baseline fell 0.82 → 0.29 with no
> change to the baseline. See `FAILURES.md` **F-007**. Every result now records
> `model_endpoint`, and `report --compare` refuses to compare across endpoints.

**All results in this repository were produced on `backend=cli`,
`endpoint=claude-cli`.**

```bash
make setup            # uv venv + editable install
make test             # expect: 121 passed, 1 skipped   (no model calls, ~0.6s)
```

---

## 3. Regenerating the merged results

The headline is two runs plus a merge. Run them **sequentially** — see §6.

```bash
export C2C_LLM_BACKEND=cli
export C2C_MIN_CALL_INTERVAL=3.0
unset ANTHROPIC_API_KEY ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN
```

### 3a. Baseline — one direct prompt

```bash
python -m c2c.eval.run --system baseline --stage baseline-v2 --workers 3 \
  --note "Clean re-measurement: CLI backend, paced calls."
```

**Checkpoint.** `Case Resolution Accuracy 0.82`, `calls=28`, ~868s, ~$1.37, and
**no** `WARNING: N of 28 cases never reached the model`. If that warning appears,
the run is void — see §6.

### 3b. Full agent — tools, loop, independent verifier

```bash
python -m c2c.eval.run --system agent --stage final-v2 --workers 1 \
  --note "Full agent: tools, loop, independent verifier, one revision."
```

**Checkpoint.** ~102 model calls across 28 cases. On the recorded run this
stopped after 18 cases with `WARNING: 10 of 28 cases never reached the model`.
That is expected under the ceiling; continue to 3c.

### 3c. Gap-fill — only the cases 3b missed

Substitute the case ids the warning actually names.

```bash
python -m c2c.eval.run --system agent --stage final-v2-gap --workers 1 \
  --cases R19,R20,R21,R22,R23,R24,R25,R26,R27,R28 \
  --note "The 10 cases final-v2 never reached."
```

**Checkpoint.** `Case Resolution Accuracy 0.90`, `calls=34`, `failed: R26`.

### 3d. Merge

```bash
python -m c2c.eval.merge --stage final-v2-merged final-v2 final-v2-gap
```

**Checkpoint.**

```
final-v2-merged: 28 cases from 2 runs
  final-v2         18 cases
  final-v2-gap     10 cases
  Case Resolution Accuracy  0.93
  failed: R07, R26
```

The merge **refuses** rather than guesses: it errors if any case is covered
twice, if coverage is incomplete, or if the parts disagree on system, model or
endpoint. It reads the *newest* file per stage — this repo contains an earlier,
crashed `final-v2` from 09:41 which is correctly ignored in favour of the 15:20
run.

### 3e. Compare

```bash
python -m c2c.eval.report --compare \
  evaluation/results/baseline-v2--20260830T092738Z.json \
  evaluation/results/final-v2-merged--20260830T194802Z.json
```

**Checkpoint.**

```
Case Resolution Accuracy   0.82   0.93   +0.11
Unsupported claims            0      0
False escalations             0      0
fixed:  R01, R04, R05, R16, R18
broken: R07, R26
```

### 3f. Durability — no model calls, ~30s

```bash
make up
python -m c2c.eval.durability
```

**Checkpoint.** `6/6`, `duplicate consequential acts 0`. Then verify by hand in
the newest `evaluation/results/durability--*.json`:

- **D01** `calls_that_reached_the_carrier == 4` (three 503s, one success)
- **D06** `submit_attempts_at_carrier == 2` **and** `submissions_that_landed == 1`
- **D05** `submit_attempts_at_carrier == 0`

If D06 shows 1 attempt the `SIGKILL` missed its window and the scenario proved
nothing — re-run.

---

## 4. End-to-end demo

```bash
make up                # control plane :8099, SDK service :9095, registers C2CCase
make demo-reset
make demo              # ~5 model calls, 2-4 minutes
```

**Checkpoints, in order:**

| Step | Expect |
|---|---|
| 1 | `{'reset': True}` |
| 2 | workflow starts; assessment runs |
| 3 | `state AWAITING_APPROVAL`, `pending_action submit_claim`, 420 units, cause `carrier_controlled` |
| 4 | approval accepted; `state SUBMITTED` / `AWAITING_CARRIER`, a `SYN-CLM-` id |
| 5 | rejection delivered; back to `AWAITING_APPROVAL` |
| 6 | challenge approved; `state CHALLENGED` |
| 7 | the case summary and claim letter, banner-stamped |
| 8 | audit: actions attempted vs landed, duplicates absorbed |

Teardown, which touches **only** what C2C started:

```bash
make down
make restate-check     # expect: all 3 pre-existing services still registered
```

---

## 5. What good looks like

| Claim | Where | Value |
|---|---|---|
| Baseline | `baseline-v2--20260830T092738Z.json` | **0.82** |
| Full agent | `final-v2-merged--20260830T194802Z.json` | **0.93** |
| Improvement | `make compare` | **+0.11** (3 cases) |
| Unsupported claims / false escalations | both runs | **0** |
| Durability | `durability--20260829T065338Z.json` | **6/6**, 0 duplicates |
| Best constant answer on this suite | `tests/test_benchmark.py` | 0.25 |

**+0.11 is three cases and there is no valid variance estimate** — the one this
project had was withdrawn in F-008. Report it as directional.

---

## 6. Known failure modes

### Throughput ceiling — the one that will bite you

**Symptom.** `LLMError('cli backend failed after N attempts: claude -p exited 1: ')`
with an empty message after the colon, and a run summary showing
`WARNING: N of 28 cases never reached the model`.

**Cause.** The CLI drops calls under sustained load and reports nothing. Single
calls succeed throughout — probing with one `claude -p` will mislead you into
thinking it is fine. The agent makes 3-4 calls per case against the baseline's
one, so it hits this and the baseline does not. See `FAILURES.md` **F-009**.

**Retry, in order of preference:**

1. `--workers 1` and `C2C_MIN_CALL_INTERVAL=3.0`
2. Split the work: run the missed cases with `--cases`, then `c2c.eval.merge`.
   A 10-case burst succeeded where a 28-case run failed twice.
3. `C2C_MIN_CALL_INTERVAL=6.0` for the smaller burst.

**Never** paper over it by pointing at a gateway. That is F-007.

### Other

| Symptom | Cause / fix |
|---|---|
| every case scores 0, `calls=0` | backend erroring. Test one: `--cases R01` |
| results look plausible but wrong | check `model_endpoint` in the result file |
| `Address already in use` on 9095 | `C2C_RESTATE_SERVICE_PORT=9096 make up` |
| workflow id rejected as used | Restate retains ids; the durability suite tags per run, the demo does not — use `C2C_DEMO_CASE=R16` for a second same-day demo |
| durability scenarios time out | stale registration: `make restate-register` |

---

## 7. Recording sequence

Target 5:00. Script with narration: `docs/DEMO_SCRIPT.md`.

### Before you hit record

```bash
make setup && make test          # 121 passed
make up
make restate-check               # 3 pre-existing services intact
make demo-reset
```

Two terminals. **Left:** `make demo`. **Right:** `make failure-tests`, then
`make compare`.

Do a **dry run of `make demo` first** and leave the output on screen — it takes
2-4 minutes and makes real model calls, which is time you do not want to be
silent for on camera.

### Take order

| Time | Terminal | Command | Say |
|---|---|---|---|
| 0:00 | — | — | the problem |
| 0:35 | editor | `prompts/baseline_v2.md` | the baseline |
| 0:50 | editor | `benchmark/POLICY.md`, one case | the benchmark, and the mistake |
| 1:20 | left | `make demo` | steps 3, 4-6, **7**, 8 |
| 2:55 | right | `make failure-tests` | D06 (2 attempts, 1 landed), D05 (0 calls) |
| 3:45 | right | `make compare` | 0.82 → 0.93; then NanoClaw |
| 4:40 | — | — | hot take |

### Numbers to read off screen, not from memory

- `make compare` → **0.82**, **0.93**, **+0.11**
- `make failure-tests` D06 → **2 attempts, 1 landed**
- D05 → **0 calls to the carrier**

### Do not show

The Restate admin UI, the workflow source, or an architecture diagram. They cost
30-60s and score nothing — the rubric asks which design choices *helped*, and the
failure-injection output answers that where a dashboard does not.

### If the demo dies mid-take

It makes ~5 model calls and is subject to §6. `make demo-reset` and start that
segment again. If it fails twice, record the rest and narrate step 7 over the
committed trajectory at
`trajectories/runs/<newest>/trajectory.md` instead.
