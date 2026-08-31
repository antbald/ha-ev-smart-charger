"""Mobile Notification Service for EV Smart Charger."""
from __future__ import annotations
import logging
from math import isfinite
from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    DEFAULT_NAME,
    HELPER_CACHED_EV_SOC_SUFFIX,
    HELPER_LIVE_ACTIVITIES_ENABLED_SUFFIX,
    HELPER_TODAY_EV_TARGET_SUFFIX,
    LIVE_ACTIVITY_MIN_TRANSITION_SECONDS,
    LIVE_ACTIVITY_MIN_UPDATE_SECONDS,
    LIVE_ACTIVITY_MODE_BOOST,
    LIVE_ACTIVITY_MODE_CHARGING,
    LIVE_ACTIVITY_RESTART_COOLDOWN_SECONDS,
    LIVE_ACTIVITY_SOC_STEP_PERCENT,
)
from ..localization import translate_runtime
from ..runtime import EVSCRuntimeData, LiveActivityState

_LOGGER = logging.getLogger(__name__)

# Notification title
NOTIFICATION_TITLE = DEFAULT_NAME
LIVE_ACTIVITY_TAG = "evsc_ev_charging"


class MobileNotificationService:
    """
    Centralized mobile notification service.

    Handles sending notifications to mobile devices via notify.mobile_app_* services
    with granular control through enable/disable switches.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        notify_services: list[str],
        entry_id: str,
        car_owner_entity: str = None,
        runtime_data: EVSCRuntimeData | None = None,
    ):
        """
        Initialize Mobile Notification Service.

        Args:
            hass: Home Assistant instance
            notify_services: List of notify service names (e.g., ["mobile_app_pixel_8"])
            entry_id: Config entry ID for finding enable/disable switches
            car_owner_entity: Person entity ID for car owner (v1.3.19+)
        """
        self.hass = hass
        self.notify_services = notify_services or []
        self.entry_id = entry_id
        self.car_owner_entity = car_owner_entity
        self._runtime_data = runtime_data
        # v2.12.0: the Live Activity tag is one shared resource on the phone, so
        # its lifecycle lives on the config entry. The local instance is only a
        # fallback for services built without runtime data (tests, early setup).
        self._local_live_activity_state = LiveActivityState()

    async def send_smart_blocker_notification(self, reason: str) -> None:
        """
        Send Smart Blocker notification if enabled.

        Args:
            reason: Reason for blocking (e.g., "Nighttime blocking active")
        """
        if not self._is_smart_blocker_enabled():
            _LOGGER.debug("Smart Blocker notifications disabled, skipping")
            return

        # Check if car owner is home before sending notification (v1.3.20+)
        if not self._is_car_owner_home():
            _LOGGER.debug("Car owner not home, skipping Smart Blocker notification")
            return

        message = translate_runtime(
            self.hass,
            "mobile.smart_blocker.message",
            reason=reason,
            time=dt_util.now().strftime("%H:%M"),
        )

        _LOGGER.info(f"Sending Smart Blocker notification at {dt_util.now().strftime('%H:%M:%S')}")
        await self._send_notification(
            message=message,
            tag="evsc_smart_blocker",
            priority="high"
        )

    async def send_priority_change_notification(
        self,
        new_priority: str,
        reason: str,
        ev_soc: float,
        ev_target: int,
        home_soc: float,
        home_target: int
    ) -> None:
        """
        Send Priority Balancer notification when priority changes.

        Args:
            new_priority: New priority (EV, Home, EV_Free)
            reason: Reason for change
            ev_soc: Current EV SOC percentage
            ev_target: Target EV SOC percentage
            home_soc: Current Home battery SOC percentage
            home_target: Target Home battery SOC percentage
        """
        if not self._is_priority_balancer_enabled():
            _LOGGER.debug("Priority Balancer notifications disabled, skipping")
            return

        # Check if car owner is home before sending notification (v1.3.19+)
        if not self._is_car_owner_home():
            _LOGGER.debug("Car owner not home, skipping Priority Balancer notification")
            return

        priority_label = translate_runtime(self.hass, f"priority.{new_priority}")
        if priority_label == f"priority.{new_priority}":
            priority_label = new_priority

        message = translate_runtime(
            self.hass,
            "mobile.priority_change.message",
            priority_label=priority_label,
            ev_soc=ev_soc,
            ev_target=ev_target,
            home_soc=home_soc,
            home_target=home_target,
            reason=reason,
        )

        await self._send_notification(
            message=message,
            tag="evsc_priority_balancer",
            priority="normal"
        )

    async def send_night_charge_notification(
        self,
        mode: str,
        reason: str,
        amperage: int,
        forecast: float = None
    ) -> None:
        """
        Send Night Smart Charge notification when charging starts.

        Args:
            mode: Charging mode ("battery" or "grid")
            reason: Reason for charging decision
            amperage: Charging amperage in A
            forecast: PV forecast in kWh (optional)
        """
        if not self._is_night_charge_enabled():
            _LOGGER.debug("Night Charge notifications disabled, skipping")
            return

        # Check if car owner is home before sending notification (v1.3.20+)
        if not self._is_car_owner_home():
            _LOGGER.debug("Car owner not home, skipping Night Charge notification")
            return

        mode_label = translate_runtime(self.hass, f"mode.{mode}")
        if mode_label == f"mode.{mode}":
            mode_label = mode

        template_key = (
            "mobile.night_charge.message_with_forecast"
            if forecast is not None
            else "mobile.night_charge.message_without_forecast"
        )
        message = translate_runtime(
            self.hass,
            template_key,
            mode_label=mode_label,
            forecast=forecast,
            reason=reason,
            amperage=amperage,
            time=dt_util.now().strftime("%H:%M"),
        )

        _LOGGER.info(f"Sending Night Charge notification ({mode} mode) at {dt_util.now().strftime('%H:%M:%S')}")
        await self._send_notification(
            message=message,
            tag="evsc_night_charge",
            priority="normal"
        )

    async def send_night_charge_skipped_notification(self, reason: str) -> None:
        """Send Night Smart Charge notification when a session is intentionally skipped."""
        if not self._is_night_charge_enabled():
            _LOGGER.debug("Night Charge notifications disabled, skipping skip notification")
            return

        if not self._is_car_owner_home():
            _LOGGER.debug("Car owner not home, skipping Night Charge skip notification")
            return

        message = translate_runtime(
            self.hass,
            "mobile.night_charge_skipped.message",
            reason=reason,
            time=dt_util.now().strftime("%H:%M"),
        )

        _LOGGER.info(
            "Sending Night Charge skipped notification at %s",
            dt_util.now().strftime("%H:%M:%S"),
        )
        await self._send_notification(
            message=message,
            tag="evsc_night_charge",
            priority="normal",
        )

    async def send_boost_charge_started_notification(
        self,
        amperage: int,
        start_soc: float,
        target_soc: int,
    ) -> None:
        """Send Boost Charge start notification using Night Charge toggle."""
        if not self._is_night_charge_enabled():
            _LOGGER.debug("Night Charge notifications disabled, skipping Boost start notification")
            return

        if not self._is_car_owner_home():
            _LOGGER.debug("Car owner not home, skipping Boost start notification")
            return

        message = translate_runtime(
            self.hass,
            "mobile.boost_started.message",
            start_soc=start_soc,
            target_soc=target_soc,
            amperage=amperage,
            time=dt_util.now().strftime("%H:%M"),
        )

        await self._send_notification(
            message=message,
            tag="evsc_boost_charge",
            priority="high"
        )
        await self.send_ev_charging_live_activity(
            mode=LIVE_ACTIVITY_MODE_BOOST,
            amperage=amperage,
            ev_soc=start_soc,
            target_soc=target_soc,
            force=True,
        )

    async def send_boost_charge_completed_notification(
        self,
        end_soc: float | None,
        target_soc: int | None,
        reason: str,
    ) -> None:
        """Send Boost Charge completion notification using Night Charge toggle."""
        if not self._is_night_charge_enabled():
            _LOGGER.debug("Night Charge notifications disabled, skipping Boost completion notification")
            return

        if not self._is_car_owner_home():
            _LOGGER.debug("Car owner not home, skipping Boost completion notification")
            return

        not_available_label = translate_runtime(self.hass, "common.not_available_short")
        soc_label = not_available_label if end_soc is None else f"{end_soc:.1f}%"
        target_label = not_available_label if target_soc is None else f"{target_soc}%"

        message = translate_runtime(
            self.hass,
            "mobile.boost_completed.message",
            end_soc_label=soc_label,
            target_soc_label=target_label,
            reason=reason,
        )

        await self._send_notification(
            message=message,
            tag="evsc_boost_charge",
            priority="normal"
        )
        await self.clear_ev_charging_live_activity()

    async def send_hybrid_mode_started_notification(self) -> None:
        """
        Send Hybrid Inverter Mode notification when probing starts (v1.8.0 — issue #20).

        Single-shot per day, no enable toggle (low spam risk by design). Caller is
        responsible for ensuring this is sent at most once per "session" (defined as
        the interval between sunrise and sunset). Filtered by car owner presence to
        avoid notifying users who are away from home.
        """
        if not self._is_car_owner_home():
            _LOGGER.debug("Car owner not home, skipping Hybrid Mode notification")
            return

        message = translate_runtime(
            self.hass,
            "mobile.hybrid_mode_started.message",
            time=dt_util.now().strftime("%H:%M"),
        )

        _LOGGER.info(
            "Sending Hybrid Mode probing notification at %s",
            dt_util.now().strftime("%H:%M:%S"),
        )
        await self._send_notification(
            message=message,
            tag="evsc_hybrid_mode",
            priority="normal",
        )

    @property
    def _live_activity_state(self) -> LiveActivityState:
        """Return the shared Live Activity state for this config entry."""
        if self._runtime_data is not None:
            return self._runtime_data.live_activity
        return self._local_live_activity_state

    async def send_ev_charging_live_activity(
        self,
        *,
        mode: str,
        amperage: int | None = None,
        ev_soc: float | None = None,
        target_soc: int | float | None = None,
        force: bool = False,
    ) -> None:
        """Start or update the iOS Live Activity / Android Live Update.

        v2.12.0: pushes are driven by discrete state changes only. See the
        Live Activity update policy block in const.py for the rationale — iOS
        throttles (and silently drops) frequent updates, and every *start*
        consumes a separate push-to-start budget whose exhaustion is invisible.
        """
        state = self._live_activity_state

        if not self.notify_services:
            # Nothing was dispatched, so the state must not claim an open
            # activity: the monitor would otherwise believe one exists and
            # start emitting clear pushes against it.
            return
        if not self.is_live_activity_enabled():
            return

        snapshot = self._build_live_activity_snapshot(
            mode=mode,
            amperage=amperage,
            ev_soc=ev_soc,
            target_soc=target_soc,
        )

        is_start = not state.active
        if is_start:
            # Starting an activity is the expensive, budget-consuming operation
            # and the only one the owner-presence filter should gate: once the
            # card is on the lock screen it must keep tracking the session,
            # otherwise it freezes on stale data for up to 8 hours.
            if not self._is_car_owner_home():
                return
            if not self._start_cooldown_elapsed(state):
                _LOGGER.debug(
                    "Live Activity start suppressed: within restart cooldown"
                )
                return
        elif not force and not self._should_send_live_activity_update(
            state, snapshot
        ):
            return

        extra_data = {
            "live_update": True,
            "critical_text": snapshot["critical_text"],
            "progress": snapshot["progress"],
            "progress_max": 100,
            "progress_bar_direction": "increasing",
            "notification_icon": "mdi:ev-station",
            "notification_icon_color": "#4CAF50",
            "color": "#4CAF50",
            "progress_bar_color": "#4CAF50",
            "background_color": "#101820",
            "text_color": "#FFFFFF",
            "url": "/ev-smart-charger",
            # Never re-alert for a card the user is already looking at.
            "alert_once": True,
        }
        if not is_start:
            # Companion App: silent updates are delivered at push priority 5,
            # which is the documented setting for power-friendly refreshes of
            # an activity that is already on screen.
            extra_data["silent"] = True

        await self._send_notification(
            title=translate_runtime(self.hass, "live_activity.title"),
            message=snapshot["message"],
            tag=LIVE_ACTIVITY_TAG,
            priority="normal",
            extra_data=extra_data,
        )
        state.active = True
        state.last_update = dt_util.utcnow()
        state.signature = snapshot["signature"]
        state.last_pushed_soc = snapshot["soc"]

    async def clear_ev_charging_live_activity(self, *, force: bool = False) -> None:
        """End the EV charging Live Activity / Live Update.

        No-ops when no activity is believed open, so a stop path that runs
        several times (or an idle monitor tick) cannot spam clear pushes.
        Pass force=True for defensive teardown (unload, feature disabled).
        """
        state = self._live_activity_state
        if not state.active and not force:
            return

        await self._send_notification(
            message="clear_notification",
            tag=LIVE_ACTIVITY_TAG,
            priority="normal",
        )
        state.active = False
        state.signature = None
        state.last_update = None
        state.last_pushed_soc = None
        state.ended_at = dt_util.utcnow()

    def _build_live_activity_snapshot(
        self,
        *,
        mode: str,
        amperage: int | None,
        ev_soc: float | None,
        target_soc: int | float | None,
    ) -> dict:
        """Build the compact EV charging state shown on the lock screen."""
        ev_soc = self._coerce_number(ev_soc)
        if ev_soc is None:
            ev_soc = self._read_number_from_runtime_entity(HELPER_CACHED_EV_SOC_SUFFIX)
        target_soc = self._coerce_number(target_soc)
        if target_soc is None:
            target_soc = self._read_number_from_runtime_entity(HELPER_TODAY_EV_TARGET_SUFFIX)
        amperage = self._coerce_number(amperage)
        if amperage is None:
            amperage = self._read_number_from_config_entity(CONF_EV_CHARGER_CURRENT)

        charging_power_w = None
        power_model = self._runtime_data.power_model if self._runtime_data else None
        if power_model is not None:
            try:
                charging_power_w = power_model.read_charging_power(self.hass)
            except Exception:
                charging_power_w = None

        charger_status = self._read_state_from_config_entity(CONF_EV_CHARGER_STATUS)
        progress = self._clamp_percent(ev_soc)
        mode_label = self._format_mode(mode)
        critical_text = f"{progress}%" if progress is not None else mode_label
        target_pct = self._clamp_percent(target_soc)
        target_label = (
            translate_runtime(self.hass, "live_activity.target", target=f"{target_pct}%")
            if target_pct is not None
            else translate_runtime(self.hass, "live_activity.target_unknown")
        )

        # Display-only parts: refreshed on the next scheduled push, never a
        # trigger for one (see the policy block in const.py).
        parts = [mode_label, self._format_speed(amperage, charging_power_w), target_label]
        status_label = self._format_status(charger_status)
        if status_label:
            parts.append(status_label)
        message = " · ".join(parts)

        # Trigger set, deliberately narrow: the display-only values above are
        # NOT part of it. The SOC is compared with hysteresis by the caller, so
        # it is carried raw rather than bucketed here.
        signature = (
            mode,
            None if target_pct is None else target_pct,
        )
        return {
            "message": message,
            "critical_text": critical_text,
            "progress": progress or 0,
            "soc": None if progress is None else float(progress),
            "signature": signature,
        }

    def _start_cooldown_elapsed(self, state: LiveActivityState) -> bool:
        """Return True when a new activity may be started."""
        if state.ended_at is None:
            return True
        elapsed = (dt_util.utcnow() - state.ended_at).total_seconds()
        return elapsed >= LIVE_ACTIVITY_RESTART_COOLDOWN_SECONDS

    def _should_send_live_activity_update(
        self,
        state: LiveActivityState,
        snapshot: dict,
    ) -> bool:
        """Decide whether an already-open activity is worth refreshing."""
        if state.last_update is None:
            return True
        elapsed = (dt_util.utcnow() - state.last_update).total_seconds()

        # A transition (mode switch, user retargeting) is meaningful enough to
        # push promptly, but still floored so a flapping owner cannot burst.
        if snapshot["signature"] != state.signature:
            return elapsed >= LIVE_ACTIVITY_MIN_TRANSITION_SECONDS

        soc = snapshot["soc"]
        if soc is None:
            return False
        if state.last_pushed_soc is None:
            # The activity opened while the SOC sensor was unavailable, so the
            # card shows no percentage. The first readable value is worth a
            # refresh; without this the hysteresis below could never arm.
            return elapsed >= LIVE_ACTIVITY_MIN_UPDATE_SECONDS
        if abs(soc - state.last_pushed_soc) < LIVE_ACTIVITY_SOC_STEP_PERCENT:
            return False
        return elapsed >= LIVE_ACTIVITY_MIN_UPDATE_SECONDS

    def _format_mode(self, mode: str) -> str:
        """Localize a Live Activity mode key, tolerating legacy free text."""
        label = translate_runtime(self.hass, f"live_activity.mode.{mode}")
        if label != f"live_activity.mode.{mode}":
            return label
        # Unknown key: a caller passed a literal label. Show it as-is rather
        # than dropping the only context the card has.
        return mode or translate_runtime(
            self.hass, f"live_activity.mode.{LIVE_ACTIVITY_MODE_CHARGING}"
        )

    def _read_number_from_runtime_entity(self, key: str) -> float | None:
        entity_id = self._runtime_data.get_entity_id(key) if self._runtime_data else None
        return self._read_number(entity_id)

    def _read_number_from_config_entity(self, config_key: str) -> float | None:
        entity_id = self._runtime_data.config.get(config_key) if self._runtime_data else None
        return self._read_number(entity_id)

    def _read_state_from_config_entity(self, config_key: str) -> str | None:
        entity_id = self._runtime_data.config.get(config_key) if self._runtime_data else None
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        return state.state

    def _read_number(self, entity_id: str | None) -> float | None:
        state = self.hass.states.get(entity_id) if entity_id else None
        return self._coerce_number(state.state if state else None)

    def _coerce_number(self, value) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if isfinite(number) else None

    def _clamp_percent(self, value: float | None) -> int | None:
        if value is None:
            return None
        return max(0, min(100, round(value)))

    def _format_speed(
        self,
        amperage: float | None,
        charging_power_w: float | None,
    ) -> str:
        if charging_power_w is not None and charging_power_w > 0:
            return f"{charging_power_w / 1000:.1f} kW"
        if amperage is not None:
            return f"{round(amperage)} A"
        return translate_runtime(self.hass, "live_activity.speed_unknown")

    def _format_status(self, charger_status: str | None) -> str:
        """Localized status suffix, empty while plainly charging.

        The mode label already reads "Charging"/"Boost"/..., so echoing
        "Charging" a second time only made the lock-screen line noisier.
        """
        keys = {
            "charger_wait": "live_activity.status.waiting",
            "charger_end": "live_activity.status.complete",
            "charger_free": "live_activity.status.idle",
        }
        key = keys.get(charger_status)
        return translate_runtime(self.hass, key) if key else ""

    def _is_smart_blocker_enabled(self) -> bool:
        """Check if Smart Blocker notifications are enabled."""
        return self._is_notification_enabled("evsc_notify_smart_blocker_enabled")

    def _is_priority_balancer_enabled(self) -> bool:
        """Check if Priority Balancer notifications are enabled."""
        return self._is_notification_enabled("evsc_notify_priority_balancer_enabled")

    def _is_night_charge_enabled(self) -> bool:
        """Check if Night Charge notifications are enabled."""
        return self._is_notification_enabled("evsc_notify_night_charge_enabled")

    def is_live_activity_enabled(self) -> bool:
        """Return True when EV charging Live Activities are enabled."""
        entity_id = None
        if self._runtime_data is not None:
            entity_id = self._runtime_data.get_entity_id(
                HELPER_LIVE_ACTIVITIES_ENABLED_SUFFIX
            )
        if not entity_id:
            return False

        state = self.hass.states.get(entity_id)
        if not state:
            return False

        return state.state == STATE_ON

    def _is_notification_enabled(self, suffix: str) -> bool:
        """
        Check if notification type is enabled via switch.

        Args:
            suffix: Entity suffix (e.g., "evsc_notify_smart_blocker_enabled")

        Returns:
            True if enabled, False otherwise
        """
        entity_id = None
        if self._runtime_data is not None:
            entity_id = self._runtime_data.get_entity_id(suffix)
        if not entity_id:
            _LOGGER.warning(f"Notification switch {suffix} not found, defaulting to enabled")
            return True  # Default to enabled if switch not found

        state = self.hass.states.get(entity_id)
        if not state:
            return True  # Default to enabled if state unavailable

        return state.state == STATE_ON

    def _is_car_owner_home(self) -> bool:
        """
        Check if car owner is home (v1.3.19+).

        Returns:
            True if car owner is home or entity not configured, False otherwise
        """
        if not self.car_owner_entity:
            _LOGGER.debug("Car owner entity not configured, defaulting to enabled")
            return True  # Default to enabled if not configured (backward compatibility)

        state = self.hass.states.get(self.car_owner_entity)
        if not state:
            _LOGGER.warning(
                f"Car owner entity {self.car_owner_entity} not found, defaulting to enabled"
            )
            return True  # Default to enabled if state unavailable

        is_home = state.state == "home"
        _LOGGER.debug(
            f"Car owner ({self.car_owner_entity}) state: {state.state}, is_home: {is_home}"
        )
        return is_home

    async def _send_notification(
        self,
        message: str,
        tag: str,
        priority: str = "normal",
        title: str = NOTIFICATION_TITLE,
        extra_data: dict | None = None,
    ) -> None:
        """
        Send notification to all configured mobile services.

        Args:
            message: Notification message
            tag: Notification tag for grouping/replacing
            priority: Notification priority (normal, high)
        """
        if not self.notify_services:
            _LOGGER.debug("No mobile notify services configured, skipping notification")
            return

        for service_name in self.notify_services:
            try:
                data = {
                    "tag": tag,
                    "priority": priority,
                    "notification_icon": "mdi:ev-station"
                }
                if extra_data:
                    data.update(extra_data)
                await self.hass.services.async_call(
                    "notify",
                    service_name,
                    {
                        "title": title,
                        "message": message,
                        "data": data,
                    },
                    blocking=False
                )
                _LOGGER.debug(f"Sent notification to {service_name}: {tag}")
            except Exception as e:
                _LOGGER.error(
                    f"Failed to send notification to {service_name}: {e}"
                )
