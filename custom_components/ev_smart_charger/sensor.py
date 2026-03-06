"""Sensor platform for EV Smart Charger diagnostics."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_SOC_CAR
from .entity_base import EVSCEntityMixin
from .runtime import EVSCRuntimeData, get_runtime_data

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EVSC diagnostic sensor entities."""
    runtime_data = get_runtime_data(entry)

    entities = [
        EVSCDiagnosticSensor(
            runtime_data,
            entry.entry_id,
            "evsc_diagnostic",
            "EVSC Diagnostic Status",
            "mdi:information-outline",
        ),
        EVSCPriorityStateSensor(
            runtime_data,
            entry.entry_id,
            "evsc_priority_daily_state",
            "EVSC Priority Daily State",
            "mdi:priority-high",
        ),
        EVSCSolarSurplusDiagnosticSensor(
            runtime_data,
            entry.entry_id,
            "evsc_solar_surplus_diagnostic",
            "EVSC Solar Surplus Diagnostic",
            "mdi:solar-power",
        ),
        EVSCLogFilePathSensor(
            hass,
            runtime_data,
            entry.entry_id,
            "evsc_log_file_path",
            "EVSC Log File Path",
            "mdi:file-document-outline",
        ),
        EVSCTodayEVTargetSensor(
            runtime_data,
            entry.entry_id,
            "evsc_today_ev_target",
            "EVSC Today EV Target",
            "mdi:battery-charging-80",
        ),
        EVSCTodayHomeTargetSensor(
            runtime_data,
            entry.entry_id,
            "evsc_today_home_target",
            "EVSC Today Home Target",
            "mdi:home-battery",
        ),
        EVSCCachedEVSOCSensor(
            runtime_data,
            entry.entry_id,
            entry.data.get(CONF_SOC_CAR),
            "evsc_cached_ev_soc",
            "EVSC Cached EV SOC",
            "mdi:car-battery",
        ),
    ]

    async_add_entities(entities)
    _LOGGER.info("✅ Created %s EVSC sensors", len(entities))


class EVSCBaseSensor(EVSCEntityMixin, SensorEntity, RestoreEntity):
    """Shared base for EVSC restoreable sensors."""

    _attr_should_poll = False

    def __init__(
        self,
        runtime_data: EVSCRuntimeData,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
        *,
        native_value: Any = None,
        native_unit_of_measurement: str | None = None,
        entity_category: EntityCategory = EntityCategory.DIAGNOSTIC,
    ) -> None:
        """Initialize the shared sensor state."""
        self._init_evsc_entity(
            runtime_data,
            entry_id,
            suffix,
            "sensor",
            name,
            icon,
            entity_category=entity_category,
        )
        self._attr_native_value = native_value
        if native_unit_of_measurement is not None:
            self._attr_native_unit_of_measurement = native_unit_of_measurement
        self._attr_extra_state_attributes: dict[str, Any] = {}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return current state attributes."""
        return self._attr_extra_state_attributes

    async def async_publish(
        self,
        value: Any,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Publish state updates through the entity object."""
        self._attr_native_value = value
        self._attr_extra_state_attributes = dict(attributes or {})
        self.async_write_ha_state()


