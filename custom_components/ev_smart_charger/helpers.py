"""Helper entity management for EV Smart Charger."""
from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from .const import (
    HELPER_FORZA_RICARICA,
    HELPER_SMART_BLOCKER_ENABLED,
    HELPER_SOLAR_THRESHOLD,
    DEFAULT_SOLAR_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


async def async_create_helpers(hass: HomeAssistant) -> None:
    """Create all required helper entities for EV Smart Charger."""

    # Create input_boolean helpers
    await _create_input_boolean(
        hass,
        HELPER_FORZA_RICARICA,
        "EVSC Forza Ricarica",
        "Global kill switch - When ON, disables all smart charging features",
        icon="mdi:power"
    )

    await _create_input_boolean(
        hass,
        HELPER_SMART_BLOCKER_ENABLED,
        "EVSC Smart Charger Blocker",
        "Blocks charging at night or when solar production is low",
        icon="mdi:solar-power"
    )

    # Create input_number helper for solar threshold
    await _create_input_number(
        hass,
        HELPER_SOLAR_THRESHOLD,
        "EVSC Solar Production Threshold",
        "Minimum solar production (W) required to allow charging",
        min_value=0,
        max_value=1000,
        step=10,
        default_value=DEFAULT_SOLAR_THRESHOLD,
        unit="W",
        icon="mdi:solar-power-variant"
    )

    _LOGGER.info("EV Smart Charger helpers created successfully")


async def _create_input_boolean(
    hass: HomeAssistant,
    entity_id: str,
    name: str,
    description: str,
    icon: str = "mdi:toggle-switch"
) -> None:
    """Create an input_boolean helper if it doesn't exist."""

    # Extract the object_id from entity_id (e.g., "input_boolean.evsc_test" -> "evsc_test")
    object_id = entity_id.split(".", 1)[1]

    # Check if entity already exists
    entity_registry = er.async_get(hass)
    existing = entity_registry.async_get(entity_id)

    if existing:
        _LOGGER.debug(f"Helper {entity_id} already exists, skipping creation")
        return

    # Create the helper using input_boolean service
    await hass.services.async_call(
        "input_boolean",
        "create",
        {
            "name": name,
            "object_id": object_id,
            "icon": icon,
        },
        blocking=True,
    )

    _LOGGER.info(f"Created input_boolean helper: {entity_id}")


async def _create_input_number(
    hass: HomeAssistant,
    entity_id: str,
    name: str,
    description: str,
    min_value: float,
    max_value: float,
    step: float,
    default_value: float,
    unit: str = "",
    icon: str = "mdi:counter"
) -> None:
    """Create an input_number helper if it doesn't exist."""

    # Extract the object_id from entity_id
    object_id = entity_id.split(".", 1)[1]

    # Check if entity already exists
    entity_registry = er.async_get(hass)
    existing = entity_registry.async_get(entity_id)

    if existing:
        _LOGGER.debug(f"Helper {entity_id} already exists, skipping creation")
        return

    # Create the helper using input_number service
    service_data = {
        "name": name,
        "object_id": object_id,
        "min": min_value,
        "max": max_value,
        "step": step,
        "initial": default_value,
        "icon": icon,
    }

    if unit:
        service_data["unit_of_measurement"] = unit

    await hass.services.async_call(
        "input_number",
        "create",
        service_data,
        blocking=True,
    )

    _LOGGER.info(f"Created input_number helper: {entity_id}")


async def async_remove_helpers(hass: HomeAssistant) -> None:
    """Remove all helper entities created by this integration."""

    helpers_to_remove = [
        HELPER_FORZA_RICARICA,
        HELPER_SMART_BLOCKER_ENABLED,
        HELPER_SOLAR_THRESHOLD,
    ]

    for helper_id in helpers_to_remove:
        object_id = helper_id.split(".", 1)[1]
        domain = helper_id.split(".", 1)[0]

        try:
            await hass.services.async_call(
                domain,
                "delete",
                {"object_id": object_id},
                blocking=True,
            )
            _LOGGER.info(f"Removed helper: {helper_id}")
        except Exception as e:
            _LOGGER.warning(f"Could not remove helper {helper_id}: {e}")
