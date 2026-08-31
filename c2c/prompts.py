"""Prompt loading with provenance.

Every prompt that affects a result is a file in the repository, and every
evaluation output records the digest of the prompts that produced it, so a
result can always be tied back to the exact instructions behind it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

POLICY_PATH = ROOT / "benchmark" / "POLICY.md"

PROMPTS = {
    "baseline_v1": ROOT / "prompts" / "baseline_v1.md",
    "baseline_v2": ROOT / "prompts" / "baseline_v2.md",
    "caseworker": ROOT / "agents" / "caseworker" / "SYSTEM_PROMPT.md",
    "caseworker_direct": ROOT / "prompts" / "caseworker_direct.md",
    "verifier": ROOT / "agents" / "verifier" / "SYSTEM_PROMPT.md",
    "intake": ROOT / "agents" / "intake" / "SYSTEM_PROMPT.md",
}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def load(name: str) -> str:
    path = PROMPTS.get(name)
    if path is None:
        raise KeyError(f"unknown prompt {name!r}; known: {sorted(PROMPTS)}")
    if not path.exists():
        raise FileNotFoundError(f"prompt {name!r} expected at {path}")
    text = path.read_text()
    # Everything above the first horizontal rule is commentary for humans about
    # why the prompt is written the way it is, and is not sent to the model.
    marker = "\n---\n"
    return text.split(marker, 1)[1].strip() if marker in text else text.strip()


def policy() -> str:
    return POLICY_PATH.read_text()


def provenance() -> dict:
    """Digests of everything that shapes a result, for the results file."""
    out = {"policy": digest(policy())}
    for name, path in PROMPTS.items():
        out[name] = digest(path.read_text()) if path.exists() else None
    return out