class EVSCDiagnosticSensor(EVSCBaseSensor):
    """EVSC Diagnostic Sensor showing real-time automation status."""

    def __init__(
        self,
        runtime_data: EVSCRuntimeData,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(
            runtime_data,
            entry_id,
            suffix,
            name,
            icon,
            native_value="Initializing",
        )

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        _LOGGER.info(
            "✅ Diagnostic sensor registered: %s (unique_id: %s)",
            self.entity_id,
            self.unique_id,
        )
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_native_value = last_state.state


class EVSCPriorityStateSensor(EVSCBaseSensor):
    """EVSC Priority State Sensor showing current charging priority."""

    def __init__(
        self,
        runtime_data: EVSCRuntimeData,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the priority sensor."""
        super().__init__(
            runtime_data,
            entry_id,
            suffix,
            name,
            icon,
            native_value="EV_Free",
        )

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        _LOGGER.info(
            "✅ Priority sensor registered: %s (unique_id: %s)",
            self.entity_id,
            self.unique_id,
        )
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_native_value = last_state.state
            self._attr_extra_state_attributes = dict(last_state.attributes)


class EVSCSolarSurplusDiagnosticSensor(EVSCBaseSensor):
    """EVSC Solar Surplus Diagnostic Sensor with detailed check information."""

    def __init__(
        self,
        runtime_data: EVSCRuntimeData,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the solar surplus diagnostic sensor."""
        super().__init__(
            runtime_data,
            entry_id,
            suffix,
            name,
            icon,
            native_value="Waiting for first check",
        )

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        _LOGGER.info(
            "✅ Solar Surplus Diagnostic sensor registered: %s (unique_id: %s)",
            self.entity_id,
            self.unique_id,
        )
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_native_value = last_state.state
            self._attr_extra_state_attributes = dict(last_state.attributes)


class EVSCLogFilePathSensor(EVSCEntityMixin, SensorEntity):
    """EVSC Log File Path Sensor."""

    _attr_should_poll = True

    def __init__(
        self,
        hass: HomeAssistant,
        runtime_data: EVSCRuntimeData,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        self._hass = hass
        self._init_evsc_entity(
            runtime_data,
            entry_id,
            suffix,
            "sensor",
            name,
            icon,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._attr_native_value = self._get_log_file_path()

    def _get_log_manager(self):
        """Return the runtime log manager when available."""
        return self._runtime_data.log_manager if self._runtime_data is not None else None

    def _get_log_file_path(self) -> str:
        """Get today's log file path from log manager."""
        log_manager = self._get_log_manager()
        if log_manager:
            return log_manager.get_log_file_path()

        now = datetime.now()
        return self._hass.config.path(
            "custom_components",
            "ev_smart_charger",
            "logs",
            str(now.year),
            f"{now.month:02d}",
            f"{now.day:02d}.log",
        )

    def _get_logs_directory(self) -> str:
        """Get base logs directory from log manager."""
        log_manager = self._get_log_manager()
        if log_manager:
            return log_manager.get_logs_directory()

        return self._hass.config.path(
            "custom_components",
            "ev_smart_charger",
            "logs",
        )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the state attributes."""
        return {
            "description": "Today's log file path (format: logs/<year>/<month>/<day>.log)",
            "friendly_name": "Log File Path",
            "logs_directory": self._get_logs_directory(),
            "structure": "logs/<year>/<month>/<day>.log",
        }

    async def async_update(self) -> None:
        """Update the sensor value."""
        self._attr_native_value = self._get_log_file_path()

    async def async_added_to_hass(self) -> None:
        """Entity added to hass."""
        await super().async_added_to_hass()
        _LOGGER.info(
            "✅ Log File Path sensor registered: %s (unique_id: %s)",
            self.entity_id,
            self.unique_id,
        )
        _LOGGER.info("  📄 Today's log file: %s", self._attr_native_value)


class EVSCTodayEVTargetSensor(EVSCBaseSensor):
    """EVSC Today EV Target Sensor."""

    def __init__(
        self,
        runtime_data: EVSCRuntimeData,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            runtime_data,
            entry_id,
            suffix,
            name,
            icon,
            native_value=None,
            native_unit_of_measurement="%",
        )

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        _LOGGER.info(
            "✅ Today EV Target sensor registered: %s (unique_id: %s)",
            self.entity_id,
            self.unique_id,
        )
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = (
                    float(last_state.state)
                    if last_state.state not in (None, "unknown", "unavailable")
                    else None
                )
            except (ValueError, TypeError):
                self._attr_native_value = None
            self._attr_extra_state_attributes = dict(last_state.attributes)


class EVSCTodayHomeTargetSensor(EVSCBaseSensor):
    """EVSC Today Home Target Sensor."""

    def __init__(
        self,
        runtime_data: EVSCRuntimeData,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            runtime_data,
            entry_id,
            suffix,
            name,
            icon,
            native_value=None,
            native_unit_of_measurement="%",
        )

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        _LOGGER.info(
            "✅ Today Home Target sensor registered: %s (unique_id: %s)",
            self.entity_id,
            self.unique_id,
        )
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = (
                    float(last_state.state)
                    if last_state.state not in (None, "unknown", "unavailable")
                    else None
                )
            except (ValueError, TypeError):
                self._attr_native_value = None
            self._attr_extra_state_attributes = dict(last_state.attributes)


class EVSCCachedEVSOCSensor(EVSCBaseSensor):
    """Reliable cache for a cloud-based EV SOC sensor."""

    def __init__(
        self,
        runtime_data: EVSCRuntimeData,
        entry_id: str,
        source_entity: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the cached sensor."""
        super().__init__(
            runtime_data,
            entry_id,
            suffix,
            name,
            icon,
            native_value=None,
            native_unit_of_measurement="%",
        )
        self._source_entity = source_entity
        self._attr_extra_state_attributes = {
            "source_entity": source_entity,
            "last_valid_update": None,
            "is_cached": False,
        }

    async def async_publish_cache(
        self,
        value: float,
        *,
        last_valid_update: datetime,
        is_cached: bool,
        cache_age_seconds: int,
    ) -> None:
        """Publish a cached EV SOC update."""
        await self.async_publish(
            value,
            {
                "source_entity": self._source_entity,
                "last_valid_update": last_valid_update.isoformat(),
                "is_cached": is_cached,
                "cache_age_seconds": cache_age_seconds,
            },
        )

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        _LOGGER.info(
            "✅ Cached EV SOC sensor registered: %s (unique_id: %s)",
            self.entity_id,
            self.unique_id,
        )
        _LOGGER.info("  🔗 Source sensor: %s", self._source_entity)
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = (
                    float(last_state.state)
                    if last_state.state not in (None, "unknown", "unavailable")
                    else None
                )
                _LOGGER.info("  🔄 Restored cached SOC: %s%%", self._attr_native_value)
            except (ValueError, TypeError):
                self._attr_native_value = None
                _LOGGER.warning("  ⚠️ Failed to restore cached SOC from: %s", last_state.state)
            self._attr_extra_state_attributes = dict(last_state.attributes)
