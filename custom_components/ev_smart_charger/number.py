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
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_GRID_IMPORT_THRESHOLD,
    DEFAULT_GRID_IMPORT_DELAY,
    DEFAULT_SURPLUS_DROP_DELAY,
    DEFAULT_HOME_BATTERY_MIN_SOC,
    DEFAULT_EV_MIN_SOC_WEEKDAY,
    DEFAULT_EV_MIN_SOC_WEEKEND,
    DEFAULT_MIN_SOLAR_FORECAST_THRESHOLD,
    DEFAULT_NIGHT_CHARGE_AMPERAGE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EVSC number entities."""

    entities = []

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

    # Create Home Battery Minimum SOC for each day of the week (for Priority Balancer)
    # Monday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_home_min_soc_monday",
            "EVSC Home Min SOC Monday",
            "mdi:calendar-monday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=50,
            unit="%",
        )
    )

    # Tuesday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_home_min_soc_tuesday",
            "EVSC Home Min SOC Tuesday",
            "mdi:calendar-tuesday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=50,
            unit="%",
        )
    )

    # Wednesday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_home_min_soc_wednesday",
            "EVSC Home Min SOC Wednesday",
            "mdi:calendar-wednesday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=50,
            unit="%",
        )
    )

    # Thursday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_home_min_soc_thursday",
            "EVSC Home Min SOC Thursday",
            "mdi:calendar-thursday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=50,
            unit="%",
        )
    )

    # Friday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_home_min_soc_friday",
            "EVSC Home Min SOC Friday",
            "mdi:calendar-friday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=50,
            unit="%",
        )
    )

    # Saturday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_home_min_soc_saturday",
            "EVSC Home Min SOC Saturday",
            "mdi:calendar-saturday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=50,
            unit="%",
        )
    )

    # Sunday
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_home_min_soc_sunday",
            "EVSC Home Min SOC Sunday",
            "mdi:calendar-sunday",
            min_value=0,
            max_value=100,
            step=5,
            default_value=50,
            unit="%",
        )
    )

    # Create Night Smart Charge entities
    # Minimum Solar Forecast Threshold
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_min_solar_forecast_threshold",
            "EVSC Min Solar Forecast Threshold",
            "mdi:solar-power-variant",
            min_value=0,
            max_value=100,
            step=1,
            default_value=DEFAULT_MIN_SOLAR_FORECAST_THRESHOLD,
            unit="kWh",
        )
    )

    # Night Charge Amperage
    entities.append(
        EVSCNumber(
            entry.entry_id,
            "evsc_night_charge_amperage",
            "EVSC Night Charge Amperage",
            "mdi:current-ac",
            min_value=6,
            max_value=32,
            step=2,
            default_value=DEFAULT_NIGHT_CHARGE_AMPERAGE,
            unit="A",
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
        _LOGGER.info(f"✅ Number entity registered: {self.entity_id} (unique_id: {self.unique_id})")

        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._value = float(last_state.state)
            except (ValueError, TypeError):
                self._value = self._attr_native_min_value
