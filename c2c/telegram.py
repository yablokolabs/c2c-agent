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

import json
import os
import time
from pathlib import Path
from typing import Optional

import httpx

from c2c import intake as intake_mod
from c2c.llm import LLM
from c2c.notify import ACTION_LABEL, PROMISE_FOR_ACTION, format_request, keyboard

API = os.environ.get("C2C_API", "http://localhost:8099")
TOKEN = os.environ.get("C2C_TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("C2C_TELEGRAM_CHAT_ID", "")
BANNER = "SYNTHETIC DEMO — NOT FOR SUBMISSION — NOT LEGAL ADVICE"

# The chat -> case mapping outlives the process. Without it, a passenger who
# sends a follow-up after a bot restart is asked from zero again — and their
# evidence can land in a fresh, duplicate case instead of the open one.
OPENED_CASES_FILE = Path(os.environ.get("C2C_OPENED_CASES_FILE", "data/opened_cases.json"))


def _extract_pdf(data: bytes) -> str:
    """Pull the text out of a PDF so it can be treated as evidence.

    Returns the extracted text, or a short explanation if the PDF is a scan
    (image-only) or corrupt — a blank string would look like an empty document
    that happens to be evidence-shaped.
    """
    try:
        from pypdf import PdfReader
        from io import BytesIO
        reader = PdfReader(BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        text = "\n\n".join(p for p in pages if p).strip()
        if text:
            return text
        return "[PDF received but no extractable text — if it is a scan, please " \
               "send the text or a photo of it]"
    except Exception as exc:  # noqa: BLE001 - a bad PDF must not drop the message
        return f"[PDF could not be read: {exc!r}]"


def _load_opened_cases() -> dict[str, str]:
    try:
        if OPENED_CASES_FILE.exists():
            return json.loads(OPENED_CASES_FILE.read_text())
    except Exception:  # noqa: BLE001 - one bad file must not hide the mapping
        pass
    return {}


def _save_opened_cases(opened: dict[str, str]) -> None:
    try:
        OPENED_CASES_FILE.parent.mkdir(parents=True, exist_ok=True)
        OPENED_CASES_FILE.write_text(json.dumps(opened, indent=2))
    except OSError:
        pass


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
        # Chat ids whose case is already open. A message that arrives while the
        # case was being opened, or after, must not land in a fresh intake that
        # interrogates the passenger from zero. Persisted, because a bot restart
        # must not forget which chat owns which case.
        self.opened_cases: dict[str, str] = _load_opened_cases()
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

        Text-shaped attachments are read as-is; PDFs are extracted with pypdf —
        boarding passes, cancellation notices and incident reports arrive as
        PDFs, and storing a placeholder instead of their text would make the
        evidence channel silently useless. Photos would need OCR, which is not
        built — and saying so is better than storing an empty document that
        looks like evidence.
        """
        try:
            meta = self.http.get(f"{self.base}/getFile", params={"file_id": file_id}).json()
            path = meta["result"]["file_path"]
            r = self.http.get(f"https://api.telegram.org/file/bot{self.token}/{path}")
            lower = path.lower()
            if lower.endswith(".pdf"):
                return _extract_pdf(r.content)[:20000]
            if lower.endswith((".txt", ".md", ".csv", ".json", ".eml")):
                return r.text[:20000]
            return f"[attachment {path} received; C2C reads text attachments and PDFs only]"
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

        # The intake assessment takes tens of seconds of model time. A passenger
        # who sees nothing that long assumes the bot is dead and sends more
        # messages. Acknowledge receipt before the model call so the silence is
        # an expected wait, not a failure.
        self.say(chat_id, "Got it — one moment while I look at this.")

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

    def _case_waits_for_evidence(self, case_id: str) -> bool:
        """True when the workflow is durably waiting for the passenger to send
        the documents the agent asked for (AWAITING_EVIDENCE).

        Fails closed: if the control plane cannot be read, the plain
        acknowledgment is sent, so a blip can never turn into a lost message.
        """
        try:
            state = self.http.get(f"{self.api}/c2c/cases/{case_id}").json()
            return state.get("state") == "AWAITING_EVIDENCE"
        except Exception:  # noqa: BLE001
            return False

    def _send_evidence(self, chat_id: str, case_id: str, docs: list[dict]) -> None:
        """Record what the passenger sent in answer to the evidence request.

        `docs` is the whole batch from one poll cycle (all the messages and
        attachments that arrived together), submitted as ONE evidence round.
        Submitting each message separately would race the workflow: the first
        POST resolves the round the workflow waits on and wakes it immediately,
        the re-assessment runs against a case file that is still missing the
        rest of the burst, and the later POSTs land on an already-resolved
        round — stored on the file but never re-assessed, so the case waits
        forever on a round nothing will resolve (FAILURES.md F-026).

        The documents go to the case file first (the re-assessment reads the
        file), then the workflow is told, using the round it is actually
        waiting on — resolving the wrong promise would leave the case waiting
        forever.
        """
        if not docs:
            self.say(chat_id, f"Your case {case_id} is open — a caseworker will be "
                              "in touch if anything else is needed.")
            return
        try:
            state = self.http.get(f"{self.api}/c2c/cases/{case_id}").json()
            round_n = int(state.get("evidence_round") or 0)
            self.http.post(f"{self.api}/c2c/cases/{case_id}/evidence",
                           json={"round": round_n, "documents": docs})
            self.say(chat_id, "Got it — I've added that to your case and I'm "
                              "re-checking it with the new documents.")
        except Exception as exc:  # noqa: BLE001
            print(f"  could not record evidence for {case_id}: {exc!r}")
            self.say(chat_id, f"Your case {case_id} is open — a caseworker will be "
                              "in touch if anything else is needed.")

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
        # All evidence from one poll cycle goes out as a single submission per
        # case. A burst of documents sent together (three PDFs in quick
        # succession) must arrive as one round: submitted separately, the first
        # one wakes the workflow and the rest land on an already-resolved
        # round, so the re-assessment never sees them (F-026).
        pending_evidence: dict[str, tuple[str, list[dict]]] = {}
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

            # Fetch the attachment once, up front. The evidence branch below
            # needs it too — a document the passenger sends in answer to an
            # evidence request IS the evidence — and extracting it after that
            # branch left it unbound there: the first message in a poll batch
            # for an open case crashed with UnboundLocalError and the
            # passenger's documents were dropped (FAILURES.md F-021).
            attachment = None
            doc = msg.get("document") or (msg.get("photo") or [{}])[-1]
            if doc.get("file_id"):
                attachment = (doc.get("file_name", "attachment"),
                              self.fetch_file(doc["file_id"]))

            # A first contact deserves an introduction, not an interrogation.
            if text.strip().lower() in ("/start", "start", "hi", "hello", "hey"):
                self.conversations.pop(chat_id, None)
                self.opened_cases.pop(chat_id, None)
                _save_opened_cases(self.opened_cases)
                intake_mod.remove_incomplete(chat_id)
                self.say(chat_id, GREETING)
                handled.append({"case_id": "-", "event": "greeted"})
                continue

            # A case is already open for this chat (the passenger's account
            # arrived, the case opened, and this message came in while it was
            # being processed or after). The intake conversation was deliberately
            # ended when the case opened; starting a fresh one would interrogate
            # the passenger from zero. If the case is durably waiting for
            # evidence, the message IS the evidence — record it and let the
            # workflow re-assess. Otherwise acknowledge deterministically, no
            # model call, nothing to drift into a first-contact question.
            if chat_id in self.opened_cases:
                case_id = self.opened_cases[chat_id]
                if self._case_waits_for_evidence(case_id):
                    docs = []
                    if text:
                        docs.append({"type": "correspondence", "content": text})
                    if attachment:
                        name, content = attachment
                        docs.append({"type": "correspondence",
                                     "content": f"[{name}]\n{content}"})
                    if docs:
                        _chat, existing = pending_evidence.get(case_id, (chat_id, []))
                        pending_evidence[case_id] = (chat_id, existing + docs)
                    else:
                        # Empty message for a waiting case: still acknowledge
                        # deterministically; nothing was sent to the file.
                        self.say(chat_id, f"Your case {case_id} is open — a caseworker will be "
                                          "in touch if anything else is needed.")
                        handled.append({"case_id": case_id, "event": "acknowledged"})
                        continue
                    handled.append({"case_id": case_id, "event": "evidence recorded"})
                else:
                    self.say(chat_id, f"Your case {case_id} is open — a caseworker will be "
                                      "in touch if anything else is needed.")
                    handled.append({"case_id": case_id, "event": "acknowledged"})
                continue

            out = self.handle_message(chat_id, text, attachment)
            if out["ready"] and out["record"]:
                case_id = self.open_case(out["record"])
                if case_id:
                    # The workflow itself announces the reference and what happens
                    # next, so saying it here too would just say it twice.
                    self.conversations.pop(chat_id, None)
                    self.opened_cases[chat_id] = case_id
                    _save_opened_cases(self.opened_cases)
                    intake_mod.remove_incomplete(chat_id)
                    handled.append({"case_id": case_id, "event": "case opened"})
            else:
                handled.append({"case_id": "-", "event": "intake in progress"})
        # Flush batched evidence: one POST per case, with everything that
        # arrived in this poll cycle, so the whole burst is one round.
        for case_id, (chat_id, docs) in pending_evidence.items():
            self._send_evidence(chat_id, case_id, docs)
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
