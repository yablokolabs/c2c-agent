"""The baseline system: one direct prompt, no tools, no verification.

This is what the agent has to beat. It is given the same model, the same
policy, the same cases and the same output schema, all in a single call.
"""

from __future__ import annotations

from typing import Optional

from c2c import prompts
from c2c.llm import LLM, LLMResult, extract_json
from c2c.models import Case, Verdict
from c2c.trajectory import Recorder


def _coerce(raw: dict) -> Verdict:
    """Accept what the model actually returns rather than demanding perfection.

    Coercion is limited to shape, never to content: missing optional fields get
    their defaults and stray keys are dropped, but no value is invented or
    corrected. A response that omits a required decision fails to parse, which
    is a real failure of the system and is scored as one.
    """
    allowed = set(Verdict.model_fields)
    cleaned = {k: v for k, v in raw.items() if k in allowed}
    if isinstance(cleaned.get("missing_evidence"), str):
        cleaned["missing_evidence"] = [cleaned["missing_evidence"]]
    if isinstance(cleaned.get("policy_citations"), str):
        cleaned["policy_citations"] = [cleaned["policy_citations"]]
    for money in ("duty_of_care_units", "downgrade_reimbursement_units"):
        if cleaned.get(money) is None:
            cleaned[money] = 0
    return Verdict.model_validate(cleaned)


def run_case(case: Case, llm: LLM, rec: Optional[Recorder] = None) -> tuple[Optional[Verdict], list[LLMResult]]:
    template = prompts.load("baseline_v1")
    system, user = template.split("## THE CASE", 1)[0], case.dossier()
    system = system.replace("{policy}", prompts.policy()).replace("## THE POLICY", "## THE POLICY").strip()
    user = "## THE CASE\n\n" + user

    if rec:
        rec.emit("AGENT_START", case_id=case.case_id, agent="baseline")
        rec.emit("MODEL_REQUEST", case_id=case.case_id, agent="baseline",
                 input={"system_digest": prompts.digest(system), "user": user})

    result = llm.complete(system, user)

    if rec:
        rec.emit("MODEL_RESPONSE", case_id=case.case_id, agent="baseline",
                 output=result.text, duration_ms=result.duration_ms, usage=result.usage())

    raw = extract_json(result.text)
    if raw is None:
        if rec:
            rec.emit("ERROR", case_id=case.case_id, agent="baseline", success=False,
                     output="response contained no parseable JSON verdict")
        return None, [result]
    try:
        verdict = _coerce(raw)
    except Exception as exc:  # noqa: BLE001
        if rec:
            rec.emit("ERROR", case_id=case.case_id, agent="baseline", success=False,
                     output=f"verdict did not validate: {exc}")
        return None, [result]

    if rec:
        rec.emit("FINAL_DECISION", case_id=case.case_id, agent="baseline",
                 output=verdict.model_dump())
    return verdict, [result]
