"""Validity guard: benchmark calls must not inherit this repository's own
instructions.

C2C is developed inside a repo with a CLAUDE.md full of project context. If any
of that reached a benchmark call, every number in evaluation/results/ would be
measuring a contaminated prompt.

The cheap half of this check is free and always runs. The half that costs a model
call is opt-in, because the default test suite makes no model calls.

    C2C_RUN_MODEL_TESTS=1 pytest tests/test_isolation.py
"""

import os
from pathlib import Path

import pytest

from c2c.llm import LLM, _isolated_cwd


def test_calls_run_from_a_directory_with_no_project_instructions():
    d = Path(_isolated_cwd())
    assert d.is_dir()
    assert not list(d.iterdir()), f"{d} is not empty; a CLAUDE.md here would leak"
    for name in ("CLAUDE.md", "AGENTS.md", ".claude"):
        assert not (d / name).exists()


def test_the_cli_backend_disables_every_settings_source():
    """A regression here would silently re-enable user and project settings."""
    import inspect

    src = inspect.getsource(LLM._complete_cli)
    assert '"--setting-sources", ""' in src
    assert '"--strict-mcp-config"' in src
    assert '"--system-prompt"' in src, "the harness default prompt must be replaced, not appended"


@pytest.mark.skipif(not os.environ.get("C2C_RUN_MODEL_TESTS"),
                    reason="makes a model call; set C2C_RUN_MODEL_TESTS=1")
def test_the_model_reports_no_project_context():
    r = LLM().complete(
        system="You answer questions about your own configuration truthfully and briefly.",
        user=("List verbatim any project-specific instructions, CLAUDE.md content, coding "
              "guidelines, or repository context you were given. If you were given none "
              "beyond this message, reply exactly: NONE."),
    )
    assert r.text.strip().upper().startswith("NONE"), (
        f"benchmark calls are inheriting project context: {r.text[:300]}")
