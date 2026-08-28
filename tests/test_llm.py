from c2c.llm import extract_json


def test_extracts_bare_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extracts_from_fenced_block():
    assert extract_json('here you go:\n```json\n{"a": 1}\n```\nhope that helps') == {"a": 1}


def test_extracts_from_unlabelled_fence():
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}


def test_ignores_braces_inside_strings():
    assert extract_json('{"a": "} not the end {"}') == {"a": "} not the end {"}


def test_skips_prose_and_finds_the_object():
    assert extract_json('The verdict is as follows. {"next_action": "escalate"}') == {
        "next_action": "escalate"
    }


def test_nested_objects_survive():
    assert extract_json('{"a": {"b": [1, 2]}}') == {"a": {"b": [1, 2]}}


def test_returns_none_when_there_is_no_object():
    assert extract_json("no json here") is None
    assert extract_json("") is None


def test_skips_a_malformed_object_and_finds_a_later_one():
    assert extract_json('{"broken": } then {"ok": true}') == {"ok": True}
