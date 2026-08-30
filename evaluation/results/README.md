# Evaluation results

One file per run, never overwritten. Each carries the commit, the model, the
backend, the benchmark digest and the digest of every prompt that shaped it.

## Which runs are comparable

**Only runs sharing an endpoint.** Files written before F-007 have no
`model_endpoint` field; for those, read the table below.

| Run | Endpoint | Valid? |
|---|---|---|
| `baseline-v0--20260828T172034Z` | CLI | **yes** — 20 cases, pre-correction metric. CRA 0.75 |
| `baseline-v1--20260828T173342Z` | CLI | **yes** — the comparison point. CRA 0.68 |
| `baseline-v1-repeat--20260829T181117Z` | CLI | **yes** — variance control. CRA 0.75 |
| `exp1-tools--20260829T070116Z` | CLI | **yes** — caseworker + tools. CRA 0.86 |
| `durability--20260829T065338Z` | n/a, no model calls | **yes** — 6/6 |
| `baseline-v1--20260830T*`, `final-v1--20260830T*` | **gateway** | **NO** — see below |
| `final-v1--20260829T1[89]*`, `--2026082[9]T2*` | CLI, but crashed or contaminated | **NO** |
| `test-*` | mixed | **NO** — harness debugging, most made zero model calls |

## The invalid runs are kept on purpose

They are the evidence for **FAILURES.md F-007**. A local gateway was used to
route around a CLI rate limit. It does not carry `claude-haiku-4-5-20251001`,
so it answered with something else — while every result file still recorded
`"model": "claude-haiku-4-5-20251001"`, because that field logged what was
*requested*.

The tell is that the **baseline** moved, with no change made to the baseline:

| Run | Endpoint | CRA | Output tokens/call |
|---|---|---|---|
| baseline-v1 | CLI | 0.68 | 7,990 |
| baseline-v1-repeat | CLI | 0.75 | 7,470 |
| baseline-v1 | gateway | 0.29 | 2,824 |
| baseline-v1 | gateway | 0.36 | 2,744 |

Deleting them would remove the only record of how the contamination was caught.
They are not deleted, and they are not counted.

Runs from `87a9e59` onward record `model_endpoint` and `first_party_model`, and
the harness warns when calls are not going to Anthropic.
