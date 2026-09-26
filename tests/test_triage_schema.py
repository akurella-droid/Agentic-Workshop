import json

import pytest

from triage_schema import CATEGORIES, PRIORITIES, ROUTES, TriageDecision, validate_decision

VALID = {
    "category": "billing",
    "priority": "P2",
    "route": "billing-team",
    "rationale": "Double charge puts money at stake, so P2.",
}


def test_valid_decision_returns_triage_decision():
    decision = validate_decision(dict(VALID))
    assert isinstance(decision, TriageDecision)
    assert decision.category == "billing"
    assert decision.priority == "P2"
    assert decision.route == "billing-team"


def test_valid_json_string_returns_triage_decision():
    decision = validate_decision(json.dumps(VALID))
    assert isinstance(decision, TriageDecision)


def test_missing_field_names_it():
    data = {k: v for k, v in VALID.items() if k != "route"}
    with pytest.raises(ValueError, match="route"):
        validate_decision(data)


def test_extra_field_names_it():
    data = dict(VALID, confidence=0.9)
    with pytest.raises(ValueError, match="confidence"):
        validate_decision(data)


def test_bad_priority_enum_names_field_and_allowed_values():
    data = dict(VALID, priority="P5")
    with pytest.raises(ValueError) as exc_info:
        validate_decision(data)
    message = str(exc_info.value)
    assert "priority" in message
    for priority in PRIORITIES:
        assert priority in message


def test_bad_category_enum_names_field_and_allowed_values():
    data = dict(VALID, category="sales")
    with pytest.raises(ValueError) as exc_info:
        validate_decision(data)
    message = str(exc_info.value)
    assert "category" in message
    for category in CATEGORIES:
        assert category in message


def test_bad_route_enum_names_field_and_allowed_values():
    data = dict(VALID, route="sales-team")
    with pytest.raises(ValueError) as exc_info:
        validate_decision(data)
    message = str(exc_info.value)
    assert "route" in message
    for route in ROUTES:
        assert route in message


def test_category_route_mismatch_names_route_and_expected_route():
    data = dict(VALID, category="billing", route="bug-team")
    with pytest.raises(ValueError) as exc_info:
        validate_decision(data)
    message = str(exc_info.value)
    assert "route" in message
    assert "billing-team" in message


def test_empty_rationale_names_field():
    data = dict(VALID, rationale="   ")
    with pytest.raises(ValueError, match="rationale"):
        validate_decision(data)


def test_multi_sentence_rationale_is_accepted():
    data = dict(VALID, rationale="Double charge. Refund now.")
    decision = validate_decision(data)
    assert isinstance(decision, TriageDecision)


def test_malformed_json_reports_not_valid_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        validate_decision("{not json")


def test_non_object_list_reports_json_object_expected():
    with pytest.raises(ValueError, match="JSON object"):
        validate_decision(json.dumps([]))


def test_non_object_string_reports_json_object_expected():
    with pytest.raises(ValueError, match="JSON object"):
        validate_decision(json.dumps("billing"))


def test_error_never_contains_raw_traceback():
    try:
        validate_decision("{not json")
    except ValueError as exc:
        assert "Traceback" not in str(exc)


def test_json_schema_has_enums_and_forbids_extra():
    schema = TriageDecision.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["category"]["enum"] == list(CATEGORIES)
    assert schema["properties"]["priority"]["enum"] == list(PRIORITIES)
    assert schema["properties"]["route"]["enum"] == list(ROUTES)
