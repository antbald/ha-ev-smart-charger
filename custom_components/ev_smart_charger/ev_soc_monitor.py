"""EV SOC Monitor component for EV Smart Charger integration (v1.4.0).

Monitors cloud-based EV SOC sensor and maintains reliable cached value.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SOC_CAR,
    EV_SOC_MONITOR_INTERVAL,
    HELPER_CACHED_EV_SOC_SUFFIX,
)
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger


class EVSOCMonitor:
    """
    EV SOC Monitor - Reliability layer for cloud-based EV SOC sensors.

    Polls cloud sensor every 5 seconds and updates cached sensor only when
    cloud sensor has valid values. Maintains last known good value when
    cloud sensor is unavailable.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        runtime_data: EVSCRuntimeData | None = None,
    ):
        """Initialize EV SOC Monitor."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self._runtime_data = runtime_data
        self.logger = EVSCLogger("EV SOC MONITOR")

        # Source sensor (cloud-based, user-configured)
        self._source_entity = config.get(CONF_SOC_CAR)

        # Cache sensor (internal, reliable)
        self._cache_entity = None  # Discovered in async_setup
        self._cache_sensor = None

        # State tracking
        self._last_valid_value = None
        self._last_valid_time = None
        self._last_source_state = None  # For change detection
        self._timer_unsub = None

    async def async_setup(self):
        """Setup: discover cache sensor and start polling timer."""
        self.logger.info("Setting up EV SOC Monitor")

        if self._runtime_data is not None:
            self._cache_entity = self._runtime_data.get_entity_id(HELPER_CACHED_EV_SOC_SUFFIX)
            self._cache_sensor = self._runtime_data.get_entity(HELPER_CACHED_EV_SOC_SUFFIX)

        if not self._cache_entity:
            self.logger.error(
                f"Cached EV SOC sensor not found! "
                f"Monitor cannot function without cache sensor."
            )
            return

        self.logger.info(f"Source sensor: {self._source_entity}")
        self.logger.info(f"Cache sensor: {self._cache_entity}")

        # Start polling timer (every 5 seconds)
        self._timer_unsub = async_track_time_interval(
            self.hass,
            self._async_poll_source_sensor,
            timedelta(seconds=EV_SOC_MONITOR_INTERVAL),
        )

        self.logger.success(
            f"EV SOC Monitor active - polling every {EV_SOC_MONITOR_INTERVAL}s"
        )

    async def _async_poll_source_sensor(self, now=None):
        """
        Poll source sensor and update cache if valid.

        Logging strategy:
        - Silent when source sensor provides valid values (normal operation)
        - WARNING only when using cached value because source unavailable
        """
        # Read source sensor state
        source_state = self.hass.states.get(self._source_entity)

        if not source_state:
            # Source entity doesn't exist (should never happen after setup)
            if self._last_source_state != "missing":
                self.logger.error(
                    f"Source sensor {self._source_entity} not found! "
                    f"Using cached value: {self._last_valid_value}%"
                )
                self._last_source_state = "missing"
            return

        # Check if state is valid (not unknown/unavailable/None)
        if self._is_valid_state(source_state):
            # Valid state - parse and update cache
            try:
                new_value = float(source_state.state)

                # Validate SOC range (0-100%)
                if not (0 <= new_value <= 100):
                    self.logger.warning(
                        f"Source SOC value out of range: {new_value}% "
                        f"(expected 0-100). Keeping cached value: {self._last_valid_value}%"
                    )
                    return

                # Update cache (silent update - normal operation)
                await self._update_cache(new_value)

                # Reset invalid state tracking
                self._last_source_state = "valid"

            except (ValueError, TypeError) as e:
                # Failed to parse as float
                if self._last_source_state != "invalid_value":
                    self.logger.warning(
                        f"Failed to parse source SOC: {source_state.state} "
                        f"(error: {e}). Using cached value: {self._last_valid_value}%"
                    )
                    self._last_source_state = "invalid_value"
        else:
            # Invalid state (unknown/unavailable) - keep cache, log warning
            if self._last_source_state != source_state.state:
                # State changed to invalid - log warning
                self.logger.warning(
                    f"{self.logger.ALERT} Using cached EV SOC: {self._last_valid_value}% "
                    f"(source sensor unavailable: {source_state.state})"
                )
                self._last_source_state = source_state.state

    def _is_valid_state(self, state) -> bool:
        """Check if state is valid (not unknown/unavailable/None)."""
        if not state:
            return False
        if state.state in [None, "unknown", "unavailable", "none"]:
            return False
        return True

    async def _update_cache(self, value: float):
        """Update cached sensor with new valid value (silent operation)."""
        self._last_valid_value = value
        self._last_valid_time = dt_util.now()

        # Calculate cache age for diagnostics
        cache_age_seconds = 0  # Just updated

        if self._cache_sensor and hasattr(self._cache_sensor, "async_publish_cache"):
            await self._cache_sensor.async_publish_cache(
                value,
                last_valid_update=self._last_valid_time,
                is_cached=False,
                cache_age_seconds=cache_age_seconds,
            )
            return
        self.logger.warning("Cached EV SOC entity object not registered in runtime data")

    async def async_remove(self):
        """Cleanup: cancel timer."""
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None

        self.logger.info("EV SOC Monitor removed")
