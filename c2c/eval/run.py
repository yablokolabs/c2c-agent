"""Evaluation harness.

    python -m c2c.eval.run --system baseline --stage baseline-v0

Writes a timestamped result file under evaluation/results/ that carries enough
metadata to reproduce it: commit, model, backend, benchmark digest, prompt
digests. Existing result files are never overwritten.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from c2c import prompts
from c2c.eval.metrics import aggregate, score_case
from c2c.llm import DEFAULT_MODEL, LLM
from c2c.models import load_cases
from c2c.trajectory import Recorder, git_sha

RESULTS_DIR = Path("evaluation/results")

SYSTEMS = {}


def register(name):
    def deco(fn):
        SYSTEMS[name] = fn
        return fn

    return deco


@register("baseline")
def _baseline(case, llm, rec):
    from c2c.baseline import run_case

    return run_case(case, llm, rec)


@register("agent-tools")
def _agent_tools(case, llm, rec):
    """Caseworker with tools, no verifier. Isolates the tool loop's effect."""
    from c2c.agent.pipeline import run_case

    return run_case(case, llm, rec, use_verifier=False)


@register("agent")
def _agent(case, llm, rec):
    """Caseworker with tools, plus the independent verifier."""
    from c2c.agent.pipeline import run_case

    return run_case(case, llm, rec, use_verifier=True)


def benchmark_digest() -> str:
    blob = "".join(
        sorted(p.read_text() for p in Path("benchmark/cases").glob("*.json"))
    )
    return prompts.digest(blob)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the C2C benchmark.")
    ap.add_argument("--system", choices=sorted(SYSTEMS), required=True)
    ap.add_argument("--stage", required=True, help="label for this run, e.g. baseline-v0")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--backend", default=None, choices=["api", "cli"])
    ap.add_argument("--cases", default=None, help="comma-separated case ids to run")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--note", default="", help="one line on why this run exists")
    args = ap.parse_args(argv)

    cases = load_cases()
    if args.cases:
        wanted = {c.strip() for c in args.cases.split(",")}
        cases = [c for c in cases if c.case_id in wanted]
        if not cases:
            print(f"no cases matched {sorted(wanted)}", file=sys.stderr)
            return 2

    llm = LLM(model=args.model, backend=args.backend)
    rec = Recorder.open(args.stage)
    runner = SYSTEMS[args.system]

    rec.emit("USER_INPUT", input={
        "system": args.system, "stage": args.stage, "model": args.model,
        "backend": llm.backend, "n_cases": len(cases), "note": args.note,
    })

    print(f"[{args.stage}] system={args.system} model={args.model} backend={llm.backend} "
          f"cases={len(cases)} -> run {rec.run_id}", flush=True)

    started = time.monotonic()
    results: dict[str, tuple] = {}

    def one(case):
        try:
            return case.case_id, runner(case, llm, rec)
        except Exception as exc:  # noqa: BLE001
            rec.emit("ERROR", case_id=case.case_id, success=False, output=repr(exc))
            return case.case_id, (None, [])

    # The first case runs alone so the cached prompt prefix is established
    # before the rest fan out; without it every worker pays the cache write.
    head, tail = cases[0], cases[1:]
    cid, out = one(head)
    results[cid] = out
    print(f"  {cid} done", flush=True)

    if tail:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            for cid, out in pool.map(one, tail):
                results[cid] = out
                print(f"  {cid} done", flush=True)

    wall_s = round(time.monotonic() - started, 1)

    scored, per_case = [], []
    totals = {"model_calls": 0, "task_input_tokens": 0, "output_tokens": 0,
              "cache_creation_tokens": 0, "cache_read_tokens": 0,
              "harness_overhead_tokens": 0, "cost_usd": 0.0}
    cost_measured = True

    for case in cases:
        verdict, calls = results.get(case.case_id, (None, []))
        s = score_case(case, verdict)
        scored.append(s)
        for c in calls:
            totals["model_calls"] += 1
            for k in ("task_input_tokens", "output_tokens", "cache_creation_tokens",
                      "cache_read_tokens", "harness_overhead_tokens"):
                totals[k] += getattr(c, k)
            if c.cost_usd is None:
                cost_measured = False
            else:
                totals["cost_usd"] += c.cost_usd
        per_case.append({
            "case_id": case.case_id,
            "title": case.title,
            "difficulty": case.difficulty,
            "tags": case.tags,
            "resolved": s.resolved,
            "expected": s.expected,
            "got": s.got,
            "flags": {
                "unsupported_claim": s.unsupported_claim,
                "unsupported_challenge": s.unsupported_challenge,
                "false_escalation": s.false_escalation,
                "missed_escalation": s.missed_escalation,
            },
            "rationale": verdict.rationale if verdict else None,
            "policy_citations": verdict.policy_citations if verdict else None,
            "model_calls": len(calls),
        })

    totals["cost_usd"] = round(totals["cost_usd"], 4) if cost_measured else None
    if not cost_measured:
        totals["cost_note"] = "cost not reported by the backend for at least one call"
    totals["wall_clock_s"] = wall_s
    totals["mean_calls_per_case"] = round(totals["model_calls"] / len(cases), 2)

    metrics = aggregate(scored)

    payload = {
        "stage": args.stage,
        "system": args.system,
        "note": args.note,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "model": args.model,
        "backend": llm.backend,
        "benchmark_digest": benchmark_digest(),
        "n_benchmark_cases": len(load_cases()),
        "prompt_provenance": prompts.provenance(),
        "python": platform.python_version(),
        "trajectory_run_id": rec.run_id,
        "metrics": metrics,
        "totals": totals,
        "cases": per_case,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{args.stage}--{stamp}.json"
    if out_path.exists():
        raise FileExistsError(f"refusing to overwrite {out_path}")
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    rec.emit("FINAL_DECISION", output={"metrics": metrics, "totals": totals})
    rec.render_markdown(f"{args.stage} ({args.system})")

    print(f"\n  Case Resolution Accuracy  {metrics['case_resolution_accuracy']:.2f}")
    for k in ("action_accuracy", "compensation_accuracy", "eligibility_accuracy",
              "cause_accuracy", "evidence_sufficiency_accuracy"):
        print(f"  {k:26} {metrics[k]:.2f}")
    for k in ("unsupported_claims", "unsupported_rejection_challenges",
              "false_escalations", "missed_escalations"):
        print(f"  {k:26} {metrics[k]}")
    print(f"  failed: {', '.join(metrics['failed_cases']) or 'none'}")
    print(f"  calls={totals['model_calls']} wall={wall_s}s cost={totals['cost_usd']}")
    print(f"\n  results     {out_path}")
    print(f"  trajectory  {rec.root}/trajectory.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
