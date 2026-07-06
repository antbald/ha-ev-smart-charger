"""Runtime monitor for EV charging Live Activities."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_CAR_OWNER,
    CONF_NOTIFY_SERVICES,
    HELPER_CHARGING_PROFILE_SUFFIX,
    HELPER_FORZA_RICARICA_SUFFIX,
)
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger
from .utils.mobile_notification_service import MobileNotificationService

LIVE_ACTIVITY_MONITOR_INTERVAL_SECONDS = 60
LIVE_ACTIVITY_CLEAR_AFTER_INACTIVE_TICKS = 2


class EVChargingLiveActivityMonitor:
    """Keep a Live Activity open for normal, non-Boost/Night charging."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict[str, Any],
        runtime_data: EVSCRuntimeData,
    ) -> None:
        """Initialize the normal charging Live Activity monitor."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self._runtime_data = runtime_data
        self.logger = EVSCLogger("LIVE ACTIVITY")
        self._mobile_notifier = MobileNotificationService(
            hass,
            config.get(CONF_NOTIFY_SERVICES, []),
            entry_id,
            config.get(CONF_CAR_OWNER),
            runtime_data=runtime_data,
        )
        self._timer_unsub = None
        self._inactive_ticks = 0
        self._live_activity_active = False

    async def async_setup(self) -> None:
        """Start the coarse polling monitor."""
        self._timer_unsub = async_track_time_interval(
            self.hass,
            self._async_tick,
            timedelta(seconds=LIVE_ACTIVITY_MONITOR_INTERVAL_SECONDS),
        )
        await self._async_tick()
        self.logger.info(
            "Normal charging Live Activity monitor started (%ss interval)",
            LIVE_ACTIVITY_MONITOR_INTERVAL_SECONDS,
        )

    async def async_remove(self) -> None:
        """Stop the monitor."""
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None
        self.logger.info("Normal charging Live Activity monitor removed")

    async def _async_tick(self, now=None) -> None:
        """Update or clear the Live Activity based on normal charging state."""
        if self._is_boost_or_night_active():
            self._inactive_ticks = 0
            self._live_activity_active = False
            return

        if not self._is_charging():
            self._inactive_ticks += 1
            if (
                self._live_activity_active
                and self._inactive_ticks >= LIVE_ACTIVITY_CLEAR_AFTER_INACTIVE_TICKS
            ):
                await self._mobile_notifier.clear_ev_charging_live_activity()
                self._live_activity_active = False
            return

        self._inactive_ticks = 0
        await self._mobile_notifier.send_ev_charging_live_activity(
            mode=self._mode_label(),
        )
        self._live_activity_active = True

    def _is_boost_or_night_active(self) -> bool:
        boost_charge = self._runtime_data.boost_charge
        if boost_charge is not None and boost_charge.is_active():
            return True

        night_smart_charge = self._runtime_data.night_smart_charge
        return night_smart_charge is not None and night_smart_charge.is_active()

    def _is_charging(self) -> bool:
        power_model = self._runtime_data.power_model
        if power_model is None:
            return False
        try:
            return power_model.is_charging(self.hass)
        except Exception as err:
            self.logger.debug("Live Activity charging check failed: %s", err)
            return False

    def _mode_label(self) -> str:
        if self._is_force_charge_enabled():
            return "Force Charge"
        if self._is_solar_surplus_context():
            return "Solar Surplus"
        return "Charging"

    def _is_force_charge_enabled(self) -> bool:
        entity_id = self._runtime_data.get_entity_id(HELPER_FORZA_RICARICA_SUFFIX)
        state = self.hass.states.get(entity_id) if entity_id else None
        return state is not None and state.state == STATE_ON

    def _is_solar_surplus_context(self) -> bool:
        coordinator = self._runtime_data.coordinator
        if (
            coordinator is not None
            and coordinator.get_active_automation_name() == "Solar Surplus"
        ):
            return True

        entity_id = self._runtime_data.get_entity_id(HELPER_CHARGING_PROFILE_SUFFIX)
        state = self.hass.states.get(entity_id) if entity_id else None
        return state is not None and state.state == "solar_surplus"
