"""Centralized file logging manager for EV Smart Charger (v1.4.15).

Restructured logging with date-based directory organization:
- logs/<year>/<month>/<day>.log
- Example: logs/2025/12/29.log
- Automatic daily file rotation at midnight
"""
from __future__ import annotations
import logging
import os
from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.util import dt as dt_util

from .const import HELPER_ENABLE_FILE_LOGGING_SUFFIX
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger

_LOGGER = logging.getLogger(__name__)


class LogManager:
    """
    Manages file logging for all EVSC components.

    Responsibilities:
    - Monitors toggle switch (evsc_enable_file_logging)
    - Enables/disables one global file handler shared by all EVSC component loggers
    - Manages date-based log file paths (year/month/day.log)
    - Handles automatic daily file rotation at midnight
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        runtime_data: EVSCRuntimeData | None = None,
    ):
        """
        Initialize log manager.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID
        """
        self.hass = hass
        self.entry_id = entry_id
        self._runtime_data = runtime_data

        # Base logs directory
        self._logs_base_path = hass.config.path(
            "custom_components",
            "ev_smart_charger",
            "logs"
        )

        self._toggle_entity = None  # Toggle switch entity ID
        self._state_listener_unsub = None  # State change listener
        self._midnight_listener_unsub = None  # Midnight rotation listener
        self._current_date = None  # Track current log date

        _LOGGER.info(f"LogManager initialized - Logs base path: {self._logs_base_path}")

    def _get_log_file_path_for_date(self, date_value: datetime) -> str:
        """
        Get log file path for a specific date.

        Path format: logs/<year>/<month>/<day>.log
        Example: logs/2025/12/29.log

        Args:
            date: Date for the log file

        Returns:
            Full path to log file
        """
        year = str(date_value.year)
        month = f"{date_value.month:02d}"
        day = f"{date_value.day:02d}"

        return os.path.join(
            self._logs_base_path,
            year,
            month,
            f"{day}.log"
        )

    def get_log_file_path(self) -> str:
        """
        Get current day's log file path.

        Returns:
            Full path to today's log file
        """
        if self._current_date is not None:
            return self._get_log_file_path_for_date(self._current_date)
        return self._get_log_file_path_for_date(dt_util.now())

    def get_logs_directory(self) -> str:
        """
        Get base logs directory path.

        Returns:
            Base logs directory path
        """
        return self._logs_base_path

    async def async_setup(self, components: list):
        """
        Setup log manager with component loggers.

        Args:
            components: List of EVSCLogger instances from all components
        """
        self._current_date = dt_util.now().date()
        _LOGGER.info(f"LogManager setup with {len(components)} component loggers")

        if self._runtime_data is not None:
            self._toggle_entity = self._runtime_data.get_entity_id(HELPER_ENABLE_FILE_LOGGING_SUFFIX)

        # Compatibility fallback for standalone tests only.
        # Production code paths must resolve integration entities via runtime_data.
        if not self._toggle_entity and self._runtime_data is None:
            for entity_id in self.hass.states.async_entity_ids():
                if entity_id.endswith(HELPER_ENABLE_FILE_LOGGING_SUFFIX):
                    self._toggle_entity = entity_id
                    _LOGGER.warning(
                        "Falling back to global state scan for file logging toggle: %s",
                        entity_id,
                    )
                    break

        if self._toggle_entity:
            _LOGGER.info(f"Found toggle entity: {self._toggle_entity}")

        if not self._toggle_entity:
            _LOGGER.warning(f"Toggle entity '{HELPER_ENABLE_FILE_LOGGING_SUFFIX}' not found")
            return

        # Apply initial state (enable/disable based on current toggle)
        await self._apply_logging_state()

        # Listen for toggle state changes
        self._state_listener_unsub = async_track_state_change_event(
            self.hass,
            [self._toggle_entity],
            self._toggle_changed
        )
        _LOGGER.info("State listener registered for toggle changes")

        # Listen for midnight to rotate log files
        self._midnight_listener_unsub = async_track_time_change(
            self.hass,
            self._handle_midnight,
            hour=0,
            minute=0,
            second=0
        )
        _LOGGER.info("Midnight listener registered for daily log rotation")

    @callback
    async def _toggle_changed(self, event):
        """Handle toggle state change event."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if not new_state:
            return

        old_value = old_state.state if old_state else "unknown"
        new_value = new_state.state

        _LOGGER.info(f"Toggle state changed: {old_value} → {new_value}")
        await self._apply_logging_state()

    @callback
    async def _handle_midnight(self, now: datetime):
        """
        Handle midnight transition - rotate to new daily log file.

        Args:
            now: Current datetime (midnight)
        """
        new_date = now.date()

        if new_date == self._current_date:
            return  # Already on correct date

        _LOGGER.info(f"Midnight rotation: {self._current_date} → {new_date}")
        self._current_date = new_date

        # Check if logging is enabled
        state = self.hass.states.get(self._toggle_entity)
        if state and state.state == "on":
            # Re-enable with new day's file
            new_log_path = self.get_log_file_path()
            _LOGGER.info(f"Rotating to new log file: {new_log_path}")
            await self.hass.async_add_executor_job(EVSCLogger.disable_global_file_logging)
            await self.hass.async_add_executor_job(
                EVSCLogger.enable_global_file_logging,
                new_log_path,
            )

    async def _apply_logging_state(self):
        """Enable or disable file logging based on toggle state."""
        state = self.hass.states.get(self._toggle_entity)

        if not state:
            _LOGGER.warning("Toggle state unavailable")
            return

        enabled = state.state == "on"

        if enabled:
            log_path = self.get_log_file_path()
            _LOGGER.info("Enabling global file logging for EVSC components")
            _LOGGER.info(f"Log file: {log_path}")
            await self.hass.async_add_executor_job(
                EVSCLogger.enable_global_file_logging,
                log_path,
            )
        else:
            _LOGGER.info("Disabling global file logging for EVSC components")
            EVSCLogger.disable_global_file_logging()

    async def async_remove(self):
        """Cleanup log manager."""
        _LOGGER.info("LogManager cleanup")

        # Remove state listener
        if self._state_listener_unsub:
            self._state_listener_unsub()
            self._state_listener_unsub = None

        # Remove midnight listener
        if self._midnight_listener_unsub:
            self._midnight_listener_unsub()
            self._midnight_listener_unsub = None

        # Disable global file logging handler
        EVSCLogger.disable_global_file_logging()

        _LOGGER.info("LogManager cleanup complete")
