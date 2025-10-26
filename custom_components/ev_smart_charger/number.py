"""Number platform for EV Smart Charger helper entities."""
from __future__ import annotations
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, DEFAULT_SOLAR_THRESHOLD

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EVSC number entities."""

    entities = []

    # Create Solar Threshold
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_solar_production_threshold",
            "EVSC Solar Production Threshold",
            "mdi:solar-power-variant",
            min_value=0,
            max_value=1000,
            step=10,
            default_value=DEFAULT_SOLAR_THRESHOLD,
            unit="W",
        )
    )

    async_add_entities(entities)
    _LOGGER.info(f"✅ Created {len(entities)} EVSC number entities")


class EVSCNumber(NumberEntity, RestoreEntity):
    """EVSC Number Entity (behaves like input_number)."""

    _attr_should_poll = False
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        entry_id: str,
        unique_id: str,
        name: str,
        icon: str,
        min_value: float,
        max_value: float,
        step: float,
        default_value: float,
        unit: str | None = None,
    ) -> None:
        """Initialize the number."""
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{unique_id}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._value = default_value

    @property
    def native_value(self) -> float:
        """Return the value."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
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
