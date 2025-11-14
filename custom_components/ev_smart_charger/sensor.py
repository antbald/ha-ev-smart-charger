"""Sensor platform for EV Smart Charger diagnostics."""
from __future__ import annotations
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, VERSION, CONF_SOC_CAR

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

    # Create Log File Path Sensor (v1.3.25)
    entities.append(
        EVSCLogFilePathSensor(
            hass,
            entry.entry_id,
            "evsc_log_file_path",
            "EVSC Log File Path",
            "mdi:file-document-outline",
        )
    )

    # Create Today EV Target Sensor (v1.3.26)
    entities.append(
        EVSCTodayEVTargetSensor(
            entry.entry_id,
            "evsc_today_ev_target",
            "EVSC Today EV Target",
            "mdi:battery-charging-80",
        )
    )

    # Create Today Home Target Sensor (v1.3.26)
    entities.append(
        EVSCTodayHomeTargetSensor(
            entry.entry_id,
            "evsc_today_home_target",
            "EVSC Today Home Target",
            "mdi:home-battery",
        )
    )

    # Create Cached EV SOC Sensor (v1.4.0)
    entities.append(
        EVSCCachedEVSOCSensor(
            hass,
            entry.entry_id,
            entry.data.get(CONF_SOC_CAR),  # Source cloud sensor
            "evsc_cached_ev_soc",
            "EVSC Cached EV SOC",
            "mdi:car-battery",
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


class EVSCLogFilePathSensor(SensorEntity):
    """EVSC Log File Path Sensor (v1.3.25)."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        self._hass = hass
        self._entry_id = entry_id
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{suffix}"
        self._attr_name = name
        self._attr_icon = icon
        # Set explicit entity_id to match pattern
        self.entity_id = f"sensor.{DOMAIN}_{entry_id}_{suffix}"

        # Get log file path from log manager
        self._attr_native_value = self._get_log_file_path()

    def _get_log_file_path(self) -> str:
        """Get log file path from log manager."""
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        log_manager = entry_data.get("log_manager")

        if log_manager:
            return log_manager.get_log_file_path()
        else:
            # Fallback: construct path manually during initial setup
            return self._hass.config.path(
                "custom_components",
                "ev_smart_charger",
                "logs",
                f"evsc_{self._entry_id}.log"
            )

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
        return {
            "description": "Path to the file logging output (when enabled)",
            "friendly_name": "Log File Path",
        }

    async def async_added_to_hass(self) -> None:
        """Entity added to hass."""
        await super().async_added_to_hass()
        _LOGGER.info(f"✅ Log File Path sensor registered: {self.entity_id} (unique_id: {self.unique_id})")
        _LOGGER.info(f"  📄 Log file path: {self._attr_native_value}")


class EVSCTodayEVTargetSensor(SensorEntity, RestoreEntity):
    """EVSC Today EV Target Sensor - shows today's EV SOC target (v1.3.26)."""

    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        self._entry_id = entry_id
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{suffix}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = "%"
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
        _LOGGER.info(f"✅ Today EV Target sensor registered: {self.entity_id} (unique_id: {self.unique_id})")

        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = float(last_state.state) if last_state.state not in [None, "unknown", "unavailable"] else None
            except (ValueError, TypeError):
                self._attr_native_value = None
            if last_state.attributes:
                self._attr_extra_state_attributes = dict(last_state.attributes)


class EVSCTodayHomeTargetSensor(SensorEntity, RestoreEntity):
    """EVSC Today Home Target Sensor - shows today's Home battery SOC target (v1.3.26)."""

    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        self._entry_id = entry_id
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{suffix}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = "%"
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
        _LOGGER.info(f"✅ Today Home Target sensor registered: {self.entity_id} (unique_id: {self.unique_id})")

        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = float(last_state.state) if last_state.state not in [None, "unknown", "unavailable"] else None
            except (ValueError, TypeError):
                self._attr_native_value = None
            if last_state.attributes:
                self._attr_extra_state_attributes = dict(last_state.attributes)


class EVSCCachedEVSOCSensor(SensorEntity, RestoreEntity):
    """EVSC Cached EV SOC Sensor - reliable cache for cloud-based EV SOC sensor (v1.4.0)."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        source_entity: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the cached sensor."""
        self._hass = hass
        self._entry_id = entry_id
        self._source_entity = source_entity
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{suffix}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = "%"
        self._attr_extra_state_attributes = {
            "source_entity": source_entity,
            "last_valid_update": None,
            "is_cached": False,
        }
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
        _LOGGER.info(f"✅ Cached EV SOC sensor registered: {self.entity_id} (unique_id: {self.unique_id})")
        _LOGGER.info(f"  🔗 Source sensor: {self._source_entity}")

        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = float(last_state.state) if last_state.state not in [None, "unknown", "unavailable"] else None
                _LOGGER.info(f"  🔄 Restored cached SOC: {self._attr_native_value}%")
            except (ValueError, TypeError):
                self._attr_native_value = None
                _LOGGER.warning(f"  ⚠️ Failed to restore cached SOC from: {last_state.state}")
            if last_state.attributes:
                self._attr_extra_state_attributes = dict(last_state.attributes)
