"""Select platform for EV Smart Charger helper entities."""
from __future__ import annotations
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, CHARGING_PROFILES, PROFILE_MANUAL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EVSC select entities."""

    entities = []

    # Create Charging Profile Selector
    entities.append(
        EVSCSelect(
            entry.entry_id,
            "evsc_charging_profile",
            "EVSC Charging Profile",
            "mdi:ev-station",
            CHARGING_PROFILES,
        )
    )

    async_add_entities(entities)
    _LOGGER.info(f"✅ Created {len(entities)} EVSC select entities")


class EVSCSelect(SelectEntity, RestoreEntity):
    """EVSC Select Entity (behaves like input_select)."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str,
        unique_id: str,
        name: str,
        icon: str,
        options: list[str],
    ) -> None:
        """Initialize the select."""
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{unique_id}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_options = options
        self._current_option = PROFILE_MANUAL  # Default to manual

    @property
    def current_option(self) -> str:
        """Return the selected option."""
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option in self.options:
            self._current_option = option
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore last selected option."""
        await super().async_added_to_hass()
        _LOGGER.info(f"✅ Select entity registered: {self.entity_id} (unique_id: {self.unique_id})")

        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state in self.options:
                self._current_option = last_state.state
