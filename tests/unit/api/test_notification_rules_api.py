# -*- coding: utf-8 -*-
"""Unit-Tests fuer K5: notification_rules.py /test Endpoint DoS-Schutz.

- Deeply-nested payload -> 422 statt Worker-Hang
- Ueber-grosse Listen/Dicts -> 422
- Unbekannte Operatoren -> 422
- Strings > max_length -> 422
- Valider Payload -> erfolgreich validiert

Feinpoliert und durchdacht - DoS-Guard fuer /notification-rules/test.
"""

import pytest
from fastapi import HTTPException

from app.api.v1.notification_rules import (
    _validate_test_payload,
    _TEST_MAX_DEPTH,
    _TEST_MAX_TOTAL_NODES,
    _TEST_MAX_STRING_LEN,
    _ALLOWED_OPERATORS,
)


pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestDepthLimit:
    def test_payload_at_max_depth_passes(self):
        # Tiefe = _TEST_MAX_DEPTH (5) -> erlaubt
        payload = {"a": {"b": {"c": {"d": {"e": "ok"}}}}}
        _validate_test_payload(payload)

    def test_payload_too_deep_raises_422(self):
        # Tiefe = 7 -> ueberschreitet max_depth=5
        payload = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "boom"}}}}}}}
        with pytest.raises(HTTPException) as exc:
            _validate_test_payload(payload)
        assert exc.value.status_code == 422
        assert "verschachtelt" in exc.value.detail.lower()


class TestNodeLimit:
    def test_too_many_total_nodes_raises_422(self):
        # 300 Dict-Keys auf einer Ebene -> ueber 200 nodes
        payload = {f"k{i}": "v" for i in range(300)}
        with pytest.raises(HTTPException) as exc:
            _validate_test_payload(payload)
        assert exc.value.status_code == 422

    def test_dict_with_too_many_keys_raises_422(self):
        # 101 Keys -> > 100 Keys/Dict
        payload = {f"k{i}": True for i in range(101)}
        with pytest.raises(HTTPException) as exc:
            _validate_test_payload(payload)
        assert exc.value.status_code == 422

    def test_list_too_long_raises_422(self):
        payload = {"items": list(range(101))}
        with pytest.raises(HTTPException) as exc:
            _validate_test_payload(payload)
        assert exc.value.status_code == 422


class TestOperatorWhitelist:
    def test_unknown_operator_in_op_field_raises_422(self):
        payload = {"field": "x", "op": "MALICIOUS_OP", "value": 1}
        with pytest.raises(HTTPException) as exc:
            _validate_test_payload(payload)
        assert exc.value.status_code == 422
        assert "operator" in exc.value.detail.lower()

    def test_unknown_operator_in_operator_field_raises_422(self):
        payload = {"operator": "XYZ", "conditions": []}
        with pytest.raises(HTTPException) as exc:
            _validate_test_payload(payload)
        assert exc.value.status_code == 422

    def test_allowed_operators_pass(self):
        for op in ["eq", "ne", "gt", "contains", "in", "AND", "OR"]:
            payload = {"field": "x", "op": op, "value": 1}
            _validate_test_payload(payload)

    def test_op_with_non_string_value_skips_whitelist(self):
        # op-key mit non-string value (z.B. None) wird durchgelassen
        payload = {"op": None, "value": 1}
        _validate_test_payload(payload)


class TestStringLimit:
    def test_overlong_string_raises_422(self):
        payload = {"field": "x" * (_TEST_MAX_STRING_LEN + 1)}
        with pytest.raises(HTTPException) as exc:
            _validate_test_payload(payload)
        assert exc.value.status_code == 422

    def test_string_at_limit_passes(self):
        payload = {"field": "x" * _TEST_MAX_STRING_LEN}
        _validate_test_payload(payload)


class TestValidPayloads:
    def test_typical_rule_condition_passes(self):
        # Realistische Bedingung wie sie in notification_rule_engine erwartet wird
        payload = {
            "operator": "AND",
            "conditions": [
                {"field": "document.type", "op": "eq", "value": "invoice"},
                {"field": "document.amount", "op": "gt", "value": 1000},
            ],
        }
        _validate_test_payload(payload)

    def test_empty_dict_passes(self):
        _validate_test_payload({})

    def test_event_data_dict_passes(self):
        event_data = {
            "document": {"type": "invoice", "amount": 5000},
            "user_id": "abc-123",
        }
        _validate_test_payload(event_data)


class TestInvalidKeyTypes:
    def test_overlong_dict_key_raises_422(self):
        payload = {"x" * 201: "v"}
        with pytest.raises(HTTPException) as exc:
            _validate_test_payload(payload)
        assert exc.value.status_code == 422
