"""Helper entity management for EV Smart Charger."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.input_boolean import InputBoolean
from homeassistant.components.input_number import InputNumber, NumberMode
from homeassistant.const import STATE_ON, STATE_OFF

from .const import (
    DOMAIN,
    HELPER_FORZA_RICARICA,
    HELPER_SMART_BLOCKER_ENABLED,
    HELPER_SOLAR_THRESHOLD,
    DEFAULT_SOLAR_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


class EVSCInputBoolean(RestoreEntity):
    """Input boolean helper for EVSC."""

    _attr_should_poll = False

    def __init__(
        self,
        entity_id: str,
        name: str,
        icon: str,
        default_state: bool = False
    ) -> None:
        """Initialize the input boolean."""
        self.entity_id = entity_id
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = entity_id
        self._state = default_state

    @property
    def state(self) -> str:
        """Return the state."""
        return STATE_ON if self._state else STATE_OFF

    @property
    def is_on(self) -> bool:
        """Return true if on."""
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        self._state = False
        self.async_write_ha_state()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle."""
        self._state = not self._state
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._state = last_state.state == STATE_ON


class EVSCInputNumber(RestoreEntity):
    """Input number helper for EVSC."""

    _attr_should_poll = False

    def __init__(
        self,
        entity_id: str,
        name: str,
        icon: str,
        min_value: float,
        max_value: float,
        step: float,
        default_value: float,
        unit: str | None = None,
    ) -> None:
        """Initialize the input number."""
        self.entity_id = entity_id
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = entity_id
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_mode = NumberMode.BOX
        self._value = default_value

    @property
    def state(self) -> float:
        """Return the state."""
        return self._value

    @property
    def native_value(self) -> float:
        """Return the value."""
        return self._value

    async def async_set_value(self, value: float) -> None:
        """Set new value."""
        if self._attr_native_min_value <= value <= self._attr_native_max_value:
            self._value = value
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore last value."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._value = float(last_state.state)
            except (ValueError, TypeError):
                self._value = self._attr_native_min_value


async def async_setup_helper_entities(hass: HomeAssistant, entry_id: str) -> list[Entity]:
    """Set up helper entities for the integration."""

    _LOGGER.info("Creating EVSC helper entities automatically...")

    entities = []

    # Create Forza Ricarica (Global Kill Switch)
    forza_ricarica = EVSCInputBoolean(
        entity_id=HELPER_FORZA_RICARICA,
        name="EVSC Forza Ricarica",
        icon="mdi:power",
        default_state=False,
    )
    entities.append(forza_ricarica)

    # Create Smart Charger Blocker Enable
    smart_blocker = EVSCInputBoolean(
        entity_id=HELPER_SMART_BLOCKER_ENABLED,
        name="EVSC Smart Charger Blocker",
        icon="mdi:solar-power",
        default_state=False,
    )
    entities.append(smart_blocker)

    # Create Solar Threshold
    solar_threshold = EVSCInputNumber(
        entity_id=HELPER_SOLAR_THRESHOLD,
        name="EVSC Solar Production Threshold",
        icon="mdi:solar-power-variant",
        min_value=0,
        max_value=1000,
        step=10,
        default_value=DEFAULT_SOLAR_THRESHOLD,
        unit="W",
    )
    entities.append(solar_threshold)

    _LOGGER.info(f"✅ Created {len(entities)} EVSC helper entities")

    return entities
