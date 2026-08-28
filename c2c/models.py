"""Shared schema for cases, verdicts and ground truth.

One verdict shape is used by the baseline, the caseworker, the verifier and the
grader, so all four are directly comparable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

CauseClass = Literal["carrier_controlled", "extraordinary", "unknown"]

NextAction = Literal[
    "submit_claim",
    "request_evidence",
    "challenge_rejection",
    "escalate",
    "accept_settlement",
    "await_carrier",
    "close_no_claim",
]

CONSEQUENTIAL_ACTIONS: frozenset[str] = frozenset(
    {"submit_claim", "send_followup", "challenge_rejection", "escalate", "accept_settlement"}
)


class Document(BaseModel):
    doc_id: str
    type: str
    content: str


class CarrierResponse(BaseModel):
    type: str
    received: str
    text: str


class GroundTruth(BaseModel):
    in_scope: bool
    qualifies: Optional[bool]
    cause_class: CauseClass
    eligible: Optional[bool]
    compensation_units: Optional[int]
    duty_of_care_units: int
    downgrade_reimbursement_units: int
    evidence_sufficient: bool
    missing_evidence: list[str]
    next_action: NextAction
    derivation: list[str]


class Case(BaseModel):
    case_id: str
    title: str
    difficulty: Literal["easy", "medium", "hard"]
    tags: list[str]
    passenger: dict
    narrative: str
    documents: list[Document]
    carrier_response: Optional[CarrierResponse] = None
    ground_truth: GroundTruth

    def dossier(self) -> str:
        """The case as the agent or baseline sees it. Ground truth is excluded."""
        parts = [
            f"CASE {self.case_id}",
            f"Passenger: {self.passenger['name']}  (booking {self.passenger['pnr']})",
            "",
            "WHAT THE PASSENGER SAYS",
            self.narrative,
            "",
            "DOCUMENTS ON FILE",
        ]
        for d in self.documents:
            parts += [f"--- {d.doc_id} [{d.type}] ---", d.content, ""]
        if self.carrier_response:
            parts += [
                f"CARRIER RESPONSE ({self.carrier_response.type}, received "
                f"{self.carrier_response.received})",
                self.carrier_response.text,
                "",
            ]
        else:
            parts += ["CARRIER RESPONSE", "None on file.", ""]
        return "\n".join(parts)


class Verdict(BaseModel):
    """What the baseline or the agent concluded about a case."""

    in_scope: bool
    qualifies: Optional[bool] = None
    cause_class: CauseClass = "unknown"
    eligible: Optional[bool] = None
    compensation_units: Optional[int] = None
    duty_of_care_units: int = 0
    downgrade_reimbursement_units: int = 0
    evidence_sufficient: bool
    missing_evidence: list[str] = Field(default_factory=list)
    next_action: NextAction
    policy_citations: list[str] = Field(default_factory=list)
    rationale: str = ""


def load_cases(directory: str | Path = "benchmark/cases") -> list[Case]:
    paths = sorted(Path(directory).glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"no benchmark cases under {directory}")
    return [Case.model_validate(json.loads(p.read_text())) for p in paths]
