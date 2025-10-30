"""Priority Balancer component for EV Smart Charger integration."""
from datetime import datetime
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SOC_CAR,
    CONF_SOC_HOME,
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

        # Cached state
        self._current_priority = None

    async def async_setup(self):
        """Setup: discover helper entities."""
        self.logger.info("Setting up Priority Balancer")

        # Discover enabled switch
        self._enabled_entity = entity_helper.get_helper_entity(
            self.hass, HELPER_PRIORITY_BALANCER_ENABLED_SUFFIX, "Priority Balancer"
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
            return False
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

        # Update cached value
        self._current_priority = priority

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

    def get_ev_target_for_today(self) -> int:
        """Get EV target SOC for current day."""
        today = datetime.now().strftime("%A").lower()
        entity_id = self._ev_min_soc_entities.get(today)

        if not entity_id:
            # Fallback to default
            if today in ["saturday", "sunday"]:
                return DEFAULT_EV_MIN_SOC_WEEKEND
            return DEFAULT_EV_MIN_SOC_WEEKDAY

        target = state_helper.get_int(self.hass, entity_id, DEFAULT_EV_MIN_SOC_WEEKDAY)
        return target

    def get_home_target_for_today(self) -> int:
        """Get Home battery target SOC for current day."""
        today = datetime.now().strftime("%A").lower()
        entity_id = self._home_min_soc_entities.get(today)

        if not entity_id:
            return DEFAULT_HOME_MIN_SOC

        target = state_helper.get_int(self.hass, entity_id, DEFAULT_HOME_MIN_SOC)
        return target

    async def get_ev_current_soc(self) -> float:
        """Get current EV SOC with fallback."""
        if not self._soc_car:
            self.logger.warning("EV SOC sensor not configured, assuming 0%")
            return 0.0

        soc = state_helper.get_float(self.hass, self._soc_car, 0.0)

        # Validate range
        if soc < 0 or soc > 100:
            self.logger.warning(f"EV SOC out of range ({soc}%), clamping to 0-100")
            soc = max(0, min(100, soc))

        return soc

    async def get_home_current_soc(self) -> float:
        """Get current Home battery SOC with fallback."""
        if not self._soc_home:
            self.logger.warning("Home SOC sensor not configured, assuming 100%")
            return 100.0

        soc = state_helper.get_float(self.hass, self._soc_home, 100.0)

        # Validate range
        if soc < 0 or soc > 100:
            self.logger.warning(f"Home SOC out of range ({soc}%), clamping to 0-100")
            soc = max(0, min(100, soc))

        return soc

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
