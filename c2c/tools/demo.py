"""Walk one case through the full durable lifecycle.

Defaults to R18: an airline blaming a bird strike for a cancellation forty hours
later, while holding two spare aircraft it never used. It exercises everything —
assessment, human approval, submission, a carrier response arriving days later, a
challenge, and a second approval — and the reasoning is the most interesting in
the benchmark, because the airline's excuse was genuine and had *expired*.

Set `C2C_DEMO_CASE` to run a different one. Restate keeps a workflow id for a
retention period, so a second run on the same day needs a different case.

Every artifact is stamped SYNTHETIC DEMO. Nothing leaves this machine.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx

from c2c.telegram import format_request, keyboard

API = os.environ.get("C2C_API", "http://localhost:8099")
CASE = os.environ.get("C2C_DEMO_CASE", "R18")
BANNER = "SYNTHETIC DEMO — NOT FOR SUBMISSION — NOT LEGAL ADVICE"

# The carrier's reply, arriving days later. Written per case so the airline and
# the flight match the file the agent just read — a rejection quoting the wrong
# flight number is the sort of thing that is invisible in a test and obvious on
# a screen.
SCRIPTED_REJECTIONS = {
    "R18": ("Indigo North has assessed your claim. IN300 on 23 June was cancelled as a "
            "consequence of a bird strike, an extraordinary circumstance outside our "
            "control. No compensation is payable. This is our final response."),
    "R12": ("Halcyon has assessed your claim. HB640 was cancelled owing to extraordinary "
            "circumstances, namely adverse weather beyond our control. No compensation is "
            "payable. This is our final response."),
    "R16": ("Orion Reach has reimbursed your expenses in full. Compensation is not payable, "
            "as OR480 was cancelled due to adverse weather constituting an extraordinary "
            "circumstance."),
}
DEFAULT_REJECTION = ("We have assessed your claim. The disruption arose from extraordinary "
                     "circumstances outside our control and no compensation is payable. "
                     "This is our final response.")


def scripted_rejection() -> dict:
    return {"type": "rejection", "text": SCRIPTED_REJECTIONS.get(CASE, DEFAULT_REJECTION)}


def rule(title: str = "") -> None:
    print(f"\n{'─' * 74}")
    if title:
        print(f"  {title}")
        print("─" * 74)


def show_status(c: httpx.Client) -> dict:
    st = c.get(f"{API}/c2c/cases/{CASE}").json()
    print(f"  state           {st.get('state', '(not started)')}")
    if st.get("pending_action"):
        print(f"  pending action  {st['pending_action']}  <- waiting on a human")
    if st.get("claim_id"):
        print(f"  claim           {st['claim_id']}")
    if st.get("escalation_reference"):
        print(f"  escalation      {st['escalation_reference']}")
    return st


def wait_for(c: httpx.Client, wanted: set[str], timeout: float = 900,
             label: str = "") -> tuple[str, bool]:
    """Wait for one of `wanted`. Returns (state, reached).

    Returning whether it was actually reached matters: an assessment takes
    several minutes, and a version of this that returned only the last-seen state
    reported a still-running case as "the case ended at INTAKE". A demo that
    misreports what happened is worse than one that fails.
    """
    started = time.monotonic()
    last = ""
    while time.monotonic() - started < timeout:
        last = c.get(f"{API}/c2c/cases/{CASE}").json().get("state", "")
        if last in wanted:
            return last, True
        if label:
            print(f"    {label}: {last or 'starting'} … {int(time.monotonic()-started)}s",
                  end="\r", flush=True)
        time.sleep(3)
    return last, False


def show_approval_request(st: dict) -> None:
    """Render the approval exactly as it reaches the passenger.

    The workflow suspends on a durable promise and does not care what resolves
    it. This is what a person actually sees — the amount, the reasoning, the
    clauses, and two buttons — rather than the HTTP call underneath.

    Rendered, not sent: no bot token is needed to run the demo, and nothing
    leaves this machine.
    """
    import textwrap

    print()
    print("  ┌─ what reaches the passenger " + "─" * 42 + "┐")
    for line in format_request(CASE, st).splitlines():
        # Wrap rather than truncate. The rationale is the part a person reads to
        # decide, and a clipped sentence is worse than no sentence.
        for out in (textwrap.wrap(line, 70) or [""]):
            print(f"  │ {out}")
    buttons = [b["text"] for b in keyboard(CASE, st.get("pending_action", ""))["inline_keyboard"][0]]
    print("  │")
    print("  │   " + "   ".join(f"[ {b} ]" for b in buttons))
    print("  └" + "─" * 71 + "┘")
    print("  (rendered as Telegram would show it; set C2C_TELEGRAM_TOKEN to send it)")


def approve(c: httpx.Client, promise: str = "approval", approved: bool = True) -> dict:
    return c.post(f"{API}/c2c/cases/{CASE}/approve",
                  json={"approved": approved, "promise": promise, "by": "demo operator",
                        "reason": "reviewed and approved for the demo"}).json()


def audit(c: httpx.Client) -> dict:
    return c.get(f"{API}/airline/_admin/audit").json()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="C2C demo")
    ap.add_argument("--approve", action="store_true", help="approve the pending action and exit")
    ap.add_argument("--advance", action="store_true", help="deliver the carrier response and exit")
    args = ap.parse_args(argv)

    with httpx.Client(timeout=600) as c:
        try:
            c.get(f"{API}/c2c/health").raise_for_status()
        except Exception:  # noqa: BLE001
            print(f"No control plane at {API}. Run: make up", file=sys.stderr)
            return 2

        if args.approve:
            st = c.get(f"{API}/c2c/cases/{CASE}").json()
            promise = {"submit_claim": "approval", "challenge_rejection": "challenge_approval",
                       "escalate": "escalation_approval"}.get(st.get("pending_action"), "approval")
            print(json.dumps(approve(c, promise), indent=2))
            return 0

        if args.advance:
            print(json.dumps(
                c.post(f"{API}/c2c/cases/{CASE}/carrier-event",
                       json={"promise": "carrier_response", "payload": scripted_rejection()}).json(),
                indent=2))
            return 0

        print(f"\n  C2C demo — case {CASE}")
        print(f"  {BANNER}")

        rule("1. Reset the synthetic world")
        print(" ", c.post(f"{API}/airline/_admin/reset").json())

        rule("2. Open the case")
        print("  The workflow starts, and the agent assesses. This takes a minute or two:")
        print("  the caseworker reads documents and looks up clauses, then an independent")
        print("  verifier checks the result.")
        c.post(f"{API}/c2c/cases/{CASE}/open", json={"opened_by": "demo"})
        state, reached = wait_for(c, {"AWAITING_APPROVAL", "CLOSED_NO_ACTION"},
                                  timeout=1200, label="assessing")
        print(" " * 60, end="\r")
        if not reached:
            print(f"\n  Still assessing after 20 minutes (state: {state or 'unknown'}).")
            print("  The workflow is durable and is still running — nothing is lost. Re-run")
            print("  this script to pick it up, or watch: "
                  f"curl {API}/c2c/cases/{CASE}")
            return 1

        rule("3. The agent has decided, and stopped")
        st = show_status(c)
        v = st.get("verdict") or {}
        print(f"\n  compensation    {v.get('compensation_units')} units")
        print(f"  duty of care    {v.get('duty_of_care_units')} units")
        print(f"  cause           {v.get('cause_class')}")
        print(f"  citations       {', '.join(v.get('policy_citations') or [])}")
        print(f"\n  rationale: {v.get('rationale', '')}")
        if state != "AWAITING_APPROVAL":
            print(f"\n  Nothing consequential to approve; the case ended at {state}.")
            return 0
        print("\n  Nothing has been sent. The workflow is suspended on a durable promise,")
        print("  consuming nothing, and will stay there for as long as it takes.")
        show_approval_request(st)

        rule("4. A human approves")
        print(" ", approve(c, "approval"))
        wait_for(c, {"AWAITING_CARRIER", "SUBMITTED"}, label="submitting")
        show_status(c)

        rule("5. Weeks pass, then the carrier rejects")
        print("  Delivered here as an external event. In production this is the 4-to-8 week")
        print("  silence where most valid claims quietly die.")
        c.post(f"{API}/c2c/cases/{CASE}/carrier-event",
               json={"promise": "carrier_response", "payload": scripted_rejection()})
        wait_for(c, {"AWAITING_APPROVAL"}, label="re-assessing")
        print(" " * 60, end="\r")
        st = show_status(c)
        print(f"\n  The rejection cites weather. The operational record on file says the crew")
        print(f"  timed out and both stations were CAVOK. The agent proposes a challenge.")
        show_approval_request(st)

        rule("6. A human approves the challenge")
        print(" ", approve(c, "challenge_approval"))
        wait_for(c, {"CHALLENGED"}, label="challenging")
        show_status(c)

        rule("7. What the passenger actually receives")
        doc = c.get(f"{API}/c2c/cases/{CASE}/document", params={"kind": "summary"}).text
        print("\n".join("  " + l for l in doc.splitlines()[:26]))
        print(f"\n  Full letter: {API}/c2c/cases/{CASE}/document?kind=letter")

        rule("8. What actually reached the carrier")
        a = audit(c)
        for e in a["effective"]:
            print(f"  {e['seq']:>3}  {e['action']:<20} {e['case_id']:<8} key={e['idempotency_key'][:8]}…")
        print(f"\n  {len(a['entries'])} action(s) attempted, {len(a['effective'])} landed.")
        print(f"  Duplicates absorbed: {len(a['entries']) - len(a['effective'])}")

        rule()
        print("  The case is now waiting on the carrier again, with a durable 28-day clock")
        print("  running. If the carrier stays silent, the workflow wakes itself and proposes")
        print("  escalation. Nobody has to remember to check.")
        print(f"\n  {BANNER}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
