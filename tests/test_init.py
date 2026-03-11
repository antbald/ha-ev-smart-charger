"""Tests for integration setup and unload."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.ev_smart_charger as integration
from custom_components.ev_smart_charger.const import (
    CONF_CAR_OWNER,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_FV_PRODUCTION,
    CONF_GRID_IMPORT,
    CONF_HOME_CONSUMPTION,
    CONF_NOTIFY_SERVICES,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    DOMAIN,
    TOTAL_INTEGRATION_ENTITIES,
)
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData


def _build_entry() -> MockConfigEntry:
    """Create a representative config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EV_CHARGER_SWITCH: "switch.charger",
            CONF_EV_CHARGER_CURRENT: "number.charger_current",
            CONF_EV_CHARGER_STATUS: "sensor.charger_status",
            CONF_SOC_CAR: "sensor.car_soc",
            CONF_SOC_HOME: "sensor.home_soc",
            CONF_FV_PRODUCTION: "sensor.solar",
            CONF_HOME_CONSUMPTION: "sensor.home_consumption",
            CONF_GRID_IMPORT: "sensor.grid_import",
            CONF_NOTIFY_SERVICES: [],
            CONF_CAR_OWNER: "person.driver",
        },
        title="EV Smart Charger",
    )


def _component_mock(name: str) -> Mock:
    """Create a reusable component mock with async setup/remove."""
    instance = Mock(name=name)
    instance.async_setup = AsyncMock()
    instance.async_refresh = AsyncMock()
    instance.async_remove = AsyncMock()
    instance.logger = Mock()
    return instance


async def test_async_setup_entry_populates_runtime_data(hass):
    """Setup stores all runtime-owned components on entry.runtime_data."""
    entry = _build_entry()
    entry.add_to_hass(hass)

    charger_controller = _component_mock("charger_controller")
    ev_soc_monitor = _component_mock("ev_soc_monitor")
    priority_balancer = _component_mock("priority_balancer")
    night_smart_charge = _component_mock("night_smart_charge")
    boost_charge = _component_mock("boost_charge")
    smart_blocker = _component_mock("smart_blocker")
    solar_surplus = _component_mock("solar_surplus")
    log_manager = _component_mock("log_manager")
    diagnostic_manager = _component_mock("diagnostic_manager")
    boost_charge.set_related_automations = Mock()

    async def forward_entry_setups(config_entry, _platforms):
        runtime_data = config_entry.runtime_data
        runtime_data.registered_entity_count = TOTAL_INTEGRATION_ENTITIES
        runtime_data.registration_event.set()

    with patch.object(integration, "_async_register_frontend", AsyncMock()), \
         patch.object(hass.config_entries, "async_forward_entry_setups", side_effect=forward_entry_setups), \
         patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)), \
         patch.object(integration, "ChargerController", return_value=charger_controller), \
         patch.object(integration, "EVSOCMonitor", return_value=ev_soc_monitor), \
         patch.object(integration, "AutomationCoordinator", return_value=Mock()), \
         patch.object(integration, "DiagnosticManager", return_value=diagnostic_manager), \
         patch.object(integration, "PriorityBalancer", return_value=priority_balancer), \
         patch.object(integration, "NightSmartCharge", return_value=night_smart_charge), \
         patch.object(integration, "BoostCharge", return_value=boost_charge), \
         patch.object(integration, "SmartChargerBlocker", return_value=smart_blocker), \
         patch.object(integration, "SolarSurplusAutomation", return_value=solar_surplus), \
         patch.object(integration, "LogManager", return_value=log_manager):
        assert await integration.async_setup_entry(hass, entry) is True

    runtime_data = entry.runtime_data
    assert isinstance(runtime_data, EVSCRuntimeData)
    assert runtime_data.expected_entity_count == TOTAL_INTEGRATION_ENTITIES
    assert runtime_data.charger_controller is charger_controller
    assert runtime_data.ev_soc_monitor is ev_soc_monitor
    assert runtime_data.priority_balancer is priority_balancer
    assert runtime_data.night_smart_charge is night_smart_charge
    assert runtime_data.boost_charge is boost_charge
    assert runtime_data.smart_blocker is smart_blocker
    assert runtime_data.solar_surplus is solar_surplus
    assert runtime_data.log_manager is log_manager
    assert runtime_data.diagnostic_manager is diagnostic_manager
    charger_controller.async_setup.assert_awaited_once()
    ev_soc_monitor.async_setup.assert_awaited_once()
    priority_balancer.async_setup.assert_awaited_once()
    diagnostic_manager.async_setup.assert_awaited_once()
    diagnostic_manager.async_refresh.assert_awaited_once()
    log_manager.async_setup.assert_awaited_once()


