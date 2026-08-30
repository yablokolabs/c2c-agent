"""Read result files back: inspect one run, or compare two.

    python -m c2c.eval.report evaluation/results/baseline-v0--*.json
    python -m c2c.eval.report --compare BASELINE.json FINAL.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HEADLINE = [
    ("case_resolution_accuracy", "Case Resolution Accuracy", "rate"),
    ("action_accuracy", "Action accuracy", "rate"),
    ("compensation_accuracy", "Compensation accuracy", "rate"),
    ("eligibility_accuracy", "Eligibility accuracy", "rate"),
    ("cause_accuracy", "Cause classification accuracy", "rate"),
    ("evidence_sufficiency_accuracy", "Evidence sufficiency accuracy", "rate"),
    ("duty_of_care_accuracy", "Duty of care accuracy", "rate"),
    ("downgrade_accuracy", "Downgrade accuracy", "rate"),
    ("unsupported_claims", "Unsupported claims", "count"),
    ("unsupported_rejection_challenges", "Unsupported challenges", "count"),
    ("false_escalations", "False escalations", "count"),
    ("missed_escalations", "Missed escalations", "count"),
]


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def show(r: dict) -> None:
    m, t = r["metrics"], r["totals"]
    print(f"\n{r['stage']}  ({r['system']})")
    print(f"  commit {r['git_sha'][:8]}  model {r['model']}  backend {r['backend']}  "
          f"{r['timestamp']}")
    endpoint = r.get("model_endpoint", "(not recorded)")
    print(f"  endpoint {endpoint}")
    if r.get("first_party_model") is False:
        print("  WARNING: served by a gateway, not Anthropic. Not comparable with "
              "first-party runs.")
    if r.get("note"):
        print(f"  note: {r['note']}")
    print()
    for key, label, kind in HEADLINE:
        v = m[key]
        print(f"  {label:32} {v:.2f}" if kind == "rate" else f"  {label:32} {v}")
    print(f"\n  model calls {t['model_calls']}  ({t['mean_calls_per_case']}/case)  "
          f"wall {t['wall_clock_s']}s  cost {t['cost_usd']}")
    print(f"  tokens: task_in {t['task_input_tokens']}  out {t['output_tokens']}  "
          f"harness_overhead {t['harness_overhead_tokens']}")

    failed = [c for c in r["cases"] if not c["resolved"]]
    if not failed:
        print("\n  every case resolved")
        return
    print(f"\n  {len(failed)} unresolved:")
    for c in failed:
        e, g = c["expected"], c["got"]
        diffs = [f"{k}: expected {e[k]!r}, got {g.get(k)!r}" for k in e if e[k] != g.get(k)]
        flags = [k for k, v in c["flags"].items() if v]
        print(f"\n    {c['case_id']} [{c['difficulty']}] {c['title']}")
        for d in diffs:
            print(f"      - {d}")
        if flags:
            print(f"      ! {', '.join(flags)}")


def compare(a: dict, b: dict) -> None:
    ea, eb = a.get("model_endpoint"), b.get("model_endpoint")
    if ea != eb:
        print(f"\n  WARNING: these runs used different endpoints ({ea} vs {eb}).\n"
              f"  A gateway can serve a different model than the one requested, so this\n"
              f"  comparison is not measuring the change you think it is.")
    ma, mb = a["metrics"], b["metrics"]
    ta, tb = a["totals"], b["totals"]
    print(f"\n{'METRIC':34}{a['stage']:>16}{b['stage']:>16}{'CHANGE':>12}")
    print("-" * 78)
    for key, label, kind in HEADLINE:
        va, vb = ma[key], mb[key]
        if kind == "rate":
            delta = f"{vb - va:+.2f}"
            print(f"{label:34}{va:>16.2f}{vb:>16.2f}{delta:>12}")
        else:
            print(f"{label:34}{va:>16}{vb:>16}{vb - va:>+12}")
    print("-" * 78)
    for key, label in [("model_calls", "Model calls"), ("wall_clock_s", "Wall clock (s)"),
                       ("cost_usd", "Cost (USD)")]:
        va, vb = ta.get(key), tb.get(key)
        if va is None or vb is None:
            print(f"{label:34}{str(va):>16}{str(vb):>16}{'not measured':>12}")
        else:
            print(f"{label:34}{va:>16}{vb:>16}{vb - va:>+12.4f}")

    fa, fb = set(ma["failed_cases"]), set(mb["failed_cases"])
    print(f"\n  fixed by {b['stage']:<20} {', '.join(sorted(fa - fb)) or 'none'}")
    print(f"  broken by {b['stage']:<19} {', '.join(sorted(fb - fa)) or 'none'}")
    print(f"  still failing              {', '.join(sorted(fa & fb)) or 'none'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--compare", action="store_true",
                    help="treat the two paths as before and after")
    args = ap.parse_args(argv)
    if args.compare:
        if len(args.paths) != 2:
            print("--compare needs exactly two result files", file=sys.stderr)
            return 2
        compare(load(args.paths[0]), load(args.paths[1]))
    else:
        for p in args.paths:
            show(load(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
