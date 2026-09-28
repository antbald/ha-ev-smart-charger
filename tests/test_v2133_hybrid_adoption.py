"""Tests for v2.13.3 — Hybrid Inverter Mode adopts a running session.

End-to-end: the real Solar Surplus tick drives the real Hybrid Inverter Mode
state machine against a simulated zero-export hybrid inverter (battery full):

    production = min(pv_available, house + ev)   # PV follows the load
    grid       = max(0, house + ev - pv_available)

Before v2.13.3 Hybrid Mode only engaged with the charger OFF. A session that
was already running when curtailment began (started by Solar Surplus, battery
support, or surviving an HA restart) stayed frozen at its amperage forever:
the measured surplus is pinned to the EV's own draw, so Solar Surplus never
sees room for the next level.
"""
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.ev_smart_charger.charger_controller import OperationResult
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_FV_PRODUCTION,
    CONF_GRID_IMPORT,
    CONF_HOME_CONSUMPTION,
    CONF_SOC_HOME,
    HYBRID_STATE_IDLE,
    HYBRID_STATE_RIDING_EDGE,
)
from custom_components.ev_smart_charger.hybrid_inverter_mode import (
    HybridInverterMode,
)
from custom_components.ev_smart_charger.solar_surplus import SolarSurplusAutomation

HOUSE_W = 400.0
PV_AVAILABLE_W = 7000.0  # enough for 24 A (5920 W total), not for 32 A


def _build(hass, *, charger_on, amps):
    config = {
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        CONF_EV_CHARGER_SWITCH: "switch.charger",
        CONF_FV_PRODUCTION: "sensor.pv",
        CONF_HOME_CONSUMPTION: "sensor.consumption",
        CONF_GRID_IMPORT: "sensor.grid",
        CONF_SOC_HOME: "sensor.home_soc",
    }
    charger = {"on": charger_on, "amps": amps}

    async def _is_charging():
        return charger["on"]

    async def _get_amps():
        return charger["amps"]

    async def _start(target_amps=None, reason=""):
        charger["on"] = True
        charger["amps"] = target_amps or charger["amps"]
        return OperationResult(True, "start", reason, amperage=charger["amps"])

    async def _stop(reason=""):
        charger["on"] = False
        return OperationResult(True, "stop", reason)

    async def _set(target_amps, reason=""):
        charger["amps"] = target_amps
        return OperationResult(True, "set_amperage", reason, amperage=target_amps)

    controller = MagicMock()
    controller.is_charging = _is_charging
    controller.get_current_amperage = _get_amps
    controller.start_charger = _start
    controller.stop_charger = _stop
    controller.set_amperage = _set

    balancer = MagicMock()
    balancer.is_enabled = MagicMock(return_value=True)
    balancer.calculate_priority = AsyncMock(return_value="EV")

    with patch(
        "custom_components.ev_smart_charger.solar_surplus.AstralTimeService"
    ) as ss_astral, patch(
        "custom_components.ev_smart_charger.hybrid_inverter_mode.AstralTimeService"
    ) as hy_astral, patch(
        "custom_components.ev_smart_charger.hybrid_inverter_mode.MobileNotificationService"
    ):
        for astral in (ss_astral, hy_astral):
            astral.return_value.is_nighttime.return_value = False
            astral.return_value.get_sunset.return_value = dt_util.now() + timedelta(days=5)
        surplus = SolarSurplusAutomation(hass, "test_entry", config, balancer, controller)
        hybrid = HybridInverterMode(hass, "test_entry", config, controller, balancer)

    surplus._hybrid_mode = hybrid
    hybrid._solar_surplus = surplus

    for entity_id, value in {
        "select.profile": "solar_surplus",
        "number.grid_threshold": "50",
        "number.grid_delay": "30",
        "number.drop_delay": "30",
        "number.solar_max": "32",
        "number.spike_delay": "0",
        "switch.hybrid": "on",
        "number.hybrid_full": "95",
        "number.hybrid_probe": "60",
        "number.hybrid_import": "60",
        "number.hybrid_fails": "5",
        "sensor.home_soc": "100",
        "sensor.charger_status": "charger_charging",
    }.items():
        hass.states.async_set(entity_id, value)

    surplus._charging_profile_entity = "select.profile"
    surplus._grid_import_threshold_entity = "number.grid_threshold"
    surplus._grid_import_delay_entity = "number.grid_delay"
    surplus._surplus_drop_delay_entity = "number.drop_delay"
    surplus._solar_max_amperage_entity = "number.solar_max"
    surplus._spike_response_delay_entity = "number.spike_delay"
    surplus._update_diagnostic_sensor = AsyncMock()
    surplus._emit_diagnostic = AsyncMock()
    surplus._acquire_control = AsyncMock(return_value=True)
    surplus._has_control = MagicMock(return_value=True)

    hybrid._enabled_entity = "switch.hybrid"
    hybrid._battery_full_threshold_entity = "number.hybrid_full"
    hybrid._probe_duration_entity = "number.hybrid_probe"
    hybrid._max_import_duration_entity = "number.hybrid_import"
    hybrid._max_failed_probes_entity = "number.hybrid_fails"
    hybrid._grid_import_threshold_entity = "number.grid_threshold"
    hybrid._solar_max_amperage_entity = "number.solar_max"
    hybrid._publish_diagnostic = AsyncMock()
    hybrid._mobile_notifier = MagicMock()
    hybrid._mobile_notifier.send_hybrid_mode_started_notification = AsyncMock()
    return surplus, hybrid, charger


