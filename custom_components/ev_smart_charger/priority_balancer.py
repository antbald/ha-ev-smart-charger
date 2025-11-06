"""Priority Balancer component for EV Smart Charger integration."""
from datetime import datetime
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    CONF_NOTIFY_SERVICES,
    CONF_CAR_OWNER,
    DEFAULT_EV_MIN_SOC_WEEKDAY,
    DEFAULT_EV_MIN_SOC_WEEKEND,
    DEFAULT_HOME_MIN_SOC,
    HELPER_PRIORITY_BALANCER_ENABLED_SUFFIX,
    PRIORITY_EV,
    PRIORITY_HOME,
    PRIORITY_EV_FREE,
)
from .utils.logging_helper import EVSCLogger
from .utils import entity_helper, state_helper
from .utils.mobile_notification_service import MobileNotificationService


class PriorityBalancer:
    """
    Independent Priority Balancer component.

    Manages EV vs Home battery charging prioritization based on daily SOC targets.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict):
        """Initialize Priority Balancer."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.logger = EVSCLogger("PRIORITY BALANCER")

        # User-mapped entities
        self._soc_car = config.get(CONF_SOC_CAR)
        self._soc_home = config.get(CONF_SOC_HOME)

        # Helper entities (discovered in async_setup)
        self._enabled_entity = None
        self._ev_min_soc_entities = {}
        self._home_min_soc_entities = {}

        # Mobile notification service
        self._mobile_notifier = MobileNotificationService(
            hass, config.get(CONF_NOTIFY_SERVICES, []), entry_id, config.get(CONF_CAR_OWNER)
        )

        # Cached state
        self._current_priority = None
        self._last_priority = None  # Track last priority for change detection

    async def async_setup(self):
        """Setup: discover helper entities."""
        self.logger.info("Setting up Priority Balancer")

        # Discover enabled switch (optional for backward compatibility)
        self._enabled_entity = entity_helper.find_by_suffix(
            self.hass, HELPER_PRIORITY_BALANCER_ENABLED_SUFFIX
        )

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
            self._ev_min_soc_entities[day] = entity_helper.find_by_suffix(
                self.hass, ev_suffix
            )

            # Home targets
            home_suffix = f"evsc_home_min_soc_{day}"
            self._home_min_soc_entities[day] = entity_helper.find_by_suffix(
                self.hass, home_suffix
            )

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
        today = datetime.now().strftime("%A").lower()
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
        today = datetime.now().strftime("%A").lower()
        entity_id = entities_dict.get(today)

        if not entity_id:
            # Fallback to default
            if default_weekend and today in ["saturday", "sunday"]:
                return default_weekend
            return default_weekday

        target = state_helper.get_int(self.hass, entity_id, default_weekday)
        return target

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
        """Update priority state sensor."""
        sensor_entity = entity_helper.find_by_suffix(
            self.hass, "evsc_priority_daily_state"
        )

        if not sensor_entity:
            self.logger.warning("Priority state sensor not found")
            return

        try:
            # Update sensor state and attributes
            self.hass.states.async_set(
                sensor_entity,
                priority,
                {
                    "balancer_enabled": self.is_enabled(),
                    "today": today.capitalize(),
                    "current_ev_soc": round(ev_soc, 1),
                    "target_ev_soc": ev_target,
                    "current_home_soc": round(home_soc, 1),
                    "target_home_soc": home_target,
                    "reason": reason,
                    "last_update": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            self.logger.error(f"Failed to update priority sensor: {e}")

    async def async_remove(self):
        """Cleanup."""
        self.logger.info("Priority Balancer removed")
