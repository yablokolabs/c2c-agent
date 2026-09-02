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

import asyncio
import os
from datetime import timedelta
from typing import Any, Callable, Optional

import httpx
import restate

from c2c import notify
from c2c.notify import format_request, keyboard

# Deliveries are retried inside the durable step. notify.send never raises — by
# design, so a Telegram outage cannot park a claim — which means ctx.run's
# max_attempts (exception-driven) can never see a refused delivery. A transient
# blip used to swallow the message permanently while the step recorded success
# (F-027). Retrying here absorbs the blip; what still fails is logged loudly and
# recorded in case state instead of vanishing without a trace.
NOTIFY_ATTEMPTS = 3


async def _deliver_notify(label: str, send_once: Callable[[], dict]) -> dict:
    """Deliver one notification, retrying transient failures. Never raises."""
    last: dict = {"delivered": False, "reason": "no attempt made"}
    for attempt in range(1, NOTIFY_ATTEMPTS + 1):
        last = send_once()
        if last.get("delivered"):
            return last
        print(f"[notify] {label} attempt {attempt}/{NOTIFY_ATTEMPTS} failed: "
              f"{last.get('reason') or last.get('status')}", flush=True)
        if attempt < NOTIFY_ATTEMPTS:
            await asyncio.sleep(attempt)  # 1s, 2s backoff
    print(f"[notify] {label} NOT delivered after {NOTIFY_ATTEMPTS} attempts", flush=True)
    return last

CONTROL_PLANE = os.environ.get("C2C_CONTROL_PLANE", "http://localhost:8099")
AIRLINE = os.environ.get("C2C_AIRLINE", "http://localhost:8099/airline")
# Longer than it looks like it needs to be, on purpose. An assessment is four or
# five model calls and takes 211s at the median and 491s at the maximum, measured
# across 34 real runs. The old 120s default was shorter than a typical
# assessment, so the workflow timed out on its own agent — and because the client
# disconnected, the control plane never logged the request either, which made it
# look as though assess was never called at all. See FAILURES.md F-014.
HTTP_TIMEOUT = float(os.environ.get("C2C_HTTP_TIMEOUT", "900"))

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


async def _tell(ctx: restate.WorkflowContext, stage: str, **fields: Any) -> None:
    """Tell the passenger where their case has got to.

    Inside `ctx.run`, so a replay after a crash does not re-send a message they
    have already read. Delivery failures are retried within the step and, if
    they persist, recorded in case state rather than swallowed (F-027).
    """

    async def deliver() -> dict:
        return await _deliver_notify(stage, lambda: notify.send(notify.render(stage, **fields)))

    result = await ctx.run(f"notify_{stage}", deliver, max_attempts=2)
    if not result.get("delivered"):
        ctx.set("notify_failure", f"{stage}: {result.get('reason') or result.get('status')}")


async def _ask_approval(ctx: restate.WorkflowContext, case_id: str, action: str,
                        verdict: dict, promise_name: str) -> None:
    """Send the approval request, with the Approve/Reject buttons.

    The case suspends on a durable promise and consumes nothing until someone
    answers, which may be days — so the passenger has to be able to answer from
    where they already are. The callback data carries the promise name the
    workflow is waiting on; the bot's callback handling resolves it.
    """
    text = format_request(case_id, {"pending_action": action, "verdict": verdict or {}})
    markup = keyboard(case_id, action)

    async def deliver() -> dict:
        return await _deliver_notify(
            f"approval_{promise_name}", lambda: notify.send(text, reply_markup=markup))

    result = await ctx.run(f"notify_approval_{promise_name}", deliver, max_attempts=2)
    if not result.get("delivered"):
        ctx.set("notify_failure", f"approval_{promise_name}: {result.get('reason') or result.get('status')}")


