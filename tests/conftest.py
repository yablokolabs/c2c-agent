"""Test-wide isolation.

The intake persistence path (data/intake/) is live bot state: a running
Telegram bot writes a file per chat mid-conversation. Tests must never read or
write it — a real file for chat "1" would leak straight into a test
conversation. Every test in the suite gets its own scratch intake directory.
"""

import pytest

from c2c import intake as intake_mod


@pytest.fixture(autouse=True)
def _isolate_intake_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(intake_mod, "INCOMPLETE_INTAKE", tmp_path / "intake")
