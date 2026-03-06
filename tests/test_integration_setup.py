"""Tests for integration setup and unload."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_smart_charger import (
    _async_register_frontend,
    async_setup_entry,
    async_unload_entry,
)
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
    PLATFORMS,
    TOTAL_INTEGRATION_ENTITIES,
)
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData


def _entry_data() -> dict:
    """Return minimal valid config entry data for setup tests."""
    return {
        CONF_EV_CHARGER_SWITCH: "switch.charger",
        CONF_EV_CHARGER_CURRENT: "number.charger_current",
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        CONF_SOC_CAR: "sensor.car_soc",
        CONF_SOC_HOME: "sensor.home_soc",
        CONF_FV_PRODUCTION: "sensor.solar",
        CONF_HOME_CONSUMPTION: "sensor.home",
        CONF_GRID_IMPORT: "sensor.grid",
        CONF_NOTIFY_SERVICES: [],
        CONF_CAR_OWNER: "person.owner",
    }


def _component(name: str) -> SimpleNamespace:
    """Create a simple component stub with setup/remove hooks."""
    return SimpleNamespace(
        logger=f"{name}-logger",
        async_setup=AsyncMock(),
        async_remove=AsyncMock(),
        set_related_automations=Mock(),
    )


def _stub_http(hass) -> SimpleNamespace:
    """Install a minimal HTTP stub on hass for frontend registration tests."""
    hass.async_add_executor_job = AsyncMock()
    hass.http = SimpleNamespace(
        async_register_static_paths=AsyncMock(),
        register_static_path=Mock(),
    )
    return hass.http


async def test_register_frontend_is_idempotent(hass) -> None:
    """Frontend static path is registered only once."""
    http = _stub_http(hass)

    await _async_register_frontend(hass)
    await _async_register_frontend(hass)

    assert http.async_register_static_paths.await_count + hass.async_add_executor_job.await_count == 1
    assert hass.data[DOMAIN]["_frontend_registered"] is True


async def test_async_setup_entry_populates_runtime_data_and_component_refs(hass) -> None:
    """Successful setup waits for registration barrier and stores runtime references."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), entry_id="entry-1")
    entry.add_to_hass(hass)
    _stub_http(hass)

    charger_controller = _component("charger")
    ev_soc_monitor = _component("soc")
    priority_balancer = _component("priority")
    night_smart_charge = _component("night")
    boost_charge = _component("boost")
    smart_blocker = _component("blocker")
    solar_surplus = _component("solar")
    log_manager = _component("log")
    coordinator = SimpleNamespace()

    async def forward_setups(config_entry, platforms):
        assert platforms == PLATFORMS
        runtime_data = config_entry.runtime_data
        runtime_data.registered_entity_count = TOTAL_INTEGRATION_ENTITIES
        runtime_data.registration_event.set()

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        side_effect=forward_setups,
        autospec=True,
    ), patch(
        "custom_components.ev_smart_charger.ChargerController",
        return_value=charger_controller,
    ), patch(
        "custom_components.ev_smart_charger.EVSOCMonitor",
        return_value=ev_soc_monitor,
    ), patch(
        "custom_components.ev_smart_charger.AutomationCoordinator",
        return_value=coordinator,
    ), patch(
        "custom_components.ev_smart_charger.PriorityBalancer",
        return_value=priority_balancer,
    ), patch(
        "custom_components.ev_smart_charger.NightSmartCharge",
        return_value=night_smart_charge,
    ), patch(
        "custom_components.ev_smart_charger.BoostCharge",
        return_value=boost_charge,
    ), patch(
        "custom_components.ev_smart_charger.SmartChargerBlocker",
        return_value=smart_blocker,
    ), patch(
        "custom_components.ev_smart_charger.SolarSurplusAutomation",
        return_value=solar_surplus,
    ), patch(
        "custom_components.ev_smart_charger.LogManager",
        return_value=log_manager,
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    runtime_data = entry.runtime_data
    assert isinstance(runtime_data, EVSCRuntimeData)
    assert runtime_data.expected_entity_count == TOTAL_INTEGRATION_ENTITIES
    assert runtime_data.charger_controller is charger_controller
    assert runtime_data.ev_soc_monitor is ev_soc_monitor
    assert runtime_data.coordinator is coordinator
    assert runtime_data.priority_balancer is priority_balancer
    assert runtime_data.night_smart_charge is night_smart_charge
    assert runtime_data.boost_charge is boost_charge
    assert runtime_data.smart_blocker is smart_blocker
    assert runtime_data.solar_surplus is solar_surplus
    assert runtime_data.log_manager is log_manager
    boost_charge.set_related_automations.assert_called_once_with(
        night_smart_charge=night_smart_charge,
        solar_surplus=solar_surplus,
    )
    log_manager.async_setup.assert_awaited_once()


async def test_async_setup_entry_raises_not_ready_on_registration_timeout(hass) -> None:
    """Registration timeout raises ConfigEntryNotReady before component creation."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), entry_id="entry-1")
    entry.add_to_hass(hass)
    _stub_http(hass)

    async def timeout_wait_for(awaitable, timeout):
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()
        raise TimeoutError

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(),
    ), patch(
        "custom_components.ev_smart_charger.asyncio.wait_for",
        side_effect=timeout_wait_for,
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)


async def test_async_unload_entry_removes_components_in_reverse_order(hass) -> None:
    """Unload removes runtime components in reverse setup order and clears runtime data."""
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), entry_id="entry-1")
    entry.add_to_hass(hass)

    call_order: list[str] = []

    def remover(name: str) -> SimpleNamespace:
        return SimpleNamespace(
            async_remove=AsyncMock(side_effect=lambda: call_order.append(name))
        )

    runtime_data = EVSCRuntimeData(config=_entry_data(), expected_entity_count=1)
    runtime_data.solar_surplus = remover("solar")
    runtime_data.smart_blocker = remover("blocker")
    runtime_data.boost_charge = remover("boost")
    runtime_data.night_smart_charge = remover("night")
    runtime_data.priority_balancer = remover("priority")
    runtime_data.log_manager = remover("log")
    runtime_data.ev_soc_monitor = remover("soc")
    runtime_data.charger_controller = SimpleNamespace()
    entry.runtime_data = runtime_data

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ):
        result = await async_unload_entry(hass, entry)

    assert result is True
    assert call_order == ["solar", "blocker", "boost", "night", "priority", "log", "soc"]
    assert entry.runtime_data is None
