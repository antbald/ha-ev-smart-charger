from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
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
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EV Smart Charger from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Store configuration data
    hass.data[DOMAIN][entry.entry_id] = {
        "config": entry.data,
        "mode": "off",  # Default mode
    }

    # Log the configured entities
    _LOGGER.info("EV Smart Charger configured with entities:")
    _LOGGER.info(f"  - Charger Switch: {entry.data.get(CONF_EV_CHARGER_SWITCH)}")
    _LOGGER.info(f"  - Charger Current: {entry.data.get(CONF_EV_CHARGER_CURRENT, 'Not configured')}")
    _LOGGER.info(f"  - Charger Status: {entry.data.get(CONF_EV_CHARGER_STATUS)}")
    _LOGGER.info(f"  - Car SOC: {entry.data.get(CONF_SOC_CAR, 'Not configured')}")
    _LOGGER.info(f"  - Home SOC: {entry.data.get(CONF_SOC_HOME, 'Not configured')}")
    _LOGGER.info(f"  - FV Production: {entry.data.get(CONF_FV_PRODUCTION, 'Not configured')}")
    _LOGGER.info(f"  - Home Consumption: {entry.data.get(CONF_HOME_CONSUMPTION, 'Not configured')}")

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener
    entry.async_on_unload(entry.add_update_listener(_reload_on_update))

    return True


async def _reload_on_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when config entry is updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
