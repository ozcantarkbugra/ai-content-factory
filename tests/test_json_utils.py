"""Tests for JSON extraction from LLM responses."""

from core.json_utils import extract_json_object


def test_extract_plain_json():
    data = extract_json_object('{"topic": "test"}')
    assert data["topic"] == "test"


def test_extract_fenced_json():
    raw = 'Here is output:\n```json\n{"decision": "APPROVE"}\n```'
    data = extract_json_object(raw)
    assert data["decision"] == "APPROVE"
