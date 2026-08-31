"""Play the airline, for a live case.

The benchmark demo scripts the carrier's reply. A case that arrives over
Telegram has no script — the workflow files the claim and then waits, correctly,
for either a response or fifty-six days. Nothing was there to answer it, so a
chat demo stopped dead after "Filed."

This is the other side of the conversation. Run it from a second terminal while
demonstrating: the passenger sees the refusal arrive, watches the agent read it
against the operational record, and gets asked whether to challenge.

It talks only to C2C's own synthetic airline endpoint. There is no outbound
network and no real carrier anywhere in this path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

API = os.environ.get("C2C_API", "http://localhost:8099")
LIVE = Path("data/cases")

REFUSAL = ("We have completed our assessment of your claim. The disruption arose from "
           "extraordinary circumstances outside our control, and no compensation is "
           "payable under the applicable policy. This is our final response.")


def newest_live_case() -> str | None:
    """The most recently opened live case. During a demo that is the one just
    created, and asking the operator to copy a reference off a phone screen
    mid-take is a good way to fumble it."""
    if not LIVE.exists():
        return None
    files = sorted(LIVE.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return json.loads(files[0].read_text())["case_id"] if files else None


def deliver(case_id: str, payload: dict, promise: str) -> dict:
    r = httpx.post(f"{API}/c2c/cases/{case_id}/carrier-event",
                   json={"promise": promise, "payload": payload}, timeout=60)
    r.raise_for_status()
    return r.json()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Send a carrier response to a live case.")
    ap.add_argument("--case", help="case id; defaults to the most recently opened one")
    ap.add_argument("--settle", type=int, metavar="UNITS",
                    help="offer a settlement of UNITS instead of refusing")
    ap.add_argument("--after-challenge", action="store_true",
                    help="answer the challenge rather than the original claim")
    args = ap.parse_args(argv)

    case_id = args.case or newest_live_case()
    if not case_id:
        print("No live case found. Open one first by messaging the bot.", file=sys.stderr)
        return 2

    if args.settle is not None:
        payload = {"type": "settlement_offer", "amount_units": args.settle,
                   "text": f"Without admission of liability we offer {args.settle} units "
                           f"in full and final settlement."}
        what = f"a settlement offer of {args.settle} units"
    else:
        payload = {"type": "rejection", "text": REFUSAL}
        what = "a refusal citing extraordinary circumstances"

    promise = "challenge_response" if args.after_challenge else "carrier_response"
    result = deliver(case_id, payload, promise)

    print(f"  case      {case_id}")
    print(f"  delivered {what}")
    print(f"  promise   {promise}")
    if result.get("duplicate"):
        print("  NOTE: this event had already been delivered; the workflow absorbed it.")
    else:
        print("  the passenger should hear from C2C within a minute or two")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
