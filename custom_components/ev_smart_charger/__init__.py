from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
)
from .automations import async_setup_automations, async_remove_automations
from .solar_surplus import SolarSurplusAutomation

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EV Smart Charger from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Log the configured entities
    _LOGGER.info("EV Smart Charger configured with entities:")
    _LOGGER.info(f"  - Charger Switch: {entry.data.get(CONF_EV_CHARGER_SWITCH)}")
    _LOGGER.info(f"  - Charger Current: {entry.data.get(CONF_EV_CHARGER_CURRENT)}")
    _LOGGER.info(f"  - Charger Status: {entry.data.get(CONF_EV_CHARGER_STATUS)}")
    _LOGGER.info(f"  - Car SOC: {entry.data.get(CONF_SOC_CAR)}")
    _LOGGER.info(f"  - Home SOC: {entry.data.get(CONF_SOC_HOME)}")
    _LOGGER.info(f"  - FV Production: {entry.data.get(CONF_FV_PRODUCTION)}")
    _LOGGER.info(f"  - Home Consumption: {entry.data.get(CONF_HOME_CONSUMPTION)}")
    _LOGGER.info(f"  - Grid Import: {entry.data.get(CONF_GRID_IMPORT)}")

    # Set up platforms (creates helper entities automatically)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Wait a moment for entities to be registered
    import asyncio
    await asyncio.sleep(2)
    _LOGGER.info("✅ Platforms setup complete, entities should be available")

    # Set up automations
    try:
        automations = await async_setup_automations(hass, entry.entry_id, entry.data)
    except Exception as e:
        _LOGGER.error(f"Failed to set up automations: {e}")
        _LOGGER.exception("Automation setup error details:")
        return False

    # Set up Solar Surplus automation
    try:
        solar_surplus = SolarSurplusAutomation(hass, entry.entry_id, entry.data)
        await solar_surplus.async_setup()
    except Exception as e:
        _LOGGER.error(f"Failed to set up Solar Surplus automation: {e}")
        _LOGGER.exception("Solar Surplus setup error details:")
        solar_surplus = None

    # Store configuration data and automations
    hass.data[DOMAIN][entry.entry_id] = {
        "config": entry.data,
        "automations": automations,
        "solar_surplus": solar_surplus,
    }

    # Register update listener
    entry.async_on_unload(entry.add_update_listener(_reload_on_update))

    _LOGGER.info("✅ EV Smart Charger setup completed successfully")

    return True


async def _reload_on_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when config entry is updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Remove automations
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    automations = entry_data.get("automations", {})
    solar_surplus = entry_data.get("solar_surplus")

    if automations:
        await async_remove_automations(automations)

    if solar_surplus:
        await solar_surplus.async_remove()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    _LOGGER.info("EV Smart Charger unloaded successfully")

    return unload_ok
