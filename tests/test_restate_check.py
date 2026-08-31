"""The tenant guard exists because C2C registers on a Restate server shared with
an unrelated project. Its baseline is a property of one *server*, and storing it
globally made it false-alarm the moment a second Restate appeared."""

import json
import pathlib

import pytest

from c2c.tools import restate_check as rc


def test_the_baseline_is_keyed_by_admin_endpoint(tmp_path, monkeypatch):
    """A containerised Restate legitimately has none of the host's tenants.
    Comparing one server against another's record is a false alarm, and a guard
    that cries wolf gets skipped."""
    baseline = tmp_path / "tenants.json"
    baseline.write_text(json.dumps({
        "http://localhost:9070": {"restate_version": "1.7.7",
                                  "pre_existing_services": ["Outreach", "LeadRegistry"]},
        "http://restate:9070": {"restate_version": "1.7.7", "pre_existing_services": []},
    }))
    monkeypatch.setattr(rc, "BASELINE", baseline)

    monkeypatch.setattr(rc, "ADMIN", "http://localhost:9070")
    monkeypatch.setattr(rc, "get", lambda p: {"version": "1.7.7"} if p == "/version" else
                        {"services": [{"name": n} for n in
                                      ("Outreach", "LeadRegistry", "C2CCase")]})
    assert rc.main() == 0, "the host's own tenants being present must pass"

    monkeypatch.setattr(rc, "ADMIN", "http://restate:9070")
    monkeypatch.setattr(rc, "get", lambda p: {"version": "1.7.7"} if p == "/version" else
                        {"services": [{"name": "C2CCase"}]})
    assert rc.main() == 0, "a different server with no tenants must not false-alarm"


def test_a_genuinely_missing_tenant_still_fails(tmp_path, monkeypatch):
    """The guard must not have been weakened by the fix."""
    baseline = tmp_path / "tenants.json"
    baseline.write_text(json.dumps({
        "http://localhost:9070": {"restate_version": "1.7.7",
                                  "pre_existing_services": ["Outreach", "LeadRegistry"]}}))
    monkeypatch.setattr(rc, "BASELINE", baseline)
    monkeypatch.setattr(rc, "ADMIN", "http://localhost:9070")
    monkeypatch.setattr(rc, "get", lambda p: {"version": "1.7.7"} if p == "/version" else
                        {"services": [{"name": n} for n in ("Outreach", "C2CCase")]})
    assert rc.main() == 1, "a vanished tenant must still fail loudly"


def test_a_new_server_records_rather_than_fails(tmp_path, monkeypatch):
    baseline = tmp_path / "tenants.json"
    monkeypatch.setattr(rc, "BASELINE", baseline)
    monkeypatch.setattr(rc, "ADMIN", "http://brand-new:9070")
    monkeypatch.setattr(rc, "get", lambda p: {"version": "1.7.7"} if p == "/version" else
                        {"services": [{"name": "C2CCase"}]})
    assert rc.main() == 0
    assert "http://brand-new:9070" in json.loads(baseline.read_text())


def test_the_durability_suite_needs_no_shell_tools():
    """It runs inside a slim container image, which has neither `ss` nor
    `pkill`. `pkill -f` also matched the caller's own shell when the pattern
    appeared in it, which killed the wrong process more than once."""
    import inspect

    from c2c.eval import durability

    src = inspect.getsource(durability)
    assert '"pkill"' not in src and '"ss"' not in src
    assert "_pids_running" in src and "_port_open" in src


def test_pid_scan_never_returns_its_own_process():
    import os

    from c2c.eval.durability import _pids_running

    assert os.getpid() not in _pids_running("python")


@pytest.mark.skipif(not pathlib.Path("docs").is_dir(),
                    reason="checks repository documentation; the runtime image "
                           "ships only the code and data it needs")
def test_no_document_points_at_a_file_that_does_not_exist():
    """A stale path in a user-facing error message sends a judge somewhere that
    is not there. Found one in configure.py after the deliverables were renamed."""
    import re

    root = pathlib.Path(".")
    referenced: dict[str, str] = {}
    for f in list(root.glob("*.md")) + list(root.glob("docs/*.md")) + list(root.rglob("c2c/**/*.py")):
        text = f.read_text()
        # Markdown link targets, and paths in prose that carry a directory —
        # not bare filenames, which are usually just being named in a sentence.
        for m in re.findall(r"\]\(([^)\s#]+\.md)\)", text):
            referenced[m] = str(f)
        for m in re.findall(r"\b((?:docs|agents|prompts|benchmark|trajectories|experiments)/[\w./-]+\.md)\b", text):
            referenced[m] = str(f)

    # CLAUDE.md deliberately names the superseded files when explaining the rename.
    superseded = {"docs/REPRODUCTION.md", "REPRODUCE_AND_RECORD.md", "FROM_SCRATCH.md"}
    def resolves(target: str, referencing: str) -> bool:
        """A link resolves either from the repo root or from beside the file
        that made it — both are ordinary in Markdown."""
        rel = target.lstrip("./")
        return (root / rel).exists() or (pathlib.Path(referencing).parent / target).exists()

    missing = {t: src for t, src in referenced.items()
               if t not in superseded and not resolves(t, src)}
    assert not missing, f"references to files that do not exist: {missing}"
