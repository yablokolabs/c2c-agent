"""Turning a conversation into a case file.

The benchmark's cases arrive pre-built. A real one arrives as a passenger typing
"my flight to Paris got cancelled and I've been ignored for a month", with a
photo of a boarding pass attached.

This is the only part of C2C that talks to a passenger in prose, and it is
deliberately the dumbest agent in the system: it organises, it does not assess.
It never mentions the policy, never estimates an amount, and never invents a
detail the passenger did not give — a case file with a plausible invented flight
number is worse than one with an obvious hole, because the hole gets asked about
and the invention does not.
"""

from __future__ import annotations

import json
import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from c2c import prompts
from c2c.llm import LLM, extract_json
from c2c.models import Case, Document

LIVE_CASES = Path("data/cases")
INCOMPLETE_INTAKE = Path("data/intake")

DOC_TYPES = {
    "booking_confirmation", "boarding_pass", "carrier_notification",
    "operational_record", "arrival_record", "receipts", "denied_boarding_notice",
    "correspondence", "claim_record", "passenger_statement",
}


@dataclass
class Intake:
    """What the passenger has given us so far."""

    messages: list[str] = field(default_factory=list)
    attachments: list[tuple[str, str]] = field(default_factory=list)  # (filename, text)

    def as_prompt(self) -> str:
        parts = ["## WHAT THE PASSENGER WROTE", ""]
        parts += ["This is the whole conversation so far, including earlier messages. "
                  "Keep everything the passenger has already told you, and do not ask "
                  "for it again.", ""]
        parts += [f"- {m}" for m in self.messages] or ["- (nothing yet)"]
        parts += ["", "## WHAT THEY ATTACHED", ""]
        if not self.attachments:
            parts.append("(nothing attached)")
        for name, text in self.attachments:
            parts += [f"--- {name} ---", text[:4000], ""]
        return "\n".join(parts)


def system_prompt() -> str:
    return prompts.load("intake")


def understand(intake: Intake, llm: LLM, rec=None) -> Optional[dict]:
    """Read the conversation. Returns the structured record, or None if the
    model produced nothing usable — which is a real failure, not something to
    paper over with a default.

    Records a trajectory like the other agents. It is the only one that sees a
    passenger's own words, which makes it the one most worth being able to audit
    afterwards.
    """
    if rec:
        rec.emit("AGENT_START", agent="intake",
                 input={"messages": len(intake.messages),
                        "attachments": [n for n, _ in intake.attachments]})
        rec.emit("USER_INPUT", agent="intake", input=intake.as_prompt())

    result = llm.complete(system_prompt(), intake.as_prompt())
    if rec:
        rec.emit("MODEL_RESPONSE", agent="intake", output=result.text,
                 duration_ms=result.duration_ms, usage=result.usage())

    raw = extract_json(result.text)
    if raw is None or "narrative" not in raw:
        if rec:
            rec.emit("ERROR", agent="intake", success=False,
                     output="no usable intake record in the reply")
        return None
    if rec:
        rec.emit("FINAL_DECISION", agent="intake",
                 output={"ready": raw.get("ready"), "missing": raw.get("missing"),
                         "pnr": raw.get("pnr")})
    return raw


def new_reference() -> str:
    """A case reference a passenger can quote back.

    Year plus five unambiguous characters — no O/0 or I/1, because this gets
    read off a phone screen and typed into an email weeks later.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    tail = "".join(random.choice(alphabet) for _ in range(5))
    return f"C2C-{datetime.now(timezone.utc):%Y}-{tail}"


def to_case(record: dict, case_id: Optional[str] = None) -> Case:
    """Build a Case from an intake record.

    No ground truth: this case came from a person, and inventing an expected
    answer for it would corrupt the one thing the benchmark guarantees.
    """
    case_id = case_id or new_reference()
    docs: list[Document] = []
    for i, d in enumerate(record.get("documents") or [], start=1):
        if not isinstance(d, dict) or not d.get("content"):
            continue
        dtype = d.get("type", "passenger_statement")
        docs.append(Document(
            doc_id=d.get("doc_id") or f"D{i}",
            type=dtype if dtype in DOC_TYPES else "passenger_statement",
            content=str(d["content"]),
        ))
    if not docs:
        docs.append(Document(doc_id="D1", type="passenger_statement",
                             content=record.get("narrative", "")))
    return Case(
        case_id=case_id,
        title=(record.get("facts") or {}).get("what_happened", "live case").replace("_", " "),
        difficulty="medium",
        tags=["live", "intake"],
        passenger={"name": record.get("passenger_name") or "Unknown",
                   "pnr": record.get("pnr") or "UNKNOWN"},
        narrative=record.get("narrative", ""),
        documents=docs,
        ground_truth=None,
    )


def save_incomplete(chat_id: str, record: dict, messages: Optional[list[str]] = None,
                    attachments: Optional[list[tuple[str, str]]] = None,
                    directory: Optional[Path] = None) -> Optional[Path]:
    """Persist an in-progress intake conversation before the case is opened.

    The live conversation is the part that dies first when the worker restarts.
    This keeps it durable enough that a passenger does not get asked from zero
    just because the process that received their first message is gone. The
    conversation itself (messages and attachments) is what must survive, with
    the model's record kept alongside for the next turn.

    Returns the path written, or None if intake cannot be made durable in this
    runtime. A missing persistent intake is not a case failure: the in-memory
    conversation still works while the worker is up.
    """
    if directory is None:
        directory = INCOMPLETE_INTAKE
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    path = directory / f"{chat_id}.json"
    payload = {
        "messages": list(messages or []),
        "attachments": list(attachments or []),
        "record": record,
    }
    try:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    except OSError:
        return None
    return path


def load_incomplete(chat_id: str, directory: Optional[Path] = None) -> Optional[dict]:
    """Reload a persisted incomplete conversation for a chat.

    Returns None when there is nothing usable on disk. Callers default to the
    standard intake directory, matching save_incomplete.
    """
    if directory is None:
        directory = INCOMPLETE_INTAKE
    path = directory / f"{chat_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001 - one bad file must not hide the rest
        return None


def remove_incomplete(chat_id: str, directory: Optional[Path] = None) -> None:
    """Forget a persisted incomplete conversation once a case has been opened.

    The passenger's account now lives in the case file, and leaving the intake
    file behind would resurrect an already-opened conversation on the next
    restart — and a ready record could open a duplicate case.
    """
    if directory is None:
        directory = INCOMPLETE_INTAKE
    try:
        (directory / f"{chat_id}.json").unlink(missing_ok=True)
    except OSError:
        pass


def save(case: Case, directory: Path = LIVE_CASES) -> Path:
    """Persist a live case. The control plane is restartable and holds no state;
    a case that arrived from a passenger has to outlive the process that
    received it."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{case.case_id}.json"
    path.write_text(json.dumps(case.model_dump(), indent=2, ensure_ascii=False) + "\n")
    return path


def load_live(directory: Path = LIVE_CASES) -> dict[str, Case]:
    if not directory.exists():
        return {}
    out = {}
    for p in sorted(directory.glob("*.json")):
        try:
            c = Case.model_validate(json.loads(p.read_text()))
            out[c.case_id] = c
        except Exception:  # noqa: BLE001 - one bad file must not hide the rest
            continue
    return out
