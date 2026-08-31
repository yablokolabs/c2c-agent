"""Durable case lifecycle, on Restate.

Agents reason. Workflows remember. Nothing in here decides anything about a
claim: it calls the control plane for that. What it owns is everything that has
to survive a process dying — which, for this problem, is most of the task.

Each Restate feature here is load-bearing for a stated invariant:

  workflow key = case_id   two intakes of the same case are the same workflow,
                           so a duplicate inbound event cannot start a second
                           lifecycle
  ctx.run                  a side effect that succeeded is never re-executed on
                           replay, so a crash after submitting does not submit
                           again
  ctx.uuid()               idempotency keys are replay-stable, so a retry
                           *inside* a side effect reuses the same key and the
                           carrier deduplicates it
  ctx.promise              a human approval that outlives the process; the
                           workflow suspends rather than polls, for days
  ctx.sleep                the 56-day and 28-day policy clocks, durable across
                           restarts
  ctx.set                  case state that survives a kill -9

Every service this module owns is prefixed `C2C`, because the Restate server it
registers with is shared with an unrelated project. See docs/ENVIRONMENT.md.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Optional

import httpx
import restate

CONTROL_PLANE = os.environ.get("C2C_CONTROL_PLANE", "http://localhost:8099")
AIRLINE = os.environ.get("C2C_AIRLINE", "http://localhost:8099/airline")
HTTP_TIMEOUT = float(os.environ.get("C2C_HTTP_TIMEOUT", "120"))

# Policy clocks. Compressed by C2C_CLOCK_SCALE so a demo and the failure suite
# can exercise real timer behaviour without waiting eight weeks; the durable
# semantics are identical either way.
CLOCK_SCALE = float(os.environ.get("C2C_CLOCK_SCALE", "1"))
CARRIER_SILENCE_DAYS = 56  # S10.1(a)
CHALLENGE_SILENCE_DAYS = 28  # S10.1(b)

CONSEQUENTIAL = {"submit_claim", "send_followup", "challenge_rejection",
                 "escalate", "accept_settlement"}

case_workflow = restate.Workflow("C2CCase")


def _clock(days: int) -> timedelta:
    return timedelta(days=days) * CLOCK_SCALE


async def _post(url: str, *, json: Any = None, params: Any = None,
                headers: Any = None) -> dict:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.post(url, json=json, params=params, headers=headers)
        r.raise_for_status()
        return r.json()


async def _set_state(ctx: restate.WorkflowContext, state: str, **extra: Any) -> None:
    ctx.set("state", state)
    for k, v in extra.items():
        ctx.set(k, v)


@case_workflow.main()
async def run(ctx: restate.WorkflowContext, req: dict) -> dict:
    """Carry one case from intake to a terminal state."""
    case_id = ctx.key()
    await _set_state(ctx, "INTAKE", case_id=case_id, opened_by=req.get("opened_by", "unknown"))

    # --- assess -------------------------------------------------------------
    # The agent runs in the control plane, not here. If it throws, Restate
    # retries this block; if it succeeded once, replay never re-runs it.
    async def do_assess() -> dict:
        return await _post(f"{CONTROL_PLANE}/c2c/assess", json={"case_id": case_id})

    # Bounded, unlike every other step here. An assessment is expensive — four
    # or five model calls — and the model transport already retries five times
    # inside it. Left unbounded, a transient backend failure compounds: Restate
    # retries the whole step, which restarts the caseworker from scratch, which
    # makes another five attempts. One observed run produced 67 agent starts for
    # 6 completed assessments and never left INTAKE. Three attempts is enough to
    # ride out a blip and few enough to surface a real outage as a failure
    # instead of a runaway. See FAILURES.md F-012.
    verdict = await ctx.run("assess", do_assess, max_attempts=3)
    ctx.set("verdict", verdict)
    await _set_state(ctx, "ASSESSED")

    action = verdict.get("next_action")
    if action not in CONSEQUENTIAL:
        await _set_state(ctx, "CLOSED_NO_ACTION")
        return {"case_id": case_id, "outcome": "closed_no_action",
                "next_action": action, "verdict": verdict}

    # --- human approval -----------------------------------------------------
    # A durable promise, not a poll. The workflow suspends here and consumes
    # nothing until someone answers, which may be days.
    await _set_state(ctx, "AWAITING_APPROVAL", pending_action=action)
    decision = await ctx.promise("approval").value()

    if not decision.get("approved"):
        # Invariant: an action a human rejected must never execute. This
        # returns before any side effect is reachable.
        await _set_state(ctx, "CLOSED_BY_HUMAN")
        return {"case_id": case_id, "outcome": "rejected_by_human",
                "rejected_action": action, "reason": decision.get("reason", ""),
                "verdict": verdict}

    # --- execute exactly once -----------------------------------------------
    # The key is generated inside a durable step, so it is stable across
    # replays. A retry that reaches the carrier twice presents the same key and
    # the second one is deduplicated there.
    idem = await ctx.run("idem_submit", lambda: str(ctx.uuid()))
    async def do_submit() -> dict:
        return await _post(
            f"{AIRLINE}/claims",
            json={
                "case_id": case_id,
                "passenger": req.get("passenger", "unknown"),
                "pnr": req.get("pnr", "unknown"),
                "compensation_units": verdict.get("compensation_units"),
                "duty_of_care_units": verdict.get("duty_of_care_units", 0),
                "policy_citations": verdict.get("policy_citations", []),
                "summary": verdict.get("rationale", ""),
            },
            headers={"Idempotency-Key": idem},
        )

    submitted = await ctx.run("submit", do_submit)
    claim_id = submitted["claim_id"]
    await _set_state(ctx, "SUBMITTED", claim_id=claim_id)

    # --- wait for the carrier, or for the policy clock ----------------------
    await _set_state(ctx, "AWAITING_CARRIER")
    reply = await _await_carrier(ctx, "carrier_response", CARRIER_SILENCE_DAYS)

    if reply is None:
        outcome = await _escalate(ctx, case_id, "S10.1(a): 56 days of carrier silence")
        return {"case_id": case_id, "claim_id": claim_id, **outcome}

    ctx.set("carrier_reply", reply)
    if reply.get("type") in ("settlement_offer", "settled", "paid"):
        await _set_state(ctx, "RESOLVED_SETTLED")
        return {"case_id": case_id, "claim_id": claim_id, "outcome": "settled",
                "carrier_reply": reply}

    # --- challenge ----------------------------------------------------------
    await _set_state(ctx, "AWAITING_APPROVAL", pending_action="challenge_rejection")
    ch_decision = await ctx.promise("challenge_approval").value()
    if not ch_decision.get("approved"):
        await _set_state(ctx, "CLOSED_BY_HUMAN")
        return {"case_id": case_id, "claim_id": claim_id, "outcome": "rejected_by_human",
                "rejected_action": "challenge_rejection"}

    ch_idem = await ctx.run("idem_challenge", lambda: str(ctx.uuid()))
    async def do_challenge() -> dict:
        return await _post(f"{AIRLINE}/claims/{claim_id}/challenge",
                           params={"case_id": case_id},
                           headers={"Idempotency-Key": ch_idem})

    await ctx.run("challenge", do_challenge)
    await _set_state(ctx, "CHALLENGED")

    after = await _await_carrier(ctx, "challenge_response", CHALLENGE_SILENCE_DAYS)
    if after is None:
        outcome = await _escalate(ctx, case_id, "S10.1(b): 28 days of silence after challenge")
        return {"case_id": case_id, "claim_id": claim_id, **outcome}

    ctx.set("challenge_reply", after)
    await _set_state(ctx, "RESOLVED_AFTER_CHALLENGE")
    return {"case_id": case_id, "claim_id": claim_id,
            "outcome": "resolved_after_challenge", "carrier_reply": after}


async def _await_carrier(
    ctx: restate.WorkflowContext, promise_name: str, days: int
) -> Optional[dict]:
    """Whichever comes first: the carrier replies, or the clock runs out."""
    reply = ctx.promise(promise_name).value()
    deadline = ctx.sleep(_clock(days), name=f"{promise_name}_deadline")
    match await restate.select(reply=reply, deadline=deadline):
        case ["reply", value]:
            return value
        case _:
            return None


async def _escalate(ctx: restate.WorkflowContext, case_id: str, ground: str) -> dict:
    await _set_state(ctx, "AWAITING_APPROVAL", pending_action="escalate")
    decision = await ctx.promise("escalation_approval").value()
    if not decision.get("approved"):
        await _set_state(ctx, "CLOSED_BY_HUMAN")
        return {"outcome": "rejected_by_human", "rejected_action": "escalate", "ground": ground}

    idem = await ctx.run("idem_escalate", lambda: str(ctx.uuid()))
    async def do_escalate() -> dict:
        return await _post(f"{AIRLINE}/escalations", params={"case_id": case_id},
                           headers={"Idempotency-Key": idem})

    lodged = await ctx.run("escalate", do_escalate)
    await _set_state(ctx, "ESCALATED", escalation_reference=lodged.get("reference"))
    return {"outcome": "escalated", "ground": ground,
            "escalation_reference": lodged.get("reference")}


# --- handlers the outside world calls ---------------------------------------

@case_workflow.handler()
async def approve(ctx: restate.WorkflowSharedContext, decision: dict) -> dict:
    """Answer a pending human approval.

    Resolving a promise twice is an error in Restate, which is the property we
    want: a duplicate approval, whether from an impatient human or a redelivered
    message, cannot produce a second side effect.
    """
    name = decision.get("promise", "approval")
    try:
        await ctx.promise(name).resolve(
            {"approved": bool(decision.get("approved")),
             "reason": decision.get("reason", ""),
             "by": decision.get("by", "unknown")}
        )
        return {"accepted": True, "promise": name, "duplicate": False}
    except Exception:  # noqa: BLE001 - already resolved
        return {"accepted": False, "promise": name, "duplicate": True,
                "detail": "this approval was already answered"}


@case_workflow.handler()
async def carrier_event(ctx: restate.WorkflowSharedContext, event: dict) -> dict:
    """Deliver a carrier response. Duplicate deliveries are absorbed."""
    name = event.get("promise", "carrier_response")
    try:
        await ctx.promise(name).resolve(event.get("payload", event))
        return {"accepted": True, "promise": name, "duplicate": False}
    except Exception:  # noqa: BLE001 - already resolved
        return {"accepted": False, "promise": name, "duplicate": True,
                "detail": "this event was already delivered"}


@case_workflow.handler()
async def status(ctx: restate.WorkflowSharedContext) -> dict:
    keys = ["state", "case_id", "verdict", "claim_id", "pending_action",
            "carrier_reply", "challenge_reply", "escalation_reference", "opened_by"]
    out = {}
    for k in keys:
        v = await ctx.get(k)
        if v is not None:
            out[k] = v
    return out


SERVICES = [case_workflow]
app = restate.app(SERVICES)
