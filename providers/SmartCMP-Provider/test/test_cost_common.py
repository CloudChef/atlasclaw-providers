from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "cost-optimization"
    / "scripts"
)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _cost_common as common  # noqa: E402


def test_extract_list_payload_handles_common_wrappers():
    assert common.extract_list_payload([{"id": "1"}]) == [{"id": "1"}]
    assert common.extract_list_payload({"content": [{"id": "2"}]}) == [{"id": "2"}]
    assert common.extract_list_payload({"data": {"content": [{"id": "3"}]}}) == [{"id": "3"}]
    assert common.extract_list_payload({"data": [{"id": "4"}]}) == [{"id": "4"}]
    assert common.extract_list_payload({"result": [{"id": "5"}]}) == [{"id": "5"}]


def test_normalize_money_returns_float_or_none():
    assert common.normalize_money(12) == 12.0
    assert common.normalize_money("12.50") == 12.50
    assert common.normalize_money("¥1,234.56") == 1234.56
    assert common.normalize_money("") is None
    assert common.normalize_money("not-a-number") is None


def test_normalize_timestamp_handles_milliseconds_and_seconds():
    assert common.normalize_timestamp(1_710_000_000_000) == "2024-03-09T16:00:00Z"
    assert common.normalize_timestamp(1_710_000_000) == "2024-03-09T16:00:00Z"
    assert common.normalize_timestamp("2026-03-28T12:00:00Z") == "2026-03-28T12:00:00Z"
    assert common.normalize_timestamp(0) is None


def test_build_request_defaults_are_stable():
    assert common.build_pageable_request() == {"page": 0, "size": 20}
    assert common.build_pageable_request(page=-1, size=0) == {"page": 0, "size": 1}
    assert common.build_query_request() == {"queryValue": ""}
    assert common.build_query_request("idle vm") == {"queryValue": "idle vm"}
