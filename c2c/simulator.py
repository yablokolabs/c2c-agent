"""Synthetic airline simulator.

A controlled external world for the durability experiments. Nothing here talks
to a real carrier; there is no outbound network at all.

Its job is to be the thing that can fail. It provides:

  - an audit log of every action that actually landed, keyed by idempotency
    key, which is how "the claim was submitted exactly once" is *measured*
    rather than asserted,
  - deterministic scripted carrier responses,
  - reproducible failure injection: 503, timeout, and duplicate delivery.

Every artifact it produces is stamped SYNTHETIC DEMO / NOT FOR SUBMISSION.
"""

from __future__ import annotations

import asyncio
import itertools
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

BANNER = "SYNTHETIC DEMO — NOT FOR SUBMISSION — NOT LEGAL ADVICE"

router = APIRouter(prefix="/airline", tags=["synthetic airline"])

Injection = Literal["none", "503", "timeout", "slow"]


class ClaimSubmission(BaseModel):
    case_id: str
    passenger: str
    pnr: str
    compensation_units: Optional[int] = None
    duty_of_care_units: int = 0
    policy_citations: list[str] = Field(default_factory=list)
    summary: str = ""


class AuditEntry(BaseModel):
    seq: int
    at: str
    action: str
    case_id: str
    idempotency_key: str
    deduplicated: bool


class World:
    """All simulator state. Reset between scenarios; never persisted."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.claims: dict[str, dict] = {}
        self.audit: list[AuditEntry] = []
        self.by_key: dict[str, str] = {}
        self.injection: Injection = "none"
        self.inject_remaining: int = 0
        self.script: dict[str, dict] = {}
        self._seq = itertools.count(1)
        self.call_counts: dict[str, int] = defaultdict(int)

    def record(self, action: str, case_id: str, key: str) -> tuple[bool, AuditEntry]:
        """Record an action. Returns (was_duplicate, entry).

        A repeated idempotency key is logged as deduplicated and does not
        produce a second effect. This log is the evidence for the
        duplicate-consequential-action metric.
        """
        dup = key in self.by_key
        entry = AuditEntry(
            seq=next(self._seq),
            at=datetime.now(timezone.utc).isoformat(),
            action=action,
            case_id=case_id,
            idempotency_key=key,
            deduplicated=dup,
        )
        self.audit.append(entry)
        if not dup:
            self.by_key[key] = f"{action}:{case_id}"
        return dup, entry

    def effective_actions(self) -> list[AuditEntry]:
        return [e for e in self.audit if not e.deduplicated]

    def count(self, action: str, case_id: str) -> int:
        return sum(
            1 for e in self.effective_actions() if e.action == action and e.case_id == case_id
        )


WORLD = World()


async def _maybe_fail(endpoint: str) -> None:
    WORLD.call_counts[endpoint] += 1
    if WORLD.inject_remaining <= 0 or WORLD.injection == "none":
        return
    WORLD.inject_remaining -= 1
    if WORLD.injection == "503":
        raise HTTPException(status_code=503, detail="synthetic carrier API unavailable")
    if WORLD.injection == "timeout":
        await asyncio.sleep(3600)
    if WORLD.injection == "slow":
        await asyncio.sleep(2)


class InjectRequest(BaseModel):
    injection: Injection = "none"
    times: int = 1


@router.post("/_admin/inject")
async def set_injection(req: InjectRequest) -> dict:
    """Arm a reproducible failure. Test-only; not part of the carrier surface."""
    WORLD.injection = req.injection
    WORLD.inject_remaining = req.times
    return {"injection": req.injection, "times": req.times}


@router.post("/_admin/reset")
async def reset() -> dict:
    WORLD.reset()
    return {"reset": True}


@router.get("/_admin/audit")
async def audit() -> dict:
    return {
        "banner": BANNER,
        "entries": [e.model_dump() for e in WORLD.audit],
        "effective": [e.model_dump() for e in WORLD.effective_actions()],
        "call_counts": dict(WORLD.call_counts),
    }


class ScriptRequest(BaseModel):
    case_id: str
    on_submit: Optional[dict] = None
    on_challenge: Optional[dict] = None


@router.post("/_admin/script")
async def script(req: ScriptRequest) -> dict:
    """Pre-programme how the carrier will respond for a case."""
    WORLD.script[req.case_id] = req.model_dump(exclude={"case_id"})
    return {"scripted": req.case_id}


@router.post("/claims", status_code=201)
async def submit_claim(
    body: ClaimSubmission,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    await _maybe_fail("submit_claim")
    dup, entry = WORLD.record("submit_claim", body.case_id, idempotency_key)
    if dup:
        existing = WORLD.claims[WORLD.by_key[idempotency_key]]
        return {"banner": BANNER, "deduplicated": True, **existing}

    claim_id = f"SYN-CLM-{entry.seq:05d}"
    record = {
        "claim_id": claim_id,
        "case_id": body.case_id,
        "status": "received",
        "filed_at": entry.at,
        "response": None,
    }
    WORLD.claims[claim_id] = record
    WORLD.claims[WORLD.by_key[idempotency_key]] = record
    return {"banner": BANNER, "deduplicated": False, **record}


@router.post("/claims/{claim_id}/challenge")
async def challenge(
    claim_id: str,
    case_id: str,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    await _maybe_fail("challenge")
    if claim_id not in WORLD.claims:
        raise HTTPException(404, "no such synthetic claim")
    dup, _ = WORLD.record("challenge_rejection", case_id, idempotency_key)
    if not dup:
        WORLD.claims[claim_id]["status"] = "challenged"
    return {"banner": BANNER, "deduplicated": dup, **WORLD.claims[claim_id]}


@router.post("/escalations")
async def escalate(
    case_id: str,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    """Lodge with the fictional Synthetic Passenger Rights Body."""
    await _maybe_fail("escalate")
    dup, entry = WORLD.record("escalate", case_id, idempotency_key)
    return {
        "banner": BANNER,
        "deduplicated": dup,
        "body": "Synthetic Passenger Rights Body (fictional)",
        "reference": f"SYN-SPRB-{entry.seq:05d}",
        "case_id": case_id,
    }


@router.get("/claims/{claim_id}")
async def get_claim(claim_id: str) -> dict:
    await _maybe_fail("get_claim")
    if claim_id not in WORLD.claims:
        raise HTTPException(404, "no such synthetic claim")
    return {"banner": BANNER, **WORLD.claims[claim_id]}


@router.post("/claims/{claim_id}/_advance")
async def advance(claim_id: str) -> dict:
    """Deliver the scripted carrier response. Drives the demo forward."""
    if claim_id not in WORLD.claims:
        raise HTTPException(404, "no such synthetic claim")
    rec = WORLD.claims[claim_id]
    plan = WORLD.script.get(rec["case_id"], {})
    key = "on_challenge" if rec["status"] == "challenged" else "on_submit"
    reply = plan.get(key)
    if not reply:
        return {"banner": BANNER, "advanced": False, "reason": "nothing scripted", **rec}
    rec["response"] = reply
    rec["status"] = reply.get("type", "responded")
    return {"banner": BANNER, "advanced": True, **rec}