@case_workflow.main()
async def run(ctx: restate.WorkflowContext, req: dict) -> dict:
    """Carry one case from intake to a terminal state."""
    case_id = ctx.key()
    await _set_state(ctx, "INTAKE", case_id=case_id, opened_by=req.get("opened_by", "unknown"))
    await _tell(ctx, "case_opened", case_id=case_id)

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
    if action == "request_evidence":
        # The agent needs documents the passenger has not sent. The case waits
        # durably instead of closing: the passenger is told exactly what is
        # missing, and every time they send something the case is re-assessed
        # with the new documents until the agent either has enough (and the
        # case proceeds) or closes it.
        #
        # Each round waits on its own promise (`evidence_0`, `evidence_1`, ...)
        # so a replay cannot re-read a resolved promise and spin without new
        # input. And the re-assess step has a fresh name per round, because
        # Restate deduplicates ctx.run by name — reusing "assess" would hand
        # back the first verdict.
        evidence_round = 0
        while True:
            missing = verdict.get("missing_evidence") or []
            await _set_state(ctx, "AWAITING_EVIDENCE", evidence_round=evidence_round)
            await _tell(ctx, "evidence_requested", case_id=case_id, pnr=req.get("pnr", case_id),
                        missing="\n".join(f"• {m}" for m in missing) or "nothing on file")
            await ctx.promise(f"evidence_{evidence_round}").value()
            evidence_round += 1

            async def do_reassess() -> dict:
                return await _post(f"{CONTROL_PLANE}/c2c/assess", json={"case_id": case_id})

            verdict = await ctx.run(f"assess_after_evidence_{evidence_round}", do_reassess,
                                    max_attempts=3)
            ctx.set("verdict", verdict)
            action = verdict.get("next_action")
            if action != "request_evidence":
                break

    if action not in CONSEQUENTIAL:
        await _set_state(ctx, "CLOSED_NO_ACTION")
        if action == "request_evidence":
            # Telling the passenger "there isn't a claim worth making" when the
            # agent simply needs more documents is the same silence that kills
            # real claims. Say exactly what is missing.
            missing = verdict.get("missing_evidence") or []
            await _tell(ctx, "evidence_requested", case_id=case_id, pnr=req.get("pnr", case_id),
                        missing="\n".join(f"• {m}" for m in missing) or "nothing on file")
        else:
            await _tell(ctx, "assessed_no_claim", pnr=req.get("pnr", case_id),
                        rationale=verdict.get("rationale", "no rationale recorded"))
        return {"case_id": case_id, "outcome": "closed_no_action",
                "next_action": action, "verdict": verdict}

    # --- human approval -----------------------------------------------------
    # A durable promise, not a poll. The workflow suspends here and consumes
    # nothing until someone answers, which may be days. The passenger is asked
    # on Telegram, with the Approve/Reject buttons.
    await _set_state(ctx, "AWAITING_APPROVAL", pending_action=action)
    await _ask_approval(ctx, case_id, action, verdict, "approval")
    decision = await ctx.promise("approval").value()

    if not decision.get("approved"):
        # Invariant: an action a human rejected must never execute. This
        # returns before any side effect is reachable.
        await _set_state(ctx, "CLOSED_BY_HUMAN")
        await _tell(ctx, "closed_by_human", pnr=req.get("pnr", case_id))
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
    await _tell(ctx, "claim_filed", amount=verdict.get("compensation_units", 0),
                case_id=case_id)

    # --- wait for the carrier, or for the policy clock ----------------------
    await _set_state(ctx, "AWAITING_CARRIER")
    reply = await _await_carrier(ctx, "carrier_response", CARRIER_SILENCE_DAYS)

    if reply is None:
        outcome = await _escalate(ctx, case_id, "S10.1(a): 56 days of carrier silence")
        return {"case_id": case_id, "claim_id": claim_id, **outcome}

    ctx.set("carrier_reply", reply)
    await _tell(ctx, "carrier_replied", pnr=req.get("pnr", case_id))

    if reply.get("type") in ("settlement_offer", "settled", "paid"):
        # S9.4: an offer is only acceptable if it meets the full entitlement.
        # Telling the passenger the shortfall is the difference between an agent
        # that closes cases and one that gets them paid properly.
        owed = ((verdict.get("compensation_units") or 0)
                + verdict.get("duty_of_care_units", 0)
                + verdict.get("downgrade_reimbursement_units", 0))
        offered = reply.get("amount_units")
        if offered is not None and offered < owed:
            await _tell(ctx, "offer_short", pnr=req.get("pnr", case_id),
                        offered=offered, owed=owed, shortfall=owed - offered)
        else:
            await _set_state(ctx, "RESOLVED_SETTLED")
            await _tell(ctx, "resolved", pnr=req.get("pnr", case_id),
                        amount=offered if offered is not None else owed)
            return {"case_id": case_id, "claim_id": claim_id, "outcome": "settled",
                    "carrier_reply": reply}

    # --- challenge ----------------------------------------------------------
    await _set_state(ctx, "AWAITING_APPROVAL", pending_action="challenge_rejection")
    await _tell(ctx, "rejection_challengeable",
                rationale=verdict.get("rationale", "the record does not support their ground"))
    await _ask_approval(ctx, case_id, "challenge_rejection", verdict, "challenge_approval")
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
    await _tell(ctx, "challenge_sent", pnr=req.get("pnr", case_id),
                citations=", ".join(verdict.get("policy_citations") or []) or "the record")

    after = await _await_carrier(ctx, "challenge_response", CHALLENGE_SILENCE_DAYS)
    if after is None:
        outcome = await _escalate(ctx, case_id, "S10.1(b): 28 days of silence after challenge")
        return {"case_id": case_id, "claim_id": claim_id, **outcome}

    ctx.set("challenge_reply", after)
    # Tell the passenger how the challenge came out. Resolving without a word
    # is the exact silence this project exists to remove (F-025).
    if after.get("type") in ("settlement_offer", "settled", "paid"):
        amount = after.get("amount_units")
        amount_text = f"{amount} units" if amount is not None else "an undisclosed figure"
        await _tell(ctx, "challenge_settled", pnr=req.get("pnr", case_id),
                    case_id=case_id, amount=amount_text)
    else:
        await _tell(ctx, "challenge_refused", pnr=req.get("pnr", case_id),
                    case_id=case_id)
    await _set_state(ctx, "RESOLVED_AFTER_CHALLENGE", pending_action=None)
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
    await _tell(ctx, "escalation_ready", pnr=case_id, ground=ground)
    await _ask_approval(ctx, case_id, "escalate", {}, "escalation_approval")
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
    await _tell(ctx, "escalated", reference=lodged.get("reference", "pending"))
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
async def evidence(ctx: restate.WorkflowSharedContext, event: dict) -> dict:
    """Deliver passenger-submitted evidence for the round the workflow is
    waiting on. Resolving the same round twice is absorbed: a redelivered
    submission cannot trigger two re-assessments."""
    name = f"evidence_{int(event.get('round', 0))}"
    try:
        await ctx.promise(name).resolve(event.get("documents", event))
        return {"accepted": True, "promise": name, "duplicate": False}
    except Exception:  # noqa: BLE001 - already resolved
        return {"accepted": False, "promise": name, "duplicate": True,
                "detail": "this evidence round was already delivered"}


@case_workflow.handler()
async def status(ctx: restate.WorkflowSharedContext) -> dict:
    keys = ["state", "case_id", "verdict", "claim_id", "pending_action",
            "carrier_reply", "challenge_reply", "escalation_reference", "opened_by",
            "evidence_round", "notify_failure"]
    out = {}
    for k in keys:
        v = await ctx.get(k)
        if v is not None:
            out[k] = v
    return out


SERVICES = [case_workflow]
app = restate.app(SERVICES)
