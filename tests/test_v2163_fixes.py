"""Tests for v2.16.3 — issue #69 (hybrid caps, night grid-start hold)."""
import pytest
from unittest.mock import MagicMock, patch

from custom_components.ev_smart_charger.const import GRID_RESTORE_STABLE_SECONDS
from custom_components.ev_smart_charger.hybrid_inverter_mode import (
    HybridInverterMode,
)
from custom_components.ev_smart_charger.night_smart_charge import NightSmartCharge
from custom_components.ev_smart_charger.utils.amperage_helper import StabilityTracker

from .test_v2130_offgrid_cap import (
    GRID_AVAILABLE_ENTITY,
    OFFGRID_ENTITY,
    _build,
)


@pytest.fixture
def automation(hass, mock_charger_controller, mock_priority_balancer):
    return _build(hass, mock_charger_controller, mock_priority_balancer)


# ── #69a: caps enforced while Hybrid Mode is in charge ─────────


async def test_effective_cap_takes_offgrid_min(hass, automation):
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "off")
    hass.states.async_set(OFFGRID_ENTITY, "10")
    assert automation.get_effective_cap_amps() <= 10


async def test_effective_cap_ignores_offgrid_when_grid_up(hass, automation):
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "on")
    hass.states.async_set(OFFGRID_ENTITY, "10")
    assert automation.get_effective_cap_amps() > 10


async def test_clamp_running_charger_above_cap(
    hass, automation, mock_charger_controller
):
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "off")
    hass.states.async_set(OFFGRID_ENTITY, "10")
    automation._ensure_control = MagicMock()

    async def _ok(*_a, **_k):
        return True

    automation._ensure_control = _ok
    cap = automation.get_effective_cap_amps()
    assert await automation._clamp_to_caps_for_hybrid(True, 20) is True
    args = mock_charger_controller.set_amperage.call_args[0]
    assert args[0] == cap


async def test_no_clamp_when_off_or_within_cap(
    hass, automation, mock_charger_controller
):
    hass.states.async_set(GRID_AVAILABLE_ENTITY, "off")
    hass.states.async_set(OFFGRID_ENTITY, "10")
    assert await automation._clamp_to_caps_for_hybrid(False, 20) is False
    assert await automation._clamp_to_caps_for_hybrid(True, 8) is False
    mock_charger_controller.set_amperage.assert_not_called()


def test_hybrid_apply_caps_uses_owner_cap():
    hybrid = HybridInverterMode.__new__(HybridInverterMode)
    hybrid._solar_surplus = MagicMock()
    hybrid._solar_surplus.get_effective_cap_amps.return_value = 10
    assert hybrid._apply_caps(32) == 10
    assert hybrid._apply_caps(8) == 8


def test_hybrid_apply_caps_without_owner():
    hybrid = HybridInverterMode.__new__(HybridInverterMode)
    hybrid._solar_surplus = None
    assert hybrid._apply_caps(24) == 24


# ── #69b: night grid-mode start hold while the grid is absent ──


def _night(grid_state):
    nsc = NightSmartCharge.__new__(NightSmartCharge)
    nsc.hass = MagicMock()
    nsc._start_grid_hold = False
    nsc._start_grid_tracker = StabilityTracker()
    nsc._power_model = MagicMock()
    nsc._power_model.is_grid_available.return_value = grid_state
    return nsc


def test_start_blocked_while_grid_off():
    nsc = _night(False)
    assert nsc._grid_start_blocked() is True
    assert nsc._start_grid_hold is True


def test_start_not_blocked_when_sensor_unmapped():
    assert _night(None)._grid_start_blocked() is False


def test_start_held_until_grid_stable():
    nsc = _night(False)
    nsc._grid_start_blocked()
    nsc._power_model.is_grid_available.return_value = True
    assert nsc._grid_start_blocked() is True  # just restored, not stable yet
    with patch.object(StabilityTracker, "is_stable", return_value=True) as st:
        assert nsc._grid_start_blocked() is False
        st.assert_called_with(GRID_RESTORE_STABLE_SECONDS)
    assert nsc._start_grid_hold is False


def test_unknown_during_hold_restarts_window():
    nsc = _night(False)
    nsc._grid_start_blocked()
    nsc._power_model.is_grid_available.return_value = True
    nsc._grid_start_blocked()
    nsc._power_model.is_grid_available.return_value = None
    assert nsc._grid_start_blocked() is True
    assert nsc._start_grid_tracker._stable_since is None
