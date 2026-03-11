"""Centralized Charger Controller for EV Smart Charger."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Optional

import async_timeout
from homeassistant.core import HomeAssistant

from .const import (
    CHARGER_AMPERAGE_STABILIZATION_DELAY,
    CHARGER_AMP_LEVELS,
    CHARGER_COMMAND_DELAY,
    CHARGER_MIN_OPERATION_INTERVAL,
    CHARGER_START_SEQUENCE_DELAY,
    CHARGER_STOP_SEQUENCE_DELAY,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_SWITCH,
    SERVICE_CALL_TIMEOUT,
)
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger


class CurrentControlAdapter:
    """Adapter for charger current entities across HA domains."""

    _SERVICE_MAP = {
        "number": ("number", "set_value", "value"),
        "input_number": ("input_number", "set_value", "value"),
        "select": ("select", "select_option", "option"),
        "input_select": ("input_select", "select_option", "option"),
    }

    def __init__(self, hass: HomeAssistant, entity_id: str | None) -> None:
        """Initialize the adapter."""
        self.hass = hass
        self.entity_id = entity_id
        self.domain = entity_id.split(".", 1)[0] if entity_id else None

    async def async_validate(self) -> None:
        """Validate entity domain and service availability."""
        if not self.entity_id:
            raise ValueError("Missing charger current control entity")

        if self.domain not in self._SERVICE_MAP:
            raise ValueError(
                f"Unsupported charger current control domain: {self.domain}"
            )

        service_domain, service_name, _ = self._SERVICE_MAP[self.domain]
        if not self.hass.services.has_service(service_domain, service_name):
            raise ValueError(
                f"Missing Home Assistant service: {service_domain}.{service_name}"
            )

    def get_numeric_state(self) -> int | None:
        """Read a numeric value from the current control entity."""
        if not self.entity_id:
            return None

        state = self.hass.states.get(self.entity_id)
        if state is None or state.state in (None, "unknown", "unavailable", "none"):
            return None

        raw_value = state.state
        try:
            return int(float(raw_value))
        except (TypeError, ValueError):
            match = re.search(r"-?\d+(?:\.\d+)?", str(raw_value))
            if match:
                return int(float(match.group(0)))
        return None

    def build_service_call(
        self,
        value: int | float | str,
    ) -> tuple[str, str, dict]:
        """Build the HA service payload for the configured domain."""
        if self.domain not in self._SERVICE_MAP or not self.entity_id:
            raise ValueError("Current control adapter not configured")

        service_domain, service_name, field_name = self._SERVICE_MAP[self.domain]
        payload_value: int | float | str

        if self.domain in ("select", "input_select"):
            if isinstance(value, (int, float)):
                payload_value = str(int(value))
            else:
                payload_value = str(value)
        else:
            payload_value = value

        return service_domain, service_name, {
            "entity_id": self.entity_id,
            field_name: payload_value,
        }


@dataclass
class OperationResult:
    """Result of a charger operation with detailed feedback."""

    success: bool
    operation: str
    reason: str
    amperage: Optional[int] = None
    queued: bool = False
    error_message: Optional[str] = None
    timestamp: datetime | None = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()
        self.queued = False

    def __str__(self) -> str:
        """Human-readable representation for logging."""
        status = "✅ SUCCESS" if self.success else "❌ FAILED"
        details = []
        if self.amperage is not None:
            details.append(f"{self.amperage}A")
        if self.error_message:
            details.append(f"Error: {self.error_message}")
        details_str = f" ({', '.join(details)})" if details else ""
        return f"{status}: {self.operation}{details_str} - {self.reason}"


class ChargerController:
    """Centralized controller for all charger operations."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        runtime_data: EVSCRuntimeData | None = None,
    ):
        """Initialize ChargerController."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self._runtime_data = runtime_data
        self.logger = EVSCLogger("CHARGER CONTROLLER")

        self._charger_switch = config.get(CONF_EV_CHARGER_SWITCH)
        self._charger_current = config.get(CONF_EV_CHARGER_CURRENT)
        self._current_control = CurrentControlAdapter(hass, self._charger_current)

        self._last_operation_time: Optional[datetime] = None
        self._current_amperage: Optional[int] = None
        self._is_on: Optional[bool] = None
        self._lock = asyncio.Lock()

        self.logger.info(
            "Initialized ChargerController - Switch: %s, Current: %s",
            self._charger_switch,
            self._charger_current,
        )

    async def _emit_operation_diagnostic(
        self,
        operation: str,
        result: str,
        *,
        reason_code: str,
        reason_detail: str,
        target_amps: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Publish a structured diagnostic event for controller operations."""
        if self._runtime_data is None or self._runtime_data.diagnostic_manager is None:
            return

        await self._runtime_data.diagnostic_manager.async_emit_event(
            component="Charger Controller",
            event=operation,
            result=result,
            reason_code=reason_code,
            reason_detail=reason_detail,
            raw_values={
                "target_amps": target_amps,
                "current_amps": self._current_amperage,
                "charger_on": self._is_on,
                "charger_switch": self._charger_switch,
                "current_entity": self._charger_current,
                "error_message": error_message,
            },
            severity="warning" if result == "failed" else "info",
        )

    async def async_setup(self):
        """Setup controller and validate capabilities."""
        self.logger.info("Setting up ChargerController")
        await self._current_control.async_validate()
        await self._refresh_state()
        self.logger.success(
            "Setup complete - Initial state: On=%s, Amperage=%sA",
            self._is_on,
            self._current_amperage,
        )

    async def _refresh_state(self):
        """Refresh cached state from Home Assistant."""
        charger_state = self.hass.states.get(self._charger_switch)
        if charger_state:
            self._is_on = charger_state.state == "on"
        self._current_amperage = self._current_control.get_numeric_state()

    async def start_charger(
        self,
        target_amps: Optional[int] = None,
        reason: str = "",
    ) -> OperationResult:
        """Start the charger with optional target amperage."""
        async with self._lock:
            try:
                self.logger.separator()
                self.logger.start(f"{self.logger.CHARGER} Start Charger")
                self.logger.info("Reason: %s", reason or "No reason provided")
                await self._wait_for_rate_limit()
                await self._refresh_state()

                if target_amps is not None:
                    normalized_target = self._normalize_target_amps(target_amps)
                    await self._set_amperage_internal(normalized_target)
                    await asyncio.sleep(CHARGER_AMPERAGE_STABILIZATION_DELAY)

                await self._call_service(
                    "switch",
                    "turn_on",
                    {"entity_id": self._charger_switch},
                )
                await asyncio.sleep(CHARGER_START_SEQUENCE_DELAY)

                self._record_operation_time()
                await self._refresh_state()
                await self._emit_operation_diagnostic(
                    "charger_start",
                    "succeeded",
                    reason_code="command_executed",
                    reason_detail=reason or "No reason provided",
                    target_amps=self._current_amperage,
                )
                return OperationResult(
                    success=True,
                    operation="start",
                    reason=reason,
                    amperage=self._current_amperage,
                )
            except Exception as ex:
                self.logger.error("Failed to start charger: %s", ex)
                await self._emit_operation_diagnostic(
                    "charger_start",
                    "failed",
                    reason_code="command_failed",
                    reason_detail=reason or "No reason provided",
                    target_amps=self._normalize_target_amps(target_amps)
                    if target_amps is not None
                    else None,
                    error_message=str(ex),
                )
                return OperationResult(
                    success=False,
                    operation="start",
                    reason=reason,
                    amperage=self._normalize_target_amps(target_amps)
                    if target_amps is not None
                    else None,
                    error_message=str(ex),
                )
            finally:
                self.logger.separator()

    async def stop_charger(self, reason: str = "") -> OperationResult:
        """Stop the charger."""
        async with self._lock:
            try:
                self.logger.separator()
                self.logger.start(f"{self.logger.CHARGER} Stop Charger")
                self.logger.info("Reason: %s", reason or "No reason provided")
                await self._wait_for_rate_limit()
                await self._stop_charger_unlocked()
                await self._emit_operation_diagnostic(
                    "charger_stop",
                    "succeeded",
                    reason_code="command_executed",
                    reason_detail=reason or "No reason provided",
                )
                return OperationResult(
                    success=True,
                    operation="stop",
                    reason=reason,
                )
            except Exception as ex:
                self.logger.error("Failed to stop charger: %s", ex)
                await self._emit_operation_diagnostic(
                    "charger_stop",
                    "failed",
                    reason_code="command_failed",
                    reason_detail=reason or "No reason provided",
                    error_message=str(ex),
                )
                return OperationResult(
                    success=False,
                    operation="stop",
                    reason=reason,
                    error_message=str(ex),
                )
            finally:
                self.logger.separator()

    async def set_amperage(self, target_amps: int, reason: str = "") -> OperationResult:
        """Set charger amperage with safe decrease handling."""
        async with self._lock:
            normalized_target = self._normalize_target_amps(target_amps)

            try:
                self.logger.separator()
                self.logger.start(f"{self.logger.CHARGER} Set Amperage")
                self.logger.info(
                    "Target: %sA (Current: %sA)",
                    normalized_target,
                    self._current_amperage,
                )
                self.logger.info("Reason: %s", reason or "No reason provided")

                await self._refresh_state()
                if self._current_amperage == normalized_target:
                    await self._emit_operation_diagnostic(
                        "charger_set_amperage",
                        "succeeded",
                        reason_code="already_at_target",
                        reason_detail=f"Already at target ({normalized_target}A)",
                        target_amps=normalized_target,
                    )
                    return OperationResult(
                        success=True,
                        operation="set_amperage",
                        reason=f"Already at target ({normalized_target}A)",
                        amperage=normalized_target,
                    )

                await self._wait_for_rate_limit()
                operation = await self._set_amperage_unlocked(normalized_target)
                await self._emit_operation_diagnostic(
                    "charger_set_amperage",
                    "succeeded",
                    reason_code="command_executed",
                    reason_detail=reason or "No reason provided",
                    target_amps=normalized_target,
                )
                return OperationResult(
                    success=True,
                    operation=operation,
                    reason=reason,
                    amperage=normalized_target,
                )
            except Exception as ex:
                self.logger.error("Failed to set amperage: %s", ex)
                await self._emit_operation_diagnostic(
                    "charger_set_amperage",
                    "failed",
                    reason_code="command_failed",
                    reason_detail=reason or "No reason provided",
                    target_amps=normalized_target,
                    error_message=str(ex),
                )
                return OperationResult(
                    success=False,
                    operation="set_amperage",
                    reason=reason,
                    amperage=normalized_target,
                    error_message=str(ex),
                )
            finally:
                self.logger.separator()

    async def adjust_for_grid_import(
        self,
        reason: str = "Grid import detected",
    ) -> OperationResult:
        """Reduce charging amperage by one level for grid import protection."""
        from .utils.amperage_helper import AmperageCalculator

        async with self._lock:
            try:
                self.logger.separator()
                self.logger.start(f"{self.logger.CHARGER} Grid Import Protection")
                self.logger.info("Reason: %s", reason)
                await self._refresh_state()

                current_amps = self._current_amperage or 0
                next_amps = AmperageCalculator.get_next_level_down(current_amps)
                await self._wait_for_rate_limit()

                if next_amps == 0:
                    await self._stop_charger_unlocked()
                    return OperationResult(
                        success=True,
                        operation="stop",
                        reason=reason,
                    )

                operation = await self._set_amperage_unlocked(next_amps)
                return OperationResult(
                    success=True,
                    operation=operation,
                    reason=reason,
                    amperage=next_amps,
                )
            except Exception as ex:
                self.logger.error("Failed to adjust for grid import: %s", ex)
                return OperationResult(
                    success=False,
                    operation="adjust_for_grid_import",
                    reason=reason,
                    error_message=str(ex),
                )
            finally:
                self.logger.separator()

    async def recover_to_target(
        self,
        target_amps: int,
        reason: str = "Conditions improved",
    ) -> OperationResult:
        """Gradually recover charging amperage toward target by one level."""
        from .utils.amperage_helper import AmperageCalculator

        normalized_target = self._normalize_target_amps(target_amps)

        async with self._lock:
            try:
                self.logger.separator()
                self.logger.start(f"{self.logger.CHARGER} Amperage Recovery")
                self.logger.info("Target: %sA", normalized_target)
                self.logger.info("Reason: %s", reason)
                await self._refresh_state()

                current_amps = self._current_amperage or 0
                if current_amps >= normalized_target:
                    return OperationResult(
                        success=True,
                        operation="recover_to_target",
                        reason=f"Already at target ({current_amps}A)",
                        amperage=current_amps,
                    )

                await self._wait_for_rate_limit()

                if not self._is_on or current_amps == 0:
                    await self._start_charger_unlocked(normalized_target)
                    return OperationResult(
                        success=True,
                        operation="start",
                        reason=reason,
                        amperage=self._current_amperage,
                    )

                next_amps = AmperageCalculator.get_next_level_up(
                    current_amps,
                    normalized_target,
                )
                operation = await self._set_amperage_unlocked(next_amps)
                return OperationResult(
                    success=True,
                    operation=operation,
                    reason=reason,
                    amperage=next_amps,
                )
            except Exception as ex:
                self.logger.error("Failed to recover amperage: %s", ex)
                return OperationResult(
                    success=False,
                    operation="recover_to_target",
                    reason=reason,
                    amperage=normalized_target,
                    error_message=str(ex),
                )
            finally:
                self.logger.separator()

    async def _start_charger_unlocked(self, target_amps: Optional[int]) -> None:
        """Start the charger without reacquiring the controller lock."""
        if target_amps is not None:
            await self._set_amperage_internal(target_amps)
            await asyncio.sleep(CHARGER_AMPERAGE_STABILIZATION_DELAY)

        await self._call_service(
            "switch",
            "turn_on",
            {"entity_id": self._charger_switch},
        )
        await asyncio.sleep(CHARGER_START_SEQUENCE_DELAY)
        self._record_operation_time()
        await self._refresh_state()

    async def _stop_charger_unlocked(self) -> None:
        """Stop the charger without reacquiring the controller lock."""
        await self._call_service(
            "switch",
            "turn_off",
            {"entity_id": self._charger_switch},
        )
        await asyncio.sleep(CHARGER_COMMAND_DELAY)
        self._record_operation_time()
        await self._refresh_state()

    async def _set_amperage_unlocked(self, target_amps: int) -> str:
        """Set charger amperage without reacquiring the controller lock."""
        await self._refresh_state()
        current_amps = self._current_amperage or 0
        is_on = bool(self._is_on)

        if is_on and target_amps < current_amps:
            await self._decrease_amperage_unlocked(target_amps)
            return "adjust_down"

        await self._set_amperage_internal(target_amps)
        self._record_operation_time()
        await self._refresh_state()
        return "set_amperage"

    async def _decrease_amperage_unlocked(self, target_amps: int) -> None:
        """Decrease amperage using the safe stop/set/start sequence."""
        await self._call_service(
            "switch",
            "turn_off",
            {"entity_id": self._charger_switch},
        )
        await asyncio.sleep(CHARGER_STOP_SEQUENCE_DELAY)
        await self._set_amperage_internal(target_amps)
        await asyncio.sleep(CHARGER_AMPERAGE_STABILIZATION_DELAY)
        await self._call_service(
            "switch",
            "turn_on",
            {"entity_id": self._charger_switch},
        )
        await asyncio.sleep(CHARGER_START_SEQUENCE_DELAY)
        self._record_operation_time()
        await self._refresh_state()

    async def _set_amperage_internal(self, amps: int) -> None:
        """Set the configured charger amperage entity."""
        service_domain, service_name, data = self._current_control.build_service_call(amps)
        await self._call_service(service_domain, service_name, data)

    async def _wait_for_rate_limit(self) -> None:
        """Wait until the minimum operation interval has elapsed."""
        if self._last_operation_time is None:
            return

        elapsed = (datetime.now() - self._last_operation_time).total_seconds()
        if elapsed >= CHARGER_MIN_OPERATION_INTERVAL:
            return

        wait_time = CHARGER_MIN_OPERATION_INTERVAL - elapsed
        self.logger.info("Rate limit active, waiting %.1fs", wait_time)
        await asyncio.sleep(wait_time)

    def _record_operation_time(self) -> None:
        """Record the completion time of the last operation."""
        self._last_operation_time = datetime.now()

    def _normalize_target_amps(self, target_amps: int | float | None) -> int:
        """Normalize a target amperage to the nearest supported level."""
        if target_amps is None:
            return CHARGER_AMP_LEVELS[0]
        return min(CHARGER_AMP_LEVELS, key=lambda value: abs(value - int(target_amps)))

    async def _call_service(self, domain: str, service: str, data: dict):
        """Call a Home Assistant service with timeout and error handling."""
        try:
            async with async_timeout.timeout(SERVICE_CALL_TIMEOUT):
                await self.hass.services.async_call(
                    domain,
                    service,
                    data,
                    blocking=True,
                )
        except asyncio.TimeoutError:
            self.logger.error("Service call timeout: %s.%s", domain, service)
            raise
        except Exception as ex:
            self.logger.error("Service call failed: %s.%s - %s", domain, service, ex)
            raise

    async def is_charging(self) -> bool:
        """Return whether the charger is currently on."""
        await self._refresh_state()
        return self._is_on or False

    async def get_current_amperage(self) -> Optional[int]:
        """Return the current configured amperage."""
        await self._refresh_state()
        return self._current_amperage

    def get_queue_size(self) -> int:
        """Compatibility shim: execution is serialized, not queued."""
        return 0

    def get_last_operation_time(self) -> Optional[datetime]:
        """Get timestamp of last operation."""
        return self._last_operation_time

    def get_seconds_since_last_operation(self) -> Optional[float]:
        """Get seconds since last operation."""
        if self._last_operation_time is None:
            return None
        return (datetime.now() - self._last_operation_time).total_seconds()
