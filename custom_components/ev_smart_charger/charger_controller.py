"""Centralized Charger Controller for EV Smart Charger."""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CHARGER_AMP_LEVELS,
    CHARGER_COMMAND_DELAY,
    CHARGER_START_SEQUENCE_DELAY,
    CHARGER_STOP_SEQUENCE_DELAY,
    CHARGER_AMPERAGE_STABILIZATION_DELAY,
    CHARGER_MIN_OPERATION_INTERVAL,
    CHARGER_QUEUE_MAX_SIZE,
    SERVICE_CALL_TIMEOUT,
)
from .utils.logging_helper import EVSCLogger
from .utils import state_helper


class ChargerOperation:
    """Represents a charger operation to be executed."""

    def __init__(self, operation_type: str, value: Optional[int] = None, reason: str = ""):
        """Initialize operation."""
        self.operation_type = operation_type  # "start", "stop", "set_amperage"
        self.value = value
        self.reason = reason
        self.timestamp = datetime.now()


class ChargerController:
    """
    Centralized controller for all charger operations.

    Manages:
    - Charger on/off
    - Amperage changes (increase/decrease)
    - Rate limiting (30 seconds between operations)
    - Operation queue for multiple requests
    - Safe decrease sequence (stop → wait → set → wait → start)
    """

    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict):
        """Initialize ChargerController."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.logger = EVSCLogger("CHARGER CONTROLLER")

        # Entity IDs from config
        self._charger_switch = config.get(CONF_EV_CHARGER_SWITCH)
        self._charger_current = config.get(CONF_EV_CHARGER_CURRENT)

        # Internal state
        self._last_operation_time: Optional[datetime] = None
        self._operation_queue: asyncio.Queue = asyncio.Queue(maxsize=CHARGER_QUEUE_MAX_SIZE)
        self._current_amperage: Optional[int] = None
        self._is_on: Optional[bool] = None
        self._lock = asyncio.Lock()
        self._processing_queue = False

        self.logger.info(
            f"Initialized ChargerController - Switch: {self._charger_switch}, "
            f"Current: {self._charger_current}"
        )

    async def async_setup(self):
        """Setup controller and read initial state."""
        self.logger.info("Setting up ChargerController")

        # Read initial state
        await self._refresh_state()

        self.logger.success(
            f"Setup complete - Initial state: "
            f"On={self._is_on}, Amperage={self._current_amperage}A"
        )

    async def _refresh_state(self):
        """Refresh cached state from Home Assistant."""
        # Read charger on/off state
        charger_state = self.hass.states.get(self._charger_switch)
        if charger_state:
            self._is_on = charger_state.state == "on"

        # Read current amperage
        self._current_amperage = state_helper.get_int(
            self.hass, self._charger_current, default=None
        )

    async def start_charger(self, target_amps: Optional[int] = None, reason: str = ""):
        """
        Start the charger with optional target amperage.

        Args:
            target_amps: Optional amperage to set (if None, uses current)
            reason: Reason for starting (for logging)
        """
        async with self._lock:
            self.logger.separator()
            self.logger.start(f"{self.logger.CHARGER} Start Charger")
            self.logger.info(f"Reason: {reason or 'No reason provided'}")

            if target_amps:
                self.logger.info(f"Target amperage: {target_amps}A")

            # Check rate limiting
            if not await self._can_execute_operation():
                self.logger.action(
                    "Operation queued",
                    f"Rate limit active, adding to queue (size: {self._operation_queue.qsize()})"
                )
                await self._operation_queue.put(
                    ChargerOperation("start", target_amps, reason)
                )
                asyncio.create_task(self._process_queue())
                return

            try:
                # Set amperage first if specified
                if target_amps and target_amps != self._current_amperage:
                    await self._set_amperage_internal(target_amps)
                    await asyncio.sleep(CHARGER_AMPERAGE_STABILIZATION_DELAY)

                # Turn on charger
                self.logger.action("Starting charger", "Calling switch.turn_on")
                await self._call_service("switch", "turn_on", {"entity_id": self._charger_switch})

                # Wait for stabilization
                await asyncio.sleep(CHARGER_START_SEQUENCE_DELAY)

                # Update state
                self._is_on = True
                self._last_operation_time = datetime.now()

                await self._refresh_state()

                self.logger.success(
                    f"{self.logger.CHARGER} Charger started successfully at {self._current_amperage}A"
                )
                self.logger.separator()

            except Exception as ex:
                self.logger.error(f"Failed to start charger: {ex}")
                self.logger.separator()
                raise

    async def stop_charger(self, reason: str = ""):
        """
        Stop the charger.

        Args:
            reason: Reason for stopping (for logging)
        """
        async with self._lock:
            self.logger.separator()
            self.logger.start(f"{self.logger.CHARGER} Stop Charger")
            self.logger.info(f"Reason: {reason or 'No reason provided'}")

            # Check rate limiting
            if not await self._can_execute_operation():
                self.logger.action(
                    "Operation queued",
                    f"Rate limit active, adding to queue (size: {self._operation_queue.qsize()})"
                )
                await self._operation_queue.put(ChargerOperation("stop", None, reason))
                asyncio.create_task(self._process_queue())
                return

            try:
                # Turn off charger
                self.logger.action("Stopping charger", "Calling switch.turn_off")
                await self._call_service("switch", "turn_off", {"entity_id": self._charger_switch})

                # Wait for charger to stop
                await asyncio.sleep(CHARGER_COMMAND_DELAY)

                # Update state
                self._is_on = False
                self._last_operation_time = datetime.now()

                await self._refresh_state()

                self.logger.success(f"{self.logger.CHARGER} Charger stopped successfully")
                self.logger.separator()

            except Exception as ex:
                self.logger.error(f"Failed to stop charger: {ex}")
                self.logger.separator()
                raise

    async def set_amperage(self, target_amps: int, reason: str = ""):
        """
        Set charger amperage with automatic increase/decrease logic.

        Args:
            target_amps: Target amperage (must be in CHARGER_AMP_LEVELS)
            reason: Reason for change (for logging)
        """
        async with self._lock:
            self.logger.separator()
            self.logger.start(f"{self.logger.CHARGER} Set Amperage")
            self.logger.info(f"Target: {target_amps}A (Current: {self._current_amperage}A)")
            self.logger.info(f"Reason: {reason or 'No reason provided'}")

            # Validate target amperage
            if target_amps not in CHARGER_AMP_LEVELS:
                closest_amp = min(CHARGER_AMP_LEVELS, key=lambda x: abs(x - target_amps))
                self.logger.action(
                    "Adjusting target",
                    f"{target_amps}A not in valid levels, using closest: {closest_amp}A"
                )
                target_amps = closest_amp

            # Check if already at target
            await self._refresh_state()
            if self._current_amperage == target_amps:
                self.logger.info(f"Already at target amperage ({target_amps}A), skipping")
                self.logger.separator()
                return

            # Check rate limiting
            if not await self._can_execute_operation():
                self.logger.action(
                    "Operation queued",
                    f"Rate limit active, adding to queue (size: {self._operation_queue.qsize()})"
                )
                await self._operation_queue.put(
                    ChargerOperation("set_amperage", target_amps, reason)
                )
                asyncio.create_task(self._process_queue())
                return

            try:
                # Determine if increase or decrease
                if target_amps > self._current_amperage:
                    await self._increase_amperage(target_amps)
                else:
                    await self._decrease_amperage(target_amps)

                self._last_operation_time = datetime.now()
                self.logger.separator()

            except Exception as ex:
                self.logger.error(f"Failed to set amperage: {ex}")
                self.logger.separator()
                raise

    async def _increase_amperage(self, target_amps: int):
        """
        Increase amperage (no need to stop charger).

        Args:
            target_amps: Target amperage
        """
        self.logger.action(
            f"{self.logger.EV} Increasing amperage",
            f"{self._current_amperage}A → {target_amps}A (immediate)"
        )

        await self._set_amperage_internal(target_amps)
        self._current_amperage = target_amps

        self.logger.success(f"{self.logger.CHARGER} Amperage increased to {target_amps}A")

    async def _decrease_amperage(self, target_amps: int):
        """
        Decrease amperage using safe sequence.

        Safe sequence:
        1. Stop charger
        2. Wait 5 seconds
        3. Set new amperage
        4. Wait 1 second
        5. Start charger

        Args:
            target_amps: Target amperage
        """
        self.logger.action(
            f"{self.logger.EV} Decreasing amperage (safe sequence)",
            f"{self._current_amperage}A → {target_amps}A"
        )

        # Step 1: Stop charger
        self.logger.info("Step 1/5: Stopping charger")
        await self._call_service("switch", "turn_off", {"entity_id": self._charger_switch})
        self._is_on = False

        # Step 2: Wait for charger to stop
        self.logger.info(f"Step 2/5: Waiting {CHARGER_STOP_SEQUENCE_DELAY} seconds")
        await asyncio.sleep(CHARGER_STOP_SEQUENCE_DELAY)

        # Step 3: Set new amperage
        self.logger.info(f"Step 3/5: Setting amperage to {target_amps}A")
        await self._set_amperage_internal(target_amps)
        self._current_amperage = target_amps

        # Step 4: Wait for stabilization
        self.logger.info(f"Step 4/5: Waiting {CHARGER_AMPERAGE_STABILIZATION_DELAY} second")
        await asyncio.sleep(CHARGER_AMPERAGE_STABILIZATION_DELAY)

        # Step 5: Restart charger
        self.logger.info("Step 5/5: Restarting charger")
        await self._call_service("switch", "turn_on", {"entity_id": self._charger_switch})
        self._is_on = True

        await asyncio.sleep(CHARGER_START_SEQUENCE_DELAY)

        self.logger.success(
            f"{self.logger.CHARGER} Amperage decreased safely to {target_amps}A and charger restarted"
        )

    async def _set_amperage_internal(self, amps: int):
        """
        Internal method to set amperage value.

        Args:
            amps: Amperage value
        """
        await self._call_service(
            "number",
            "set_value",
            {"entity_id": self._charger_current, "value": amps}
        )

    async def _can_execute_operation(self) -> bool:
        """
        Check if operation can be executed based on rate limiting.

        Returns:
            True if operation can execute now, False if should be queued
        """
        if self._last_operation_time is None:
            return True

        time_since_last = (datetime.now() - self._last_operation_time).total_seconds()

        if time_since_last < CHARGER_MIN_OPERATION_INTERVAL:
            remaining = CHARGER_MIN_OPERATION_INTERVAL - time_since_last
            self.logger.action(
                f"{self.logger.ALERT} Rate limit active",
                f"Last operation {time_since_last:.1f}s ago, need {remaining:.1f}s more"
            )
            return False

        return True

    async def _process_queue(self):
        """Process queued operations when rate limit allows."""
        if self._processing_queue:
            return

        self._processing_queue = True

        try:
            while not self._operation_queue.empty():
                # Wait for rate limit
                if self._last_operation_time:
                    time_since_last = (datetime.now() - self._last_operation_time).total_seconds()
                    if time_since_last < CHARGER_MIN_OPERATION_INTERVAL:
                        wait_time = CHARGER_MIN_OPERATION_INTERVAL - time_since_last
                        self.logger.info(f"Queue processor waiting {wait_time:.1f}s before next operation")
                        await asyncio.sleep(wait_time)

                # Get next operation
                operation = await self._operation_queue.get()

                self.logger.info(
                    f"Processing queued operation: {operation.operation_type} "
                    f"(queued {(datetime.now() - operation.timestamp).total_seconds():.1f}s ago)"
                )

                # Execute operation (without locking again to avoid deadlock)
                if operation.operation_type == "start":
                    await self.start_charger(operation.value, operation.reason)
                elif operation.operation_type == "stop":
                    await self.stop_charger(operation.reason)
                elif operation.operation_type == "set_amperage":
                    await self.set_amperage(operation.value, operation.reason)

        finally:
            self._processing_queue = False

    async def _call_service(self, domain: str, service: str, data: dict):
        """
        Call Home Assistant service with timeout and error handling.

        Args:
            domain: Service domain
            service: Service name
            data: Service data
        """
        try:
            async with async_timeout.timeout(SERVICE_CALL_TIMEOUT):
                await self.hass.services.async_call(
                    domain, service, data, blocking=True
                )
        except asyncio.TimeoutError:
            self.logger.error(f"Service call timeout: {domain}.{service}")
            raise
        except Exception as ex:
            self.logger.error(f"Service call failed: {domain}.{service} - {ex}")
            raise

    async def is_charging(self) -> bool:
        """
        Check if charger is currently on.

        Returns:
            True if charging, False otherwise
        """
        await self._refresh_state()
        return self._is_on or False

    async def get_current_amperage(self) -> Optional[int]:
        """
        Get current amperage setting.

        Returns:
            Current amperage or None if unavailable
        """
        await self._refresh_state()
        return self._current_amperage

    def get_queue_size(self) -> int:
        """
        Get current queue size.

        Returns:
            Number of operations in queue
        """
        return self._operation_queue.qsize()

    def get_last_operation_time(self) -> Optional[datetime]:
        """
        Get timestamp of last operation.

        Returns:
            Datetime of last operation or None
        """
        return self._last_operation_time

    def get_seconds_since_last_operation(self) -> Optional[float]:
        """
        Get seconds since last operation.

        Returns:
            Seconds since last operation or None
        """
        if self._last_operation_time is None:
            return None
        return (datetime.now() - self._last_operation_time).total_seconds()
