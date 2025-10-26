"""Helper entity management for EV Smart Charger."""
from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.components import input_boolean, input_number
from .const import (
    HELPER_FORZA_RICARICA,
    HELPER_SMART_BLOCKER_ENABLED,
    HELPER_SOLAR_THRESHOLD,
    DEFAULT_SOLAR_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


async def async_create_helpers(hass: HomeAssistant) -> None:
    """Create all required helper entities for EV Smart Charger."""

    _LOGGER.info("Setting up EV Smart Charger helper entities...")

    # Try to create helpers, but don't fail if they already exist or can't be created
    try:
        # Check if input_boolean component is loaded
        if INPUT_BOOLEAN_DOMAIN not in hass.config.components:
            await hass.async_add_executor_job(
                hass.config_entries.async_forward_entry_setup,
                None,
                INPUT_BOOLEAN_DOMAIN
            )

        # Create Forza Ricarica helper
        await _ensure_helper_exists(
            hass,
            HELPER_FORZA_RICARICA,
            "EVSC Forza Ricarica",
            "input_boolean",
            {
                "name": "EVSC Forza Ricarica",
                "icon": "mdi:power"
            }
        )

        # Create Smart Blocker Enabled helper
        await _ensure_helper_exists(
            hass,
            HELPER_SMART_BLOCKER_ENABLED,
            "EVSC Smart Charger Blocker",
            "input_boolean",
            {
                "name": "EVSC Smart Charger Blocker",
                "icon": "mdi:solar-power"
            }
        )

        # Create Solar Threshold helper
        await _ensure_helper_exists(
            hass,
            HELPER_SOLAR_THRESHOLD,
            "EVSC Solar Production Threshold",
            "input_number",
            {
                "name": "EVSC Solar Production Threshold",
                "min": 0,
                "max": 1000,
                "step": 10,
                "initial": DEFAULT_SOLAR_THRESHOLD,
                "unit_of_measurement": "W",
                "icon": "mdi:solar-power-variant"
            }
        )

        _LOGGER.info("✅ EV Smart Charger helpers setup completed")

    except Exception as e:
        _LOGGER.warning(f"Could not auto-create all helpers: {e}")
        _LOGGER.warning("Please create the following helpers manually:")
        _LOGGER.warning(f"  1. input_boolean.evsc_forza_ricarica")
        _LOGGER.warning(f"  2. input_boolean.evsc_smart_charger_blocker_enabled")
        _LOGGER.warning(f"  3. input_number.evsc_solar_production_threshold (0-1000W, step 10)")


async def _ensure_helper_exists(
    hass: HomeAssistant,
    entity_id: str,
    name: str,
    domain: str,
    config: dict
) -> None:
    """Ensure a helper entity exists, create if it doesn't."""

    # Check if entity already exists in state machine
    existing_state = hass.states.get(entity_id)
    if existing_state:
        _LOGGER.debug(f"Helper {entity_id} already exists")
        return

    # Try to create via service call (works if the integration supports it)
    try:
        object_id = entity_id.split(".", 1)[1]

        service_data = {
            "object_id": object_id,
            **config
        }

        await hass.services.async_call(
            domain,
            "create",
            service_data,
            blocking=True,
        )

        _LOGGER.info(f"✅ Created helper: {entity_id}")

    except Exception as e:
        _LOGGER.debug(f"Could not auto-create {entity_id}: {e}")
        _LOGGER.info(f"⚠️  Please create {entity_id} manually with: {config}")


async def async_remove_helpers(hass: HomeAssistant) -> None:
    """Remove all helper entities created by this integration."""

    helpers_to_remove = [
        HELPER_FORZA_RICARICA,
        HELPER_SMART_BLOCKER_ENABLED,
        HELPER_SOLAR_THRESHOLD,
    ]

    for helper_id in helpers_to_remove:
        try:
            object_id = helper_id.split(".", 1)[1]
            domain = helper_id.split(".", 1)[0]

            await hass.services.async_call(
                domain,
                "delete",
                {"object_id": object_id},
                blocking=True,
            )
            _LOGGER.info(f"Removed helper: {helper_id}")
        except Exception as e:
            _LOGGER.debug(f"Could not remove helper {helper_id}: {e}")


# Constants for component domains
INPUT_BOOLEAN_DOMAIN = "input_boolean"
INPUT_NUMBER_DOMAIN = "input_number"