async def test_async_setup_entry_raises_not_ready_on_registration_timeout(hass):
    """Setup fails fast when helper entity registration never completes."""
    entry = _build_entry()
    entry.add_to_hass(hass)

    async def raise_timeout(awaitable, *args, **kwargs):
        awaitable.close()
        raise TimeoutError

    with patch.object(integration, "_async_register_frontend", AsyncMock()), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()), \
         patch.object(integration.asyncio, "wait_for", new=AsyncMock(side_effect=raise_timeout)):
        with pytest.raises(ConfigEntryNotReady):
            await integration.async_setup_entry(hass, entry)


async def test_async_setup_entry_cleans_up_diagnostic_manager_on_late_failure(hass):
    """Late setup failures must remove the diagnostic manager listener state."""
    entry = _build_entry()
    entry.add_to_hass(hass)

    charger_controller = _component_mock("charger_controller")
    ev_soc_monitor = _component_mock("ev_soc_monitor")
    priority_balancer = _component_mock("priority_balancer")
    diagnostic_manager = _component_mock("diagnostic_manager")
    priority_balancer.async_setup.side_effect = RuntimeError("priority setup failed")

    async def forward_entry_setups(config_entry, _platforms):
        runtime_data = config_entry.runtime_data
        runtime_data.registered_entity_count = TOTAL_INTEGRATION_ENTITIES
        runtime_data.registration_event.set()

    with patch.object(integration, "_async_register_frontend", AsyncMock()), \
         patch.object(hass.config_entries, "async_forward_entry_setups", side_effect=forward_entry_setups), \
         patch.object(integration, "ChargerController", return_value=charger_controller), \
         patch.object(integration, "EVSOCMonitor", return_value=ev_soc_monitor), \
         patch.object(integration, "AutomationCoordinator", return_value=Mock()), \
         patch.object(integration, "DiagnosticManager", return_value=diagnostic_manager), \
         patch.object(integration, "PriorityBalancer", return_value=priority_balancer):
        with pytest.raises(RuntimeError, match="priority setup failed"):
            await integration.async_setup_entry(hass, entry)

    diagnostic_manager.async_setup.assert_awaited_once()
    diagnostic_manager.async_remove.assert_awaited_once()
    ev_soc_monitor.async_remove.assert_awaited_once()


async def test_async_unload_entry_cleans_up_runtime_components(hass):
    """Unload removes components in reverse order and clears runtime_data."""
    entry = _build_entry()
    entry.add_to_hass(hass)
    runtime_data = EVSCRuntimeData(config=dict(entry.data), expected_entity_count=TOTAL_INTEGRATION_ENTITIES)
    entry.runtime_data = runtime_data

    runtime_data.solar_surplus = _component_mock("solar_surplus")
    runtime_data.smart_blocker = _component_mock("smart_blocker")
    runtime_data.boost_charge = _component_mock("boost_charge")
    runtime_data.night_smart_charge = _component_mock("night_smart_charge")
    runtime_data.priority_balancer = _component_mock("priority_balancer")
    runtime_data.diagnostic_manager = _component_mock("diagnostic_manager")
    runtime_data.log_manager = _component_mock("log_manager")
    runtime_data.ev_soc_monitor = _component_mock("ev_soc_monitor")
    runtime_data.charger_controller = _component_mock("charger_controller")

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ) as unload_platforms:
        assert await integration.async_unload_entry(hass, entry) is True

    runtime_data.solar_surplus.async_remove.assert_awaited_once()
    runtime_data.smart_blocker.async_remove.assert_awaited_once()
    runtime_data.boost_charge.async_remove.assert_awaited_once()
    runtime_data.night_smart_charge.async_remove.assert_awaited_once()
    runtime_data.priority_balancer.async_remove.assert_awaited_once()
    runtime_data.diagnostic_manager.async_remove.assert_awaited_once()
    runtime_data.log_manager.async_remove.assert_awaited_once()
    runtime_data.ev_soc_monitor.async_remove.assert_awaited_once()
    unload_platforms.assert_awaited_once()
    assert entry.runtime_data is None
