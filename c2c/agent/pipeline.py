"""Caseworker, then verifier, then at most one revision.

One revision, not a loop to convergence. Two reasons. The measured one comes
later in the changelog; the design one is that a verifier and a caseworker that
disagree twice are not converging, they are oscillating, and the second
disagreement is information the passenger should get rather than something to
grind away.
"""

from __future__ import annotations

from typing import Optional

from c2c.agent import caseworker, verifier
from c2c.llm import LLM, LLMResult
from c2c.models import Case, Verdict
from c2c.trajectory import Recorder

def run_case(
    case: Case,
    llm: LLM,
    rec: Optional[Recorder] = None,
    use_verifier: bool = True,
    enforce_arithmetic: bool = False,
) -> tuple[Optional[Verdict], list[LLMResult]]:
    calls: list[LLMResult] = []

    verdict, cw_calls, _box = caseworker.run(
        case, llm, rec, enforce_arithmetic=enforce_arithmetic)
    calls += cw_calls
    if verdict is None or not use_verifier:
        return verdict, calls

    report, v_calls = verifier.run(case, verdict, llm, rec)
    calls += v_calls
    if report["decision"] == "pass":
        return verdict, calls

    revised, r_calls, _box2 = caseworker.run(
        case, llm, rec, feedback=verifier.format_feedback(report),
        enforce_arithmetic=enforce_arithmetic,
    )
    calls += r_calls
    if revised is None:
        # The revision failed to produce anything. The original verdict stands;
        # discarding a real verdict because the retry broke would be worse.
        if rec:
            rec.emit("ERROR", case_id=case.case_id, agent="pipeline", success=False,
                     output="revision produced no verdict; keeping the original")
        return verdict, calls

    if rec:
        rec.emit("FINAL_DECISION", case_id=case.case_id, agent="pipeline",
                 output=revised.model_dump(),
                 input={"changed_after_verification": revised.model_dump() != verdict.model_dump()})
    return revised, calls
