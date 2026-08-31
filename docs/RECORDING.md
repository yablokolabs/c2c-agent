# Recording the solution video

*Supports deliverable 03. The narration itself is in [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md); this is the mechanics.*

## Sequence

Target 5:00. Script with narration: `docs/DEMO_SCRIPT.md`.

### Before you hit record — this part is not optional

```bash
make setup && make test          # 121 passed
make up
make restate-check               # 3 pre-existing services intact
make demo-reset
make demo                        # RUN THIS BEFORE RECORDING. 7-16 minutes.
```

**Leave the finished `make demo` output in the left terminal and scroll back to
the top.** You will narrate over the completed run, scrolling through steps 3 to
8. It is a genuine execution — the same one, just not in real time — and the
trajectory is committed alongside it.

Do not attempt to run it live. A single assessment is 3.5 minutes at the median
and the demo does two, which is longer than the entire video.

If a case id is already used (Restate retains workflow ids), either use
`C2C_DEMO_CASE=R16` or purge the invocations for that key through the admin API
at `:9070`.

Two terminals. **Left:** the completed `make demo` output. **Right:**
`make failure-tests`, then `make compare` — both of these are fast and *can* be
run live.

### Take order

| Time | Terminal | Command | Say |
|---|---|---|---|
| 0:00 | — | — | the problem |
| 0:35 | editor | `prompts/baseline_v2.md` | the baseline |
| 0:50 | editor | `benchmark/POLICY.md`, one case | the benchmark, and the mistake |
| 1:20 | left | scroll the **already-completed** `make demo` output | steps 3, 4-6, **7**, 8 |
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

### If the demo fails during the pre-run

It makes ~10 model calls and is subject to the throughput ceiling in §6. It is
durable: the workflow survives, so re-running the script picks the case up where
it stopped rather than starting over. Check with
`curl localhost:8099/c2c/cases/R12`.

If it fails repeatedly, narrate step 7 over the committed trajectory at
`trajectories/runs/<newest>/trajectory.md` and the artifact at
`GET /c2c/cases/R12/document`.
