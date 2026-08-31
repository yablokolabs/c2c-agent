"""Telling the passenger what is happening.

The workflow already moves through eleven states. Until now it told nobody,
which is a strange thing for a project whose whole argument is that claims die
in the silences. A durable system that holds your case for eight weeks and never
says so is, from where the passenger sits, indistinguishable from one that
forgot.

Two rules shape this:

**Notifications are side effects and get the same treatment as any other.** They
are sent from inside `ctx.run`, so a replay after a crash does not re-send a
message the passenger already read. Being told twice that your claim was filed
is a small harm; being told twice that you have been paid is not.

**A dead notifier must never stall a case.** Delivery failures are swallowed and
recorded. The claim matters; the message about the claim does not.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import httpx

BANNER = "SYNTHETIC DEMO — NOT FOR SUBMISSION — NOT LEGAL ADVICE"


def _load_dotenv() -> None:
    """Read .env if present. Keeps the bot token out of the shell history and
    out of the repository; `.env` is gitignored."""
    p = Path(".env")
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

TOKEN = os.environ.get("C2C_TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("C2C_TELEGRAM_CHAT_ID", "")


# The stages the passenger is told about, in the order they occur. The wording
# is deliberately plain: someone reading this on a phone six weeks after their
# flight should understand it without re-reading the policy.
STAGES = {
    "case_opened": (
        "Your case is open: *{case_id}*\n\n"
        "Quote that reference if you ever need to. I'm reading through what you "
        "sent now and working out what you're owed — that takes a few minutes.\n\n"
        "I'll come back to you before anything goes to the airline. Nothing is "
        "sent without you saying so."
    ),
    "assessed_no_claim": (
        "I've finished going through {pnr}.\n\n"
        "On these facts there isn't a claim worth making, and I'd rather tell you "
        "that than have you chase it. Here's why:\n\n{rationale}"
    ),
    "claim_filed": (
        "Filed. Your claim for *{amount} units* is with the airline ({case_id}).\n\n"
        "They now have 56 days to give a final answer. If they go quiet, I'll "
        "escalate automatically — you don't need to remember any of this."
    ),
    "carrier_replied": (
        "The airline has replied on {pnr}.\n\n"
        "I'm checking what they've said against the policy and the operational "
        "record before I do anything."
    ),
    "rejection_challengeable": (
        "They've refused — and their reason doesn't hold up.\n\n"
        "{rationale}\n\nI'd like to challenge it. It's your call."
    ),
    "challenge_sent": (
        "Challenge sent on {pnr}, citing {citations}.\n\n"
        "They have 28 days. If they maintain the refusal or say nothing, "
        "escalation becomes available and I'll ask you then."
    ),
    "escalation_ready": (
        "It's time to escalate {pnr}.\n\n{ground}\n\n"
        "This goes to the Synthetic Passenger Rights Body. Your call."
    ),
    "escalated": (
        "Escalated. Reference *{reference}*.\n\n"
        "It's out of the airline's hands now. I'll keep watching."
    ),
    "offer_short": (
        "The airline has offered *{offered} units* on {pnr}.\n\n"
        "By my reading you're owed *{owed}*. That's {shortfall} short, so I'd "
        "push back rather than accept. Your call."
    ),
    "offer_full": (
        "The airline has offered *{offered} units* on {pnr}, which matches the "
        "full entitlement as I calculate it.\n\nI'd accept. Your call."
    ),
    "resolved": (
        "Done. {pnr} is settled at *{amount} units*.\n\n"
        "Check your account over the next few days. Closing the case."
    ),
    "closed_by_human": (
        "Closed {pnr} at your request. Nothing was sent.\n\n"
        "If you change your mind the case is still here."
    ),
}


def render(stage: str, **fields) -> str:
    template = STAGES.get(stage)
    if template is None:
        raise KeyError(f"unknown stage {stage!r}; known: {sorted(STAGES)}")
    return template.format(**fields) + f"\n\n_{BANNER}_"


def configured() -> bool:
    return bool(TOKEN and CHAT_ID)


def send(text: str, chat_id: Optional[str] = None, timeout: float = 15) -> dict:
    """Deliver one update. Never raises.

    A notifier that can throw is a notifier that can stall a claim. The workflow
    calls this from inside a durable step, and a durable step that fails is
    retried — so a Telegram outage would otherwise park the case rather than the
    message.
    """
    if not configured():
        print(f"\n[notify — no C2C_TELEGRAM_TOKEN set, printing instead]\n{text}\n", flush=True)
        return {"delivered": False, "reason": "not configured", "text": text}
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id or CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=timeout,
        )
        if r.status_code == 200:
            return {"delivered": True, "status": 200}
        # Surface Telegram's own reason. Swallowing it turned "chat not found"
        # -- a five-second fix -- into an opaque 400.
        try:
            reason = r.json().get("description", "")
        except Exception:  # noqa: BLE001
            reason = r.text[:200]
        return {"delivered": False, "status": r.status_code, "reason": reason}
    except Exception as exc:  # noqa: BLE001 - a dead notifier must not stall a case
        return {"delivered": False, "reason": repr(exc)[:200]}
