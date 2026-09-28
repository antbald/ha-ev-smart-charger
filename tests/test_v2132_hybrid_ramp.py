"""Tests for v2.13.2 — Hybrid Inverter Mode RIDING_EDGE ramp no longer freezes.

Before v2.13.2 a step-up required ``grid_import <= threshold / 2`` while a
step-down required ``grid_import > threshold`` sustained. In between, the
amperage was held forever. Zero-export inverters regulate to a small residual
import that grows with the load, so the ramp stalled (~10 A on a typical
install) with plenty of PV headroom left. The ramp now climbs whenever the
import is within the threshold; anti-oscillation is an amperage ceiling that
blocks re-climbing a level that just forced a step-down.
"""
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.util import dt as dt_util

from custom_components.ev_smart_charger.charger_controller import OperationResult
from custom_components.ev_smart_charger.const import (
    CONF_GRID_IMPORT,
    HYBRID_EDGE_CEILING_SECONDS,
    HYBRID_STATE_RIDING_EDGE,
)
from custom_components.ev_smart_charger.hybrid_inverter_mode import (
    HybridInverterMode,
)

TICK = timedelta(seconds=60)


def _build(hass, start_amps=6):
    hass.states.async_set("number.grid_threshold", "50")
    hass.states.async_set("number.solar_max", "32")
    hass.states.async_set("number.max_import_duration", "60")
    amps = {"value": start_amps}

    async def _get_amps():
        return amps["value"]

    async def _set_amps(target_amps, reason=""):
        amps["value"] = target_amps
        return OperationResult(
            success=True, operation="set_amperage", reason=reason, amperage=target_amps
        )

    controller = MagicMock()
    controller.get_current_amperage = _get_amps
    controller.set_amperage = AsyncMock(side_effect=_set_amps)
    with patch(
        "custom_components.ev_smart_charger.hybrid_inverter_mode.AstralTimeService"
    ), patch(
        "custom_components.ev_smart_charger.hybrid_inverter_mode.MobileNotificationService"
    ):
        hybrid = HybridInverterMode(
            hass, "test_entry", {CONF_GRID_IMPORT: "sensor.grid"}, controller, MagicMock()
        )
    hybrid._grid_import_threshold_entity = "number.grid_threshold"
    hybrid._solar_max_amperage_entity = "number.solar_max"
    hybrid._max_import_duration_entity = "number.max_import_duration"
    hybrid._state = HYBRID_STATE_RIDING_EDGE
    hybrid._publish_diagnostic = AsyncMock()
    return hybrid, amps


async def _run(hybrid, amps, grid_fn, ticks, now):
    history = []
    for _ in range(ticks):
        await hybrid._handle_riding_edge(now, grid_fn(amps["value"]), amps["value"])
        history.append(amps["value"])
        now += TICK
    return history, now


async def test_ramp_reaches_max_with_zero_import(hass):
    hybrid, amps = _build(hass)
    history, _ = await _run(hybrid, amps, lambda a: 0.0, 20, dt_util.now())
    assert history[-1] == 32


async def test_residual_import_within_threshold_does_not_freeze_ramp(hass):
    """Regression: residual import between threshold/2 and threshold."""
    hybrid, amps = _build(hass)
    # ~1.5% of the EV load: 21 W at 6 A, 35 W at 10 A, 48 W at 14 A…
    history, _ = await _run(
        hybrid, amps, lambda a: min(45.0, 0.015 * a * 230), 20, dt_util.now()
    )
    assert history[-1] == 32


async def test_step_down_sets_ceiling_and_blocks_reclimb(hass):
    """A level that tripped a step-down is not re-climbed until it expires."""
    hybrid, amps = _build(hass, start_amps=13)
    real_edge = 10  # inverter can supply up to 10 A without importing

    def grid(a):
        return 0.0 if a <= real_edge else 400.0

    now = dt_util.now()
    history, now = await _run(hybrid, amps, grid, 9, now)
    assert 13 not in history[2:]
    assert history[-1] == 10
    assert hybrid.get_diagnostic_snapshot()["edge_ceiling_amps"] == 13

    # After the ceiling expires the edge is re-probed once.
    now += timedelta(seconds=HYBRID_EDGE_CEILING_SECONDS)
    history, _ = await _run(hybrid, amps, grid, 3, now)
    assert 13 in history


async def test_sustained_import_above_threshold_still_steps_down(hass):
    hybrid, amps = _build(hass, start_amps=16)
    history, _ = await _run(hybrid, amps, lambda a: 120.0, 3, dt_util.now())
    assert history == [16, 13, 13]