async def _simulate(hass, surplus, hybrid, charger, *, ticks, consumption_includes_ev,
                    curtailed=True):
    clock = [dt_util.now()]
    history = []
    with patch("homeassistant.util.dt.now", side_effect=lambda *a, **k: clock[0]):
        for _ in range(ticks):
            ev_w = charger["amps"] * 230 if charger["on"] else 0.0
            demand = HOUSE_W + ev_w
            production = min(PV_AVAILABLE_W, demand) if curtailed else PV_AVAILABLE_W
            hass.states.async_set("sensor.pv", str(production))
            hass.states.async_set(
                "sensor.consumption",
                str(demand if consumption_includes_ev else HOUSE_W),
            )
            hass.states.async_set("sensor.grid", str(max(0.0, demand - PV_AVAILABLE_W)))
            await surplus._async_periodic_check(ignore_rate_limit=True)
            history.append((hybrid._state, charger["amps"] if charger["on"] else 0))
            clock[0] += timedelta(seconds=60)
    return history


@pytest.mark.parametrize("consumption_includes_ev", [False, True])
async def test_running_session_is_adopted_and_ramps_past_10a(
    hass, consumption_includes_ev
):
    """Regression: a 10 A session under curtailment used to stay at 10 A forever."""
    surplus, hybrid, charger = _build(hass, charger_on=True, amps=10)
    history = await _simulate(
        hass, surplus, hybrid, charger, ticks=16,
        consumption_includes_ev=consumption_includes_ev,
    )
    assert history[1][0] == HYBRID_STATE_RIDING_EDGE
    assert max(amps for _, amps in history) >= 24
    # Settles on the real edge (24 A) instead of stopping the charger.
    assert history[-1] == (HYBRID_STATE_RIDING_EDGE, 24)


@pytest.mark.parametrize("consumption_includes_ev", [False, True])
async def test_probe_from_off_rides_edge_without_restarting(
    hass, consumption_includes_ev
):
    """At the real PV limit the edge steps down one level instead of exiting."""
    surplus, hybrid, charger = _build(hass, charger_on=False, amps=6)
    history = await _simulate(
        hass, surplus, hybrid, charger, ticks=24,
        consumption_includes_ev=consumption_includes_ev,
    )
    reached = [i for i, (_, amps) in enumerate(history) if amps >= 24]
    assert reached
    assert all(state == HYBRID_STATE_RIDING_EDGE for state, _ in history[reached[0]:])
    assert all(amps >= 24 for _, amps in history[reached[0]:])


async def test_real_surplus_is_left_to_solar_surplus(hass):
    """Without curtailment Solar Surplus can ramp on its own — no adoption."""
    surplus, hybrid, charger = _build(hass, charger_on=True, amps=10)
    history = await _simulate(
        hass, surplus, hybrid, charger, ticks=4,
        consumption_includes_ev=False, curtailed=False,
    )
    assert all(state == HYBRID_STATE_IDLE for state, _ in history)
