"""Centralized file logging manager for EV Smart Charger (v1.4.15).

Restructured logging with date-based directory organization:
- logs/<year>/<month>/<day>.log
- Example: logs/2025/12/29.log
- Automatic daily file rotation at midnight
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change

from .const import HELPER_ENABLE_FILE_LOGGING_SUFFIX

_LOGGER = logging.getLogger(__name__)


class LogManager:
    """
    Manages file logging for all EVSC components.

    Responsibilities:
    - Monitors toggle switch (evsc_enable_file_logging)
    - Enables/disables file logging on all component loggers
    - Manages date-based log file paths (year/month/day.log)
    - Handles automatic daily file rotation at midnight
    """

    def __init__(self, hass: HomeAssistant, entry_id: str):
        """
        Initialize log manager.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID
        """
        self.hass = hass
        self.entry_id = entry_id

        # Base logs directory
        self._logs_base_path = hass.config.path(
            "custom_components",
            "ev_smart_charger",
            "logs"
        )

        self._components = []  # Store EVSCLogger instances
        self._toggle_entity = None  # Toggle switch entity ID
        self._state_listener_unsub = None  # State change listener
        self._midnight_listener_unsub = None  # Midnight rotation listener
        self._current_date = None  # Track current log date

        _LOGGER.info(f"LogManager initialized - Logs base path: {self._logs_base_path}")

    def _get_log_file_path_for_date(self, date: datetime) -> str:
        """
        Get log file path for a specific date.

        Path format: logs/<year>/<month>/<day>.log
        Example: logs/2025/12/29.log

        Args:
            date: Date for the log file

        Returns:
            Full path to log file
        """
        year = str(date.year)
        month = f"{date.month:02d}"
        day = f"{date.day:02d}"

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
        return self._get_log_file_path_for_date(datetime.now())

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
        self._components = components
        self._current_date = datetime.now().date()
        _LOGGER.info(f"LogManager setup with {len(components)} component loggers")

        # Find toggle switch entity
        for entity_id in self.hass.states.async_entity_ids():
            if entity_id.endswith(HELPER_ENABLE_FILE_LOGGING_SUFFIX):
                self._toggle_entity = entity_id
                _LOGGER.info(f"Found toggle entity: {entity_id}")
                break

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
            # Disable current logging
            for logger in self._components:
                logger.disable_file_logging()

            # Re-enable with new day's file
            new_log_path = self.get_log_file_path()
            _LOGGER.info(f"Rotating to new log file: {new_log_path}")

            for logger in self._components:
                await self.hass.async_add_executor_job(
                    logger.enable_file_logging,
                    new_log_path
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
            _LOGGER.info(f"Enabling file logging for {len(self._components)} components")
            _LOGGER.info(f"Log file: {log_path}")

            for logger in self._components:
                await self.hass.async_add_executor_job(
                    logger.enable_file_logging,
                    log_path
                )
        else:
            _LOGGER.info(f"Disabling file logging for {len(self._components)} components")
            for logger in self._components:
                logger.disable_file_logging()

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

        # Disable file logging on all components
        for logger in self._components:
            logger.disable_file_logging()

        _LOGGER.info("LogManager cleanup complete")
