import pytest

from c2c.agent.tools import TOOL_SPEC, ToolBox, safe_eval
from c2c.models import load_cases

CASES = {c.case_id: c for c in load_cases()}


@pytest.fixture()
def box():
    return ToolBox(case=CASES["R21"])


def test_calculate_does_arithmetic(box):
    assert box.call("calculate", {"expression": "420 * 0.5"}) == "420 * 0.5 = 210"
    assert box.call("calculate", {"expression": "210 + 31 + 58 + 21"}).endswith("= 320")


def test_calculate_refuses_anything_that_is_not_arithmetic():
    for hostile in ["__import__('os').system('ls')", "open('/etc/passwd').read()", "x + 1"]:
        with pytest.raises(Exception):
            safe_eval(hostile)


def test_tool_spec_names_every_implemented_tool():
    for name in ("list_documents", "read_document", "policy_lookup", "calculate"):
        assert f"{name}(" in TOOL_SPEC
        assert hasattr(ToolBox(case=CASES["R21"]), f"_t_{name}")


def test_list_documents_shows_every_document_and_the_carrier_slot(box):
    out = box.call("list_documents", {})
    for d in CASES["R21"].documents:
        assert d.doc_id in out
    assert "no carrier response on file" in out


def test_list_documents_reports_a_carrier_response_when_there_is_one():
    out = ToolBox(case=CASES["R23"]).call("list_documents", {})
    assert "carrier response on file: rejection" in out


def test_read_document_returns_full_text(box):
    out = box.call("read_document", {"doc_id": "D8"})
    assert "Offered re-routing on GM216" in out


def test_read_document_is_case_insensitive_and_names_what_exists(box):
    assert "GM216" in box.call("read_document", {"doc_id": "d8"})
    err = box.call("read_document", {"doc_id": "D99"})
    assert err.startswith("ERROR") and "D1" in err


def test_policy_lookup_by_clause_id(box):
    out = box.call("policy_lookup", {"query": "S5.4"})
    assert "taper" in out.lower() and "3h30m" in out


def test_policy_lookup_takes_several_ids(box):
    out = box.call("policy_lookup", {"query": "S4.3, S4.4"})
    assert "2 hours before" in out and "1 hour before" in out


def test_policy_lookup_falls_back_to_keywords(box):
    assert "S6.3" in box.call("policy_lookup", {"query": "capped"})


def test_no_tool_returns_a_verdict(box):
    """The whole design rests on this: tools retrieve and compute, they never
    decide. If a tool ever answers the question, the benchmark stops measuring
    reasoning."""
    for name in ("list_documents", "read_document", "policy_lookup", "calculate"):
        assert not name.startswith(("assess", "decide", "eligib", "verdict"))
    assert not any(hasattr(box, f"_t_{n}") for n in ("assess", "decide", "check_eligibility"))


def test_unknown_tool_is_reported_not_raised(box):
    assert "no tool named" in box.call("make_decision", {})


def test_calls_are_recorded_for_the_trajectory(box):
    box.call("list_documents", {})
    box.call("calculate", {"expression": "1+1"})
    assert [c["tool"] for c in box.calls] == ["list_documents", "calculate"]
