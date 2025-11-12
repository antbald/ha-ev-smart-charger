"""Centralized logging system for EVSC integration."""
import logging
import os
from logging.handlers import RotatingFileHandler

_LOGGER = logging.getLogger(__name__)


class EVSCLogger:
    """Standardized logging for EVSC components."""

    # Emoji constants
    SEPARATOR = "═"
    DECISION = "🎯"
    ACTION = "⚡"
    ERROR = "❌"
    WARNING = "⚠️"
    INFO = "ℹ️"
    SUCCESS = "✅"
    SKIP = "⏭️"
    START = "🔄"
    STOP = "🛑"
    NIGHT = "🌙"
    DAY = "☀️"
    BATTERY = "🔋"
    EV = "🚗"
    CAR = "🚗"  # Alias for EV (v1.3.13+)
    HOME = "🏠"
    SOLAR = "🌞"
    GRID = "⚡"
    CALENDAR = "📅"
    CLOCK = "⏰"
    BALANCE = "⚖️"
    BLOCKER = "🚫"
    CHARGER = "🔌"
    ALERT = "🚨"

    def __init__(self, component_name: str):
        """Initialize logger with component name."""
        self.component = component_name
        self._file_handler = None  # Track file handler (v1.3.25)

    def separator(self, length: int = 64):
        """Log visual separator."""
        _LOGGER.info(self.SEPARATOR * length)

    def info(self, message: str):
        """Log info message."""
        _LOGGER.info(f"{self.INFO} [{self.component}] {message}")

    def decision(self, decision_type: str, decision: str, reason: str):
        """Log a decision with reason."""
        _LOGGER.info(f"{self.DECISION} [{self.component}] Decision: {decision}")
        _LOGGER.info(f"   Reason: {reason}")

    def action(self, action: str, details: str = ""):
        """Log an action."""
        msg = f"{self.ACTION} [{self.component}] Action: {action}"
        if details:
            msg += f" - {details}"
        _LOGGER.info(msg)

    def success(self, message: str):
        """Log success."""
        _LOGGER.info(f"{self.SUCCESS} [{self.component}] {message}")

    def error(self, message: str):
        """Log error."""
        _LOGGER.error(f"{self.ERROR} [{self.component}] {message}")

    def warning(self, message: str):
        """Log warning."""
        _LOGGER.warning(f"{self.WARNING} [{self.component}] {message}")

    def skip(self, reason: str):
        """Log skip with reason."""
        _LOGGER.info(f"{self.SKIP} [{self.component}] Skipped: {reason}")

    def start(self, process: str):
        """Log process start."""
        _LOGGER.info(f"{self.START} [{self.component}] Starting: {process}")

    def stop(self, process: str, reason: str = ""):
        """Log process stop."""
        msg = f"{self.STOP} [{self.component}] Stopping: {process}"
        if reason:
            msg += f" - Reason: {reason}"
        _LOGGER.info(msg)

    def state_change(self, entity: str, old_state: str, new_state: str):
        """Log state change."""
        _LOGGER.info(
            f"{self.INFO} [{self.component}] State change: {entity} ({old_state} → {new_state})"
        )

    def sensor_value(self, sensor_name: str, value: any, unit: str = ""):
        """Log sensor value."""
        msg = f"{self.INFO} [{self.component}] {sensor_name}: {value}"
        if unit:
            msg += f" {unit}"
        _LOGGER.info(msg)

    def debug(self, message: str):
        """Log debug message."""
        _LOGGER.debug(f"[{self.component}] {message}")

    # ========== FILE LOGGING METHODS (v1.3.25) ==========

    def enable_file_logging(self, log_file_path: str, max_bytes: int = 10485760, backup_count: int = 5):
        """
        Enable logging to file with rotation.

        Args:
            log_file_path: Full path to log file
            max_bytes: Max size per file in bytes (default 10MB)
            backup_count: Number of backup files to keep (default 5)
        """
        if self._file_handler:
            # Already enabled
            return

        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

            # Create rotating file handler
            self._file_handler = RotatingFileHandler(
                log_file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )

            # Format: timestamp - component - level - message (with emojis)
            formatter = logging.Formatter(
                '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            self._file_handler.setFormatter(formatter)

            # Add handler to module logger (shared by all EVSCLogger instances)
            _LOGGER.addHandler(self._file_handler)

            self.info(f"File logging enabled: {log_file_path}")

        except Exception as ex:
            self.error(f"Failed to enable file logging: {ex}")

    def disable_file_logging(self):
        """Disable file logging."""
        if self._file_handler:
            try:
                self.info("File logging disabled")
                _LOGGER.removeHandler(self._file_handler)
                self._file_handler.close()
                self._file_handler = None
            except Exception as ex:
                self.error(f"Failed to disable file logging: {ex}")

    def is_file_logging_enabled(self) -> bool:
        """Check if file logging is active."""
        return self._file_handler is not None
