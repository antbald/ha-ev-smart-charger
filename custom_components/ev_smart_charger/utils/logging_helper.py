"""Centralized logging system for EVSC integration (v1.4.15).

Updated to support date-based log file structure:
- Daily log files (one per day)
- No rotation needed (new file each day)
- Path format: logs/<year>/<month>/<day>.log
"""
from __future__ import annotations

import logging
import os
import threading
from itertools import count

_LOGGER = logging.getLogger(__name__)
_PACKAGE_LOGGER = logging.getLogger("custom_components.ev_smart_charger")
_GLOBAL_FILE_HANDLER: logging.FileHandler | None = None
_GLOBAL_FILE_HANDLER_PATH: str | None = None
_GLOBAL_FILE_HANDLER_LOCK = threading.Lock()
_EVENT_COUNTER = count(1)
_EVENT_COUNTER_LOCK = threading.Lock()


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
        self._component_slug = self._slug(component_name)

    @staticmethod
    def _slug(value: str) -> str:
        """Return a stable lowercase slug for identifiers."""
        return "".join(
            char.lower() if char.isalnum() else "_"
            for char in value
        ).strip("_")

    @staticmethod
    def _normalize_text(value) -> str:
        """Return compact text safe for log payloads."""
        if value is None:
            return "-"
        text = " ".join(str(value).split())
        if not text:
            return "-"
        if any(ch.isspace() for ch in text) or any(ch in text for ch in ['"', "=", "[", "]"]):
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return text

    @classmethod
    def _format_value(cls, value) -> str:
        """Format scalars, sequences, and mappings as compact key=value values."""
        if isinstance(value, dict):
            items = ",".join(
                f"{cls._slug(str(key))}:{cls._format_value(inner)}"
                for key, inner in sorted(value.items(), key=lambda item: str(item[0]))
            )
            return cls._normalize_text(f"{{{items}}}")
        if isinstance(value, (list, tuple, set)):
            items = ",".join(cls._format_value(item) for item in value)
            return cls._normalize_text(f"[{items}]")
        return cls._normalize_text(value)

    @classmethod
    def next_decision_id(cls, component_name: str) -> str:
        """Return a stable monotonic decision identifier."""
        with _EVENT_COUNTER_LOCK:
            seq = next(_EVENT_COUNTER)
        return f"{cls._slug(component_name)}_{seq:06d}"

    @classmethod
    def format_event_payload(cls, payload: dict[str, object]) -> str:
        """Format a structured payload as grep-friendly key=value pairs."""
        parts = []
        for key, value in payload.items():
            if value is None:
                continue
            parts.append(f"{cls._slug(str(key))}={cls._format_value(value)}")
        return " ".join(parts)

    def separator(self, length: int = 64):
        """Log visual separator."""
        _LOGGER.info(self.SEPARATOR * length)

    def info(self, message: str, *args):
        """Log info message."""
        if args:
            message = message % args
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

    def success(self, message: str, *args):
        """Log success."""
        if args:
            message = message % args
        _LOGGER.info(f"{self.SUCCESS} [{self.component}] {message}")

    def error(self, message: str, *args):
        """Log error."""
        if args:
            message = message % args
        _LOGGER.error(f"{self.ERROR} [{self.component}] {message}")

    def warning(self, message: str, *args):
        """Log warning."""
        if args:
            message = message % args
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

    def debug(self, message: str, *args):
        """Log debug message."""
        if args:
            message = message % args
        _LOGGER.debug(f"[{self.component}] {message}")

    def event(
        self,
        event: str,
        result: str,
        reason_code: str = "",
        *,
        reason_detail: str = "",
        owner=None,
        trigger: str | None = None,
        entity_ids: dict | list | None = None,
        raw_values: dict | list | None = None,
        session_id: str | None = None,
        decision_id: str | None = None,
        external_cause: str | None = None,
        severity: str = "info",
        extra: dict | None = None,
    ) -> str:
        """Emit a structured key=value diagnostic event."""
        payload: dict[str, object] = {
            "event": event,
            "component": self._component_slug,
            "session_id": session_id or self._component_slug,
            "decision_id": decision_id or self.next_decision_id(self.component),
            "result": result,
            "reason_code": reason_code or "-",
            "reason_detail": reason_detail or "-",
            "owner": owner,
            "trigger": trigger,
            "external_cause": external_cause,
            "entity_ids": entity_ids,
            "raw_values": raw_values,
        }
        if extra:
            payload.update(extra)

        message = f"[{self.component}] {self.format_event_payload(payload)}"
        if severity == "error":
            _LOGGER.error(message)
        elif severity == "warning":
            _LOGGER.warning(message)
        elif severity == "success":
            _LOGGER.info(f"{self.SUCCESS} {message}")
        else:
            _LOGGER.info(f"{self.INFO} {message}")
        return payload["decision_id"]  # type: ignore[return-value]

    def trace_event(
        self,
        title: str,
        payload: dict[str, object],
        *,
        decision_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Emit a multi-line trace snapshot for deep diagnostics."""
        trace_payload = {
            "title": title,
            "decision_id": decision_id or self.next_decision_id(self.component),
            "session_id": session_id or self._component_slug,
            **payload,
        }
        self.info(f"TRACE START {self.format_event_payload(trace_payload)}")
        for key, value in trace_payload.items():
            self.info(f"TRACE {self._slug(str(key))}={self._format_value(value)}")
        self.info("TRACE END")

    # ========== FILE LOGGING METHODS (v1.4.15 - Daily files) ==========

    @classmethod
    def _normalize_log_path(cls, log_file_path: str) -> str:
        """Return normalized absolute path for stable handler identity checks."""
        return os.path.abspath(log_file_path)

    @classmethod
    def _build_file_handler(cls, log_file_path: str) -> logging.FileHandler:
        """Create configured file handler for EVSC daily logging."""
        handler = logging.FileHandler(
            log_file_path,
            mode="a",
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        return handler

    @classmethod
    def enable_global_file_logging(cls, log_file_path: str) -> bool:
        """
        Enable global file logging handler once for the whole integration logger.

        Returns:
            True if the handler was created or switched to a different path,
            False if already enabled with the same target file.
        """
        global _GLOBAL_FILE_HANDLER, _GLOBAL_FILE_HANDLER_PATH
        normalized_path = cls._normalize_log_path(log_file_path)

        with _GLOBAL_FILE_HANDLER_LOCK:
            if _GLOBAL_FILE_HANDLER and _GLOBAL_FILE_HANDLER_PATH == normalized_path:
                return False

            if _GLOBAL_FILE_HANDLER:
                _PACKAGE_LOGGER.removeHandler(_GLOBAL_FILE_HANDLER)
                _GLOBAL_FILE_HANDLER.close()
                _GLOBAL_FILE_HANDLER = None
                _GLOBAL_FILE_HANDLER_PATH = None

            os.makedirs(os.path.dirname(normalized_path), exist_ok=True)
            handler = cls._build_file_handler(normalized_path)
            _PACKAGE_LOGGER.addHandler(handler)

            _GLOBAL_FILE_HANDLER = handler
            _GLOBAL_FILE_HANDLER_PATH = normalized_path
            return True

    @classmethod
    def disable_global_file_logging(cls) -> bool:
        """
        Disable global file logging handler.

        Returns:
            True if handler was disabled, False if already disabled.
        """
        global _GLOBAL_FILE_HANDLER, _GLOBAL_FILE_HANDLER_PATH

        with _GLOBAL_FILE_HANDLER_LOCK:
            if not _GLOBAL_FILE_HANDLER:
                return False

            _PACKAGE_LOGGER.removeHandler(_GLOBAL_FILE_HANDLER)
            _GLOBAL_FILE_HANDLER.close()
            _GLOBAL_FILE_HANDLER = None
            _GLOBAL_FILE_HANDLER_PATH = None
            return True

    @classmethod
    def is_global_file_logging_enabled(cls) -> bool:
        """Check whether global file logging is enabled."""
        return _GLOBAL_FILE_HANDLER is not None

    @classmethod
    def get_global_log_file_path(cls) -> str | None:
        """Return current global log file path when enabled."""
        return _GLOBAL_FILE_HANDLER_PATH

    @classmethod
    def get_global_file_handler_count(cls) -> int:
        """Expose current number of file handlers attached to EVSC logger."""
        return sum(
            1
            for handler in _PACKAGE_LOGGER.handlers
            if isinstance(handler, logging.FileHandler)
        )

    def enable_file_logging(self, log_file_path: str):
        """
        Enable logging to file.

        Since v1.4.15: Uses simple FileHandler (no rotation needed).
        Log files are organized by date: logs/<year>/<month>/<day>.log
        Daily rotation is handled by LogManager at midnight.

        Args:
            log_file_path: Full path to log file (e.g., logs/2025/12/29.log)
        """
        try:
            changed = self.enable_global_file_logging(log_file_path)
            if changed:
                self.info(f"File logging enabled: {self.get_global_log_file_path()}")
            else:
                self.debug(f"File logging already enabled: {self.get_global_log_file_path()}")

        except Exception as ex:
            self.error(f"Failed to enable file logging: {ex}")

    def disable_file_logging(self):
        """Disable file logging."""
        try:
            changed = self.disable_global_file_logging()
            if changed:
                self.info("File logging disabled")
            else:
                self.debug("File logging already disabled")
        except Exception as ex:
            self.error(f"Failed to disable file logging: {ex}")

    def is_file_logging_enabled(self) -> bool:
        """Check if file logging is active."""
        return self.is_global_file_logging_enabled()
