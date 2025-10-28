from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
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
from .night_smart_charge import NightSmartCharge

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
    _LOGGER.info(f"🔄 Setting up platforms: {PLATFORMS}")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("✅ async_forward_entry_setups completed")

    # Give entities a moment to register and write initial state
    import asyncio
    await asyncio.sleep(2)

    # Check entity registry for proper verification
    entity_registry = er.async_get(hass)
    registry_entities = [
        entity.entity_id for entity in entity_registry.entities.values()
        if entity.config_entry_id == entry.entry_id
    ]

    # Also check state machine
    all_entities = hass.states.async_entity_ids()
    state_entities = [e for e in all_entities if f"ev_smart_charger_{entry.entry_id}" in e]

    _LOGGER.info(f"🔍 Entity Registry: Found {len(registry_entities)} entities")
    _LOGGER.info(f"🔍 State Machine: Found {len(state_entities)} entities")

    if registry_entities:
        _LOGGER.info("✅ Entities registered in Entity Registry:")
        for entity_id in registry_entities:
            state = hass.states.get(entity_id)
            status = "✓ has state" if state else "⚠ no state yet"
            _LOGGER.info(f"  - {entity_id} ({status})")
    else:
        _LOGGER.error("❌ NO ENTITIES IN REGISTRY! Entity registration failed.")

    if not state_entities and registry_entities:
        _LOGGER.warning("⚠️ Entities in registry but not in state machine yet - this may resolve shortly")

    _LOGGER.info("✅ Platforms setup complete, proceeding with automations")

    # Set up Night Smart Charge automation first (needed by other automations)
    try:
        night_smart_charge = NightSmartCharge(hass, entry.entry_id, entry.data)
        await night_smart_charge.async_setup()
    except Exception as e:
        _LOGGER.error(f"Failed to set up Night Smart Charge automation: {e}")
        _LOGGER.exception("Night Smart Charge setup error details:")
        night_smart_charge = None

    # Set up automations (passing night_smart_charge reference)
    try:
        automations = await async_setup_automations(hass, entry.entry_id, entry.data, night_smart_charge)
    except Exception as e:
        _LOGGER.error(f"Failed to set up automations: {e}")
        _LOGGER.exception("Automation setup error details:")
        return False

    # Set up Solar Surplus automation (passing night_smart_charge reference)
    try:
        solar_surplus = SolarSurplusAutomation(hass, entry.entry_id, entry.data, night_smart_charge)
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
        "night_smart_charge": night_smart_charge,
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
    night_smart_charge = entry_data.get("night_smart_charge")

    if automations:
        await async_remove_automations(automations)

    if solar_surplus:
        await solar_surplus.async_remove()

    if night_smart_charge:
        await night_smart_charge.async_remove()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    _LOGGER.info("EV Smart Charger unloaded successfully")

    return unload_ok
