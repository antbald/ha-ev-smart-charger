"""Centralized file logging manager for EV Smart Charger (v1.3.25)."""
from __future__ import annotations
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import HELPER_ENABLE_FILE_LOGGING_SUFFIX, FILE_LOG_MAX_SIZE_MB, FILE_LOG_BACKUP_COUNT

_LOGGER = logging.getLogger(__name__)


class LogManager:
    """
    Manages file logging for all EVSC components.

    Responsibilities:
    - Monitors toggle switch (evsc_enable_file_logging)
    - Enables/disables file logging on all component loggers
    - Manages log file path and rotation settings
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

        # Log file path in custom_components directory
        self._log_file_path = hass.config.path(
            "custom_components",
            "ev_smart_charger",
            "logs",
            f"evsc_{entry_id}.log"
        )

        self._components = []  # Store EVSCLogger instances
        self._toggle_entity = None  # Toggle switch entity ID
        self._state_listener_unsub = None  # State change listener

        _LOGGER.info(f"LogManager initialized - Log path: {self._log_file_path}")

    async def async_setup(self, components: list):
        """
        Setup log manager with component loggers.

        Args:
            components: List of EVSCLogger instances from all components
        """
        self._components = components
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

    async def _apply_logging_state(self):
        """Enable or disable file logging based on toggle state."""
        state = self.hass.states.get(self._toggle_entity)

        if not state:
            _LOGGER.warning("Toggle state unavailable")
            return

        enabled = state.state == "on"

        if enabled:
            _LOGGER.info(f"Enabling file logging for {len(self._components)} components")
            for logger in self._components:
                logger.enable_file_logging(
                    self._log_file_path,
                    max_bytes=FILE_LOG_MAX_SIZE_MB * 1024 * 1024,
                    backup_count=FILE_LOG_BACKUP_COUNT
                )
        else:
            _LOGGER.info(f"Disabling file logging for {len(self._components)} components")
            for logger in self._components:
                logger.disable_file_logging()

    def get_log_file_path(self) -> str:
        """Get the log file path."""
        return self._log_file_path

    async def async_remove(self):
        """Cleanup log manager."""
        _LOGGER.info("LogManager cleanup")

        # Remove state listener
        if self._state_listener_unsub:
            self._state_listener_unsub()
            self._state_listener_unsub = None

        # Disable file logging on all components
        for logger in self._components:
            logger.disable_file_logging()

        _LOGGER.info("LogManager cleanup complete")
