"""Number entities for EV Smart Charger."""
from __future__ import annotations
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_GRID_IMPORT_THRESHOLD,
    DEFAULT_GRID_IMPORT_DELAY,
    DEFAULT_SURPLUS_DROP_DELAY,
    DEFAULT_HOME_BATTERY_MIN_SOC,
    DEFAULT_BATTERY_SUPPORT_AMPERAGE,
    DEFAULT_EV_MIN_SOC_WEEKDAY,
    DEFAULT_EV_MIN_SOC_WEEKEND,
    DEFAULT_HOME_MIN_SOC,
    DEFAULT_MIN_SOLAR_FORECAST_THRESHOLD,
    DEFAULT_NIGHT_CHARGE_AMPERAGE,
    DEFAULT_BOOST_CHARGE_AMPERAGE,
    DEFAULT_BOOST_TARGET_SOC,
)
from .entity_base import EVSCEntityMixin
from .runtime import get_runtime_data

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EVSC number entities."""

    runtime_data = get_runtime_data(entry)

    # ── Number definition table ──────────────────────────────────
    # (suffix, name, icon, min, max, step, default, unit)
    _NUMBER_DEFS: list[tuple[str, str, str, float, float, float, float, str]] = [
        # Solar Surplus controls
        ("evsc_check_interval", "EVSC Check Interval", "mdi:timer-outline", 1, 60, 1, DEFAULT_CHECK_INTERVAL, "min"),
        ("evsc_grid_import_threshold", "EVSC Grid Import Threshold", "mdi:transmission-tower", 0, 1000, 10, DEFAULT_GRID_IMPORT_THRESHOLD, "W"),
        ("evsc_grid_import_delay", "EVSC Grid Import Delay", "mdi:timer-sand", 0, 120, 5, DEFAULT_GRID_IMPORT_DELAY, "s"),
        ("evsc_surplus_drop_delay", "EVSC Surplus Drop Delay", "mdi:timer-sand", 0, 120, 5, DEFAULT_SURPLUS_DROP_DELAY, "s"),
        # Home battery
        ("evsc_home_battery_min_soc", "EVSC Home Battery Min SOC", "mdi:battery-50", 0, 100, 5, DEFAULT_HOME_BATTERY_MIN_SOC, "%"),
        ("evsc_battery_support_amperage", "EVSC Battery Support Amperage", "mdi:current-ac", 6, 32, 2, DEFAULT_BATTERY_SUPPORT_AMPERAGE, "A"),
        # Night Smart Charge
        ("evsc_min_solar_forecast_threshold", "EVSC Min Solar Forecast Threshold", "mdi:solar-power-variant", 0, 100, 1, DEFAULT_MIN_SOLAR_FORECAST_THRESHOLD, "kWh"),
        ("evsc_night_charge_amperage", "EVSC Night Charge Amperage", "mdi:current-ac", 6, 32, 2, DEFAULT_NIGHT_CHARGE_AMPERAGE, "A"),
        # Boost Charge
        ("evsc_boost_charge_amperage", "EVSC Boost Charge Amperage", "mdi:flash", 6, 32, 2, DEFAULT_BOOST_CHARGE_AMPERAGE, "A"),
        ("evsc_boost_target_soc", "EVSC Boost Target SOC", "mdi:battery-charging-90", 0, 100, 1, DEFAULT_BOOST_TARGET_SOC, "%"),
    ]

    entities = [
        EVSCNumber(
            runtime_data, entry.entry_id,
            suffix, name, icon,
            min_value=mn, max_value=mx, step=st,
            default_value=dv, unit=u,
        )
        for suffix, name, icon, mn, mx, st, dv, u in _NUMBER_DEFS
    ]

    # Daily SOC targets — generated per day
    _DAYS = [
        ("monday", DEFAULT_EV_MIN_SOC_WEEKDAY),
        ("tuesday", DEFAULT_EV_MIN_SOC_WEEKDAY),
        ("wednesday", DEFAULT_EV_MIN_SOC_WEEKDAY),
        ("thursday", DEFAULT_EV_MIN_SOC_WEEKDAY),
        ("friday", DEFAULT_EV_MIN_SOC_WEEKDAY),
        ("saturday", DEFAULT_EV_MIN_SOC_WEEKEND),
        ("sunday", DEFAULT_EV_MIN_SOC_WEEKEND),
    ]
    for day, ev_default in _DAYS:
        cap = day.capitalize()
        # EV daily SOC target
        entities.append(
            EVSCNumber(
                runtime_data, entry.entry_id,
                f"evsc_ev_min_soc_{day}",
                f"EVSC EV Min SOC {cap}",
                f"mdi:calendar-{day}",
                min_value=0, max_value=100, step=5,
                default_value=ev_default, unit="%",
            )
        )
        # Home daily SOC target
        entities.append(
            EVSCNumber(
                runtime_data, entry.entry_id,
                f"evsc_home_min_soc_{day}",
                f"EVSC Home Min SOC {cap}",
                f"mdi:calendar-{day}",
                min_value=0, max_value=100, step=5,
                default_value=DEFAULT_HOME_MIN_SOC, unit="%",
            )
        )

    async_add_entities(entities)
    _LOGGER.info(f"✅ Created {len(entities)} EVSC number entities")


class EVSCNumber(EVSCEntityMixin, NumberEntity, RestoreEntity):
    """EVSC Number Entity (behaves like input_number)."""

    _attr_should_poll = False
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        runtime_data,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
        min_value: float,
        max_value: float,
        step: float,
        default_value: float,
        unit: str | None = None,
    ) -> None:
        """Initialize the number."""
        self._init_evsc_entity(
            runtime_data,
            entry_id,
            suffix,
            "number",
            name,
            icon,
            entity_category=EntityCategory.CONFIG,
        )
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
                _LOGGER.info(f"✅ Restored {self.entity_id} = {self._value}")
            except (ValueError, TypeError):
                self._value = self._attr_native_min_value
                _LOGGER.warning(f"⚠️ Failed to restore {self.entity_id}, using default {self._value}")
        else:
            _LOGGER.info(f"ℹ️ No previous state for {self.entity_id}, using default {self._value}")

        # CRITICAL FIX (v1.3.22): Push restored value to state machine immediately
        # Without this, state remains "unavailable" for hours until manual modification
        self.async_write_ha_state()
