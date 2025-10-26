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

    async_add_entities(entities)
    _LOGGER.info(f"✅ Created {len(entities)} EVSC switch entities")


class EVSCSwitch(SwitchEntity, RestoreEntity):
    """EVSC Switch Entity (behaves like input_boolean)."""

    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        unique_id: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the switch."""
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{unique_id}"
        self._attr_name = name
        self._attr_icon = icon
        self._is_on = False

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

        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == STATE_ON
