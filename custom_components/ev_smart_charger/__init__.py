"""The EV Smart Charger integration."""
from __future__ import annotations
import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .automation_coordinator import AutomationCoordinator
from .charger_controller import ChargerController
from .priority_balancer import PriorityBalancer
from .night_smart_charge import NightSmartCharge
from .automations import SmartChargerBlocker
from .solar_surplus import SolarSurplusAutomation

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EV Smart Charger from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.info("=" * 64)
    _LOGGER.info("🚗 EV Smart Charger v1.3.1 - Starting setup")
    _LOGGER.info("=" * 64)

    # ========== PHASE 1: SETUP PLATFORMS (Helper Entities) ==========
    _LOGGER.info("📦 Phase 1: Setting up platforms (helper entities)")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info(f"✅ Platforms registered: {', '.join(PLATFORMS)}")

    # Wait for entity registration
    _LOGGER.info("⏳ Waiting 2 seconds for entity registration...")
    await asyncio.sleep(2)

    # Verify entity registration
    entity_registry = er.async_get(hass)
    registry_entities = [
        entity.entity_id
        for entity in entity_registry.entities.values()
        if entity.config_entry_id == entry.entry_id
    ]
    _LOGGER.info(f"✅ {len(registry_entities)} helper entities registered")

    # ========== PHASE 2: CREATE CHARGER CONTROLLER (Centralized Charger Control) ==========
    _LOGGER.info("🔌 Phase 2: Creating Charger Controller")
    charger_controller = ChargerController(hass, entry.entry_id, entry.data)
    try:
        await charger_controller.async_setup()
        _LOGGER.info("✅ Charger Controller setup complete")
    except Exception as e:
        _LOGGER.error(f"❌ Failed to set up Charger Controller: {e}")
        _LOGGER.exception("Charger Controller setup error details:")
        return False

    # ========== PHASE 3: CREATE AUTOMATION COORDINATOR ==========
    _LOGGER.info("🔧 Phase 3: Creating Automation Coordinator")
    coordinator = AutomationCoordinator(hass, entry.entry_id)
    _LOGGER.info("✅ Automation Coordinator created")

    # ========== PHASE 4: CREATE PRIORITY BALANCER (Independent Component) ==========
    _LOGGER.info("⚖️  Phase 4: Creating Priority Balancer")
    priority_balancer = PriorityBalancer(hass, entry.entry_id, entry.data)
    try:
        await priority_balancer.async_setup()
        _LOGGER.info("✅ Priority Balancer setup complete")
    except Exception as e:
        _LOGGER.error(f"❌ Failed to set up Priority Balancer: {e}")
        _LOGGER.exception("Priority Balancer setup error details:")
        return False

    # ========== PHASE 5: CREATE NIGHT SMART CHARGE (depends on Priority Balancer & Charger Controller) ==========
    _LOGGER.info("🌙 Phase 5: Creating Night Smart Charge")
    night_smart_charge = NightSmartCharge(hass, entry.entry_id, entry.data, priority_balancer, charger_controller)
    try:
        await night_smart_charge.async_setup()
        _LOGGER.info("✅ Night Smart Charge setup complete")
    except Exception as e:
        _LOGGER.error(f"❌ Failed to set up Night Smart Charge: {e}")
        _LOGGER.exception("Night Smart Charge setup error details:")
        night_smart_charge = None

    # ========== PHASE 6: CREATE SMART BLOCKER (depends on Night Smart Charge & Charger Controller) ==========
    _LOGGER.info("🚫 Phase 6: Creating Smart Charger Blocker")
    smart_blocker = SmartChargerBlocker(hass, entry.entry_id, entry.data, night_smart_charge, charger_controller)
    try:
        await smart_blocker.async_setup()
        _LOGGER.info("✅ Smart Charger Blocker setup complete")
    except Exception as e:
        _LOGGER.error(f"❌ Failed to set up Smart Charger Blocker: {e}")
        _LOGGER.exception("Smart Blocker setup error details:")
        smart_blocker = None

    # ========== PHASE 7: CREATE SOLAR SURPLUS (depends on Priority Balancer & Charger Controller) ==========
    _LOGGER.info("☀️  Phase 7: Creating Solar Surplus automation")
    solar_surplus = SolarSurplusAutomation(hass, entry.entry_id, entry.data, priority_balancer, charger_controller)
    try:
        await solar_surplus.async_setup()
        _LOGGER.info("✅ Solar Surplus automation setup complete")
    except Exception as e:
        _LOGGER.error(f"❌ Failed to set up Solar Surplus: {e}")
        _LOGGER.exception("Solar Surplus setup error details:")
        solar_surplus = None

    # ========== PHASE 8: STORE REFERENCES ==========
    _LOGGER.info("💾 Phase 8: Storing component references")
    hass.data[DOMAIN][entry.entry_id] = {
        "config": entry.data,
        "charger_controller": charger_controller,
        "coordinator": coordinator,
        "priority_balancer": priority_balancer,
        "night_smart_charge": night_smart_charge,
        "smart_blocker": smart_blocker,
        "solar_surplus": solar_surplus,
    }

    # Register update listener
    entry.async_on_unload(entry.add_update_listener(_reload_on_update))

    _LOGGER.info("=" * 64)
    _LOGGER.info("✅ EV Smart Charger v1.3.1 - Setup completed successfully!")
    _LOGGER.info("=" * 64)

    return True


async def _reload_on_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when config entry is updated."""
    _LOGGER.info("🔄 Configuration updated - reloading integration")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("=" * 64)
    _LOGGER.info("🔄 EV Smart Charger - Starting unload")
    _LOGGER.info("=" * 64)

    # Get stored components
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})

    # Remove automations in reverse order (opposite of setup)
    solar_surplus = entry_data.get("solar_surplus")
    if solar_surplus:
        _LOGGER.info("🗑️  Removing Solar Surplus automation")
        await solar_surplus.async_remove()

    smart_blocker = entry_data.get("smart_blocker")
    if smart_blocker:
        _LOGGER.info("🗑️  Removing Smart Charger Blocker")
        await smart_blocker.async_remove()

    night_smart_charge = entry_data.get("night_smart_charge")
    if night_smart_charge:
        _LOGGER.info("🗑️  Removing Night Smart Charge")
        await night_smart_charge.async_remove()

    priority_balancer = entry_data.get("priority_balancer")
    if priority_balancer:
        _LOGGER.info("🗑️  Removing Priority Balancer")
        await priority_balancer.async_remove()

    charger_controller = entry_data.get("charger_controller")
    if charger_controller:
        _LOGGER.info("🗑️  Removing Charger Controller")
        # ChargerController doesn't need explicit cleanup, just logging

    # Unload platforms
    _LOGGER.info("🗑️  Unloading platforms")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.info("=" * 64)
        _LOGGER.info("✅ EV Smart Charger - Unloaded successfully")
        _LOGGER.info("=" * 64)
    else:
        _LOGGER.error("❌ Failed to unload some platforms")

    return unload_ok
