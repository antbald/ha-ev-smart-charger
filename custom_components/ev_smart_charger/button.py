"""On-demand Lovelace dashboard creation for EV Smart Charger."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .dashboard_manager import (
    async_offer_dashboard_builder,
    async_prepare_dashboard_builder,
)
from .entity_base import EVSCEntityMixin
from .runtime import get_runtime_data


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Expose a non-polling configuration button on the charger device."""
    async_add_entities([BuildCustomDashboardButton(entry)])


class BuildCustomDashboardButton(EVSCEntityMixin, ButtonEntity):
    """Prepare the native admin builder without modifying an existing dashboard."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._init_evsc_entity(
            get_runtime_data(entry),
            entry.entry_id,
            "build_custom_dashboard",
            "button",
            None,
            "mdi:view-dashboard-plus-outline",
            entity_category=EntityCategory.CONFIG,
            translation_key="build_custom_dashboard",
        )

    async def async_press(self) -> None:
        """Require the same admin role as Home Assistant Dashboard Settings."""
        user_id = getattr(self._context, "user_id", None)
        user = await self.hass.auth.async_get_user(user_id) if user_id else None
        if user is None or not user.is_active or not user.is_admin:
            raise HomeAssistantError("An administrator must press Build Custom Dashboard")
        if not await async_prepare_dashboard_builder(self.hass, self._entry):
            raise HomeAssistantError(
                "The dashboard builder is unavailable. Add the EV Smart Charger card "
                "in Settings > Dashboards."
            )
        async_offer_dashboard_builder(self.hass, self._entry)
