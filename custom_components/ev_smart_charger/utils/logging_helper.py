"""Centralized logging system for EVSC integration."""
import logging

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
