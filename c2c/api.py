"""C2C control plane.

FastAPI owns HTTP and nothing else. It does not hold case state — Restate does —
and it does not decide anything about a claim — the agent does. Its job is to be
the surface the workflow, the human and the demo all talk to.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from c2c.agent.pipeline import run_case
from c2c.artifact import case_summary, claim_letter
from c2c.llm import DEFAULT_MODEL, LLM
from c2c.models import Verdict, load_cases
from c2c.trajectory import Recorder

RESTATE_INGRESS = os.environ.get("C2C_RESTATE_INGRESS", "http://localhost:8080")
WORKFLOW = "C2CCase"

router = APIRouter(prefix="/c2c", tags=["control plane"])

_cases = {c.case_id: c for c in load_cases()}
_recorder: Optional[Recorder] = None


def recorder() -> Recorder:
    global _recorder
    if _recorder is None:
        _recorder = Recorder.open("live")
    return _recorder


class AssessRequest(BaseModel):
    case_id: str
    model: str = DEFAULT_MODEL


@router.post("/assess")
async def assess(req: AssessRequest) -> dict:
    """Run the agent over a case. Called by the workflow's durable assess step.

    Deliberately not idempotent in itself — Restate's `ctx.run` gives it
    exactly-once semantics, and duplicating that here would be two mechanisms
    for one invariant.
    """
    case = _cases.get(req.case_id)
    if case is None:
        raise HTTPException(404, f"no such benchmark case {req.case_id!r}")
    verdict, _calls = run_case(case, LLM(model=req.model), recorder())
    if verdict is None:
        raise HTTPException(502, "the agent produced no verdict")
    return verdict.model_dump()


class OpenRequest(BaseModel):
    opened_by: str = "demo"


@router.post("/cases/{case_id}/open")
async def open_case(case_id: str, req: OpenRequest) -> dict:
    """Start the durable workflow for a case, and return immediately.

    Restate keys the workflow by case_id, so opening the same case twice
    attaches to the existing run rather than starting a second one.
    """
    case = _cases.get(case_id)
    if case is None:
        raise HTTPException(404, f"no such benchmark case {case_id!r}")
    payload = {"opened_by": req.opened_by,
               "passenger": case.passenger["name"], "pnr": case.passenger["pnr"]}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{RESTATE_INGRESS}/{WORKFLOW}/{case_id}/run/send", json=payload)
        r.raise_for_status()
        return {"case_id": case_id, "started": True, "restate": r.json()}


class Approval(BaseModel):
    approved: bool
    reason: str = ""
    by: str = "human"
    promise: str = "approval"


@router.post("/cases/{case_id}/approve")
async def approve(case_id: str, decision: Approval) -> dict:
    """Answer a pending human approval. Consequential actions wait on this."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{RESTATE_INGRESS}/{WORKFLOW}/{case_id}/approve", json=decision.model_dump()
        )
        r.raise_for_status()
        return r.json()


class CarrierEvent(BaseModel):
    payload: dict
    promise: str = "carrier_response"


@router.post("/cases/{case_id}/carrier-event")
async def carrier_event(case_id: str, event: CarrierEvent) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{RESTATE_INGRESS}/{WORKFLOW}/{case_id}/carrier_event", json=event.model_dump()
        )
        r.raise_for_status()
        return r.json()


@router.get("/cases/{case_id}")
async def case_status(case_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{RESTATE_INGRESS}/{WORKFLOW}/{case_id}/status")
        r.raise_for_status()
        return r.json()


@router.get("/cases/{case_id}/document", response_class=PlainTextResponse)
async def case_document(case_id: str, kind: str = "summary") -> str:
    """The artifact the passenger actually receives.

    Rendered from the workflow's stored verdict, deterministically. Asking a
    model to write the letter as well would add a place for a figure to drift
    away from the one that was assessed and approved.
    """
    case = _cases.get(case_id)
    if case is None:
        raise HTTPException(404, f"no such benchmark case {case_id!r}")
    state = await case_status(case_id)
    raw = state.get("verdict")
    if not raw:
        raise HTTPException(409, "this case has not been assessed yet")
    verdict = Verdict.model_validate({k: v for k, v in raw.items() if k in Verdict.model_fields})
    if kind == "letter":
        return claim_letter(case, verdict)
    if kind == "summary":
        return case_summary(case, verdict)
    raise HTTPException(400, "kind must be 'summary' or 'letter'")


@router.get("/cases")
async def list_cases() -> dict:
    return {"cases": [
        {"case_id": c.case_id, "title": c.title, "difficulty": c.difficulty,
         "passenger": c.passenger["name"]}
        for c in _cases.values()
    ]}


@router.get("/health")
async def health() -> dict:
    return {"ok": True, "cases": len(_cases), "restate_ingress": RESTATE_INGRESS}
