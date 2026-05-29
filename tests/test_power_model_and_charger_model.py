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
    CONF_CHARGER_MODEL,
    CONF_EV_CHARGER_CURRENT,
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
