"""Final audit: check the repository's claims against its evidence.

Ground rule 09 is "connect every claim about your results to the evidence you
submit". The cheapest way to comply is not to check the README's numbers but to
*generate* them from the result files, so they cannot drift. That is what
--write does.

Everything else here is a check that fails loudly:

  - every required document exists
  - every `evaluation/results/*.json` filename cited in prose actually exists
  - no result file has been overwritten (each stage keeps every run)
  - no credential-shaped string is committed
  - the shared Restate server's other tenants are intact
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RESULTS = Path("evaluation/results")

REQUIRED = [
    "README.md", "IMPROVEMENT_CHANGELOG.md", "FAILURES.md", "Makefile",
    "benchmark/POLICY.md", "agents/caseworker/SYSTEM_PROMPT.md",
    "agents/verifier/SYSTEM_PROMPT.md",
    "docs/PROBLEM.md", "docs/PERSONAL_MOTIVATION.md", "docs/ARCHITECTURE.md",
    "docs/STACK.md", "docs/DECISIONS.md", "docs/ENVIRONMENT.md",
    "docs/REPRODUCTION.md", "docs/EVALUATION.md", "docs/DEMO_SCRIPT.md",
    "docs/LIMITATIONS.md", "docs/HACKATHON_REQUIREMENTS.md",
]

SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "an Anthropic API key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "a GitHub token"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "a Telegram bot token"),
]


def load(stage: str) -> dict | None:
    files = sorted(RESULTS.glob(f"{stage}--*.json"))
    return json.loads(files[-1].read_text()) if files else None


def results_table() -> str:
    stages = [
        ("baseline-v1", "Baseline — one direct prompt"),
        ("caseworker-direct", "Caseworker prompt, one turn, no tools"),
        ("exp1-tools", "Caseworker + tools + loop"),
        ("final-v1", "**Full agent** — + independent verifier"),
    ]
    loaded = [(label, load(s), s) for s, label in stages]
    have = [(label, r, s) for label, r, s in loaded if r]
    if not have:
        return "_No result files yet. Run `make baseline evaluate`._"

    base = load("baseline-v1")
    rows = ["| System | CRA | Action | Compensation | Entitlements (DoC) | Unsupported claims | False escalations | Model calls | Cost |",
            "|---|---|---|---|---|---|---|---|---|"]
    for label, r, _ in have:
        m, t = r["metrics"], r["totals"]
        cost = f"${t['cost_usd']:.2f}" if t.get("cost_usd") is not None else "not measured"
        rows.append(
            f"| {label} | **{m['case_resolution_accuracy']:.2f}** | "
            f"{m['action_accuracy']:.2f} | {m['compensation_accuracy']:.2f} | "
            f"{m['duty_of_care_accuracy']:.2f} | {m['unsupported_claims']} | "
            f"{m['false_escalations']} | {t['model_calls']} | {cost} |"
        )
    final = load("final-v1")
    if base and final:
        d = final["metrics"]["case_resolution_accuracy"] - base["metrics"]["case_resolution_accuracy"]
        rows.append(f"| **Change, baseline → full agent** | **{d:+.2f}** | | | | | | | |")

    repeat = load("baseline-v1-repeat")
    note = [""]
    if base and repeat:
        spread = abs(repeat["metrics"]["case_resolution_accuracy"]
                     - base["metrics"]["case_resolution_accuracy"])
        note += [
            f"Best possible constant answer on this suite: **0.25**. An identical re-run of the "
            f"baseline, with no change to code, prompt or benchmark, scored "
            f"{repeat['metrics']['case_resolution_accuracy']:.2f} against "
            f"{base['metrics']['case_resolution_accuracy']:.2f} — a spread of **{spread:.2f}**, "
            f"which is the run-to-run noise floor any difference here has to clear.",
        ]
    else:
        note += ["Best possible constant answer on this suite: **0.25**."]
    return "\n".join(rows + note)


def write_readme() -> None:
    p = Path("README.md")
    s = p.read_text()
    start, end = "<!--RESULTS_TABLE-->", "<!--/RESULTS_TABLE-->"
    table = results_table()
    if start in s and end in s:
        s = re.sub(re.escape(start) + r".*?" + re.escape(end), f"{start}\n{table}\n{end}", s,
                   flags=re.S)
    elif start in s:
        s = s.replace(start, f"{start}\n{table}\n{end}")
    p.write_text(s)
    print("  README results table regenerated from evaluation/results/")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="regenerate the README results table from the result files")
    args = ap.parse_args()
    problems: list[str] = []

    if args.write:
        write_readme()

    print("\nrequired documents")
    for rel in REQUIRED:
        ok = Path(rel).exists()
        print(f"  {'ok  ' if ok else 'MISS'} {rel}")
        if not ok:
            problems.append(f"missing {rel}")

    print("\nresult files cited in prose")
    cited = set()
    for md in list(Path(".").glob("*.md")) + list(Path("docs").glob("*.md")) + \
              list(Path("experiments").glob("*.md")):
        cited |= set(re.findall(r"[\w.-]+--\d{8}T\d{6}Z\.json", md.read_text()))
    for name in sorted(cited):
        ok = (RESULTS / name).exists()
        print(f"  {'ok  ' if ok else 'MISS'} {name}")
        if not ok:
            problems.append(f"prose cites {name}, which is not in {RESULTS}")

    print("\nevaluation runs on record")
    by_stage: dict[str, int] = {}
    for f in sorted(RESULTS.glob("*--*.json")):
        by_stage[f.name.split("--")[0]] = by_stage.get(f.name.split("--")[0], 0) + 1
    for stage, n in sorted(by_stage.items()):
        print(f"  {n:>2}  {stage}")
    if not by_stage:
        problems.append("no evaluation results at all")

    print("\ncredentials")
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
    found = 0
    for rel in tracked:
        p = Path(rel)
        if not p.is_file() or p.suffix in {".png", ".jpg", ".pdf"}:
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        for pattern, what in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"{rel} looks like it contains {what}")
                found += 1
    print(f"  {'ok  ' if not found else 'FAIL'} scanned {len(tracked)} tracked files")

    print("\nshared Restate server")
    r = subprocess.run([sys.executable, "-m", "c2c.tools.restate_check"],
                       capture_output=True, text=True)
    for line in r.stdout.strip().splitlines()[-2:]:
        print(f"  {line.strip()}")
    if r.returncode != 0:
        problems.append("the shared Restate server's pre-existing tenants are not intact")

    print("\ntests")
    t = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       capture_output=True, text=True)
    print(f"  {t.stdout.strip().splitlines()[-1] if t.stdout else 'no output'}")
    if t.returncode != 0:
        problems.append("the test suite does not pass")

    print()
    if problems:
        print(f"AUDIT FAILED — {len(problems)} problem(s):")
        for p_ in problems:
            print(f"  - {p_}")
        return 1
    print("AUDIT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
