"""Backend selection, endpoint provenance, call pacing and CLI isolation.

These exist because a gateway silently served a different model than the one
requested for a whole evening's runs, and nothing in the results said so. See
FAILURES.md F-007.

No mocks of the Anthropic SDK here. A MagicMock accepts any attribute or method,
which is how the earlier version of this file passed while the code under it
would have crashed on a real response.
"""

import os
from unittest.mock import patch

import pytest

from c2c.llm import (ANTHROPIC_API, LLM, LLMError, _cli_env, _only_benign_warning,
                     choose_backend, resolve_endpoint)


def env(**over):
    base = {k: "" for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
                            "ANTHROPIC_AUTH_TOKEN", "C2C_LLM_BACKEND")}
    return patch.dict(os.environ, {**base, **over})


# --- backend selection ------------------------------------------------------

def test_an_api_key_selects_the_api_backend():
    with env(ANTHROPIC_API_KEY="sk-ant-test"):
        assert choose_backend() == "api"


def test_a_gateway_needs_both_a_url_and_a_token():
    with env(ANTHROPIC_BASE_URL="http://127.0.0.1:8082", ANTHROPIC_AUTH_TOKEN="t"):
        assert choose_backend() == "api"
    with env(ANTHROPIC_BASE_URL="http://127.0.0.1:8082"):
        assert choose_backend() == "cli", "a URL with no token must not select api"
    with env(ANTHROPIC_AUTH_TOKEN="t"):
        assert choose_backend() == "cli", "a token with no URL must not select api"


def test_nothing_configured_falls_back_to_the_cli():
    with env():
        assert choose_backend() == "cli"


def test_the_backend_can_be_forced():
    with env(ANTHROPIC_API_KEY="sk-ant-test", C2C_LLM_BACKEND="cli"):
        assert choose_backend() == "cli"


def test_an_unknown_backend_is_rejected_loudly():
    with pytest.raises(LLMError):
        LLM(backend="telepathy")


# --- endpoint provenance ----------------------------------------------------

def test_a_first_party_api_call_records_anthropic():
    with env(ANTHROPIC_API_KEY="sk-ant-test"):
        assert resolve_endpoint("api") == ANTHROPIC_API
        assert LLM(backend="api").endpoint == ANTHROPIC_API


def test_a_gateway_call_records_the_gateway_not_anthropic():
    """The whole point: a run through a gateway must be identifiable afterwards."""
    with env(ANTHROPIC_BASE_URL="http://127.0.0.1:8082", ANTHROPIC_AUTH_TOKEN="t"):
        assert resolve_endpoint("api") == "http://127.0.0.1:8082"
        assert LLM(backend="api").endpoint == "http://127.0.0.1:8082"


def test_the_cli_backend_records_itself_even_when_a_gateway_is_configured():
    with env(ANTHROPIC_BASE_URL="http://127.0.0.1:8082", ANTHROPIC_AUTH_TOKEN="t"):
        assert LLM(backend="cli").endpoint == "claude-cli"


def test_the_evaluation_harness_knows_which_endpoints_are_first_party():
    from c2c.eval.run import _is_first_party

    assert _is_first_party("claude-cli")
    assert _is_first_party(ANTHROPIC_API)
    assert not _is_first_party("http://127.0.0.1:8082")


# --- CLI isolation ----------------------------------------------------------

def test_the_cli_subprocess_never_inherits_a_gateway():
    """With ANTHROPIC_BASE_URL set, the claude CLI routes through it too, so the
    cli backend silently stops being the cli backend."""
    with env(ANTHROPIC_BASE_URL="http://127.0.0.1:8082", ANTHROPIC_AUTH_TOKEN="t",
             ANTHROPIC_API_KEY="sk-ant-test"):
        assert not [k for k in _cli_env() if k.startswith("ANTHROPIC_")]


def test_the_cli_subprocess_keeps_everything_else():
    with patch.dict(os.environ, {"PATH": "/usr/bin", "HOME": "/home/x"}):
        e = _cli_env()
        assert e["PATH"] == "/usr/bin" and e["HOME"] == "/home/x"


# --- benign warnings --------------------------------------------------------

def test_a_warning_with_a_usable_answer_is_not_a_failure():
    assert _only_benign_warning("Warning: claude.ai connectors are disabled", '{"result":"x"}')


def test_a_warning_with_no_answer_is_still_a_failure():
    assert not _only_benign_warning("claude.ai connectors are disabled", "")


def test_a_real_error_is_never_swallowed():
    assert not _only_benign_warning("rate limit exceeded", '{"result":"x"}')
    assert not _only_benign_warning("Authentication failed", '{"result":"x"}')


# --- pacing -----------------------------------------------------------------

def test_calls_are_paced_apart():
    import time

    with patch.object(LLM, "_min_interval", 0.05):
        LLM._last_call_at = 0.0
        started = time.monotonic()
        for _ in range(3):
            LLM._pace()
        assert time.monotonic() - started >= 0.10


def test_pacing_is_shared_across_instances():
    """Two workers must not each get their own budget."""
    assert LLM(backend="cli")._pace_lock is LLM(backend="cli")._pace_lock
