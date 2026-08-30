"""Combine result files that together cover the benchmark once.

`final-v2` reached 18 of 28 cases before the backend's throughput ceiling
stopped it; `final-v2-gap` re-ran the remaining 10. Neither is a complete run and
neither should be reported as one, but together they cover all 28 cases exactly
once, with the same system, model, endpoint and prompts.

This merges them into one result and refuses to do so if that is not true: no
case may be covered twice, none may be missing, and every part must agree on
system, model and endpoint. The output records which runs it came from.

    python -m c2c.eval.merge --stage final-v2-merged final-v2 final-v2-gap
"""

from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path

from c2c.eval.metrics import aggregate
from c2c.models import load_cases

RESULTS = Path("evaluation/results")


def newest(stage: str) -> dict:
    files = sorted(RESULTS.glob(f"{stage}--*.json"))
    if not files:
        raise SystemExit(f"no result files for stage {stage!r}")
    return json.loads(files[-1].read_text())


def reached(r: dict) -> list[dict]:
    """Only cases that actually got a model call. A case the model never saw is
    not a case it got wrong, and must not be carried into a merged result."""
    return [c for c in r["cases"] if c["model_calls"] > 0]


class MergeError(SystemExit):
    pass


def merge(parts: list[dict], stage: str) -> dict:
    for field in ("system", "model", "backend", "benchmark_digest"):
        values = {p.get(field) for p in parts}
        if len(values) > 1:
            raise MergeError(f"parts disagree on {field}: {values}")
    endpoints = {p.get("model_endpoint") for p in parts}
    if len(endpoints) > 1:
        raise MergeError(f"parts used different endpoints: {endpoints} — not comparable")

    by_case: dict[str, dict] = {}
    for p in parts:
        for c in reached(p):
            if c["case_id"] in by_case:
                raise MergeError(
                    f"{c['case_id']} appears in more than one part; a merged run must "
                    f"cover each case exactly once")
            by_case[c["case_id"]] = c

    expected = {c.case_id for c in load_cases()}
    missing = sorted(expected - set(by_case))
    if missing:
        raise MergeError(f"merged parts do not cover the benchmark; missing {missing}")

    class S:
        def __init__(self, c):
            e, g = c["expected"], c["got"]
            ok = lambda k: e[k] == g.get(k)  # noqa: E731
            self.case_id = c["case_id"]
            self.action_correct = ok("next_action")
            self.compensation_correct = ok("compensation_units")
            self.duty_of_care_correct = ok("duty_of_care_units")
            self.downgrade_correct = ok("downgrade_reimbursement_units")
            self.eligibility_correct = ok("eligible")
            self.cause_correct = ok("cause_class")
            self.evidence_correct = ok("evidence_sufficient")
            self.resolved = (self.action_correct and self.compensation_correct
                             and self.duty_of_care_correct and self.downgrade_correct)
            f = c["flags"]
            self.unsupported_claim = f["unsupported_claim"]
            self.unsupported_challenge = f["unsupported_challenge"]
            self.false_escalation = f["false_escalation"]
            self.missed_escalation = f["missed_escalation"]

    scores = [S(by_case[cid]) for cid in sorted(by_case)]
    totals = {k: sum(p["totals"].get(k) or 0 for p in parts)
              for k in ("model_calls", "task_input_tokens", "output_tokens",
                        "harness_overhead_tokens", "wall_clock_s")}
    totals["cost_usd"] = round(sum(p["totals"].get("cost_usd") or 0 for p in parts), 4)
    totals["cases_without_model_call"] = 0

    return {
        "stage": stage,
        "system": parts[0]["system"],
        "merged_from": [{"stage": p["stage"], "timestamp": p["timestamp"],
                         "cases": sorted(c["case_id"] for c in reached(p))} for p in parts],
        "note": ("Merged from runs that each covered part of the benchmark. Every case "
                 "appears exactly once, from the same system, model and endpoint."),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": parts[-1]["git_sha"],
        "model": parts[0]["model"],
        "backend": parts[0]["backend"],
        "model_endpoint": parts[0].get("model_endpoint"),
        "first_party_model": parts[0].get("first_party_model"),
        "benchmark_digest": parts[0]["benchmark_digest"],
        "prompt_provenance": parts[-1]["prompt_provenance"],
        "metrics": aggregate(scores),
        "totals": totals,
        "cases": [by_case[cid] for cid in sorted(by_case)],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stages", nargs="+")
    ap.add_argument("--stage", required=True)
    a = ap.parse_args(argv)

    out = merge([newest(s) for s in a.stages], a.stage)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS / f"{a.stage}--{stamp}.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    m = out["metrics"]
    print(f"{a.stage}: {m['n_cases']} cases from {len(a.stages)} runs")
    for p in out["merged_from"]:
        print(f"  {p['stage']:16} {len(p['cases']):>2} cases")
    print(f"\n  Case Resolution Accuracy  {m['case_resolution_accuracy']:.2f}")
    print(f"  action {m['action_accuracy']:.2f}  compensation {m['compensation_accuracy']:.2f}  "
          f"duty of care {m['duty_of_care_accuracy']:.2f}")
    print(f"  unsupported claims {m['unsupported_claims']}  false escalations "
          f"{m['false_escalations']}")
    print(f"  failed: {', '.join(m['failed_cases']) or 'none'}")
    print(f"\n  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
