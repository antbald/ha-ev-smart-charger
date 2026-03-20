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

    # ── Switch definition table ──────────────────────────────────
    # (suffix, name, icon, default_state)
    _SWITCH_DEFS: list[tuple[str, str, str, bool]] = [
        # Core automation controls
        ("evsc_forza_ricarica", "Forza Ricarica", "mdi:power", False),
        ("evsc_boost_charge_enabled", "Boost Charge", "mdi:flash", False),
        ("evsc_smart_charger_blocker_enabled", "Smart Charger Blocker", "mdi:solar-power", False),
        ("evsc_use_home_battery", "Use Home Battery", "mdi:home-battery", False),
        ("evsc_priority_balancer_enabled", "Priority Balancer", "mdi:scale-balance", False),
        ("evsc_night_smart_charge_enabled", "Night Smart Charge", "mdi:moon-waning-crescent", False),
        (HELPER_PRESERVE_HOME_BATTERY_SUFFIX, "Preserve Home Battery", "mdi:battery-heart-variant", False),
        # Notification switches (default ON)
        ("evsc_notify_smart_blocker_enabled", "Notify Smart Blocker", "mdi:bell-outline", True),
        ("evsc_notify_priority_balancer_enabled", "Notify Priority Balancer", "mdi:bell-outline", True),
        ("evsc_notify_night_charge_enabled", "Notify Night Charge", "mdi:bell-outline", True),
        # Logging switches
        ("evsc_enable_file_logging", "Enable File Logging", "mdi:file-document-outline", False),
        (HELPER_TRACE_LOGGING_ENABLED_SUFFIX, "Trace Logging", "mdi:timeline-text-outline", False),
    ]

    entities = [
        EVSCSwitch(runtime_data, entry.entry_id, *defn)
        for defn in _SWITCH_DEFS
    ]

    # Car Ready switches — generated per day (v1.3.13+)
    _DAYS = [
        ("monday", DEFAULT_CAR_READY_WEEKDAY),
        ("tuesday", DEFAULT_CAR_READY_WEEKDAY),
        ("wednesday", DEFAULT_CAR_READY_WEEKDAY),
        ("thursday", DEFAULT_CAR_READY_WEEKDAY),
        ("friday", DEFAULT_CAR_READY_WEEKDAY),
        ("saturday", DEFAULT_CAR_READY_WEEKEND),
        ("sunday", DEFAULT_CAR_READY_WEEKEND),
    ]
    for day, default in _DAYS:
        entities.append(
            EVSCSwitch(
                runtime_data,
                entry.entry_id,
                f"evsc_car_ready_{day}",
                f"Car Ready {day.capitalize()}",
                "mdi:car-clock",
                default,
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

        # CRITICAL FIX (v1.6.0): Push restored value to state machine immediately
        # Without this, state remains "unavailable" until manual modification
        self.async_write_ha_state()
