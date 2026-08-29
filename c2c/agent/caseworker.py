"""The caseworker: a tool-using loop over one case.

One JSON object per turn, either a tool call or a verdict. The transcript is
resent each turn, which keeps the model transport single-shot and keeps the
system prefix byte-identical so it stays cached.
"""

from __future__ import annotations

from typing import Optional

from c2c import prompts
from c2c.agent.tools import TOOL_SPEC, ToolBox
from c2c.llm import LLM, LLMResult, extract_json
from c2c.models import Case, Verdict
from c2c.trajectory import Recorder

MAX_STEPS = 10

# EXP-005. EXP-001 measured `calculate` being called 3 times across 28 cases,
# including on neither of the two cases that fail *because of* arithmetic — even
# though the prompt already says to use it for every arithmetic step. Asking did
# not work. This enforces it: a verdict asserting money it never computed is
# handed back once, with the arithmetic it owes.
#
# Deliberately narrow. It fires only when there is money to check and the tool
# was never called at all, it fires at most once per case, and it never supplies
# or corrects a number — it only makes the agent do the step it skipped.
ENFORCE_ARITHMETIC = False


def _owes_arithmetic(v: Verdict) -> bool:
    return bool((v.compensation_units or 0) or v.duty_of_care_units
                or v.downgrade_reimbursement_units)


def coerce_verdict(raw: dict) -> Verdict:
    """Shape-only coercion. No value is invented or corrected."""
    allowed = set(Verdict.model_fields)
    cleaned = {k: v for k, v in raw.items() if k in allowed}
    for key in ("missing_evidence", "policy_citations"):
        if isinstance(cleaned.get(key), str):
            cleaned[key] = [cleaned[key]]
    for money in ("duty_of_care_units", "downgrade_reimbursement_units"):
        if cleaned.get(money) is None:
            cleaned[money] = 0
    return Verdict.model_validate(cleaned)


def system_prompt() -> str:
    return (
        prompts.load("caseworker")
        .replace("{tools}", TOOL_SPEC)
        .replace("{policy}", prompts.policy())
    )


def run(
    case: Case,
    llm: LLM,
    rec: Optional[Recorder] = None,
    feedback: Optional[str] = None,
    enforce_arithmetic: bool = ENFORCE_ARITHMETIC,
) -> tuple[Optional[Verdict], list[LLMResult], ToolBox]:
    """Work one case. `feedback` carries a verifier rejection into a retry."""
    box = ToolBox(case=case)
    system = system_prompt()
    calls: list[LLMResult] = []

    opening = ["## THE CASE", "", case.dossier()]
    if feedback:
        opening += [
            "## AN INDEPENDENT VERIFIER REJECTED YOUR PREVIOUS VERDICT",
            "",
            feedback,
            "",
            "Re-examine the points raised. The verifier is not automatically right: if "
            "the record supports your original reading, say so and keep it, citing the "
            "document. If it does not, correct it.",
            "",
        ]
    opening.append("Begin. Reply with exactly one JSON object.")
    transcript = "\n".join(opening)

    agent = "caseworker" + ("/revision" if feedback else "")
    arithmetic_enforced = False
    if rec:
        rec.emit("AGENT_START", case_id=case.case_id, agent=agent,
                 input={"feedback": feedback} if feedback else None)

    for step in range(MAX_STEPS):
        result = llm.complete(system, transcript)
        calls.append(result)
        if rec:
            rec.emit("MODEL_RESPONSE", case_id=case.case_id, agent=agent,
                     output=result.text, duration_ms=result.duration_ms,
                     usage=result.usage(), step=step)

        raw = extract_json(result.text)
        if raw is None:
            transcript += ("\n\nYour last reply contained no JSON object. Reply with exactly "
                           "one JSON object: a tool call, or {\"verdict\": {...}}.")
            if rec:
                rec.emit("RETRY", case_id=case.case_id, agent=agent, step=step,
                         output="no JSON object in the reply")
            continue

        if "verdict" in raw:
            try:
                verdict = coerce_verdict(raw["verdict"])
            except Exception as exc:  # noqa: BLE001
                transcript += f"\n\nYour verdict did not validate: {exc}\nReturn a corrected verdict."
                if rec:
                    rec.emit("RETRY", case_id=case.case_id, agent=agent, step=step,
                             output=f"verdict did not validate: {exc}")
                continue
            if (enforce_arithmetic and not arithmetic_enforced
                    and _owes_arithmetic(verdict)
                    and not any(c["tool"] == "calculate" for c in box.calls)):
                arithmetic_enforced = True
                if rec:
                    rec.emit("RETRY", case_id=case.case_id, agent=agent, step=step,
                             output="verdict asserts money without computing it; "
                                    "arithmetic enforcement triggered")
                transcript += (
                    "\n\nYou have given amounts without computing any of them. Use "
                    "`calculate` to work through every arithmetic step behind those "
                    "figures: the band amount, each reduction and how they compose, and "
                    "any sum of receipts against the Part 6 cap. Then give your verdict "
                    "again.\n\nThe figures may well be right. Check them rather than "
                    "assume it, and change them only if the arithmetic says so."
                )
                continue
            if rec:
                rec.emit("FINAL_DECISION", case_id=case.case_id, agent=agent,
                         output=verdict.model_dump(), steps=step + 1,
                         tool_calls=len(box.calls),
                         arithmetic_enforced=arithmetic_enforced)
            return verdict, calls, box

        tool = raw.get("tool")
        if not tool:
            transcript += ("\n\nThat object was neither a tool call nor a verdict. Reply with "
                           "{\"tool\": ..., \"args\": {...}} or {\"verdict\": {...}}.")
            continue

        args = raw.get("args") or {}
        if rec:
            rec.emit("TOOL_CALL", case_id=case.case_id, agent=agent, tool=tool,
                     input=args, output=raw.get("why"))
        out = box.call(tool, args if isinstance(args, dict) else {})
        if rec:
            rec.emit("TOOL_RESULT", case_id=case.case_id, agent=agent, tool=tool,
                     output=out, success=not out.startswith("ERROR"))
        transcript += (f"\n\nYou called: {tool}({args})\n\nResult:\n{out}\n\n"
                       "Next step. Reply with exactly one JSON object.")

    if rec:
        rec.emit("ERROR", case_id=case.case_id, agent=agent, success=False,
                 output=f"no verdict within {MAX_STEPS} steps")
    return None, calls, box
