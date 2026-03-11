"""Test SmartChargerBlocker logic."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from custom_components.ev_smart_charger.automation_coordinator import (
    AutomationCoordinator,
    PRIORITY_NIGHT_CHARGE,
    PRIORITY_SMART_BLOCKER,
)
from custom_components.ev_smart_charger.automations import SmartChargerBlocker
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_STATUS,
)


@pytest.fixture
def blocker(hass, mock_charger_controller):
    """Create a SmartChargerBlocker instance."""
    config = {
        CONF_EV_CHARGER_SWITCH: "switch.charger",
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
    }

    # Mock NightSmartCharge dependency
    mock_nsc = MagicMock()
    mock_nsc.is_active.return_value = False

    with patch("custom_components.ev_smart_charger.automations.AstralTimeService") as mock_astral:
        instance = SmartChargerBlocker(
            hass, "test_entry", config, mock_nsc, mock_charger_controller
        )

        # Mock helper entities
        instance._forza_ricarica_entity = "switch.force_charge"
        instance._blocker_enabled_entity = "switch.blocker_enabled"
        instance._night_charge_time_entity = "input_datetime.night_charge_time"

        return instance


async def test_should_block_charging_normal(hass, blocker):
    """Test blocking logic in normal conditions."""
    # Setup
    hass.states.async_set("switch.force_charge", "off")
    hass.states.async_set("switch.blocker_enabled", "on")

    # Case 1: In blocking window
    blocker._astral_service.is_in_blocking_window.return_value = (True, "Sunset")
    should_block, reason = await blocker._should_block_charging()
    assert should_block is True
    assert "Sunset" in reason

    # Case 2: Outside blocking window
    blocker._astral_service.is_in_blocking_window.return_value = (False, "Daytime")
    should_block, reason = await blocker._should_block_charging()
    assert should_block is False


async def test_should_block_overrides(hass, blocker):
    """Test overrides (Forza Ricarica, Blocker Disabled)."""
    # Case 1: Forza Ricarica ON
    hass.states.async_set("switch.force_charge", "on")
    hass.states.async_set("switch.blocker_enabled", "on")
    blocker._astral_service.is_in_blocking_window.return_value = (True, "Sunset")

    should_block, reason = await blocker._should_block_charging()
    assert should_block is False
    assert "Forza Ricarica" in reason

    # Case 2: Blocker Disabled
    hass.states.async_set("switch.force_charge", "off")
    hass.states.async_set("switch.blocker_enabled", "off")

    should_block, reason = await blocker._should_block_charging()
    assert should_block is False
    assert "disabled" in reason


async def test_should_not_block_when_boost_active(hass, blocker):
    """Boost Charge should bypass Smart Charger Blocker while active."""
    hass.states.async_set("switch.force_charge", "off")
    hass.states.async_set("switch.blocker_enabled", "on")
    blocker._boost_charge = MagicMock()
    blocker._boost_charge.is_active.return_value = True

    should_block, reason = await blocker._should_block_charging()

    assert should_block is False
    assert "Boost Charge" in reason

async def test_check_and_block_execution(hass, blocker):
    """Test the execution of blocking action."""
    hass.states.async_set("switch.force_charge", "off")
    hass.states.async_set("switch.blocker_enabled", "on")
    blocker._astral_service.is_in_blocking_window.return_value = (True, "Sunset")

    # Register persistent_notification.create service
    hass.services.async_register("persistent_notification", "create", lambda service: None)

    await blocker._check_and_block_if_needed("Test Trigger")

    # Verify charger stopped
    blocker.charger_controller.stop_charger.assert_called_once()
    assert blocker._currently_blocking is True


async def _assign_blocker_control(blocker, hass):
    """Assign coordinator ownership to Smart Charger Blocker."""
    coordinator = AutomationCoordinator(hass, "test-entry")
    blocker._coordinator = coordinator
    blocker._currently_blocking = True
    blocker._enforcement_start_time = datetime(2026, 3, 9, 0, 0, 0)

    allowed, _ = await coordinator.request_charger_action(
        automation_name="Smart Charger Blocker",
        action="turn_off",
        reason="Nighttime block",
        priority=PRIORITY_SMART_BLOCKER,
    )

    assert allowed is True
    assert coordinator.is_automation_active("Smart Charger Blocker") is True
    return coordinator


async def test_allow_charging_releases_stale_blocker_ownership(hass, blocker):
    """Allowing charging must release stale coordinator ownership."""
    coordinator = await _assign_blocker_control(blocker, hass)
    hass.states.async_set("switch.force_charge", "off")
    hass.states.async_set("switch.blocker_enabled", "on")
    blocker._astral_service.is_in_blocking_window.return_value = (
        False,
        "Outside blocking window (daytime allowed)",
    )

    await blocker._check_and_block_if_needed("Test Trigger")

    assert blocker._currently_blocking is False
    assert blocker._enforcement_start_time is None
    assert coordinator.get_active_automation() is None


@pytest.mark.parametrize(
    ("force_state", "blocker_state"),
    [
        ("on", "on"),
        ("off", "off"),
    ],
)
async def test_non_blocking_early_exits_release_blocker_ownership(
    hass, blocker, force_state, blocker_state
):
    """Early exits that disable blocking must release stale coordinator ownership."""
    coordinator = await _assign_blocker_control(blocker, hass)
    hass.states.async_set("switch.force_charge", force_state)
    hass.states.async_set("switch.blocker_enabled", blocker_state)

    await blocker._check_and_block_if_needed("Test Trigger")

    assert blocker._currently_blocking is False
    assert blocker._enforcement_start_time is None
    assert coordinator.get_active_automation() is None


async def test_night_charge_can_acquire_control_after_blocker_allows(hass, blocker):
    """Night Smart Charge must acquire control once blocker allows charging."""
    coordinator = await _assign_blocker_control(blocker, hass)
    hass.states.async_set("switch.force_charge", "off")
    hass.states.async_set("switch.blocker_enabled", "on")
    blocker._astral_service.is_in_blocking_window.return_value = (
        False,
        "Outside blocking window (daytime allowed)",
    )

    await blocker._check_and_block_if_needed("Test Trigger")

    allowed, reason = await coordinator.request_charger_action(
        automation_name="Night Smart Charge",
        action="turn_on",
        reason="Scheduled night charge",
        priority=PRIORITY_NIGHT_CHARGE,
    )

    assert allowed is True
    assert reason == "Action allowed"
    assert coordinator.is_automation_active("Night Smart Charge") is True


async def test_periodic_recheck_releases_blocker_when_conditions_clear(hass, blocker):
    """Periodic re-check must release blocker ownership after the blocking window ends."""
    coordinator = await _assign_blocker_control(blocker, hass)
    hass.states.async_set("switch.force_charge", "off")
    hass.states.async_set("switch.blocker_enabled", "on")
    blocker._astral_service.is_in_blocking_window.return_value = (
        False,
        "Outside blocking window (daytime allowed)",
    )

    await blocker._async_periodic_enforcement_check(datetime(2026, 3, 9, 7, 0, 0))

    assert blocker._currently_blocking is False
    assert blocker._enforcement_start_time is None
    assert coordinator.get_active_automation() is None


async def test_periodic_recheck_releases_stale_owner_without_enforcement(hass, blocker):
    """Periodic re-check must release stale coordinator ownership even without enforcement state."""
    coordinator = AutomationCoordinator(hass, "test-entry")
    blocker._coordinator = coordinator

    allowed, _ = await coordinator.request_charger_action(
        automation_name="Smart Charger Blocker",
        action="turn_off",
        reason="Stale owner",
        priority=PRIORITY_SMART_BLOCKER,
    )

    assert allowed is True
    assert coordinator.is_automation_active("Smart Charger Blocker") is True
    assert blocker._currently_blocking is False

    await blocker._async_periodic_enforcement_check(datetime(2026, 3, 9, 7, 0, 0))

    assert coordinator.get_active_automation() is None
