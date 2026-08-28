import json

import pytest

from c2c.trajectory import Recorder, render_markdown


def test_records_and_reads_back(tmp_path):
    r = Recorder.open("test", root=tmp_path)
    r.emit("AGENT_START", case_id="R01", agent="caseworker")
    r.emit("FINAL_DECISION", case_id="R01", output={"next_action": "submit_claim"})
    events = r.read()
    assert [e["event_type"] for e in events] == ["AGENT_START", "FINAL_DECISION"]
    assert all(e["run_id"] == r.run_id for e in events)
    assert all(e["git_sha"] for e in events)


def test_rejects_unknown_event_type(tmp_path):
    r = Recorder.open("test", root=tmp_path)
    with pytest.raises(ValueError):
        r.emit("MADE_UP_EVENT")


def test_trims_oversized_fields(tmp_path):
    r = Recorder.open("test", root=tmp_path)
    r.emit("TOOL_RESULT", output="x" * 50_000)
    out = r.read()[0]["output"]
    assert len(out) < 50_000 and "trimmed" in out


def test_events_are_one_json_object_per_line(tmp_path):
    r = Recorder.open("test", root=tmp_path)
    for _ in range(3):
        r.emit("RETRY", input="something\nwith\nnewlines")
    lines = r.events_path.read_text().splitlines()
    assert len(lines) == 3
    assert all(json.loads(line) for line in lines)


def test_markdown_groups_by_case(tmp_path):
    r = Recorder.open("test", root=tmp_path)
    r.emit("AGENT_START", case_id="R01")
    r.emit("AGENT_START", case_id="R02")
    md = render_markdown(r.read(), "t")
    assert "## Case R01" in md and "## Case R02" in md


def test_markdown_flags_verifier_rejection(tmp_path):
    r = Recorder.open("test", root=tmp_path)
    r.emit("VERIFIER_REJECT", case_id="R01", output={"reason": "band B not band C"})
    assert "verify REJECT" in render_markdown(r.read(), "t")
