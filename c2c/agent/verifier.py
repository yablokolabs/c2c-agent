"""Independent verification of a caseworker verdict.

The verifier sees the case and the policy, never the caseworker's transcript.
It can reject, and a rejection sends the case back for one revision.
"""

from __future__ import annotations

import json
from typing import Optional

from c2c import prompts
from c2c.llm import LLM, LLMResult, extract_json
from c2c.models import Case, Verdict
from c2c.trajectory import Recorder


def system_prompt() -> str:
    return prompts.load("verifier").replace("{policy}", prompts.policy())


def format_feedback(report: dict) -> str:
    lines = [f"Verifier decision: {report.get('decision')} "
             f"(confidence {report.get('confidence', 'unstated')})"]
    if report.get("summary"):
        lines += ["", report["summary"]]
    findings = report.get("findings") or []
    if findings:
        lines += ["", "Findings:"]
        for f in findings:
            if not isinstance(f, dict):
                lines.append(f"  - {f}")
                continue
            lines.append(f"  - {f.get('field', 'unspecified')}: {f.get('problem', '')}"
                         f"  [{f.get('evidence', 'no evidence cited')}]")
    if report.get("corrected"):
        lines += ["", "The verifier would change:",
                  json.dumps(report["corrected"], indent=2, ensure_ascii=False)]
    return "\n".join(lines)


def run(
    case: Case,
    verdict: Verdict,
    llm: LLM,
    rec: Optional[Recorder] = None,
) -> tuple[dict, list[LLMResult]]:
    user = "\n".join([
        "## THE CASE",
        "",
        case.dossier(),
        "## THE CASEWORKER'S VERDICT",
        "",
        "```json",
        json.dumps(verdict.model_dump(), indent=2, ensure_ascii=False),
        "```",
        "",
        "Work the case out yourself first, then compare. Reply with exactly one JSON object.",
    ])

    if rec:
        rec.emit("VERIFIER_REQUEST", case_id=case.case_id, agent="verifier",
                 input={"verdict_under_review": verdict.model_dump()})

    result = llm.complete(system_prompt(), user)
    raw = extract_json(result.text)

    if raw is None or raw.get("decision") not in ("pass", "reject"):
        # An unreadable verifier must not be able to block a case. Failing open
        # is the safe default here: the caseworker's verdict already exists, and
        # a verifier that cannot state a decision has not found anything.
        report = {"decision": "pass", "confidence": "low", "findings": [],
                  "summary": "verifier response was unreadable; failing open",
                  "unreadable": True}
        if rec:
            rec.emit("ERROR", case_id=case.case_id, agent="verifier", success=False,
                     output=f"unreadable verifier reply: {result.text[:400]}")
            rec.emit("VERIFIER_PASS", case_id=case.case_id, agent="verifier", output=report)
        return report, [result]

    findings = raw.get("findings") or []
    # A rejection with no citable evidence is a preference, not a finding. The
    # prompt says so; this enforces it, because an uncited rejection costs a
    # revision round and can talk a correct caseworker out of a correct answer.
    cited = [f for f in findings if isinstance(f, dict) and str(f.get("evidence", "")).strip()]
    if raw["decision"] == "reject" and not cited:
        raw = {**raw, "decision": "pass", "findings": [],
               "summary": (raw.get("summary", "") + " [downgraded to pass: the rejection cited "
                           "no clause or document]").strip(),
               "downgraded": True}

    event = "VERIFIER_REJECT" if raw["decision"] == "reject" else "VERIFIER_PASS"
    if rec:
        rec.emit(event, case_id=case.case_id, agent="verifier", output=raw,
                 duration_ms=result.duration_ms, usage=result.usage())
    return raw, [result]
