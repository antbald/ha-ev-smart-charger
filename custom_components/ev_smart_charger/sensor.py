"""Sensor platform for EV Smart Charger diagnostics."""
from __future__ import annotations
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, VERSION

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

    # Create Solar Surplus Diagnostic Sensor
    entities.append(
        EVSCSolarSurplusDiagnosticSensor(
            entry.entry_id,
            "evsc_solar_surplus_diagnostic",
            "EVSC Solar Surplus Diagnostic",
            "mdi:solar-power",
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
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the diagnostic sensor."""
        self._entry_id = entry_id
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{suffix}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_value = "Initializing"
        # Set explicit entity_id to match pattern
        self.entity_id = f"sensor.{DOMAIN}_{entry_id}_{suffix}"

    @property
    def device_info(self):
        """Return device info to group all entities under one device."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "EV Smart Charger",
            "manufacturer": "antbald",
            "model": "EV Smart Charger",
            "sw_version": VERSION,
        }

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        # Attributes will be set directly via hass.states.async_set
        return {}

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        _LOGGER.info(f"✅ Diagnostic sensor registered: {self.entity_id} (unique_id: {self.unique_id})")

        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_native_value = last_state.state


class EVSCPriorityStateSensor(SensorEntity, RestoreEntity):
    """EVSC Priority State Sensor showing current charging priority."""

    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the priority sensor."""
        self._entry_id = entry_id
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{suffix}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_value = "EV_Free"
        self._attr_extra_state_attributes = {}
        # Set explicit entity_id to match pattern
        self.entity_id = f"sensor.{DOMAIN}_{entry_id}_{suffix}"

    @property
    def device_info(self):
        """Return device info to group all entities under one device."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "EV Smart Charger",
            "manufacturer": "antbald",
            "model": "EV Smart Charger",
            "sw_version": VERSION,
        }

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return self._attr_extra_state_attributes

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        _LOGGER.info(f"✅ Priority sensor registered: {self.entity_id} (unique_id: {self.unique_id})")

        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_native_value = last_state.state
            if last_state.attributes:
                self._attr_extra_state_attributes = dict(last_state.attributes)


class EVSCSolarSurplusDiagnosticSensor(SensorEntity, RestoreEntity):
    """EVSC Solar Surplus Diagnostic Sensor with detailed check information."""

    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the solar surplus diagnostic sensor."""
        self._entry_id = entry_id
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{suffix}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_value = "Waiting for first check"
        self._attr_extra_state_attributes = {}
        # Set explicit entity_id to match pattern
        self.entity_id = f"sensor.{DOMAIN}_{entry_id}_{suffix}"

    @property
    def device_info(self):
        """Return device info to group all entities under one device."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "EV Smart Charger",
            "manufacturer": "antbald",
            "model": "EV Smart Charger",
            "sw_version": VERSION,
        }

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return self._attr_extra_state_attributes

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        _LOGGER.info(f"✅ Solar Surplus Diagnostic sensor registered: {self.entity_id} (unique_id: {self.unique_id})")

        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_native_value = last_state.state
            if last_state.attributes:
                self._attr_extra_state_attributes = dict(last_state.attributes)
