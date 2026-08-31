"""The tenant guard exists because C2C registers on a Restate server shared with
an unrelated project. Its baseline is a property of one *server*, and storing it
globally made it false-alarm the moment a second Restate appeared."""

import json

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
