from __future__ import annotations
from datetime import datetime
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    CONF_NOTIFY_SERVICES,
    CONF_CAR_OWNER,
    DEFAULT_EV_MIN_SOC_WEEKDAY,
    DEFAULT_EV_MIN_SOC_WEEKEND,
    DEFAULT_HOME_MIN_SOC,
    HELPER_PRIORITY_BALANCER_ENABLED_SUFFIX,
    HELPER_TODAY_EV_TARGET_SUFFIX,
    HELPER_TODAY_HOME_TARGET_SUFFIX,
    HELPER_CACHED_EV_SOC_SUFFIX,
    PRIORITY_EV,
    PRIORITY_HOME,
    PRIORITY_EV_FREE,
)
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger
from .utils import state_helper
from .utils.mobile_notification_service import MobileNotificationService


class PriorityBalancer:
    """
    Independent Priority Balancer component.

    Manages EV vs Home battery charging prioritization based on daily SOC targets.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        runtime_data: EVSCRuntimeData | None = None,
    ):
        """Initialize Priority Balancer."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self._runtime_data = runtime_data
        self.logger = EVSCLogger("PRIORITY BALANCER")

        # User-mapped entities
        self._soc_car_source = config.get(CONF_SOC_CAR)  # Cloud sensor (original)
        self._soc_car = None  # Cached sensor (discovered in async_setup) - v1.4.0
        self._soc_home = config.get(CONF_SOC_HOME)

        # Helper entities (discovered in async_setup)
        self._enabled_entity = None
        self._ev_min_soc_entities = {}
        self._home_min_soc_entities = {}
        self._today_ev_target_sensor = None  # v1.3.26
        self._today_home_target_sensor = None  # v1.3.26
        self._priority_sensor_entity_obj = None
        self._today_ev_target_sensor_obj = None
        self._today_home_target_sensor_obj = None

        # Mobile notification service
        self._mobile_notifier = MobileNotificationService(
            hass,
            config.get(CONF_NOTIFY_SERVICES, []),
            entry_id,
            config.get(CONF_CAR_OWNER),
            runtime_data=runtime_data,
        )

        # Cached state
        self._current_priority = None
        self._last_priority = None  # Track last priority for change detection

    async def async_setup(self):
        """Setup: discover helper entities."""
        self.logger.info("Setting up Priority Balancer")

        def resolve_entity(key: str) -> str | None:
            if self._runtime_data is None:
                return None
            return self._runtime_data.get_entity_id(key)

        # Discover enabled switch (optional for backward compatibility)
        self._enabled_entity = resolve_entity(HELPER_PRIORITY_BALANCER_ENABLED_SUFFIX)

        if not self._enabled_entity:
            self.logger.warning(
                f"Helper entity {HELPER_PRIORITY_BALANCER_ENABLED_SUFFIX} not found - "
                f"Priority Balancer will be enabled by default. "
                f"Restart Home Assistant to create missing helper entities."
            )

        # Discover daily SOC target entities
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

        for day in days:
            # EV targets
            ev_suffix = f"evsc_ev_min_soc_{day}"
            self._ev_min_soc_entities[day] = resolve_entity(ev_suffix)

            # Home targets
            home_suffix = f"evsc_home_min_soc_{day}"
            self._home_min_soc_entities[day] = resolve_entity(home_suffix)

        # Discover cached EV SOC sensor (v1.4.0)
        self._soc_car = resolve_entity(HELPER_CACHED_EV_SOC_SUFFIX)

        if not self._soc_car:
            self.logger.error("Cached EV SOC sensor not found in runtime data")
        else:
            self.logger.info(
                f"✅ Using cached EV SOC sensor: {self._soc_car} "
                f"(source: {self._soc_car_source})"
            )

        # Discover today's target sensors (v1.3.26)
        self._today_ev_target_sensor = resolve_entity(HELPER_TODAY_EV_TARGET_SUFFIX)
        self._today_home_target_sensor = resolve_entity(HELPER_TODAY_HOME_TARGET_SUFFIX)
        if self._runtime_data is not None:
            self._priority_sensor_entity_obj = self._runtime_data.get_entity("evsc_priority_daily_state")
            self._today_ev_target_sensor_obj = self._runtime_data.get_entity(HELPER_TODAY_EV_TARGET_SUFFIX)
            self._today_home_target_sensor_obj = self._runtime_data.get_entity(HELPER_TODAY_HOME_TARGET_SUFFIX)

        if self._today_ev_target_sensor:
            self.logger.info(f"Discovered Today EV Target sensor: {self._today_ev_target_sensor}")
        if self._today_home_target_sensor:
            self.logger.info(f"Discovered Today Home Target sensor: {self._today_home_target_sensor}")

        self.logger.success("Priority Balancer setup complete")

    def is_enabled(self) -> bool:
        """Check if Priority Balancer is enabled."""
        if not self._enabled_entity:
            # Default to enabled for backward compatibility
            return True
        return state_helper.get_bool(self.hass, self._enabled_entity)

    async def calculate_priority(self) -> str:
        """
        Calculate priority based on current SOCs vs daily targets.

        Returns:
            PRIORITY_EV: EV below target
            PRIORITY_HOME: EV at/above target, Home below target
            PRIORITY_EV_FREE: Both at/above targets
        """
        self.logger.separator()
        self.logger.start("Priority calculation")
        self.logger.separator()

        # Get today
        today = dt_util.now().strftime("%A").lower()
        self.logger.sensor_value(f"{self.logger.CALENDAR} Today", today.capitalize())

        # Get current SOCs
        ev_soc = await self.get_ev_current_soc()
        home_soc = await self.get_home_current_soc()

        self.logger.sensor_value(f"{self.logger.EV} Current EV SOC", ev_soc, "%")
        self.logger.sensor_value(f"{self.logger.HOME} Current Home SOC", home_soc, "%")

        # Get targets
        ev_target = self.get_ev_target_for_today()
        home_target = self.get_home_target_for_today()

        self.logger.sensor_value(f"{self.logger.EV} Target EV SOC", ev_target, "%")
        self.logger.sensor_value(f"{self.logger.HOME} Target Home SOC", home_target, "%")

        # Decision logic
        if ev_soc < ev_target:
            priority = PRIORITY_EV
            reason = f"EV below target ({ev_soc}% < {ev_target}%)"
        elif home_soc < home_target:
            priority = PRIORITY_HOME
            reason = f"EV at/above target ({ev_soc}% >= {ev_target}%), Home below target ({home_soc}% < {home_target}%)"
        else:
            priority = PRIORITY_EV_FREE
            reason = f"Both targets met: EV {ev_soc}% >= {ev_target}%, Home {home_soc}% >= {home_target}%"

        self.logger.separator()
        self.logger.decision("Priority", priority, reason)
        self.logger.separator()
        await self._emit_diagnostic(
            event="priority_calculated",
            result=priority,
            reason_code="priority_decision",
            reason_detail=reason,
            raw_values={
                "ev_soc": round(ev_soc, 1),
                "ev_target": ev_target,
                "home_soc": round(home_soc, 1),
                "home_target": home_target,
                "today": today,
            },
        )

        # Check if priority changed and send notification
        if self._last_priority is not None and self._last_priority != priority:
            self.logger.info(f"Priority changed: {self._last_priority} → {priority}")
            await self._mobile_notifier.send_priority_change_notification(
                new_priority=priority,
                reason=reason,
                ev_soc=ev_soc,
                ev_target=ev_target,
                home_soc=home_soc,
                home_target=home_target
            )

        # Update cached value
        self._current_priority = priority
        self._last_priority = priority

        # Update sensor
        await self._update_priority_sensor(
            priority, reason, ev_soc, ev_target, home_soc, home_target, today
        )

        return priority

    def get_current_priority(self) -> str | None:
        """Get cached priority (use calculate_priority for fresh calculation)."""
        return self._current_priority

    async def is_ev_target_reached(self) -> bool:
        """Check if EV has reached today's target."""
        ev_soc = await self.get_ev_current_soc()
        ev_target = self.get_ev_target_for_today()
        reached = ev_soc >= ev_target

        self.logger.info(
            f"{self.logger.EV} EV target check: {ev_soc}% >= {ev_target}% = {reached}"
        )

        return reached

    async def is_home_target_reached(self) -> bool:
        """Check if Home battery has reached today's target."""
        home_soc = await self.get_home_current_soc()
        home_target = self.get_home_target_for_today()
        reached = home_soc >= home_target

        self.logger.info(
            f"{self.logger.HOME} Home target check: {home_soc}% >= {home_target}% = {reached}"
        )

        return reached

    def _get_target_for_today(
        self,
        entities_dict: dict[str, str],
        default_weekday: int,
        default_weekend: int = None
    ) -> int:
        """
        Generic method to get target SOC for current day.

        Args:
            entities_dict: Dictionary mapping day names to entity IDs
            default_weekday: Default value for weekdays
            default_weekend: Default value for weekends (if None, uses default_weekday)

        Returns:
            Target SOC for today
        """
        today = dt_util.now().strftime("%A").lower()
        entity_id = entities_dict.get(today)

        # Entity not configured - use weekend/weekday default
        if not entity_id:
            default_value = default_weekend if (default_weekend and today in ["saturday", "sunday"]) else default_weekday
            return default_value

        # v1.3.22: Get state directly to check availability
        state = state_helper.get_state(self.hass, entity_id)

        # State not yet restored/available
        if state in [None, "unknown", "unavailable"]:
            default_value = default_weekend if (default_weekend and today in ["saturday", "sunday"]) else default_weekday
            self.logger.warning(
                f"⚠️ Entity {entity_id} state is {state}, using temporary default {default_value}%"
            )
            self.logger.warning(
                f"   If this persists, check entity state in Developer Tools → States"
            )
            return default_value

        # Parse valid state
        try:
            target = int(float(state))
            return target
        except (ValueError, TypeError) as e:
            default_value = default_weekend if (default_weekend and today in ["saturday", "sunday"]) else default_weekday
            self.logger.error(f"❌ Invalid state for {entity_id}: {state} - {e}")
            return default_value

    def get_ev_target_for_today(self) -> int:
        """Get EV target SOC for current day."""
        return self._get_target_for_today(
            self._ev_min_soc_entities,
            DEFAULT_EV_MIN_SOC_WEEKDAY,
            DEFAULT_EV_MIN_SOC_WEEKEND
        )

    def get_home_target_for_today(self) -> int:
        """Get Home battery target SOC for current day."""
        return self._get_target_for_today(
            self._home_min_soc_entities,
            DEFAULT_HOME_MIN_SOC
        )

    def _get_soc_with_validation(
        self,
        sensor_entity: str | None,
        sensor_name: str,
        default_value: float
    ) -> float:
        """
        Generic method to get SOC with validation and range clamping.

        Args:
            sensor_entity: Entity ID of the SOC sensor
            sensor_name: Name for logging (e.g., "EV", "Home")
            default_value: Default value if sensor not configured

        Returns:
            SOC value (0-100)
        """
        if not sensor_entity:
            self.logger.warning(
                f"{sensor_name} SOC sensor not configured, assuming {default_value}%"
            )
            return default_value

        soc = state_helper.get_float(self.hass, sensor_entity, default_value)

        # Validate range
        if soc < 0 or soc > 100:
            self.logger.warning(
                f"{sensor_name} SOC out of range ({soc}%), clamping to 0-100"
            )
            soc = max(0, min(100, soc))

        return soc

    async def get_ev_current_soc(self) -> float:
        """Get current EV SOC with fallback."""
        return self._get_soc_with_validation(self._soc_car, "EV", 0.0)

    async def get_home_current_soc(self) -> float:
        """Get current Home battery SOC with fallback."""
        return self._get_soc_with_validation(self._soc_home, "Home", 100.0)

    async def _update_priority_sensor(
        self,
        priority: str,
        reason: str,
        ev_soc: float,
        ev_target: int,
        home_soc: float,
        home_target: int,
        today: str,
    ):
        """Update priority state sensor and today's target sensors (v1.3.26)."""
        sensor_entity = None
        if self._runtime_data is not None:
            sensor_entity = self._runtime_data.get_entity_id("evsc_priority_daily_state")
            self._priority_sensor_entity_obj = self._runtime_data.get_entity(
                "evsc_priority_daily_state"
            )

        if not sensor_entity:
            self.logger.warning("Priority state sensor not found")
            return

        try:
            priority_attributes = {
                "balancer_enabled": self.is_enabled(),
                "today": today.capitalize(),
                "current_ev_soc": round(ev_soc, 1),
                "target_ev_soc": ev_target,
                "current_home_soc": round(home_soc, 1),
                "target_home_soc": home_target,
                "reason": reason,
                "last_update": dt_util.now().isoformat(),
            }

            # Update priority state sensor
            if self._priority_sensor_entity_obj and hasattr(
                self._priority_sensor_entity_obj, "async_publish"
            ):
                await self._priority_sensor_entity_obj.async_publish(
                    priority,
                    priority_attributes,
                )
            else:
                self.logger.warning("Priority state sensor object not registered in runtime data")

            # Update today's EV target sensor (v1.3.26)
            if self._today_ev_target_sensor:
                ev_attributes = {
                    "day": today.capitalize(),
                    "unit_of_measurement": "%",
                }
                if self._today_ev_target_sensor_obj and hasattr(
                    self._today_ev_target_sensor_obj, "async_publish"
                ):
                    await self._today_ev_target_sensor_obj.async_publish(
                        ev_target,
                        ev_attributes,
                    )
                else:
                    self.logger.warning("Today EV target sensor object not registered in runtime data")

            # Update today's Home target sensor (v1.3.26)
            if self._today_home_target_sensor:
                home_attributes = {
                    "day": today.capitalize(),
                    "unit_of_measurement": "%",
                }
                if self._today_home_target_sensor_obj and hasattr(
                    self._today_home_target_sensor_obj, "async_publish"
                ):
                    await self._today_home_target_sensor_obj.async_publish(
                        home_target,
                        home_attributes,
                    )
                else:
                    self.logger.warning("Today Home target sensor object not registered in runtime data")

        except Exception as e:
            self.logger.error(f"Failed to update priority sensor: {e}")

    async def _emit_diagnostic(
        self,
        *,
        event: str,
        result: str,
        reason_code: str,
        reason_detail: str,
        raw_values: dict | None = None,
    ) -> None:
        """Publish structured balancer diagnostics when available."""
        if self._runtime_data is None or self._runtime_data.diagnostic_manager is None:
            return

        await self._runtime_data.diagnostic_manager.async_emit_event(
            component="Priority Balancer",
            event=event,
            result=result,
            reason_code=reason_code,
            reason_detail=reason_detail,
            raw_values=raw_values,
        )

    async def async_remove(self):
        """Cleanup."""
        self.logger.info("Priority Balancer removed")
