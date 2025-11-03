"""Switch platform for EV Smart Charger helper entities."""
from __future__ import annotations
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import STATE_ON

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EVSC switch entities."""
    _LOGGER.info(f"🔄 switch.py async_setup_entry called for entry {entry.entry_id}")

    entities = []

    # Create Forza Ricarica (Global Kill Switch)
    entities.append(
        EVSCSwitch(
            entry.entry_id,
            "evsc_forza_ricarica",
            "EVSC Forza Ricarica",
            "mdi:power",
        )
    )

    # Create Smart Charger Blocker Enable
    entities.append(
        EVSCSwitch(
            entry.entry_id,
            "evsc_smart_charger_blocker_enabled",
            "EVSC Smart Charger Blocker",
            "mdi:solar-power",
        )
    )

    # Create Use Home Battery switch
    entities.append(
        EVSCSwitch(
            entry.entry_id,
            "evsc_use_home_battery",
            "EVSC Use Home Battery",
            "mdi:home-battery",
        )
    )

    # Create Priority Balancer switch
    entities.append(
        EVSCSwitch(
            entry.entry_id,
            "evsc_priority_balancer_enabled",
            "EVSC Priority Balancer",
            "mdi:scale-balance",
        )
    )

    # Create Night Smart Charge switch
    entities.append(
        EVSCSwitch(
            entry.entry_id,
            "evsc_night_smart_charge_enabled",
            "EVSC Night Smart Charge",
            "mdi:moon-waning-crescent",
        )
    )

    # Notification switches (default ON)
    entities.append(
        EVSCSwitch(
            entry.entry_id,
            "evsc_notify_smart_blocker_enabled",
            "EVSC Notify Smart Blocker",
            "mdi:bell-outline",
            default_state=True
        )
    )

    entities.append(
        EVSCSwitch(
            entry.entry_id,
            "evsc_notify_priority_balancer_enabled",
            "EVSC Notify Priority Balancer",
            "mdi:bell-outline",
            default_state=True
        )
    )

    entities.append(
        EVSCSwitch(
            entry.entry_id,
            "evsc_notify_night_charge_enabled",
            "EVSC Notify Night Charge",
            "mdi:bell-outline",
            default_state=True
        )
    )

    async_add_entities(entities)
    _LOGGER.info(f"✅ Created {len(entities)} EVSC switch entities")


class EVSCSwitch(SwitchEntity, RestoreEntity):
    """EVSC Switch Entity (behaves like input_boolean)."""

    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        suffix: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the switch."""
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{suffix}"
        self._attr_name = name
        self._attr_icon = icon
        self._is_on = False
        # Set explicit entity_id to match pattern
        self.entity_id = f"switch.{DOMAIN}_{entry_id}_{suffix}"

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
