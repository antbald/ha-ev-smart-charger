"""Sensor platform for EV Smart Charger diagnostics."""
from __future__ import annotations
import logging
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EVSC diagnostic sensor entities."""

    entities = []

    # Create Diagnostic Sensor
    entities.append(
        EVSCDiagnosticSensor(
            entry.entry_id,
            "evsc_diagnostic",
            "EVSC Diagnostic Status",
            "mdi:information-outline",
        )
    )

    # Create Priority State Sensor
    entities.append(
        EVSCPriorityStateSensor(
            entry.entry_id,
            "evsc_priority_daily_state",
            "EVSC Priority Daily State",
            "mdi:priority-high",
        )
    )

    async_add_entities(entities)
    _LOGGER.info(f"✅ Created {len(entities)} EVSC sensors")


class EVSCDiagnosticSensor(SensorEntity, RestoreEntity):
    """EVSC Diagnostic Sensor showing real-time automation status."""

    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        unique_id: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the diagnostic sensor."""
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{unique_id}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_value = "Initializing"

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        # Attributes will be set directly via hass.states.async_set
        return {}

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_native_value = last_state.state


class EVSCPriorityStateSensor(SensorEntity, RestoreEntity):
    """EVSC Priority State Sensor showing current charging priority."""

    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        unique_id: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the priority sensor."""
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{unique_id}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_value = "EV_Free"
        self._attr_extra_state_attributes = {}

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return self._attr_extra_state_attributes

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_native_value = last_state.state
            if last_state.attributes:
                self._attr_extra_state_attributes = dict(last_state.attributes)
