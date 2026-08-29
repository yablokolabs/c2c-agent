"""Structured trajectory recording.

Canonical format is one JSONL file per run at
`trajectories/runs/<run-id>/events.jsonl`, with a judge-readable Markdown
rendering alongside it.

Private chain-of-thought is deliberately not captured. What is captured is the
material a reviewer needs to audit a decision: the instructions the agent was
given, the tools it called, what came back, the rationale it stated, the
verifier's decisions, retries, workflow transitions, human checkpoints and the
outcome.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

EVENT_TYPES = frozenset({
    "USER_INPUT", "AGENT_START", "MODEL_REQUEST", "MODEL_RESPONSE",
    "TOOL_CALL", "TOOL_RESULT", "VERIFIER_REQUEST", "VERIFIER_PASS",
    "VERIFIER_REJECT", "WORKFLOW_TRANSITION", "WORKFLOW_SUSPEND",
    "WORKFLOW_RESUME", "EXTERNAL_EVENT", "RETRY", "ERROR",
    "HUMAN_APPROVAL_REQUIRED", "HUMAN_APPROVED", "HUMAN_REJECTED",
    "FINAL_DECISION",
})


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        ).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def new_run_id(stage: str) -> str:
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{stage}-{uuid.uuid4().hex[:6]}"


@dataclass
class Recorder:
    run_id: str
    root: Path
    git_sha: str

    @classmethod
    def open(cls, stage: str, root: str | Path = "trajectories/runs") -> "Recorder":
        run_id = new_run_id(stage)
        d = Path(root) / run_id
        d.mkdir(parents=True, exist_ok=True)
        return cls(run_id=run_id, root=d, git_sha=git_sha())

    @property
    def events_path(self) -> Path:
        return self.root / "events.jsonl"

    def emit(
        self,
        event_type: str,
        *,
        case_id: Optional[str] = None,
        agent: Optional[str] = None,
        workflow_state: Optional[str] = None,
        tool: Optional[str] = None,
        input: Any = None,
        output: Any = None,
        duration_ms: Optional[int] = None,
        success: Optional[bool] = None,
        **extra: Any,
    ) -> None:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {event_type!r}")
        rec = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "case_id": case_id,
            "agent": agent,
            "event_type": event_type,
            "workflow_state": workflow_state,
            "tool": tool,
            "input": _trim(input),
            "output": _trim(output),
            "duration_ms": duration_ms,
            "success": success,
            "git_sha": self.git_sha,
        }
        rec.update(extra)
        with self.events_path.open("a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def read(self) -> list[dict]:
        if not self.events_path.exists():
            return []
        return [json.loads(line) for line in self.events_path.read_text().splitlines() if line]

    def render_markdown(self, title: str = "") -> Path:
        out = self.root / "trajectory.md"
        out.write_text(render_markdown(self.read(), title or self.run_id))
        return out


MAX_FIELD_CHARS = 12000


def _trim(v: Any) -> Any:
    if isinstance(v, str) and len(v) > MAX_FIELD_CHARS:
        return v[:MAX_FIELD_CHARS] + f"\n...[trimmed, {len(v)} chars total]"
    return v


_ICONS = {
    "USER_INPUT": "person", "AGENT_START": "start", "MODEL_REQUEST": "model in",
    "MODEL_RESPONSE": "model out", "TOOL_CALL": "tool", "TOOL_RESULT": "tool result",
    "VERIFIER_REQUEST": "verify", "VERIFIER_PASS": "verify pass",
    "VERIFIER_REJECT": "verify REJECT", "WORKFLOW_TRANSITION": "workflow",
    "WORKFLOW_SUSPEND": "suspend", "WORKFLOW_RESUME": "resume",
    "EXTERNAL_EVENT": "external", "RETRY": "retry", "ERROR": "ERROR",
    "HUMAN_APPROVAL_REQUIRED": "awaiting human", "HUMAN_APPROVED": "human approved",
    "HUMAN_REJECTED": "human REJECTED", "FINAL_DECISION": "final",
}


def render_markdown(events: list[dict], title: str) -> str:
    lines = [f"# Trajectory — {title}", ""]
    if events:
        lines += [
            f"- Run: `{events[0].get('run_id')}`",
            f"- Commit: `{events[0].get('git_sha')}`",
            f"- Events: {len(events)}",
            f"- Span: {events[0]['timestamp']} to {events[-1]['timestamp']}",
            "",
        ]
    current_case = object()
    for e in events:
        if e.get("case_id") != current_case:
            current_case = e.get("case_id")
            lines += ["", f"## Case {current_case or '(no case)'}", ""]
        label = _ICONS.get(e["event_type"], e["event_type"])
        head = f"**{label}**"
        if e.get("agent"):
            head += f" · `{e['agent']}`"
        if e.get("tool"):
            head += f" · tool `{e['tool']}`"
        if e.get("workflow_state"):
            head += f" · state `{e['workflow_state']}`"
        if e.get("duration_ms") is not None:
            head += f" · {e['duration_ms']} ms"
        if e.get("success") is False:
            head += " · FAILED"
        lines.append(f"### {head}")
        lines.append(f"<sub>{e['timestamp']}</sub>")
        for key in ("input", "output"):
            val = e.get(key)
            if val in (None, "", [], {}):
                continue
            body = val if isinstance(val, str) else json.dumps(val, indent=2, ensure_ascii=False)
            lines += ["", f"*{_label(e, key)}*", "", _fence(body), body, _fence(body)]
        lines.append("")
    return "\n".join(lines)


def _label(event: dict, key: str) -> str:
    """A TOOL_CALL records the model's stated reason in `output`, which reads
    wrongly as a result. Name it for what it is."""
    if event["event_type"] == "TOOL_CALL":
        return {"input": "arguments", "output": "why the agent called it"}[key]
    return key


def _fence(body: str) -> str:
    """Model output routinely contains its own fenced blocks. Pick a longer
    fence so the nesting renders instead of breaking out."""
    longest = 0
    run = 0
    for ch in body:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    return "`" * max(3, longest + 1)
