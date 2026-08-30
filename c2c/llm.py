"""Model transport.

Two backends behind one interface:

  api  — the Anthropic SDK, used when ANTHROPIC_API_KEY is set. This is the
         documented path for anyone reproducing the results.
  cli  — `claude -p`, used when there is no API key. This is what the build
         host had available. See docs/ENVIRONMENT.md.

The CLI backend pays a fixed harness overhead on top of C2C's own prompt. It is
reported separately from task tokens so the two backends stay comparable and so
C2C never claims credit for, or is charged for, tokens it did not author.

Keeping the system prompt byte-identical across calls matters: it makes the
cached prefix stable, which took the measured CLI cost from $0.0162 to $0.0025
per call. The policy document therefore lives in the system prompt, not the
user turn.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# USD per million tokens. Used only by the api backend; the cli backend reports
# the cost the harness itself measured.
PRICES = {
    "claude-haiku-4-5-20251001": {"in": 1.00, "out": 5.00, "cache_write": 1.25, "cache_read": 0.10},
    "claude-sonnet-5": {"in": 3.00, "out": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "claude-opus-5": {"in": 15.00, "out": 75.00, "cache_write": 18.75, "cache_read": 1.50},
}


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    backend: str
    duration_ms: int
    task_input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    harness_overhead_tokens: int = 0
    cost_usd: Optional[float] = None
    endpoint: str = ""
    raw: dict = field(default_factory=dict)

    def usage(self) -> dict:
        return {
            "task_input_tokens": self.task_input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "harness_overhead_tokens": self.harness_overhead_tokens,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
        }


ANTHROPIC_API = "https://api.anthropic.com"


def choose_backend() -> str:
    forced = os.environ.get("C2C_LLM_BACKEND")
    if forced:
        return forced
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api"
    # A local or self-hosted gateway, addressed by base URL plus token.
    if os.environ.get("ANTHROPIC_BASE_URL") and os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "api"
    return "cli"


def resolve_endpoint(backend: str) -> str:
    """Where calls actually go.

    This is recorded in every result file. A gateway can serve a completely
    different model than the one requested while the request still names
    `claude-haiku-4-5`, so the model field alone is not provenance. Runs whose
    endpoint is not api.anthropic.com are not comparable with runs that are.
    """
    if backend == "cli":
        return "claude-cli"
    return os.environ.get("ANTHROPIC_BASE_URL") or ANTHROPIC_API


class LLM:
    # Spacing between calls, shared across every LLM instance and worker thread.
    # The CLI backend starts refusing under concurrent load, and a refusal is
    # indistinguishable in the results from a model that could not answer, so
    # pacing is cheaper than the ambiguity. Tune with C2C_MIN_CALL_INTERVAL.
    _min_interval = float(os.environ.get("C2C_MIN_CALL_INTERVAL", "1.0"))
    _last_call_at = 0.0
    _pace_lock = threading.Lock()

    def __init__(self, model: str = DEFAULT_MODEL, backend: Optional[str] = None,
                 max_retries: int = 3, timeout_s: int = 300):
        self.model = model
        self.backend = backend or choose_backend()
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self.calls = 0
        if self.backend not in ("api", "cli"):
            raise LLMError(f"unknown backend {self.backend!r}")
        self.endpoint = resolve_endpoint(self.backend)

    @classmethod
    def _pace(cls) -> None:
        with cls._pace_lock:
            wait = cls._min_interval - (time.monotonic() - cls._last_call_at)
            if wait > 0:
                time.sleep(wait)
            cls._last_call_at = time.monotonic()

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> LLMResult:
        last: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                self._pace()
                started = time.monotonic()
                if self.backend == "api":
                    r = self._complete_api(system, user, max_tokens)
                else:
                    r = self._complete_cli(system, user)
                r.duration_ms = int((time.monotonic() - started) * 1000)
                r.endpoint = self.endpoint
                self.calls += 1
                return r
            except Exception as exc:  # noqa: BLE001 - retried and re-raised below
                last = exc
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
        raise LLMError(f"{self.backend} backend failed after {self.max_retries} attempts: {last}")

    def _complete_api(self, system: str, user: str, max_tokens: int) -> LLMResult:
        import anthropic

        # Determine the API key and base URL for the local proxy
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            # Fallback to AUTH_TOKEN if API key is not set (for local proxy)
            api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN")
        base_url = os.environ.get("ANTHROPIC_BASE_URL")

        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url
        )
        msg = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        u = msg.usage
        p = PRICES.get(self.model, PRICES[DEFAULT_MODEL])
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        cost = (
            u.input_tokens * p["in"]
            + u.output_tokens * p["out"]
            + cw * p["cache_write"]
            + cr * p["cache_read"]
        ) / 1e6
        return LLMResult(
            text="".join(b.text for b in msg.content if b.type == "text"),
            model=self.model,
            backend="api",
            duration_ms=0,
            task_input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_creation_tokens=cw,
            cache_read_tokens=cr,
            harness_overhead_tokens=0,
            cost_usd=round(cost, 6),
        )

    def _complete_cli(self, system: str, user: str) -> LLMResult:
        cmd = [
            "claude", "-p",
            "--model", self.model,
            "--output-format", "json",
            "--system-prompt", system,
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--setting-sources", "",
            "--allowed-tools", "",
            "--max-turns", "1",
        ]
        # A fresh directory per call, removed afterwards. A shared one accumulates
        # session state across a 150-call run, and it must contain no CLAUDE.md,
        # so project instructions cannot leak into a benchmark call.
        with tempfile.TemporaryDirectory(prefix="c2c-llm-") as cwd:
            proc = subprocess.run(
                cmd, input=user, capture_output=True, text=True,
                timeout=self.timeout_s, cwd=cwd, env=_cli_env(),
            )

        if proc.returncode != 0 and not _only_benign_warning(proc.stderr, proc.stdout):
            raise LLMError(f"claude -p exited {proc.returncode}: {proc.stderr[:500]}")
        try:
            d = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise LLMError(f"claude -p returned non-JSON: {proc.stdout[:300]}") from exc
        if d.get("is_error"):
            raise LLMError(f"claude -p reported an error: {str(d)[:500]}")

        u = d.get("usage", {})
        # The CLI reports one input figure covering both C2C's prompt and the
        # harness's own. The harness portion was measured at 12,587 tokens with
        # an empty task prompt (docs/ENVIRONMENT.md); anything above that is
        # attributed to C2C.
        cached = (u.get("cache_creation_input_tokens", 0) or 0) + (u.get("cache_read_input_tokens", 0) or 0)
        overhead = min(cached, HARNESS_BASELINE_TOKENS)
        return LLMResult(
            text=d.get("result", ""),
            model=self.model,
            backend="cli",
            duration_ms=int(d.get("duration_ms", 0)),
            task_input_tokens=(u.get("input_tokens", 0) or 0) + max(0, cached - overhead),
            output_tokens=u.get("output_tokens", 0) or 0,
            cache_creation_tokens=u.get("cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=u.get("cache_read_input_tokens", 0) or 0,
            harness_overhead_tokens=overhead,
            cost_usd=d.get("total_cost_usd"),
            raw={"session_id": d.get("session_id")},
        )


BENIGN_CLI_WARNINGS = ("claude.ai connectors are disabled",)


def _only_benign_warning(stderr: str, stdout: str) -> bool:
    """True when the CLI exited non-zero but still produced a usable answer.

    It exits 1 on warnings that have nothing to do with the completion. Losing a
    good result to one of those turns a warning into a scored failure.
    """
    if not stdout.strip():
        return False
    low = stderr.lower()
    return any(w in low for w in BENIGN_CLI_WARNINGS)


def _cli_env() -> dict:
    """The CLI subprocess environment, with every ANTHROPIC_* variable removed.

    This is a correctness fix, not tidiness. With ANTHROPIC_BASE_URL set in the
    parent shell the `claude` CLI routes through that gateway too, so the "cli"
    backend silently stops being the CLI backend and starts serving whatever the
    gateway serves. That happened here, and the runs it produced looked like
    ordinary bad results rather than a different model. See FAILURES.md F-007.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
    return env


HARNESS_BASELINE_TOKENS = 12587

def _isolated_cwd() -> str:
    """A directory with no CLAUDE.md, so project instructions cannot leak into a
    benchmark call. Kept for the isolation tests; `_complete_cli` now makes a
    fresh one per call and removes it afterwards."""
    return tempfile.mkdtemp(prefix="c2c-llm-")


def extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model response.

    Models wrap JSON in prose and fences with some regularity. Failing to parse
    is a real failure of the system under test and is recorded as such, so this
    stays deliberately simple: strip fences, then scan for a balanced object.
    """
    if not text:
        return None
    s = text.strip()
    if "```" in s:
        parts = s.split("```")
        for part in parts[1:]:
            body = part.split("\n", 1)[-1] if part[:20].strip().lower().startswith("json") else part
            got = _first_object(body)
            if got is not None:
                return got
    return _first_object(s)


def _first_object(s: str) -> Optional[dict]:
    start = s.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        got = json.loads(s[start : i + 1])
                        if isinstance(got, dict):
                            return got
                    except json.JSONDecodeError:
                        break
        start = s.find("{", start + 1)
    return None
