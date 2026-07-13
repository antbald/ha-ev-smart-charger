"""Tests for v2.8.0 — consumption-spike fast response (Solar Surplus).

An event-driven grid-import listener detects household demand spikes
(washing machine, induction hob, ...) while the EV charges on surplus.
When PV production is stable vs the last per-tick baseline and the import
persists for `evsc_spike_response_delay` seconds, the charger steps down
in ONE operation to the amp level that zeroes the measured import.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.ev_smart_charger.solar_surplus import SolarSurplusAutomation
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
    CONF_SOC_HOME,
)


@pytest.fixture
def automation(hass, mock_charger_controller, mock_priority_balancer):
    """Create a SolarSurplusAutomation instance wired for the fast path."""
    config = {
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        CONF_FV_PRODUCTION: "sensor.solar",
        CONF_HOME_CONSUMPTION: "sensor.consumption",
        CONF_GRID_IMPORT: "sensor.grid",
        CONF_SOC_HOME: "sensor.home_soc",
    }

    with patch(
        "custom_components.ev_smart_charger.solar_surplus.AstralTimeService"
    ) as mock_astral:
        mock_astral.return_value.is_nighttime.return_value = False

        auto = SolarSurplusAutomation(
            hass, "test_entry", config, mock_priority_balancer, mock_charger_controller
        )

        auto._grid_import_threshold_entity = "number.grid_threshold"
        auto._grid_import_delay_entity = "number.grid_delay"
        auto._spike_response_delay_entity = "number.spike_delay"

        return auto


def _arm_charging_spike(hass, automation, *, production=3000, grid=1500,
                        threshold=50, delay=10, current_amps=16):
    """Put the system in a 'charging with an active consumption spike' state."""
    hass.states.async_set("sensor.solar", str(production))
    hass.states.async_set("sensor.grid", str(grid))
    hass.states.async_set("number.grid_threshold", str(threshold))
    hass.states.async_set("number.spike_delay", str(delay))
    automation._spike_baseline_production = production
    automation.charger_controller.is_charging = AsyncMock(return_value=True)
    automation.charger_controller.get_current_amperage = AsyncMock(
        return_value=current_amps
    )


# ── Classifier ──────────────────────────────────────────────────


async def test_production_stability_classifier(hass, automation):
    """Stable PV → consumption spike; dropped PV → cloud (legacy path)."""
    # No baseline yet → never classified as consumption spike
    automation._spike_baseline_production = None
    assert automation._is_production_stable(3000) is False

    automation._spike_baseline_production = 3000
    # tolerance = max(300, 0.15*3000) = 450
    assert automation._is_production_stable(3000) is True
    assert automation._is_production_stable(2600) is True   # within tolerance
    assert automation._is_production_stable(2400) is False  # cloud


# ── Preconditions ───────────────────────────────────────────────


async def test_conditions_disabled_when_delay_zero(hass, automation):
    """delay = 0 disables the fast path entirely (legacy behaviour)."""
    _arm_charging_spike(hass, automation, delay=0)
    ok, _, _ = await automation._spike_conditions_met()
    assert ok is False


async def test_conditions_require_charging_session(hass, automation):
    """Fast path is a no-op unless the charger is actually charging."""
    _arm_charging_spike(hass, automation)
    automation.charger_controller.is_charging = AsyncMock(return_value=False)
    ok, _, _ = await automation._spike_conditions_met()
    assert ok is False


async def test_conditions_stand_down_during_hybrid_probe(hass, automation):
    """Hybrid Mode PROBING/RIDING_EDGE must never be undercut."""
    _arm_charging_spike(hass, automation)
    hybrid = MagicMock()
    hybrid.is_active = MagicMock(return_value=True)
    automation._hybrid_mode = hybrid
    ok, _, _ = await automation._spike_conditions_met()
    assert ok is False


async def test_conditions_met_on_real_spike(hass, automation):
    """All gates open: charging, owned, import high, PV stable."""
    _arm_charging_spike(hass, automation)
    ok, grid_import, threshold = await automation._spike_conditions_met()
    assert ok is True
    assert grid_import == 1500
    assert threshold == 50


# ── Listener debounce ───────────────────────────────────────────


async def test_listener_arms_debounce_and_schedules_check(hass, automation):
    """First over-threshold event arms the timer and schedules verification."""
    _arm_charging_spike(hass, automation)

    event = MagicMock()
    event.data = {"new_state": hass.states.get("sensor.grid")}

    with patch(
        "custom_components.ev_smart_charger.solar_surplus.async_call_later"
    ) as mock_later:
        await automation._async_grid_import_changed(event)

    assert automation._spike_high_since is not None
    mock_later.assert_called_once()
    assert mock_later.call_args[0][1] == 10  # configured delay

    # A second event while armed must NOT re-schedule
    with patch(
        "custom_components.ev_smart_charger.solar_surplus.async_call_later"
    ) as mock_later2:
        await automation._async_grid_import_changed(event)
    mock_later2.assert_not_called()


async def test_listener_resets_when_import_recovers(hass, automation):
    """Import back under threshold before the delay → tracking cleared."""
    _arm_charging_spike(hass, automation)
    cancel = MagicMock()
    automation._spike_high_since = 123.0
    automation._spike_check_unsub = cancel

    hass.states.async_set("sensor.grid", "20")  # recovered
    event = MagicMock()
    event.data = {"new_state": hass.states.get("sensor.grid")}
    await automation._async_grid_import_changed(event)

    assert automation._spike_high_since is None
    cancel.assert_called_once()


# ── One-shot step-down ──────────────────────────────────────────


async def test_one_shot_step_down_zeroes_import(hass, automation):
    """16A with 1500W import → lands directly on 8A in a single operation.

    max_allowed = 16 - (1500 + 100 margin) / 230V = 9.04A → highest level ≤ 9.04 = 8A.
    """
    _arm_charging_spike(hass, automation, grid=1500, current_amps=16)
    automation._spike_high_since = 100.0

    await automation._execute_spike_step_down()

    automation.charger_controller.set_amperage.assert_called_once()
    assert automation.charger_controller.set_amperage.call_args[0][0] == 8
    automation.charger_controller.stop_charger.assert_not_called()
    # Debounce cleared and periodic timers invalidated (fresh stability window)
    assert automation._spike_high_since is None
    assert automation._surplus_stable_since is None
    assert automation._last_grid_import_high is None


async def test_step_down_stops_when_floor_still_imports(hass, automation):
    """At 6A with a large import, even the floor imports → stop the charger."""
    _arm_charging_spike(hass, automation, grid=800, current_amps=6)
    automation._spike_high_since = 100.0

    await automation._execute_spike_step_down()

    automation.charger_controller.stop_charger.assert_called_once()
    automation.charger_controller.set_amperage.assert_not_called()


async def test_step_down_aborts_when_cloud_arrived_mid_debounce(hass, automation):
    """Production dropped during the debounce → legacy path, no fast action."""
    _arm_charging_spike(hass, automation)
    automation._spike_high_since = 100.0
    hass.states.async_set("sensor.solar", "1000")  # cloud mid-debounce

    await automation._execute_spike_step_down()

    automation.charger_controller.set_amperage.assert_not_called()
    automation.charger_controller.stop_charger.assert_not_called()
    assert automation._spike_high_since is None


async def test_step_down_rate_limited(hass, automation):
    """A second fast action within SPIKE_MIN_ACTION_INTERVAL is suppressed."""
    _arm_charging_spike(hass, automation)
    automation._spike_high_since = 100.0

    with patch("time.monotonic", return_value=1000.0):
        await automation._execute_spike_step_down()
    automation.charger_controller.set_amperage.assert_called_once()

    automation._spike_high_since = 100.0
    with patch("time.monotonic", return_value=1010.0):  # +10s < 30s
        await automation._execute_spike_step_down()
    automation.charger_controller.set_amperage.assert_called_once()  # still once


async def test_small_import_falls_back_to_single_level(hass, automation):
    """Import below one level step still steps at least one level down.

    16A with 60W import: max_allowed = 16 - 160/230 = 15.3 → highest level 13A.
    """
    _arm_charging_spike(hass, automation, grid=60, threshold=50, current_amps=16)
    automation._spike_high_since = 100.0

    await automation._execute_spike_step_down()

    automation.charger_controller.set_amperage.assert_called_once()
    assert automation.charger_controller.set_amperage.call_args[0][0] == 13
