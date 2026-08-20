"""Manual "Stop Charging" control for EV Smart Charger (v2.10.0 — issue #55).

The integration already ships a manual override that forces the charger ON
(``evsc_forza_ricarica``) and vetoes every automation ``turn_off``. There was no
mirror image: a control whose job is simply *"stop charging right now and don't
let any automation restart it until I say so"*.

This component owns the behavioural half of ``switch.evsc_stop_charging``:

* **immediate effect** — flipping the switch ON stops the charger within the
  same second instead of waiting for some automation tick to be denied;
* **hold** — a periodic re-assert catches charging that started *outside* the
  integration (wallbox auto-resume, a manual flip of the raw charger switch).
  Automation-driven starts are already denied upstream by
  ``AutomationCoordinator._is_manual_stop_active``;
* **release** — flipping the switch OFF releases coordinator ownership and lets
  normal arbitration resume. Nothing is re-started on purpose: the user's own
  automations take over on their next tick.
"""
from __future__ import annotations

from datetime import timedelta

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    HELPER_STOP_CHARGING_SUFFIX,
    MANUAL_STOP_RECHECK_INTERVAL_SECONDS,
    PRIORITY_OVERRIDE,
)
from .runtime import EVSCRuntimeData
from .utils.logging_helper import EVSCLogger

MANUAL_STOP_OWNER_NAME = "Manual Stop"


class ManualStopControl:
    """Enforce the manual Stop Charging override."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        charger_controller,
        runtime_data: EVSCRuntimeData | None = None,
        coordinator=None,
    ) -> None:
        """Initialize the manual stop control."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.charger_controller = charger_controller
        self._runtime_data = runtime_data
        self._coordinator = coordinator

        self.logger = EVSCLogger("MANUAL STOP")

        self._switch_entity: str | None = None
        self._switch_unsub = None
        self._timer_unsub = None
        self._holding = False

    # ── helpers ──────────────────────────────────────────────────

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Resolve an integration-owned helper entity from runtime data."""
        if self._runtime_data is None:
            return None
        return self._runtime_data.get_entity_id(suffix)

    def is_active(self) -> bool:
        """Return True when the manual stop switch is ON."""
        if not self._switch_entity:
            return False
        state = self.hass.states.get(self._switch_entity)
        return bool(state and state.state == STATE_ON)

    async def _emit_diagnostic(
        self,
        *,
        event: str,
        result: str,
        reason_code: str,
        reason_detail: str,
        raw_values: dict | None = None,
        severity: str = "info",
    ) -> None:
        """Publish a structured diagnostic event when available."""
        if self._runtime_data is None or self._runtime_data.diagnostic_manager is None:
            return
        await self._runtime_data.diagnostic_manager.async_emit_event(
            component=MANUAL_STOP_OWNER_NAME,
            event=event,
            result=result,
            reason_code=reason_code,
            reason_detail=reason_detail,
            raw_values=raw_values or {},
            severity=severity,
        )

    # ── lifecycle ────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Discover the helper switch and register listeners."""
        self.logger.separator()
        self.logger.start("Manual Stop control setup")

        self._switch_entity = self._find_entity_by_suffix(HELPER_STOP_CHARGING_SUFFIX)
        if not self._switch_entity:
            self.logger.warning(
                f"Helper entity not found: {HELPER_STOP_CHARGING_SUFFIX} - "
                "manual stop disabled. Restart Home Assistant to create it."
            )
            return

        self._switch_unsub = async_track_state_change_event(
            self.hass, self._switch_entity, self._async_switch_changed
        )
        self._timer_unsub = async_track_time_interval(
            self.hass,
            self._async_periodic_hold_check,
            timedelta(seconds=MANUAL_STOP_RECHECK_INTERVAL_SECONDS),
        )

        # A restart with the switch already ON must re-assert the hold: the
        # state-change listener above only fires on future transitions.
        if self.is_active():
            self.logger.warning("Manual stop restored as ACTIVE - enforcing hold")
            await self._enforce_stop("Manual stop active at startup")

        self.logger.success("Setup completed")
        self.logger.info(f"Monitoring switch: {self._switch_entity}")
        self.logger.separator()

    async def async_remove(self) -> None:
        """Remove listeners."""
        if self._switch_unsub:
            self._switch_unsub()
            self._switch_unsub = None
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None
        self.logger.info("Manual Stop control removed")

    # ── event handlers ───────────────────────────────────────────

    @callback
    async def _async_switch_changed(self, event) -> None:
        """React to the Stop Charging switch being toggled."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return

        is_on = new_state.state == STATE_ON
        was_on = bool(old_state and old_state.state == STATE_ON)
        if is_on == was_on:
            return

        if is_on:
            self.logger.separator()
            self.logger.warning("Manual stop ENGAGED by user")
            await self._enforce_stop("Manual stop requested by user")
            self.logger.separator()
        else:
            self.logger.info("Manual stop RELEASED by user")
            self._release_control("Manual stop released by user")
            await self._emit_diagnostic(
                event="manual_stop",
                result="released",
                reason_code="manual_stop_released",
                reason_detail="Manual stop switch turned OFF",
            )

    @callback
    async def _async_periodic_hold_check(self, now) -> None:
        """Re-assert the hold while the switch stays ON."""
        if not self.is_active():
            if self._holding:
                # Defensive: the switch went OFF without a state event
                # reaching us (e.g. entity removed / restored elsewhere).
                self._release_control("Manual stop no longer active")
            return

        if not await self.charger_controller.is_charging():
            return

        self.logger.warning(
            "Charger started while manual stop is active - re-asserting stop"
        )
        await self._enforce_stop("Manual stop hold: charger restarted externally")

    # ── enforcement ──────────────────────────────────────────────

    async def _enforce_stop(self, reason: str) -> None:
        """Stop the charger and take coordinator ownership."""
        if self._coordinator:
            allowed, coord_reason = await self._coordinator.request_charger_action(
                automation_name=MANUAL_STOP_OWNER_NAME,
                action="turn_off",
                reason=reason,
                priority=PRIORITY_OVERRIDE,
            )
            if not allowed:
                # Should not happen: the coordinator always allows turn_off
                # while the manual stop switch is ON. Stop anyway — a manual
                # stop must never be silently swallowed.
                self.logger.warning(f"Coordinator denied manual stop: {coord_reason}")

        result = await self.charger_controller.stop_charger(f"Manual stop: {reason}")
        self._holding = True

        success = getattr(result, "success", True)
        if success:
            self.logger.success("Charger stopped and held by manual stop")
        else:
            self.logger.error(f"Manual stop failed: {getattr(result, 'message', '')}")

        await self._emit_diagnostic(
            event="manual_stop",
            result="stopped" if success else "failed",
            reason_code="manual_stop_engaged",
            reason_detail=reason,
            raw_values={"holding": self._holding},
            severity="warning",
        )

    def _release_control(self, reason: str) -> None:
        """Release coordinator ownership without restarting anything."""
        self._holding = False
        if self._coordinator:
            self._coordinator.release_control(MANUAL_STOP_OWNER_NAME, reason)
