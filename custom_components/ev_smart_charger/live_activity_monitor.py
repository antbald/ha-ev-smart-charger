"""Runtime monitor for EV charging Live Activities."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from homeassistant.util import dt as dt_util

from .const import (
    CONF_CAR_OWNER,
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_NOTIFY_SERVICES,
    HELPER_CHARGING_PROFILE_SUFFIX,
    HELPER_FORZA_RICARICA_SUFFIX,
    HELPER_LIVE_ACTIVITIES_ENABLED_SUFFIX,
    HELPER_STOP_CHARGING_SUFFIX,
    LIVE_ACTIVITY_CLEAR_GRACE_SECONDS,
    LIVE_ACTIVITY_DEFINITIVE_STOP_GRACE_SECONDS,
    LIVE_ACTIVITY_MODE_CHARGING,
    LIVE_ACTIVITY_MODE_FORCE_CHARGE,
    LIVE_ACTIVITY_MODE_SOLAR_SURPLUS,
    LIVE_ACTIVITY_STOP_GRACE_SECONDS,
)
from .power_model import is_charge_complete_status, is_disconnected_status
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger
from .utils.mobile_notification_service import MobileNotificationService

LIVE_ACTIVITY_MONITOR_INTERVAL_SECONDS = 60

# Stop signal tiers (see the grace constants in const.py).
STOP_SIGNAL_UNPLUGGED = "unplugged"
STOP_SIGNAL_COMPLETE = "charge_complete"
STOP_SIGNAL_MANUAL_STOP = "manual_stop"
STOP_SIGNAL_CHARGER_OFF = "charger_off"

# Signals that a running amperage step can never produce.
_DEFINITIVE_STOP_SIGNALS = (
    STOP_SIGNAL_UNPLUGGED,
    STOP_SIGNAL_COMPLETE,
    STOP_SIGNAL_MANUAL_STOP,
)


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
        self._state_unsub = None
        # v2.12.0: measured in wall-clock seconds instead of ticks. The Tuya
        # safe-decrease sequence (stop → 5s → set → 1s → start) makes measured
        # power read zero for a few seconds on every amperage step, so a tick
        # landing inside that window used to count as "not charging" and could
        # end the activity after two of them — and each restart costs
        # push-to-start budget.
        self._not_charging_since = None
        self._last_enabled = False

    async def async_setup(self) -> None:
        """Start the coarse polling monitor and the stop-signal listeners."""
        self._timer_unsub = async_track_time_interval(
            self.hass,
            self._async_tick,
            timedelta(seconds=LIVE_ACTIVITY_MONITOR_INTERVAL_SECONDS),
        )
        self._register_state_listeners()
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
        if self._state_unsub:
            self._state_unsub()
            self._state_unsub = None
        # An unclosed activity would otherwise sit on the lock screen with
        # frozen data until Apple expires it (up to 8 hours).
        await self._mobile_notifier.clear_ev_charging_live_activity()
        self.logger.info("Normal charging Live Activity monitor removed")

    # ========== EVENT WIRING (v2.12.1) ==========

    def _register_state_listeners(self) -> None:
        """React to the discrete signals that end a charging session.

        Polling alone answered "is the session over?" up to 60 s late, on top of
        the grace period — long enough for a user who just unplugged to keep
        staring at a card that says the car is charging. Only *discrete* signals
        are subscribed: the measured charging power moves continuously and would
        fire dozens of events per minute for no decision it can make on its own
        (a power dip is the ambiguous tier, which the interval tick handles).
        """
        entities = [
            self.config.get(CONF_EV_CHARGER_SWITCH),
            self.config.get(CONF_EV_CHARGER_STATUS),
            self._runtime_data.get_entity_id(HELPER_STOP_CHARGING_SUFFIX),
            self._runtime_data.get_entity_id(HELPER_FORZA_RICARICA_SUFFIX),
            self._runtime_data.get_entity_id(
                HELPER_LIVE_ACTIVITIES_ENABLED_SUFFIX
            ),
        ]
        tracked = sorted({entity for entity in entities if entity})
        if not tracked:
            self.logger.debug(
                "No discrete charging-state entities mapped, "
                "Live Activity monitor stays interval-only"
            )
            return

        self._state_unsub = async_track_state_change_event(
            self.hass, tracked, self._async_state_event
        )
        self.logger.debug(
            "Live Activity stop listeners registered on %s", ", ".join(tracked)
        )

    async def _async_state_event(self, event) -> None:
        """Re-evaluate immediately when a discrete signal changes."""
        await self._async_tick()

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

        # v2.12.1: a classified stop signal OUTRANKS the measured reading. The
        # reported failure was a card frozen on "charging" after the session
        # ended, and the only way the old power/status check could produce that
        # is a wallbox power sensor that keeps its last value (or a status that
        # lags) once the charger is switched off — in which case is_charging()
        # answers True forever and the clear path was never even reached.
        stop_signal = self._stop_signal()
        charging = stop_signal is None and self._is_charging()

        if self._is_boost_or_night_active():
            # Boost / Night Charge own the tag while active and keep it fresh
            # from their own monitors; the normal path must not fight them —
            # except on a definitive end-of-session signal, because a session
            # object that lingers "active" after the cable came out must not
            # pin a stale "charging" card on the Lock Screen.
            if stop_signal in _DEFINITIVE_STOP_SIGNALS:
                await self._async_handle_not_charging(stop_signal)
                return
            self._not_charging_since = None
            return

        if not charging:
            await self._async_handle_not_charging(stop_signal)
            return

        self._not_charging_since = None
        await self._mobile_notifier.send_ev_charging_live_activity(
            mode=self._mode_label(),
        )

    async def _async_handle_not_charging(self, stop_signal: str | None = None) -> None:
        """Close the activity once the charging gap is confirmed.

        How long the confirmation takes depends on how unambiguous the evidence
        is (v2.12.1): a cable out / charge complete / manual stop hold ends the
        session on the spot, a commanded charger-off waits out the Tuya
        stop→set→start window, and a bare power dip keeps the long grace it was
        given in v2.12.0.
        """
        state = self._runtime_data.live_activity
        if not state.active:
            self._not_charging_since = None
            return

        now = dt_util.utcnow()
        if self._not_charging_since is None:
            self._not_charging_since = now

        grace = self._clear_grace_seconds(stop_signal)
        elapsed = (now - self._not_charging_since).total_seconds()
        if elapsed < grace:
            return

        self.logger.info(
            "Ending EV charging Live Activity (%s, %.0fs)",
            stop_signal or "no measured charging",
            elapsed,
        )
        await self._mobile_notifier.clear_ev_charging_live_activity()
        self._not_charging_since = None

    def _clear_grace_seconds(self, stop_signal: str | None) -> int:
        """Return the confirmation window for this class of stop evidence."""
        if stop_signal in _DEFINITIVE_STOP_SIGNALS:
            return LIVE_ACTIVITY_DEFINITIVE_STOP_GRACE_SECONDS
        if stop_signal == STOP_SIGNAL_CHARGER_OFF:
            return LIVE_ACTIVITY_STOP_GRACE_SECONDS
        return LIVE_ACTIVITY_CLEAR_GRACE_SECONDS

    def _stop_signal(self) -> str | None:
        """Classify why charging is not happening, or None when ambiguous.

        Deliberately conservative: an unmapped or unavailable entity never
        produces a signal, so a flapping sensor can only ever fall back to the
        long ambiguous grace — never close a card on a live session.
        """
        if self._is_helper_on(HELPER_STOP_CHARGING_SUFFIX):
            return STOP_SIGNAL_MANUAL_STOP

        status = self._charger_status()
        if status is not None:
            if is_disconnected_status(status):
                return STOP_SIGNAL_UNPLUGGED
            if is_charge_complete_status(status):
                return STOP_SIGNAL_COMPLETE

        if self._charger_switch_state() == STATE_OFF:
            return STOP_SIGNAL_CHARGER_OFF
        return None

    def _charger_status(self) -> str | None:
        entity_id = self.config.get(CONF_EV_CHARGER_STATUS)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        return state.state

    def _charger_switch_state(self) -> str | None:
        entity_id = self.config.get(CONF_EV_CHARGER_SWITCH)
        state = self.hass.states.get(entity_id) if entity_id else None
        return state.state if state else None

    def _is_helper_on(self, suffix: str) -> bool:
        entity_id = self._runtime_data.get_entity_id(suffix)
        state = self.hass.states.get(entity_id) if entity_id else None
        return state is not None and state.state == STATE_ON

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
        return self._is_helper_on(HELPER_FORZA_RICARICA_SUFFIX)

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
