from __future__ import annotations
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.select import SelectEntity
from .const import DOMAIN, MODES

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EVSCModeSelect(entry, data)], True)

class EVSCModeSelect(SelectEntity):
    _attr_name = "EVSC Mode"
    _attr_icon = "mdi:car-electric"
    _attr_should_poll = False
    _attr_options = MODES
    def __init__(self, entry: ConfigEntry, data: dict):
        self._entry = entry
        self._data = data
        self._attr_unique_id = f"{entry.entry_id}_mode"
    @property
    def current_option(self) -> str:
        return self._data.get("mode", "off")
    async def async_select_option(self, option: str) -> None:
        if option in self.options:
            self._data["mode"] = option
            self.async_write_ha_state()
