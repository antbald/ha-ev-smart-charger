"""Runtime monitor for EV charging Live Activities."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from homeassistant.util import dt as dt_util

from .const import (
    CONF_CAR_OWNER,
    CONF_NOTIFY_SERVICES,
    HELPER_CHARGING_PROFILE_SUFFIX,
    HELPER_FORZA_RICARICA_SUFFIX,
    LIVE_ACTIVITY_CLEAR_GRACE_SECONDS,
    LIVE_ACTIVITY_MODE_CHARGING,
    LIVE_ACTIVITY_MODE_FORCE_CHARGE,
    LIVE_ACTIVITY_MODE_SOLAR_SURPLUS,
)
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger
from .utils.mobile_notification_service import MobileNotificationService

LIVE_ACTIVITY_MONITOR_INTERVAL_SECONDS = 60


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
        # v2.12.0: measured in wall-clock seconds instead of ticks. The Tuya
        # safe-decrease sequence (stop → 5s → set → 1s → start) makes measured
        # power read zero for a few seconds on every amperage step, so a tick
        # landing inside that window used to count as "not charging" and could
        # end the activity after two of them — and each restart costs
        # push-to-start budget.
        self._not_charging_since = None
        self._last_enabled = False

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
        """Stop the monitor and close any activity it left on screen."""
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None
        # An unclosed activity would otherwise sit on the lock screen with
        # frozen data until Apple expires it (up to 8 hours).
        await self._mobile_notifier.clear_ev_charging_live_activity()
        self.logger.info("Normal charging Live Activity monitor removed")

    async def _async_tick(self, now=None) -> None:
        """Update or clear the Live Activity based on normal charging state."""
        enabled = self._mobile_notifier.is_live_activity_enabled()
        if not enabled:
            if self._last_enabled:
                await self._mobile_notifier.clear_ev_charging_live_activity()
            self._not_charging_since = None
            self._last_enabled = False
            return

        self._last_enabled = True

        if self._is_boost_or_night_active():
            # Boost / Night Charge own the tag while active and keep it fresh
            # from their own monitors; the normal path must not fight them.
            self._not_charging_since = None
            return

        if not self._is_charging():
            await self._async_handle_not_charging()
            return

        self._not_charging_since = None
        await self._mobile_notifier.send_ev_charging_live_activity(
            mode=self._mode_label(),
        )

    async def _async_handle_not_charging(self) -> None:
        """Close the activity only after a sustained charging gap."""
        state = self._runtime_data.live_activity
        if not state.active:
            self._not_charging_since = None
            return

        now = dt_util.utcnow()
        if self._not_charging_since is None:
            self._not_charging_since = now
            return

        elapsed = (now - self._not_charging_since).total_seconds()
        if elapsed < LIVE_ACTIVITY_CLEAR_GRACE_SECONDS:
            return

        await self._mobile_notifier.clear_ev_charging_live_activity()
        self._not_charging_since = None

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
            return LIVE_ACTIVITY_MODE_FORCE_CHARGE
        if self._is_solar_surplus_context():
            return LIVE_ACTIVITY_MODE_SOLAR_SURPLUS
        return LIVE_ACTIVITY_MODE_CHARGING

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
