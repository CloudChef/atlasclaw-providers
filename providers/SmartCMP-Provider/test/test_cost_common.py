# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

from smartcmp_provider.domain import cost as common


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


def test_normalize_timestamp_uses_atlasclaw_request_timezone(monkeypatch):
    del monkeypatch
    assert common.normalize_timestamp(
        1_710_000_000_000,
        timezone_name="America/New_York",
    ) == "2024-03-09T11:00:00-05:00"
    assert common.normalize_timestamp(
        1_783_616_463_695,
        timezone_name="America/New_York",
    ) == "2026-07-09T13:01:03.695000-04:00"

    assert common.normalize_timestamp(
        1_710_000_000_000,
        timezone_name="not-a-real-timezone",
    ) == "2024-03-09T16:00:00Z"
