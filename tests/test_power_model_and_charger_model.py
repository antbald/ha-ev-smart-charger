"""Tests for the v2.0.0 phase-mode + charger-model logic.

Covers the single source of truth (ChargingModel / const helpers), the
parametrized AmperageCalculator level steppers, and the charger-model-gated
amperage-decrease behaviour in ChargerController.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ev_smart_charger.const import (
    CHARGER_AMP_LEVELS,
    CHARGER_MODEL_GENERIC,
    CHARGER_MODEL_TUYA,
    CHARGER_STATUS_CHARGING,
    CHARGER_STATUS_FREE,
    CHARGING_POWER_DRAWING_FLOOR_W,
    CONF_BATTERY_POWER,
    CONF_CHARGER_MODEL,
    CONF_CHARGING_POWER,
    CONF_CHARGING_POWER_L2,
    CONF_CHARGING_POWER_L3,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_FV_PRODUCTION,
    CONF_FV_PRODUCTION_L2,
    CONF_FV_PRODUCTION_L3,
    CONF_GRID_IMPORT,
    CONF_GRID_IMPORT_L2,
    CONF_GRID_IMPORT_L3,
    CONF_HOME_CONSUMPTION,
    CONF_HOME_CONSUMPTION_L2,
    CONF_HOME_CONSUMPTION_L3,
    CONF_PHASE_MODE,
    GENERIC_AMP_LEVELS,
    PHASE_MODE_THREE,
    VOLTAGE_EU,
    get_amp_levels,
    get_effective_voltage,
    get_phase_count,
    is_three_phase,
)
from custom_components.ev_smart_charger.charger_controller import ChargerController
from custom_components.ev_smart_charger.power_model import ChargingModel
from custom_components.ev_smart_charger.utils.amperage_helper import AmperageCalculator


SINGLE_CONFIG = {
    CONF_FV_PRODUCTION: "sensor.pv",
    CONF_HOME_CONSUMPTION: "sensor.cons",
    CONF_GRID_IMPORT: "sensor.grid",
}

THREE_CONFIG = {
    CONF_PHASE_MODE: PHASE_MODE_THREE,
    CONF_CHARGER_MODEL: CHARGER_MODEL_GENERIC,
    CONF_FV_PRODUCTION: "sensor.pv1",
    CONF_FV_PRODUCTION_L2: "sensor.pv2",
    CONF_FV_PRODUCTION_L3: "sensor.pv3",
    CONF_HOME_CONSUMPTION: "sensor.cons1",
    CONF_HOME_CONSUMPTION_L2: "sensor.cons2",
    CONF_HOME_CONSUMPTION_L3: "sensor.cons3",
    CONF_GRID_IMPORT: "sensor.grid1",
    CONF_GRID_IMPORT_L2: "sensor.grid2",
    CONF_GRID_IMPORT_L3: "sensor.grid3",
}


# ----------------------------------------------------------------------------
# const helpers + ChargingModel (pure)
# ----------------------------------------------------------------------------


def test_const_helpers_default_single_tuya():
    """Empty config = single-phase, 230 V, Tuya levels (unchanged behaviour)."""
    assert is_three_phase({}) is False
    assert get_phase_count({}) == 1
    assert get_effective_voltage({}) == VOLTAGE_EU  # 230
    assert get_amp_levels({}) == CHARGER_AMP_LEVELS


def test_const_helpers_three_phase_generic():
    """Three-phase = 690 V; generic model = 1 A levels."""
    assert is_three_phase(THREE_CONFIG) is True
    assert get_phase_count(THREE_CONFIG) == 3
    assert get_effective_voltage(THREE_CONFIG) == VOLTAGE_EU * 3  # 690
    assert get_amp_levels(THREE_CONFIG) == GENERIC_AMP_LEVELS
    assert GENERIC_AMP_LEVELS[0] == 6 and GENERIC_AMP_LEVELS[-1] == 32
    assert 7 in GENERIC_AMP_LEVELS and 11 in GENERIC_AMP_LEVELS  # 1 A granularity


def test_charging_model_single():
    model = ChargingModel.from_config(SINGLE_CONFIG)
    assert model.phase_count == 1
    assert model.effective_voltage == 230
    assert model.amp_levels == CHARGER_AMP_LEVELS
    assert model.charger_model == CHARGER_MODEL_TUYA
    assert model.production_entities() == ["sensor.pv"]
    assert model.grid_import_entities() == ["sensor.grid"]
    # 3680 W single-phase → 16 A
    assert model.watts_to_amps(3680) == pytest.approx(16.0)


def test_charging_model_three_phase():
    model = ChargingModel.from_config(THREE_CONFIG)
    assert model.phase_count == 3
    assert model.effective_voltage == 690
    assert model.amp_levels == GENERIC_AMP_LEVELS
    assert model.production_entities() == ["sensor.pv1", "sensor.pv2", "sensor.pv3"]
    assert model.consumption_entities() == ["sensor.cons1", "sensor.cons2", "sensor.cons3"]
    assert model.grid_import_entities() == ["sensor.grid1", "sensor.grid2", "sensor.grid3"]
    # 11040 W total / 690 → 16 A per phase
    assert model.watts_to_amps(11040) == pytest.approx(16.0)
    # labelled list gains Ln suffixes (9 power sensors in three-phase)
    labelled = model.labelled_power_entities()
    assert len(labelled) == 9
    assert ("sensor.pv2", "Solar Production L2") in labelled


# ----------------------------------------------------------------------------
# AmperageCalculator parametrization
# ----------------------------------------------------------------------------


def test_amperage_calculator_default_is_tuya():
    """No amp_levels arg → Tuya discrete behaviour preserved."""
    assert AmperageCalculator.get_next_level_down(16) == 13
    assert AmperageCalculator.get_next_level_up(13, 32) == 16
    assert AmperageCalculator.get_next_level_down(6) == 0  # at minimum → stop


def test_amperage_calculator_generic_levels():
    """Generic 1 A levels step by one ampere."""
    assert AmperageCalculator.get_next_level_down(11, GENERIC_AMP_LEVELS) == 10
    assert AmperageCalculator.get_next_level_up(11, 32, GENERIC_AMP_LEVELS) == 12
    assert AmperageCalculator.get_next_level_down(6, GENERIC_AMP_LEVELS) == 0
    assert AmperageCalculator.get_next_level_up(31, 32, GENERIC_AMP_LEVELS) == 32


# ----------------------------------------------------------------------------
# Power readers (need hass for state)
# ----------------------------------------------------------------------------


async def test_read_production_sums_phases(hass):
    """Three-phase production = sum of the three phase sensors."""
    hass.states.async_set("sensor.pv1", "1000")
    hass.states.async_set("sensor.pv2", "1500")
    hass.states.async_set("sensor.pv3", "500")
    model = ChargingModel.from_config(THREE_CONFIG)
    assert model.read_production(hass) == pytest.approx(3000.0)


async def test_read_production_single_phase_unchanged(hass):
    """Single-phase production reads exactly the one configured sensor."""
    hass.states.async_set("sensor.pv", "2200")
    model = ChargingModel.from_config(SINGLE_CONFIG)
    assert model.read_production(hass) == pytest.approx(2200.0)


# ----------------------------------------------------------------------------
# Battery-discharge reader (v2.1.0 — issue #29)
# ----------------------------------------------------------------------------


def test_read_battery_discharge_none_when_unconfigured():
    """No battery sensor mapped → None (distinct from a real 0 W reading)."""
    model = ChargingModel.from_config(SINGLE_CONFIG)
    assert model._battery_power_entity is None
    # hass unused on the None path
    assert model.read_battery_discharge(hass=None) is None


async def test_read_battery_discharge_sign_convention(hass):
    """Negative raw = discharging → positive watts; positive raw → 0."""
    config = dict(SINGLE_CONFIG)
    config[CONF_BATTERY_POWER] = "sensor.battery_power"
    model = ChargingModel.from_config(config)

    hass.states.async_set("sensor.battery_power", "-1800")  # discharging 1800 W
    assert model.read_battery_discharge(hass) == pytest.approx(1800.0)

    hass.states.async_set("sensor.battery_power", "1200")  # charging → no discharge
    assert model.read_battery_discharge(hass) == pytest.approx(0.0)

    hass.states.async_set("sensor.battery_power", "0")
    assert model.read_battery_discharge(hass) == pytest.approx(0.0)


# ----------------------------------------------------------------------------
# Charging-power reader + drawing-now SSOT (v2.2.0)
# ----------------------------------------------------------------------------


def test_read_charging_power_none_when_unconfigured():
    """No charging-power sensor mapped → None (status fallback territory)."""
    model = ChargingModel.from_config(SINGLE_CONFIG)
    assert model.charging_power_entities() == []
    assert model.read_charging_power(hass=None) is None


async def test_read_charging_power_single_phase(hass):
    """Single-phase reads the one configured sensor."""
    config = dict(SINGLE_CONFIG)
    config[CONF_CHARGING_POWER] = "sensor.cp"
    model = ChargingModel.from_config(config)
    hass.states.async_set("sensor.cp", "3680")
    assert model.read_charging_power(hass) == pytest.approx(3680.0)


async def test_read_charging_power_sums_three_phases(hass):
    """Three-phase charging power = sum of the three phase sensors."""
    config = dict(THREE_CONFIG)
    config[CONF_CHARGING_POWER] = "sensor.cp1"
    config[CONF_CHARGING_POWER_L2] = "sensor.cp2"
    config[CONF_CHARGING_POWER_L3] = "sensor.cp3"
    model = ChargingModel.from_config(config)
    hass.states.async_set("sensor.cp1", "3680")
    hass.states.async_set("sensor.cp2", "3680")
    hass.states.async_set("sensor.cp3", "3680")
    assert model.read_charging_power(hass) == pytest.approx(11040.0)


async def test_read_charging_power_reversed_sign_clamps_to_zero(hass):
    """A reversed-sign sensor (negative while charging) reads a flat 0 W."""
    config = dict(SINGLE_CONFIG)
    config[CONF_CHARGING_POWER] = "sensor.cp"
    model = ChargingModel.from_config(config)
    hass.states.async_set("sensor.cp", "-3680")
    assert model.read_charging_power(hass) == pytest.approx(0.0)


async def test_read_charging_power_normalizes_kw_to_watts(hass):
    """A kW-unit sensor (Tuya/Easee/Wallbox/go-e) is normalized to watts so the
    backend floor and the frontend agree (else a real session reads < floor)."""
    config = dict(SINGLE_CONFIG)
    config[CONF_CHARGING_POWER] = "sensor.cp"
    model = ChargingModel.from_config(config)
    hass.states.async_set("sensor.cp", "3.68", {"unit_of_measurement": "kW"})
    assert model.read_charging_power(hass) == pytest.approx(3680.0)
    # And the verdict is "charging" (3680 W > floor), not a false negative.
    assert model.is_charging(hass) is True


async def test_read_charging_power_genuine_zero(hass):
    """A real 0 W reading is 0.0, NOT None (distinct from unconfigured)."""
    config = dict(SINGLE_CONFIG)
    config[CONF_CHARGING_POWER] = "sensor.cp"
    model = ChargingModel.from_config(config)
    hass.states.async_set("sensor.cp", "0")
    assert model.read_charging_power(hass) == pytest.approx(0.0)


async def test_read_charging_power_unavailable_returns_none(hass):
    """A mapped-but-unavailable sensor → None (cannot measure)."""
    config = dict(SINGLE_CONFIG)
    config[CONF_CHARGING_POWER] = "sensor.cp"
    model = ChargingModel.from_config(config)
    hass.states.async_set("sensor.cp", "unavailable")
    assert model.read_charging_power(hass) is None


async def test_read_charging_power_partial_three_phase_returns_none(hass):
    """All-or-nothing: one missing phase → None, never a misleading partial sum."""
    config = dict(THREE_CONFIG)
    config[CONF_CHARGING_POWER] = "sensor.cp1"
    config[CONF_CHARGING_POWER_L2] = "sensor.cp2"
    config[CONF_CHARGING_POWER_L3] = "sensor.cp3"
    model = ChargingModel.from_config(config)
    hass.states.async_set("sensor.cp1", "3680")
    hass.states.async_set("sensor.cp2", "3680")
    hass.states.async_set("sensor.cp3", "unknown")
    assert model.read_charging_power(hass) is None


async def test_is_charging_measured_above_and_below_floor(hass):
    """Stateless drawing-now: power > floor → True, below → False."""
    config = dict(SINGLE_CONFIG)
    config[CONF_CHARGING_POWER] = "sensor.cp"
    model = ChargingModel.from_config(config)

    hass.states.async_set("sensor.cp", str(CHARGING_POWER_DRAWING_FLOOR_W + 1000))
    assert model.is_charging(hass) is True

    hass.states.async_set("sensor.cp", str(CHARGING_POWER_DRAWING_FLOOR_W - 50))
    assert model.is_charging(hass) is False


async def test_is_charging_measured_overrides_lying_status(hass):
    """Measured 0 W beats a wallbox stuck on 'charger_charging' (the blind spot)."""
    config = dict(SINGLE_CONFIG)
    config[CONF_CHARGING_POWER] = "sensor.cp"
    config[CONF_EV_CHARGER_STATUS] = "sensor.status"
    model = ChargingModel.from_config(config)
    hass.states.async_set("sensor.cp", "0")
    hass.states.async_set("sensor.status", CHARGER_STATUS_CHARGING)
    assert model.is_charging(hass) is False


async def test_is_charging_falls_back_to_status_when_no_power_sensor(hass):
    """No power sensor → legacy status string drives the verdict (byte-for-byte)."""
    config = dict(SINGLE_CONFIG)
    config[CONF_EV_CHARGER_STATUS] = "sensor.status"
    model = ChargingModel.from_config(config)

    hass.states.async_set("sensor.status", CHARGER_STATUS_CHARGING)
    assert model.is_charging(hass) is True

    hass.states.async_set("sensor.status", CHARGER_STATUS_FREE)
    assert model.is_charging(hass) is False


async def test_is_charging_false_when_nothing_configured(hass):
    """No power sensor and no status → False (never crashes on None)."""
    model = ChargingModel.from_config(SINGLE_CONFIG)
    assert model.is_charging(hass) is False


async def test_is_charging_status_fallback_is_tolerant(hass):
    """No power sensor: a non-Tuya brand string ('Charging') still counts as
    charging (tolerant blocklist), matching the frontend; idle strings do not."""
    config = dict(SINGLE_CONFIG)
    config[CONF_EV_CHARGER_STATUS] = "sensor.status"
    model = ChargingModel.from_config(config)

    hass.states.async_set("sensor.status", "Charging")  # brand-specific string
    assert model.is_charging(hass) is True

    hass.states.async_set("sensor.status", "charger_wait")  # transitional → idle
    assert model.is_charging(hass) is False


async def test_is_plugged_in_status_semantics(hass):
    """Plugged-in reads status: FREE/unavailable → False, anything else → True."""
    config = dict(SINGLE_CONFIG)
    config[CONF_EV_CHARGER_STATUS] = "sensor.status"
    model = ChargingModel.from_config(config)

    hass.states.async_set("sensor.status", CHARGER_STATUS_FREE)
    assert model.is_plugged_in(hass) is False

    hass.states.async_set("sensor.status", CHARGER_STATUS_CHARGING)
    assert model.is_plugged_in(hass) is True

    hass.states.async_set("sensor.status", "unavailable")
    assert model.is_plugged_in(hass) is False


# ----------------------------------------------------------------------------
# Charger-model-gated decrease (the headline behaviour)
# ----------------------------------------------------------------------------


def _make_controller(hass, charger_model: str) -> ChargerController:
    config = {
        CONF_EV_CHARGER_SWITCH: "switch.charger",
        CONF_EV_CHARGER_CURRENT: "number.charger_current",
        CONF_CHARGER_MODEL: charger_model,
    }
    return ChargerController(hass, "entry_id", config)


async def test_tuya_decrease_uses_stop_set_start(hass):
    """Tuya: lowering amperage turns the charger off then on (safe sequence)."""
    controller = _make_controller(hass, CHARGER_MODEL_TUYA)
    controller._is_on = True
    controller._current_amperage = 16
    controller._refresh_state = AsyncMock()
    controller._call_service = AsyncMock()
    controller._set_amperage_internal = AsyncMock()

    op = await controller._set_amperage_unlocked(10)

    assert op == "adjust_down"
    # turn_off then turn_on were both issued
    services = [c.args[1] for c in controller._call_service.await_args_list]
    assert "turn_off" in services
    assert "turn_on" in services


async def test_generic_decrease_is_live_no_stop(hass):
    """Generic: lowering amperage sets the value live, never stops the charger."""
    controller = _make_controller(hass, CHARGER_MODEL_GENERIC)
    controller._is_on = True
    controller._current_amperage = 16
    controller._refresh_state = AsyncMock()
    controller._call_service = AsyncMock()
    controller._set_amperage_internal = AsyncMock()

    op = await controller._set_amperage_unlocked(10)

    assert op == "set_amperage"
    controller._set_amperage_internal.assert_awaited_once_with(10)
    # the charger switch was never toggled
    services = [c.args[1] for c in controller._call_service.await_args_list]
    assert "turn_off" not in services
    assert "turn_on" not in services


def test_controller_normalizes_to_model_levels(hass):
    """Generic snaps to the nearest integer; Tuya snaps to discrete levels."""
    tuya = _make_controller(hass, CHARGER_MODEL_TUYA)
    generic = _make_controller(hass, CHARGER_MODEL_GENERIC)
    # 11 A: Tuya → nearest discrete (10), generic → 11 (valid level)
    assert tuya._normalize_target_amps(11) == 10
    assert generic._normalize_target_amps(11) == 11


# ----------------------------------------------------------------------------
# Drawing-now SSOT in the controller (v2.2.0) + byte-for-byte fallback
# ----------------------------------------------------------------------------


async def test_is_charging_no_power_sensor_uses_switch_echo(hass):
    """THE sacred regression guard: charger_controller.is_charging() stays
    commanded-on (switch echo) and is unaffected by the v2.2.0 SSOT. With no
    power sensor mapped (default), it reflects _is_on exactly as pre-v2.2."""
    controller = _make_controller(hass, CHARGER_MODEL_TUYA)
    assert controller._measured_power_w is None  # no power sensor

    controller._is_on = True
    assert await controller.is_charging() is True

    controller._is_on = False
    assert await controller.is_charging() is False


async def test_tuya_decrease_uses_sequence_regardless_of_measured_power(hass):
    """v2.2.0 control is commanded-only: a Tuya decrease while commanded-on uses
    the safe stop/set/start sequence even if measured power momentarily reads 0 W
    (a glitch/trickle must never trigger a live current change on Tuya)."""
    controller = _make_controller(hass, CHARGER_MODEL_TUYA)
    controller._is_on = True            # commanded on
    controller._current_amperage = 16
    controller._measured_power_w = 0.0  # measured low — must NOT change the gate
    controller._refresh_state = AsyncMock()  # keep the manual cache values
    controller._call_service = AsyncMock()
    controller._set_amperage_internal = AsyncMock()

    op = await controller._set_amperage_unlocked(10)

    assert op == "adjust_down"
    services = [c.args[1] for c in controller._call_service.await_args_list]
    assert "turn_off" in services
    assert "turn_on" in services
