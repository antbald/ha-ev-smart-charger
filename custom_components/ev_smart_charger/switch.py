"""Switch platform for EV Smart Charger helper entities."""
from __future__ import annotations
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import STATE_ON

from .const import (
    DEFAULT_CAR_READY_WEEKDAY,
    DEFAULT_CAR_READY_WEEKEND,
    HELPER_PRESERVE_HOME_BATTERY_SUFFIX,
    HELPER_TRACE_LOGGING_ENABLED_SUFFIX,
)
from .entity_base import EVSCEntityMixin
from .runtime import get_runtime_data

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EVSC switch entities."""
    _LOGGER.info(f"🔄 switch.py async_setup_entry called for entry {entry.entry_id}")

    runtime_data = get_runtime_data(entry)
    entities = []

    # Create Forza Ricarica (Global Kill Switch)
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_forza_ricarica",
            "Forza Ricarica",
            "mdi:power",
        )
    )

    # Create Boost Charge switch
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_boost_charge_enabled",
            "Boost Charge",
            "mdi:flash",
        )
    )

    # Create Smart Charger Blocker Enable
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_smart_charger_blocker_enabled",
            "Smart Charger Blocker",
            "mdi:solar-power",
        )
    )

    # Create Use Home Battery switch
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_use_home_battery",
            "Use Home Battery",
            "mdi:home-battery",
        )
    )

    # Create Priority Balancer switch
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_priority_balancer_enabled",
            "Priority Balancer",
            "mdi:scale-balance",
        )
    )

    # Create Night Smart Charge switch
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_night_smart_charge_enabled",
            "Night Smart Charge",
            "mdi:moon-waning-crescent",
        )
    )

    # Create Preserve Home Battery switch
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            HELPER_PRESERVE_HOME_BATTERY_SUFFIX,
            "Preserve Home Battery",
            "mdi:battery-heart-variant",
            default_state=False,
        )
    )

    # Notification switches (default ON)
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_notify_smart_blocker_enabled",
            "Notify Smart Blocker",
            "mdi:bell-outline",
            default_state=True
        )
    )

    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_notify_priority_balancer_enabled",
            "Notify Priority Balancer",
            "mdi:bell-outline",
            default_state=True
        )
    )

    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_notify_night_charge_enabled",
            "Notify Night Charge",
            "mdi:bell-outline",
            default_state=True
        )
    )

    # File Logging switch (v1.3.25)
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_enable_file_logging",
            "Enable File Logging",
            "mdi:file-document-outline",
            default_state=False  # Default OFF to save storage
        )
    )

    # Trace Logging switch
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            HELPER_TRACE_LOGGING_ENABLED_SUFFIX,
            "Trace Logging",
            "mdi:timeline-text-outline",
            default_state=False,
        )
    )

    # Car Ready switches (v1.3.13+)
    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_car_ready_monday",
            "Car Ready Monday",
            "mdi:car-clock",
            default_state=DEFAULT_CAR_READY_WEEKDAY,
        )
    )

    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_car_ready_tuesday",
            "Car Ready Tuesday",
            "mdi:car-clock",
            default_state=DEFAULT_CAR_READY_WEEKDAY,
        )
    )

    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_car_ready_wednesday",
            "Car Ready Wednesday",
            "mdi:car-clock",
            default_state=DEFAULT_CAR_READY_WEEKDAY,
        )
    )

    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_car_ready_thursday",
            "Car Ready Thursday",
            "mdi:car-clock",
            default_state=DEFAULT_CAR_READY_WEEKDAY,
        )
    )

    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_car_ready_friday",
            "Car Ready Friday",
            "mdi:car-clock",
            default_state=DEFAULT_CAR_READY_WEEKDAY,
        )
    )

    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_car_ready_saturday",
            "Car Ready Saturday",
            "mdi:car-clock",
            default_state=DEFAULT_CAR_READY_WEEKEND,
        )
    )

    entities.append(
        EVSCSwitch(
            runtime_data,
            entry.entry_id,
            "evsc_car_ready_sunday",
            "Car Ready Sunday",
            "mdi:car-clock",
            default_state=DEFAULT_CAR_READY_WEEKEND,
        )
    )

    async_add_entities(entities)
    _LOGGER.info(f"✅ Created {len(entities)} EVSC switch entities")


class EVSCSwitch(EVSCEntityMixin, SwitchEntity, RestoreEntity):
    """EVSC Switch Entity (behaves like input_boolean)."""

    _attr_should_poll = False

    def __init__(
        self,
        runtime_data,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
        default_state: bool = False,
    ) -> None:
        """Initialize the switch."""
        self._init_evsc_entity(
            runtime_data,
            entry_id,
            suffix,
            "switch",
            name,
            icon,
            entity_category=EntityCategory.CONFIG,
        )
        self._is_on = default_state
        self._default_state = default_state

    @property
    def is_on(self) -> bool:
        """Return true if on."""
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on."""
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off."""
        self._is_on = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        _LOGGER.info(f"✅ Switch entity registered: {self.entity_id} (unique_id: {self.unique_id})")

        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == STATE_ON
            _LOGGER.info(f"  ↩️ Restored state: {self._is_on}")
        else:
            # No previous state, use default
            self._is_on = self._default_state
            _LOGGER.info(f"  🆕 No previous state, using default: {self._is_on}")
