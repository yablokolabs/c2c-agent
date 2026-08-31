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
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from c2c import prompts
from c2c.llm import LLM, extract_json
from c2c.models import Case, Document

LIVE_CASES = Path("data/cases")

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
        parts += [f"- {m}" for m in self.messages] or ["- (nothing yet)"]
        parts += ["", "## WHAT THEY ATTACHED", ""]
        if not self.attachments:
            parts.append("(nothing attached)")
        for name, text in self.attachments:
            parts += [f"--- {name} ---", text[:4000], ""]
        return "\n".join(parts)


def system_prompt() -> str:
    return prompts.load("intake")


def understand(intake: Intake, llm: LLM) -> Optional[dict]:
    """Read the conversation. Returns the structured record, or None if the
    model produced nothing usable — which is a real failure, not something to
    paper over with a default."""
    result = llm.complete(system_prompt(), intake.as_prompt())
    raw = extract_json(result.text)
    if raw is None or "narrative" not in raw:
        return None
    return raw


def to_case(record: dict, case_id: Optional[str] = None) -> Case:
    """Build a Case from an intake record.

    No ground truth: this case came from a person, and inventing an expected
    answer for it would corrupt the one thing the benchmark guarantees.
    """
    case_id = case_id or f"LIVE-{uuid.uuid4().hex[:6].upper()}"
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
