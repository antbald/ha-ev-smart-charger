"""Shared entity helpers for EV Smart Charger."""
from __future__ import annotations

from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, VERSION
from .runtime import EVSCRuntimeData


class EVSCEntityMixin:
    """Shared metadata and runtime registration for EVSC entities."""

    _attr_has_entity_name = True

    def _init_evsc_entity(
        self,
        runtime_data: EVSCRuntimeData | None,
        entry_id: str,
        key: str,
        entity_domain: str,
        name: str | None,
        icon: str | None = None,
        *,
        entity_category: EntityCategory | None = None,
        translation_key: str | None = None,
    ) -> None:
        """Initialize EVSC shared entity metadata."""
        self._runtime_data = runtime_data
        self._entry_id = entry_id
        self._entity_key = key
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{key}"
        self._attr_name = name if translation_key is None else None
        self._attr_translation_key = translation_key or key
        if icon is not None:
            self._attr_icon = icon
        if entity_category is not None:
            self._attr_entity_category = entity_category
        self.entity_id = f"{entity_domain}.{DOMAIN}_{entry_id}_{key}"

    @property
    def device_info(self):
        """Return device info to group all entities under one device."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "EV Smart Charger",
            "manufacturer": "antbald",
            "model": "EV Smart Charger",
            "sw_version": VERSION,
        }

    async def async_added_to_hass(self) -> None:
        """Register the entity in runtime data when it is added to hass."""
        await super().async_added_to_hass()
        if self._runtime_data is not None:
            self._runtime_data.register_entity(
                self._entity_key,
                self.entity_id,
                self,
            )
