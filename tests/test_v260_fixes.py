"""Isolated unit tests for the v2.6.0 mass bug-fix release.

These cover the highest-risk new logic in a way that does NOT depend on the
fragile full-HA night-charge / solar-surplus harness (whose pre-existing
environmental failures are unrelated to this release):

- issue #36: ChargingModel.is_grid_available fail-safe reader.
- issue #42: AstralTimeService.is_nighttime nighttime-window offsets.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.ev_smart_charger.const import (
    CONF_FV_PRODUCTION,
    CONF_GRID_AVAILABLE,
    CONF_GRID_IMPORT,
    CONF_HOME_CONSUMPTION,
)
from custom_components.ev_smart_charger.power_model import ChargingModel
from custom_components.ev_smart_charger.utils.astral_time_service import (
    AstralTimeService,
)

import homeassistant.util.dt as dt_util


_BASE_CONFIG = {
    CONF_FV_PRODUCTION: "sensor.pv",
    CONF_HOME_CONSUMPTION: "sensor.cons",
    CONF_GRID_IMPORT: "sensor.grid",
}


# ----------------------------------------------------------------------------
# issue #36 — grid_available fail-safe reader
# ----------------------------------------------------------------------------
def test_grid_available_none_when_unmapped():
    """No sensor mapped → None (feature off, never stops the session)."""
    model = ChargingModel.from_config(_BASE_CONFIG)
    assert model.is_grid_available(hass=None) is None


async def test_grid_available_true_on(hass):
    config = {**_BASE_CONFIG, CONF_GRID_AVAILABLE: "binary_sensor.grid"}
    model = ChargingModel.from_config(config)
    hass.states.async_set("binary_sensor.grid", "on")
    assert model.is_grid_available(hass) is True


async def test_grid_available_false_off(hass):
    config = {**_BASE_CONFIG, CONF_GRID_AVAILABLE: "binary_sensor.grid"}
    model = ChargingModel.from_config(config)
    hass.states.async_set("binary_sensor.grid", "off")
    assert model.is_grid_available(hass) is False


@pytest.mark.parametrize("bad_state", ["unavailable", "unknown"])
async def test_grid_available_none_on_invalid_state(hass, bad_state):
    """Fail-safe: an unavailable/unknown sensor must NOT read as 'grid lost'.

    This is the bug caught in adversarial review: get_bool(default=False) would
    have collapsed these to False and spuriously stopped the night session at
    boot or on an inverter-integration restart.
    """
    config = {**_BASE_CONFIG, CONF_GRID_AVAILABLE: "binary_sensor.grid"}
    model = ChargingModel.from_config(config)
    hass.states.async_set("binary_sensor.grid", bad_state)
    assert model.is_grid_available(hass) is None


# ----------------------------------------------------------------------------
# issue #42 — nighttime-window offsets
# ----------------------------------------------------------------------------
def _at(hour: int, minute: int = 0):
    return dt_util.now().replace(hour=hour, minute=minute, second=0, microsecond=0)


def _service_with_fixed_sun(hass):
    """AstralTimeService whose sunset=18:00 and sunrise=06:00 (today)."""
    svc = AstralTimeService(hass)
    sunset = _at(18, 0)
    sunrise = _at(6, 0)
    return svc, sunset, sunrise


def test_is_nighttime_default_offsets_unchanged(hass):
    svc, sunset, sunrise = _service_with_fixed_sun(hass)
    with patch.object(svc, "get_sunset", return_value=sunset), patch.object(
        svc, "get_sunrise", return_value=sunrise
    ):
        # 17:30 is daytime with no offsets.
        assert svc.is_nighttime(_at(17, 30)) is False
        # 06:30 is daytime with no offsets.
        assert svc.is_nighttime(_at(6, 30)) is False
        # 22:00 / 03:00 are night regardless.
        assert svc.is_nighttime(_at(22, 0)) is True
        assert svc.is_nighttime(_at(3, 0)) is True


def test_is_nighttime_sunset_offset_starts_night_earlier(hass):
    svc, sunset, sunrise = _service_with_fixed_sun(hass)
    with patch.object(svc, "get_sunset", return_value=sunset), patch.object(
        svc, "get_sunrise", return_value=sunrise
    ):
        # 17:30 with a 60-min pre-sunset offset → night begins at 17:00.
        assert svc.is_nighttime(_at(17, 30), 60, 0) is True
        # 16:30 still daytime (before the 17:00 extended start).
        assert svc.is_nighttime(_at(16, 30), 60, 0) is False


def test_is_nighttime_sunrise_offset_ends_night_later(hass):
    svc, sunset, sunrise = _service_with_fixed_sun(hass)
    with patch.object(svc, "get_sunset", return_value=sunset), patch.object(
        svc, "get_sunrise", return_value=sunrise
    ):
        # 06:30 with a 60-min post-sunrise offset → night ends at 07:00.
        assert svc.is_nighttime(_at(6, 30), 0, 60) is True
        # 07:30 is daytime again (after the 07:00 extended end).
        assert svc.is_nighttime(_at(7, 30), 0, 60) is False
