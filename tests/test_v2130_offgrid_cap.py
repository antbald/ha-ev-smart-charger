"""Tests for v2.13.0 — off-grid amperage ceiling for Solar Surplus (issue #57).

While the optional ``grid_available`` binary_sensor reads explicitly OFF (the
hybrid inverter is islanded), Solar Surplus must not size the charger from PV
surplus alone: an islanded inverter's real per-phase AC-output capacity can be
well below what abundant PV + battery would otherwise supply, and the excess
trips an AC over-current fault.

The ceiling is opt-in (default 32 A = off) and fail-safe: unmapped or
unavailable ``grid_available`` reads as "don't act", so no existing install
changes behaviour.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.ev_smart_charger.solar_surplus import SolarSurplusAutomation
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
    CONF_GRID_AVAILABLE,
    CONF_SOC_HOME,
)

OFFGRID_ENTITY = "number.offgrid_max"
GRID_AVAILABLE_ENTITY = "binary_sensor.grid_available"


def _build(hass, controller, balancer, *, map_grid_sensor=True):
    config = {
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        CONF_FV_PRODUCTION: "sensor.solar",
        CONF_HOME_CONSUMPTION: "sensor.consumption",
        CONF_GRID_IMPORT: "sensor.grid",
        CONF_SOC_HOME: "sensor.home_soc",
    }
    if map_grid_sensor:
        config[CONF_GRID_AVAILABLE] = GRID_AVAILABLE_ENTITY

    with patch(
        "custom_components.ev_smart_charger.solar_surplus.AstralTimeService"
    ) as mock_astral:
        mock_astral.return_value.is_nighttime.return_value = False
        auto = SolarSurplusAutomation(
            hass, "test_entry", config, balancer, controller
        )
    auto._offgrid_max_amperage_entity = OFFGRID_ENTITY
    return auto


@pytest.fixture
def automation(hass, mock_charger_controller, mock_priority_balancer):
    return _build(hass, mock_charger_controller, mock_priority_balancer)


# ── Fail-safe gating ────────────────────────────────────────────


async def test_no_cap_when_grid_sensor_unmapped(
    hass, mock_charger_controller, mock_priority_balancer
):
    """No grid_available sensor → is_grid_available() is None → never caps."""
    auto = _build(
        hass, mock_charger_controller, mock_priority_balancer, map_grid_sensor=False
    )
    hass.states.async_set(OFFGRID_ENTITY, "10")
    assert auto._get_offgrid_cap_amps() is None


@pytest.mark.parametrize("state", ["unavailable", "unknown"])
async def test_no_cap_when_grid_sensor_unavailable(hass, automation, state):
    """A boot-time / integration-restart flap must never cap the charger."""
    hass.states.async_set(GRID_AVAILABLE_ENTITY, state)
    hass.states.async_set(OFFGRID_ENTITY, "10")
    assert automation._get_offgrid_cap_amps() is None


async def test_no_cap_when_grid_present(hass, automation):
    """Grid up → full amperage stays available (the whole point vs solar_max)."""
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "on")
    hass.states.async_set(OFFGRID_ENTITY, "10")
    assert automation._get_offgrid_cap_amps() is None


async def test_no_cap_at_default_32a(hass, automation):
    """Default 32 A = off, even while off-grid → byte-for-byte legacy."""
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "off")
    hass.states.async_set(OFFGRID_ENTITY, "32")
    assert automation._get_offgrid_cap_amps() is None


# ── Snapping ────────────────────────────────────────────────────


async def test_cap_applies_when_offgrid(hass, automation):
    """Off-grid + ceiling below the top level → the ceiling applies."""
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "off")
    hass.states.async_set(OFFGRID_ENTITY, "16")
    assert automation._get_offgrid_cap_amps() == 16


async def test_cap_snaps_down_to_valid_amp_level(hass, automation):
    """A ceiling between two levels snaps DOWN, never up (17 A → 16 A)."""
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "off")
    hass.states.async_set(OFFGRID_ENTITY, "17")
    assert automation._get_offgrid_cap_amps() == 16


async def test_cap_never_below_charger_floor(hass, automation):
    """A ceiling under the 6 A floor clamps to the floor, not to an invalid 0."""
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "off")
    hass.states.async_set(OFFGRID_ENTITY, "4")
    assert automation._get_offgrid_cap_amps() == automation._amp_levels[0]


# ── Enforcement ─────────────────────────────────────────────────


def _prepare_tick(hass, automation, *, current_amps):
    """Minimal state so _async_periodic_check reaches the enforcement gate."""
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "off")
    hass.states.async_set(OFFGRID_ENTITY, "10")
    hass.states.async_set("sensor.solar", "6000")
    hass.states.async_set("sensor.consumption", "500")
    hass.states.async_set("sensor.grid", "0")
    hass.states.async_set("sensor.charger_status", "charger_charging")
    automation.charger_controller.is_charging = AsyncMock(return_value=True)
    automation.charger_controller.get_current_amperage = AsyncMock(
        return_value=current_amps
    )
    automation.charger_controller.set_amperage = AsyncMock()
    automation._ensure_control = AsyncMock(return_value=True)
    automation._update_diagnostic_sensor = AsyncMock()


async def test_running_session_over_ceiling_is_clamped_immediately(hass, automation):
    """A session already running above the ceiling drops to it in ONE step."""
    _prepare_tick(hass, automation, current_amps=20)

    await automation._offgrid_overload_guard(charger_is_on=True, current_amps=20)

    automation.charger_controller.set_amperage.assert_awaited_once()
    assert automation.charger_controller.set_amperage.await_args.args[0] == 10


async def test_session_at_or_below_ceiling_is_not_touched(hass, automation):
    """No spurious charger operation when already at/below the ceiling."""
    _prepare_tick(hass, automation, current_amps=10)

    await automation._offgrid_overload_guard(charger_is_on=True, current_amps=10)

    automation.charger_controller.set_amperage.assert_not_awaited()


async def test_guard_is_noop_when_charger_off(hass, automation):
    """Nothing to clamp when the charger is not running."""
    _prepare_tick(hass, automation, current_amps=0)

    await automation._offgrid_overload_guard(charger_is_on=False, current_amps=0)

    automation.charger_controller.set_amperage.assert_not_awaited()


async def test_guard_is_noop_when_grid_present(hass, automation):
    """Grid up → a high-amperage session is left alone."""
    _prepare_tick(hass, automation, current_amps=20)
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "on")

    await automation._offgrid_overload_guard(charger_is_on=True, current_amps=20)

    automation.charger_controller.set_amperage.assert_not_awaited()
