"""Helper entity management for EV Smart Charger."""
from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_create_helpers(hass: HomeAssistant) -> None:
    """Log instructions for creating required helper entities."""

    _LOGGER.warning("=" * 80)
    _LOGGER.warning("EV SMART CHARGER: Manual Helper Creation Required")
    _LOGGER.warning("=" * 80)
    _LOGGER.warning("")
    _LOGGER.warning("Please create these 3 helper entities via the Home Assistant UI:")
    _LOGGER.warning("")
    _LOGGER.warning("1. Go to: Settings → Devices & Services → Helpers")
    _LOGGER.warning("2. Click: + CREATE HELPER")
    _LOGGER.warning("3. Create the following helpers:")
    _LOGGER.warning("")
    _LOGGER.warning("   Helper 1: EVSC Forza Ricarica")
    _LOGGER.warning("   - Type: Toggle")
    _LOGGER.warning("   - Name: EVSC Forza Ricarica")
    _LOGGER.warning("   - Entity ID: input_boolean.evsc_forza_ricarica")
    _LOGGER.warning("   - Icon: mdi:power")
    _LOGGER.warning("")
    _LOGGER.warning("   Helper 2: EVSC Smart Charger Blocker")
    _LOGGER.warning("   - Type: Toggle")
    _LOGGER.warning("   - Name: EVSC Smart Charger Blocker")
    _LOGGER.warning("   - Entity ID: input_boolean.evsc_smart_charger_blocker_enabled")
    _LOGGER.warning("   - Icon: mdi:solar-power")
    _LOGGER.warning("")
    _LOGGER.warning("   Helper 3: EVSC Solar Production Threshold")
    _LOGGER.warning("   - Type: Number")
    _LOGGER.warning("   - Name: EVSC Solar Production Threshold")
    _LOGGER.warning("   - Entity ID: input_number.evsc_solar_production_threshold")
    _LOGGER.warning("   - Min: 0")
    _LOGGER.warning("   - Max: 1000")
    _LOGGER.warning("   - Step: 10")
    _LOGGER.warning("   - Unit: W")
    _LOGGER.warning("   - Icon: mdi:solar-power-variant")
    _LOGGER.warning("")
    _LOGGER.warning("=" * 80)
    _LOGGER.warning("After creating helpers, restart Home Assistant")
    _LOGGER.warning("=" * 80)


async def async_remove_helpers(hass: HomeAssistant) -> None:
    """Remove helper entities (placeholder for future implementation)."""
    _LOGGER.info("Helper removal not implemented - please delete manually if needed")
