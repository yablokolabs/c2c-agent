"""Telegram approval surface.

The workflow suspends on `ctx.promise("approval")` and does not care what
resolves it. This adapter is one thing that can.

It earns its place on the project's own thesis: the argument is that valid claims
die in multi-week silences because nobody is still holding the case. An approval
request that arrives where the passenger already is, weeks after they last
thought about the claim, is the point. A web form they have to remember to open
is not.

Everything here is a thin translation. It formats a pending action into a
message, and turns a tap back into `POST /c2c/cases/{id}/approve`. It holds no
state and makes no decisions, so if it dies the case is untouched.

Needs `C2C_TELEGRAM_TOKEN` and `C2C_TELEGRAM_CHAT_ID`. Everything else in this
project runs without it, including the whole evaluation.
"""

from __future__ import annotations

import os
import time
from typing import Optional

import httpx

from c2c import intake as intake_mod
from c2c.llm import LLM

API = os.environ.get("C2C_API", "http://localhost:8099")
TOKEN = os.environ.get("C2C_TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("C2C_TELEGRAM_CHAT_ID", "")
BANNER = "SYNTHETIC DEMO — NOT FOR SUBMISSION — NOT LEGAL ADVICE"

PROMISE_FOR_ACTION = {
    "submit_claim": "approval",
    "challenge_rejection": "challenge_approval",
    "escalate": "escalation_approval",
    "accept_settlement": "approval",
    "send_followup": "approval",
}

ACTION_LABEL = {
    "submit_claim": "Submit this claim to the carrier",
    "challenge_rejection": "Challenge the carrier's rejection",
    "escalate": "Escalate to the Synthetic Passenger Rights Body",
    "accept_settlement": "Accept the carrier's settlement offer",
    "send_followup": "Send a follow-up to the carrier",
}


def format_request(case_id: str, state: dict) -> str:
    """The approval message. Everything a person needs to answer without
    opening anything else, and nothing they don't."""
    action = state.get("pending_action", "")
    v = state.get("verdict") or {}
    lines = [
        f"*Case {case_id}* needs your approval",
        "",
        f"*{ACTION_LABEL.get(action, action)}*",
        "",
    ]
    if v.get("compensation_units") is not None:
        lines.append(f"Compensation: *{v['compensation_units']} units*")
    if v.get("duty_of_care_units"):
        lines.append(f"Duty of care: {v['duty_of_care_units']} units")
    if v.get("downgrade_reimbursement_units"):
        lines.append(f"Downgrade: {v['downgrade_reimbursement_units']} units")
    if v.get("cause_class"):
        lines.append(f"Cause: {v['cause_class'].replace('_', ' ')}")
    if v.get("policy_citations"):
        lines.append(f"Under: {', '.join(v['policy_citations'])}")
    if v.get("rationale"):
        lines += ["", v["rationale"]]
    lines += ["", f"_{BANNER}_"]
    return "\n".join(lines)


def keyboard(case_id: str, action: str) -> dict:
    promise = PROMISE_FOR_ACTION.get(action, "approval")
    return {"inline_keyboard": [[
        {"text": "Approve", "callback_data": f"ok|{case_id}|{promise}"},
        {"text": "Reject", "callback_data": f"no|{case_id}|{promise}"},
    ]]}


def parse_callback(data: str) -> Optional[dict]:
    """`ok|R12|approval` -> a decision. Anything else is ignored rather than
    guessed at: a malformed callback must never approve something."""
    parts = (data or "").split("|")
    if len(parts) != 3 or parts[0] not in ("ok", "no"):
        return None
    verdict, case_id, promise = parts
    if not case_id or not promise:
        return None
    return {"case_id": case_id, "approved": verdict == "ok", "promise": promise}


class Telegram:
    def __init__(self, token: str = TOKEN, chat_id: str = CHAT_ID,
                 api: str = API, client: Optional[httpx.Client] = None):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.api = api
        self.token = token
        self.http = client or httpx.Client(timeout=60)
        self.offset = 0
        # Per-chat intake conversations. Deliberately in memory: an in-progress
        # conversation is cheap to restart, and once a case is opened its content
        # is persisted by c2c.intake and its lifecycle by Restate.
        self.conversations: dict[str, intake_mod.Intake] = {}

    def send_approval_request(self, case_id: str, state: dict) -> dict:
        return self.http.post(f"{self.base}/sendMessage", json={
            "chat_id": self.chat_id,
            "text": format_request(case_id, state),
            "parse_mode": "Markdown",
            "reply_markup": keyboard(case_id, state.get("pending_action", "")),
        }).json()

    def deliver(self, decision: dict) -> dict:
        """Resolve the workflow's approval promise. The only thing this adapter
        does that has an effect."""
        return self.http.post(
            f"{self.api}/c2c/cases/{decision['case_id']}/approve",
            json={"approved": decision["approved"], "promise": decision["promise"],
                  "by": "telegram", "reason": "answered from Telegram"},
        ).json()

    # --- intake: a passenger describing what happened ----------------------

    def _conversation(self, chat_id: str) -> intake_mod.Intake:
        return self.conversations.setdefault(chat_id, intake_mod.Intake())

    def fetch_file(self, file_id: str) -> str:
        """Download an attachment and return its text.

        Only text-shaped attachments are read. A photo of a boarding pass would
        need OCR, which is not built — and saying so is better than silently
        storing an empty document that looks like evidence.
        """
        try:
            meta = self.http.get(f"{self.base}/getFile", params={"file_id": file_id}).json()
            path = meta["result"]["file_path"]
            if not path.lower().endswith((".txt", ".md", ".csv", ".json", ".eml")):
                return f"[attachment {path} received; C2C reads text attachments only]"
            r = self.http.get(f"https://api.telegram.org/file/bot{self.token}/{path}")
            return r.text[:20000]
        except Exception as exc:  # noqa: BLE001 - a bad attachment must not drop the message
            return f"[attachment could not be read: {exc!r}]"

    def handle_message(self, chat_id: str, text: str, attachment: Optional[tuple] = None,
                       llm: Optional[LLM] = None) -> dict:
        """Take one passenger message, and reply.

        Returns the intake record once there is enough to open a case. Opening
        the case is the caller's job, not this adapter's — it holds no state that
        matters and makes no decisions.
        """
        conv = self._conversation(chat_id)
        if text:
            conv.messages.append(text)
        if attachment:
            conv.attachments.append(attachment)

        record = intake_mod.understand(conv, llm or LLM())
        if record is None:
            self.say(chat_id, "Sorry — I didn't follow that. Can you tell me the flight, "
                              "the date, and what went wrong?")
            return {"ready": False, "record": None}

        self.say(chat_id, record.get("reply") or "Thanks — I've noted that.")
        return {"ready": bool(record.get("ready")), "record": record}

    def say(self, chat_id: str, text: str) -> dict:
        return self.http.post(f"{self.base}/sendMessage",
                              json={"chat_id": chat_id, "text": text}).json()

    def open_case(self, record: dict) -> Optional[str]:
        """Persist the case, then start its durable workflow. In that order: a
        case that exists only in a running process is exactly what this project
        argues against."""
        try:
            created = self.http.post(f"{self.api}/c2c/cases/from-intake",
                                     json={"record": record}).json()
            case_id = created["case_id"]
            self.http.post(f"{self.api}/c2c/cases/{case_id}/open",
                           json={"opened_by": "telegram"})
            return case_id
        except Exception as exc:  # noqa: BLE001
            print(f"  could not open case: {exc!r}")
            return None

    def poll_once(self) -> list[dict]:
        r = self.http.get(f"{self.base}/getUpdates",
                          params={"offset": self.offset, "timeout": 25}).json()
        handled = []
        for update in r.get("result", []):
            self.offset = update["update_id"] + 1

            cb = update.get("callback_query")
            if cb:
                decision = parse_callback(cb.get("data", ""))
                if decision is None:
                    continue
                result = self.deliver(decision)
                handled.append({**decision, "event": "approval", "result": result})
                self.http.post(f"{self.base}/answerCallbackQuery", json={
                    "callback_query_id": cb["id"],
                    "text": "Approved" if decision["approved"] else "Rejected",
                })
                continue

            msg = update.get("message")
            if not msg:
                continue
            chat_id = str(msg.get("chat", {}).get("id", ""))
            text = msg.get("text") or msg.get("caption") or ""
            attachment = None
            doc = msg.get("document") or (msg.get("photo") or [{}])[-1]
            if doc.get("file_id"):
                attachment = (doc.get("file_name", "attachment"),
                              self.fetch_file(doc["file_id"]))

            out = self.handle_message(chat_id, text, attachment)
            if out["ready"] and out["record"]:
                case_id = self.open_case(out["record"])
                if case_id:
                    self.say(chat_id, f"I've opened case {case_id} and started work on it. "
                                      f"I'll message you at every step, and I won't send "
                                      f"anything to the airline without asking you first.")
                    handled.append({"case_id": case_id, "event": "case opened"})
            else:
                handled.append({"case_id": "-", "event": "intake in progress"})
        return handled


def main() -> int:
    from c2c import notify

    notify._load_dotenv()
    token = os.environ.get("C2C_TELEGRAM_TOKEN", "")
    chat = os.environ.get("C2C_TELEGRAM_CHAT_ID", "")
    if not token:
        print("C2C_TELEGRAM_TOKEN is not set. Put it in .env:\n"
              "  C2C_TELEGRAM_TOKEN=...\n  C2C_TELEGRAM_CHAT_ID=...\n\n"
              "Everything also works over HTTP without it:\n"
              "  curl -X POST localhost:8099/c2c/cases/R12/approve "
              "-H 'content-type: application/json' -d '{\"approved\":true}'")
        return 2

    tg = Telegram(token=token, chat_id=chat)
    print(f"C2C is listening on Telegram. Control plane: {tg.api}")
    print("A passenger can now describe a disruption and attach documents.\n")
    while True:
        try:
            for h in tg.poll_once():
                print(f"  {h.get('case_id', '?')}: {h.get('event', 'handled')}")
        except Exception as exc:  # noqa: BLE001 - a dead adapter must not kill a case
            print(f"  poll failed, retrying: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
