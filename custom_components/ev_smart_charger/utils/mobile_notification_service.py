"""Mobile Notification Service for EV Smart Charger."""
from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON
from homeassistant.util import dt as dt_util

from ..const import DEFAULT_NAME
from ..localization import translate_runtime
from ..runtime import EVSCRuntimeData

_LOGGER = logging.getLogger(__name__)

# Notification title
NOTIFICATION_TITLE = DEFAULT_NAME


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

    def _is_smart_blocker_enabled(self) -> bool:
        """Check if Smart Blocker notifications are enabled."""
        return self._is_notification_enabled("evsc_notify_smart_blocker_enabled")

    def _is_priority_balancer_enabled(self) -> bool:
        """Check if Priority Balancer notifications are enabled."""
        return self._is_notification_enabled("evsc_notify_priority_balancer_enabled")

    def _is_night_charge_enabled(self) -> bool:
        """Check if Night Charge notifications are enabled."""
        return self._is_notification_enabled("evsc_notify_night_charge_enabled")

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
        priority: str = "normal"
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
                await self.hass.services.async_call(
                    "notify",
                    service_name,
                    {
                        "title": NOTIFICATION_TITLE,
                        "message": message,
                        "data": {
                            "tag": tag,
                            "priority": priority,
                            "notification_icon": "mdi:ev-station"
                        }
                    },
                    blocking=False
                )
                _LOGGER.debug(f"Sent notification to {service_name}: {tag}")
            except Exception as e:
                _LOGGER.error(
                    f"Failed to send notification to {service_name}: {e}"
                )
