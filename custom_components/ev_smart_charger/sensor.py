from __future__ import annotations
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EVSCSensor(entry, data)], True)

class EVSCSensor(SensorEntity):
    _attr_name = "EVSC State"
    _attr_icon = "mdi:ev-station"
    _attr_should_poll = False
    def __init__(self, entry: ConfigEntry, data: dict):
        self._entry = entry
        self._data = data
        self._attr_unique_id = f"{entry.entry_id}_state"
    @property
    def native_value(self):
        return f"mode:{self._data.get('mode','off')}"
