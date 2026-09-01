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


GREETING = """Hi — I'm C2C.

If a flight was cancelled, badly delayed, overbooked or downgraded, I'll work out
whether you're owed compensation, and then chase it for you.

The chasing is the part that matters. Airlines take weeks to reply, often refuse
on grounds their own records contradict, and most valid claims die because nobody
kept going. I don't get tired of a case.

To start, just tell me what happened. Helpful if you can include:

  • the flight number and date
  • where you were flying from and to
  • your booking reference
  • what went wrong, and what the airline told you

Anything you don't have, I'll ask about — I won't guess. You can attach documents
as text files too.

I never send anything to an airline without asking you first.

_SYNTHETIC DEMO — NOT FOR SUBMISSION — NOT LEGAL ADVICE_"""


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
                 api: str = API, client: Optional[httpx.Client] = None,
                 recorder=None):
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
        self.recorder = recorder

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
        # Load any persisted incomplete intake first. The in-memory dict is
        # still the fast path and the source of truth while the worker is up,
        # but a restart must not make a passenger start from zero.
        existing = self.conversations.get(chat_id)
        if existing is not None and existing.messages:
            return existing
        persisted = intake_mod.load_incomplete(chat_id)
        if persisted:
            messages = list(persisted.get("messages") or [])
            attachments = [(name, text) for name, text in persisted.get("attachments") or []]
            # Files written before the conversation itself was persisted only
            # carried the model record; fall back to its narrative so nothing
            # the passenger already said is lost.
            if not messages and (persisted.get("record") or {}).get("narrative"):
                messages = [persisted["record"]["narrative"]]
            if messages:
                conv = intake_mod.Intake(messages=messages, attachments=attachments)
                self.conversations[chat_id] = conv
                return conv
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

        record = intake_mod.understand(conv, llm or LLM(), rec=self.recorder)
        if record is None:
            self.say(chat_id, "Sorry — I didn't follow that. Can you tell me the flight, "
                              "the date, and what went wrong?")
            return {"ready": False, "record": None}

        # Persist the in-progress intake before we reply. This is what survives
        # a worker restart: the case itself is not opened yet, and the passenger
        # should not be asked from zero because the process that received their
        # first message went away. If persistence fails, the in-memory
        # conversation still works while the worker is up.
        intake_mod.save_incomplete(chat_id, record, conv.messages, conv.attachments)

        reply = record.get("reply") or self._fallback_reply(record)
        self.say(chat_id, reply)
        return {"ready": self._ready(record), "record": record}

    @staticmethod
    def _ready(record: dict) -> bool:
        """A ready intake record must not still be asking the passenger things.

        Opening a case drops the intake conversation, so if the model claims
        ready while its reply asks a question, the passenger's answer would land
        in a fresh intake and they would be asked from zero. Treat that as not
        ready: keep the conversation going until the model asks nothing more.
        """
        if not record.get("ready"):
            return False
        return "?" not in (record.get("reply") or "")

    def _fallback_reply(self, record: dict) -> str:
        """A passenger should never get a blank acknowledgment when the model
        returned a usable intake record but left `reply` empty.

        Keep it state-aware: if the case is ready, say so. If not, tell the
        passenger what is still missing rather than restarting from zero.
        """
        content = record or {}
        if content.get("ready"):
            facts = content.get("facts") or {}
            pieces = [p for p in (facts.get("carrier"), facts.get("flight_number"),
                                  facts.get("route"), facts.get("disruption_date"))
                      if p]
            if pieces:
                return "Got it — I have enough to start your case."
            return "Thanks — I've noted that."
        missing = content.get("missing") or []
        if missing:
            return ("Thanks — I've noted what you've told me. "
                    "I still need: " + "; ".join(missing) + ".")
        return "Thanks — I've noted that."

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

            # A first contact deserves an introduction, not an interrogation.
            if text.strip().lower() in ("/start", "start", "hi", "hello", "hey"):
                self.conversations.pop(chat_id, None)
                intake_mod.remove_incomplete(chat_id)
                self.say(chat_id, GREETING)
                handled.append({"case_id": "-", "event": "greeted"})
                continue
            attachment = None
            doc = msg.get("document") or (msg.get("photo") or [{}])[-1]
            if doc.get("file_id"):
                attachment = (doc.get("file_name", "attachment"),
                              self.fetch_file(doc["file_id"]))

            out = self.handle_message(chat_id, text, attachment)
            if out["ready"] and out["record"]:
                case_id = self.open_case(out["record"])
                if case_id:
                    # The workflow itself announces the reference and what happens
                    # next, so saying it here too would just say it twice.
                    self.conversations.pop(chat_id, None)
                    intake_mod.remove_incomplete(chat_id)
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

    from c2c.trajectory import Recorder

    tg = Telegram(token=token, chat_id=chat, recorder=Recorder.open("intake"))
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
