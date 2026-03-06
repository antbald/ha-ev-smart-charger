"""Time entities for EV Smart Charger."""
from __future__ import annotations

import logging
from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_NIGHT_CHARGE_TIME,
    DEFAULT_CAR_READY_TIME,
)
from .entity_base import EVSCEntityMixin
from .runtime import get_runtime_data

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the time platform."""
    runtime_data = get_runtime_data(entry)
    entities = []

    # Night Charge Time (v0.9.3+)
    entities.append(
        EVSCTime(
            runtime_data,
            entry.entry_id,
            "evsc_night_charge_time",
            "Night Charge Time",
            "mdi:clock-time-one",
            DEFAULT_NIGHT_CHARGE_TIME,
        )
    )

    # Car Ready Time (v1.3.18+)
    entities.append(
        EVSCTime(
            runtime_data,
            entry.entry_id,
            "evsc_car_ready_time",
            "Car Ready Time",
            "mdi:clock-check",
            DEFAULT_CAR_READY_TIME,
        )
    )

    async_add_entities(entities, True)
    _LOGGER.info(f"✅ Created {len(entities)} EVSC time entities")


class EVSCTime(EVSCEntityMixin, RestoreEntity, TimeEntity):
    """Representation of an EVSC time entity."""

    def __init__(
        self,
        runtime_data,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
        default_value: str,
    ) -> None:
        """Initialize the time entity."""
        self._init_evsc_entity(
            runtime_data,
            entry_id,
            suffix,
            "time",
            name,
            icon,
            entity_category=EntityCategory.CONFIG,
        )
        self._default_value = default_value
        self._attr_native_value = None

    @property
    def native_value(self) -> time | None:
        """Return the time value."""
        return self._attr_native_value

    async def async_set_value(self, value: time) -> None:
        """Update the time."""
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore last state when added to hass."""
        await super().async_added_to_hass()

        # Try to restore previous state
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (None, "unknown", "unavailable"):
            try:
                # Parse time string "HH:MM:SS"
                time_parts = last_state.state.split(":")
                if len(time_parts) >= 2:
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])
                    second = int(time_parts[2]) if len(time_parts) > 2 else 0
                    self._attr_native_value = time(hour, minute, second)
                    _LOGGER.debug(f"Restored time entity {self._attr_name} to {self._attr_native_value}")
            except (ValueError, IndexError) as e:
                _LOGGER.warning(f"Failed to restore time entity {self._attr_name}: {e}")
                # Use default
                time_parts = self._default_value.split(":")
                self._attr_native_value = time(int(time_parts[0]), int(time_parts[1]), int(time_parts[2]))
        else:
            # Use default value
            time_parts = self._default_value.split(":")
            self._attr_native_value = time(int(time_parts[0]), int(time_parts[1]), int(time_parts[2]))
            _LOGGER.debug(f"Initialized time entity {self._attr_name} with default {self._attr_native_value}")
