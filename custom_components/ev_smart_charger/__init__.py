from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import (
    DOMAIN,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
)
from .helpers import async_create_helpers, async_remove_helpers
from .automations import async_setup_automations, async_remove_automations

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

    # Create helper entities (don't fail if they can't be created)
    try:
        await async_create_helpers(hass)
    except Exception as e:
        _LOGGER.warning(f"Helper creation had issues: {e}")
        _LOGGER.warning("Integration will continue, but you may need to create helpers manually")

    # Set up automations
    try:
        automations = await async_setup_automations(hass, entry.entry_id, entry.data)
    except Exception as e:
        _LOGGER.error(f"Failed to set up automations: {e}")
        _LOGGER.exception("Automation setup error details:")
        return False

    # Store configuration data and automations
    hass.data[DOMAIN][entry.entry_id] = {
        "config": entry.data,
        "automations": automations,
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

    if automations:
        await async_remove_automations(automations)

    # Remove helpers (only on final unload, not on reload)
    # Note: We keep helpers so users don't lose their settings
    # Uncomment the line below if you want to remove helpers on unload
    # await async_remove_helpers(hass)

    hass.data[DOMAIN].pop(entry.entry_id, None)

    _LOGGER.info("EV Smart Charger unloaded successfully")

    return True
