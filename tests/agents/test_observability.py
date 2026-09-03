"""Tests for structured observability logging — task P8-BE-3."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from backend.observability import CycleObserver, emit_structured_event


def test_structured_observability_events(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="aegis.observability")
    cycle_id = "cycle_obs_test_001"
    obs = CycleObserver(cycle_id)

    # Emit all 10 required event types
    events: list[dict[str, Any]] = [
        obs.agent_invocation("MarketAnalysisAgent", inputs={"symbol": "SPY"}),
        obs.input_summary("Portfolio down 5% with rising VIX"),
        obs.output("MarketAnalysisAgent", {"regime": "RISK_OFF"}),
        obs.decision("SELECT_STRATEGY", "PROTECTIVE_PUT", "Hedging against tech drop"),
        obs.tool_call("get_option_chain", {"symbol": "SPY"}),
        obs.risk_check("APPROVE", violations=[]),
        obs.order("ord_100", "MLEG", "SUBMITTED"),
        obs.fill("ord_100", "SPY261218P00500000", 10.0, 5.20),
        obs.error("Transient timeout on news fetch", error_type="NETWORK"),
        obs.reassessment_trigger("VOLATILITY_SPIKE", observed=32.5, threshold=25.0),
    ]

    expected_types = {
        "agent_invocation",
        "input_summary",
        "output",
        "decision",
        "tool_call",
        "risk_check",
        "order",
        "fill",
        "error",
        "reassessment_trigger",
    }

    emitted_types = {e["event_type"] for e in events}
    assert emitted_types == expected_types

    # Assert every event carries the shared cycle_id and an ISO timestamp
    for e in events:
        assert e["cycle_id"] == cycle_id
        assert "timestamp" in e

    # Assert logs captured structured JSON
    log_records = [json.loads(record.message) for record in caplog.records if record.name == "aegis.observability"]
    assert len(log_records) == 10
    assert all(r["cycle_id"] == cycle_id for r in log_records)
