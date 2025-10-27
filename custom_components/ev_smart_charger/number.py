"""Number platform for EV Smart Charger helper entities."""
from __future__ import annotations
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    DEFAULT_SOLAR_THRESHOLD,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_GRID_IMPORT_THRESHOLD,
    DEFAULT_GRID_IMPORT_DELAY,
    DEFAULT_SURPLUS_DROP_DELAY,
    DEFAULT_HOME_BATTERY_MIN_SOC,
    DEFAULT_EV_MIN_SOC_WEEKDAY,
    DEFAULT_EV_MIN_SOC_WEEKEND,
)

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

    # Create Check Interval
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_check_interval",
            "EVSC Check Interval",
            "mdi:timer-outline",
            min_value=1,
            max_value=60,
            step=1,
            default_value=DEFAULT_CHECK_INTERVAL,
            unit="min",
        )
    )

    # Create Grid Import Threshold
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_grid_import_threshold",
            "EVSC Grid Import Threshold",
            "mdi:transmission-tower",
            min_value=0,
            max_value=1000,
            step=10,
            default_value=DEFAULT_GRID_IMPORT_THRESHOLD,
            unit="W",
        )
    )

    # Create Grid Import Delay
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_grid_import_delay",
            "EVSC Grid Import Delay",
            "mdi:timer-sand",
            min_value=0,
            max_value=120,
            step=5,
            default_value=DEFAULT_GRID_IMPORT_DELAY,
            unit="s",
        )
    )

    # Create Surplus Drop Delay
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_surplus_drop_delay",
            "EVSC Surplus Drop Delay",
            "mdi:timer-sand",
            min_value=0,
            max_value=120,
            step=5,
            default_value=DEFAULT_SURPLUS_DROP_DELAY,
            unit="s",
        )
    )

    # Create Home Battery Minimum SOC
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_home_battery_min_soc",
            "EVSC Home Battery Min SOC",
            "mdi:battery-50",
            min_value=0,
            max_value=100,
            step=5,
            default_value=DEFAULT_HOME_BATTERY_MIN_SOC,
            unit="%",
        )
    )

    # Create EV Minimum SOC for each day of the week
    # Monday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_ev_min_soc_monday",
            "EVSC EV Min SOC Monday",
            "mdi:calendar-monday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=DEFAULT_EV_MIN_SOC_WEEKDAY,
            unit="%",
        )
    )

    # Tuesday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_ev_min_soc_tuesday",
            "EVSC EV Min SOC Tuesday",
            "mdi:calendar-tuesday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=DEFAULT_EV_MIN_SOC_WEEKDAY,
            unit="%",
        )
    )

    # Wednesday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_ev_min_soc_wednesday",
            "EVSC EV Min SOC Wednesday",
            "mdi:calendar-wednesday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=DEFAULT_EV_MIN_SOC_WEEKDAY,
            unit="%",
        )
    )

    # Thursday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_ev_min_soc_thursday",
            "EVSC EV Min SOC Thursday",
            "mdi:calendar-thursday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=DEFAULT_EV_MIN_SOC_WEEKDAY,
            unit="%",
        )
    )

    # Friday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_ev_min_soc_friday",
            "EVSC EV Min SOC Friday",
            "mdi:calendar-friday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=DEFAULT_EV_MIN_SOC_WEEKDAY,
            unit="%",
        )
    )

    # Saturday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_ev_min_soc_saturday",
            "EVSC EV Min SOC Saturday",
            "mdi:calendar-saturday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=DEFAULT_EV_MIN_SOC_WEEKEND,
            unit="%",
        )
    )

    # Sunday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_ev_min_soc_sunday",
            "EVSC EV Min SOC Sunday",
            "mdi:calendar-sunday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=DEFAULT_EV_MIN_SOC_WEEKEND,
            unit="%",
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
        # Explicitly set entity_id for proper registration
        self.entity_id = f"number.{DOMAIN}_{entry_id}_{unique_id}"

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
