"""Hybrid Inverter Mode — curtailment discovery via probing (v1.8.0).

Addresses issue #20: in hybrid zero-export inverter systems (Deye, Sunsynk,
Solis, Growatt, Goodwe, etc.) with a full home battery, the inverter actively
curtails PV production to avoid grid export. The reported `fv_production`
matches `home_consumption`, making `surplus = production - consumption ≈ 0`.
Solar Surplus believes there is no headroom, so the EV charger never starts —
even though kilowatts of PV are available the moment a load is applied.

This module implements an opt-in **probing** strategy: when conditions suggest
curtailment (battery full, low grid import, daytime, no surplus), start the
charger at 6A as a test and watch `grid_import`. If the inverter ramps PV and
the import stays low → headroom confirmed, continue and ride the edge of the
import limit. If import rises and persists → no headroom, stop and cool down.

State machine:

    IDLE
      └─ entry conditions met → [start_charger(6A) + notify_once] → PROBING

    PROBING (probe_duration s at 6A, two-phase observation)
      ├─ Phase A (0-20s "transient grace"): ignore grid_import (inverter ramp)
      ├─ Phase B (20-probe_duration): if grid_import > threshold for
      │  max_import_duration consecutive seconds → FAIL
      ├─ probe completes with grid_import OK → RIDING_EDGE
      └─ FAIL → stop_charger + COOLDOWN_SHORT, append to failure window

    RIDING_EDGE
      ├─ headroom_ok_since ≥ HYBRID_HEADROOM_STABLE_SECONDS → step amperage up
      ├─ import_violation_since ≥ max_import_duration → step amperage down
      ├─ at 6A and import persists → STOP + COOLDOWN_SHORT (counts as FAIL)
      ├─ sustained ≥ HYBRID_RIDING_EDGE_SUCCESS_DURATION → reset failure window
      └─ exit condition fails → IDLE (graceful, NOT counted as FAIL)

    COOLDOWN_SHORT (HYBRID_COOLDOWN_SHORT_SECONDS) → IDLE

    COOLDOWN_LONG (HYBRID_COOLDOWN_LONG_SECONDS) → IDLE
      Entered when failure window count reaches max_failed_probes.
      Failure window is NOT cleared (persistence against thrashing).

    HARD_EXIT
      Entered when N (HYBRID_MAX_DAILY_LONG_COOLDOWNS) long cooldowns happen
      in one day, OR when sunset buffer triggers during RIDING_EDGE. Cleared
      automatically at the next sunrise (when is_nighttime returns False
      again after having been True).

Worst-case grid cost is bounded by sliding window + daily cap: ~350Wh/day.

Driven exclusively by Solar Surplus periodic ticks. No internal timer is
registered — this eliminates any race condition and keeps the state machine
strictly single-threaded inside the async event loop.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CHARGER_MODEL_GENERIC,
    CHARGER_STATUS_END,
    CHARGER_STATUS_FREE,
    CONF_CAR_OWNER,
    CONF_EV_CHARGER_STATUS,
    CONF_GRID_IMPORT,
    CONF_NOTIFY_SERVICES,
    CONF_SOC_HOME,
    DEFAULT_GRID_IMPORT_THRESHOLD,
    DEFAULT_HYBRID_BATTERY_FULL_THRESHOLD,
    DEFAULT_HYBRID_MAX_FAILED_PROBES,
    DEFAULT_HYBRID_MAX_IMPORT_DURATION,
    DEFAULT_HYBRID_PROBE_DURATION,
    DEFAULT_SOLAR_MAX_AMPERAGE,
    HELPER_GRID_IMPORT_THRESHOLD_SUFFIX,
    HELPER_HYBRID_BATTERY_FULL_THRESHOLD_SUFFIX,
    HELPER_HYBRID_DIAGNOSTIC_SUFFIX,
    HELPER_HYBRID_INVERTER_MODE_SUFFIX,
    HELPER_HYBRID_MAX_FAILED_PROBES_SUFFIX,
    HELPER_HYBRID_MAX_IMPORT_DURATION_SUFFIX,
    HELPER_HYBRID_PROBE_DURATION_SUFFIX,
    HELPER_MAX_BATTERY_DISCHARGE_FOR_EV_SUFFIX,
    HELPER_SOLAR_MAX_AMPERAGE_SUFFIX,
    HYBRID_COOLDOWN_LONG_SECONDS,
    HYBRID_COOLDOWN_SHORT_SECONDS,
    HYBRID_FAILURE_WINDOW_SECONDS,
    HYBRID_GRID_ENTRY_SMOOTH_SECONDS,
    HYBRID_HEADROOM_STABLE_SECONDS,
    HYBRID_MAX_DAILY_LONG_COOLDOWNS,
    HYBRID_MAX_NEGATIVE_SURPLUS_W,
    HYBRID_PROBE_AMPERAGE,
    HYBRID_RIDING_EDGE_SUCCESS_DURATION,
    HYBRID_STATE_COOLDOWN_LONG,
    HYBRID_STATE_COOLDOWN_SHORT,
    HYBRID_STATE_HARD_EXIT,
    HYBRID_STATE_IDLE,
    HYBRID_STATE_PROBING,
    HYBRID_STATE_RIDING_EDGE,
    HYBRID_SUNSET_BUFFER_MIN,
    HYBRID_TRANSIENT_GRACE_SECONDS,
    PRIORITY_EV_FREE,
    PRIORITY_HOME,
    SURPLUS_STOP_THRESHOLD,
)
from .power_model import ChargingModel
from .runtime import EVSCRuntimeData
from .utils.amperage_helper import AmperageCalculator
from .utils.astral_time_service import AstralTimeService
from .utils.logging_helper import EVSCLogger
from .utils.mobile_notification_service import MobileNotificationService
from .utils.state_helper import get_bool, get_float, get_int, get_state, validate_sensor


class HybridInverterMode:
    """Curtailment-discovery state machine driven by Solar Surplus ticks."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        charger_controller: Any,
        priority_balancer: Any,
        runtime_data: EVSCRuntimeData | None = None,
        coordinator: Any | None = None,
    ) -> None:
        """Initialize Hybrid Inverter Mode (dependencies via constructor)."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.charger_controller = charger_controller
        self.priority_balancer = priority_balancer
        self._runtime_data = runtime_data
        self._coordinator = coordinator
        self.logger = EVSCLogger("HYBRID INVERTER")
        self._astral_service = AstralTimeService(hass)
        self._mobile_notifier = MobileNotificationService(
            hass=hass,
            notify_services=config.get(CONF_NOTIFY_SERVICES, []) or [],
            entry_id=entry_id,
            car_owner_entity=config.get(CONF_CAR_OWNER),
            runtime_data=runtime_data,
        )

        # User-configured input sensors
        self._grid_import = config.get(CONF_GRID_IMPORT)
        self._soc_home = config.get(CONF_SOC_HOME)
        self._charger_status = config.get(CONF_EV_CHARGER_STATUS)

        # v2.0.0: phase model. Levels follow the charger model; the negative-surplus
        # floor scales with phase count (the 6 A probe draws phase_count× the power).
        _pm = runtime_data.power_model if runtime_data is not None else None
        self._power_model = (
            _pm if isinstance(_pm, ChargingModel) else ChargingModel.from_config(config)
        )
        self._amp_levels = self._power_model.amp_levels
        self._max_negative_surplus_w = (
            HYBRID_MAX_NEGATIVE_SURPLUS_W * self._power_model.phase_count
        )

        # Helper entities resolved in async_setup()
        self._enabled_entity: str | None = None
        self._battery_full_threshold_entity: str | None = None
        self._probe_duration_entity: str | None = None
        self._max_import_duration_entity: str | None = None
        self._max_failed_probes_entity: str | None = None
        self._grid_import_threshold_entity: str | None = None
        self._solar_max_amperage_entity: str | None = None
        # v2.1.0 (issue #29): battery-discharge masking limit (W). 0 = off.
        self._max_battery_discharge_entity: str | None = None
        self._diagnostic_sensor: Any | None = None

        # Back-reference to Solar Surplus for control acquisition
        # Set via set_solar_surplus_owner() after Solar Surplus is created
        self._solar_surplus: Any | None = None

        # State machine
        self._state: str = HYBRID_STATE_IDLE
        self._state_entered_at: datetime | None = None
        self._cooldown_until: datetime | None = None

        # Failure tracking (sliding window + daily cap)
        self._failed_probes_window: list[datetime] = []
        self._long_cooldowns_today: int = 0
        self._long_cooldowns_date: Any | None = None  # date the counter refers to

        # PROBING phase tracking
        self._probe_started_at: datetime | None = None
        self._import_violation_since: datetime | None = None
        # v2.1.0 (issue #29): independent battery-discharge violation clock.
        # MUST stay separate from _import_violation_since — sharing one timestamp
        # for two signals would let a battery violation trip the grid path.
        self._battery_violation_since: datetime | None = None
        # Last battery discharge (W) read this tick; None when unconfigured.
        # Cached so get_diagnostic_snapshot() (which takes no hass) can surface it.
        self._last_battery_discharge_w: float | None = None

        # RIDING_EDGE tracking
        self._headroom_ok_since: datetime | None = None
        self._riding_edge_entered_at: datetime | None = None
        self._current_target_amps: int = 0
        # issue #38: self-tuning step-up for Generic chargers. Generic uses 1A
        # levels, so 6→17A is 11 ticks (~11 min at 1-min check interval) vs ~5
        # for Tuya. After 2 consecutive single-level step-ups on stable headroom
        # we jump 2 levels at a time to converge faster. Reset on any step-down
        # or exit. Tuya is unaffected (its levels are already coarse).
        self._consecutive_stepup_count: int = 0

        # Grid import entry smoothing (so we don't enter PROBING on a 1s dip)
        self._grid_import_below_threshold_since: datetime | None = None

        # Notification dedup ("session" = sunrise→sunset)
        self._notification_sent_on_date: Any | None = None

        # Hard exit tracking (stays True until sunrise)
        self._hard_exit_until_sunrise: bool = False
        self._was_nighttime_last_tick: bool = False

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Resolve helper entities. No timers are registered."""
        self.logger.separator()
        self.logger.start(f"{self.logger.SOLAR} Hybrid Inverter Mode setup")

        self._enabled_entity = self._find_entity_by_suffix(
            HELPER_HYBRID_INVERTER_MODE_SUFFIX
        )
        self._battery_full_threshold_entity = self._find_entity_by_suffix(
            HELPER_HYBRID_BATTERY_FULL_THRESHOLD_SUFFIX
        )
        self._probe_duration_entity = self._find_entity_by_suffix(
            HELPER_HYBRID_PROBE_DURATION_SUFFIX
        )
        self._max_import_duration_entity = self._find_entity_by_suffix(
            HELPER_HYBRID_MAX_IMPORT_DURATION_SUFFIX
        )
        self._max_failed_probes_entity = self._find_entity_by_suffix(
            HELPER_HYBRID_MAX_FAILED_PROBES_SUFFIX
        )
        self._grid_import_threshold_entity = self._find_entity_by_suffix(
            HELPER_GRID_IMPORT_THRESHOLD_SUFFIX
        )
        self._solar_max_amperage_entity = self._find_entity_by_suffix(
            HELPER_SOLAR_MAX_AMPERAGE_SUFFIX
        )
        # v2.1.0 (issue #29): battery-only helper; None in PV-only mode → feature off.
        self._max_battery_discharge_entity = self._find_entity_by_suffix(
            HELPER_MAX_BATTERY_DISCHARGE_FOR_EV_SUFFIX
        )

        if self._runtime_data is not None:
            self._diagnostic_sensor = self._runtime_data.get_entity(
                HELPER_HYBRID_DIAGNOSTIC_SUFFIX
            )

        missing: list[str] = []
        for name, value in [
            ("evsc_hybrid_inverter_mode", self._enabled_entity),
            ("evsc_hybrid_battery_full_threshold", self._battery_full_threshold_entity),
            ("evsc_hybrid_probe_duration", self._probe_duration_entity),
            ("evsc_hybrid_max_import_duration", self._max_import_duration_entity),
            ("evsc_hybrid_max_failed_probes", self._max_failed_probes_entity),
        ]:
            if not value:
                missing.append(name)

        if missing:
            self.logger.warning(
                f"Hybrid Inverter Mode: missing helper entities {missing} — "
                "module will remain inactive until they materialize"
            )

        # On startup, NEVER assume "orphan probe" — the charger may be at 6A
        # because Solar Surplus opportunistic deadband legitimately started it.
        # Just go to IDLE and let the next tick decide.
        self._state = HYBRID_STATE_IDLE
        self._state_entered_at = dt_util.now()
        await self._publish_diagnostic(reason="setup complete")

        self.logger.success("Hybrid Inverter Mode setup complete (state=IDLE)")
        self.logger.separator()

    def set_solar_surplus_owner(self, solar_surplus: Any) -> None:
        """Inject the Solar Surplus reference for control acquisition.

        Called by __init__.py after SolarSurplusAutomation has been built.
        We need this back-reference so probing can go through the existing
        coordinator-owned `_acquire_control` / `_release_control` flow.
        """
        self._solar_surplus = solar_surplus

    async def async_remove(self) -> None:
        """Cleanup on unload — stop the charger if active and reset."""
        if self._state in (HYBRID_STATE_PROBING, HYBRID_STATE_RIDING_EDGE):
            await self._stop_charger("integration unload")
        self._state = HYBRID_STATE_IDLE
        self.logger.info("Hybrid Inverter Mode removed")

    # ─────────────────────────────────────────────────────────────
    # Public API used by Solar Surplus
    # ─────────────────────────────────────────────────────────────

    def is_active(self) -> bool:
        """Return True if state is PROBING or RIDING_EDGE."""
        return self._state in (HYBRID_STATE_PROBING, HYBRID_STATE_RIDING_EDGE)

    async def is_relevant(
        self,
        *,
        surplus_amps: float,
        surplus_watts: float,
        grid_import: float,
        charger_is_on: bool,
        priority: str | None,
        now: datetime,
    ) -> bool:
        """Return True if Solar Surplus must delegate this tick to hybrid mode.

        When state != IDLE → always True (so tick() can manage exit).
        When state == IDLE → True only if ALL entry conditions hold.
        """
        # Always handle non-IDLE states (so we can gracefully exit)
        if self._state != HYBRID_STATE_IDLE:
            return True

        # Toggle must be ON
        if not self._enabled_entity or not get_bool(self.hass, self._enabled_entity):
            return False

        # Update HARD_EXIT clearing (only relevant when IDLE — if we transitioned
        # through HARD_EXIT, the flag persists across IDLE until sunrise).
        is_night = self._astral_service.is_nighttime(now)
        if self._hard_exit_until_sunrise and self._was_nighttime_last_tick and not is_night:
            # Sunrise just happened → clear HARD_EXIT lockout
            self._hard_exit_until_sunrise = False
            self._long_cooldowns_today = 0
            self.logger.info(
                f"{self.logger.DAY} Sunrise — clearing HARD_EXIT lockout, "
                "Hybrid Mode available again"
            )
        self._was_nighttime_last_tick = is_night

        if self._hard_exit_until_sunrise:
            return False

        # Cooldown still active?
        if self._cooldown_until is not None and now < self._cooldown_until:
            return False

        # Daytime required
        if is_night:
            return False

        # Sunset buffer — never start a probe in the last HYBRID_SUNSET_BUFFER_MIN
        # minutes of solar window. PV is genuinely low then; curtailment is unlikely.
        sunset = self._astral_service.get_sunset(now)
        if sunset is not None:
            buffer = timedelta(minutes=HYBRID_SUNSET_BUFFER_MIN)
            if now + buffer >= sunset:
                return False

        # Home battery must be reported full
        soc_home = get_float(self.hass, self._soc_home, default=None)
        threshold = get_int(
            self.hass,
            self._battery_full_threshold_entity,
            default=DEFAULT_HYBRID_BATTERY_FULL_THRESHOLD,
        )
        if soc_home is None or threshold is None or soc_home < threshold:
            self._grid_import_below_threshold_since = None
            return False

        # Surplus must look near-zero (curtailment signature). If surplus is real
        # and above start threshold, normal Solar Surplus path handles it.
        if surplus_amps >= SURPLUS_STOP_THRESHOLD:
            self._grid_import_below_threshold_since = None
            return False

        # 6A floor protection: if the house consumes much more than PV ceiling,
        # there is no plausible headroom even with curtailment.
        if surplus_watts < self._max_negative_surplus_w:
            self._grid_import_below_threshold_since = None
            return False

        # Charger must currently be off AND plugged in (not free, not finished).
        if charger_is_on:
            return False
        status = get_state(self.hass, self._charger_status)
        if status in (CHARGER_STATUS_FREE, CHARGER_STATUS_END, None, "unavailable", "unknown"):
            return False

        # Priority Balancer must not say HOME. EV_FREE override is allowed only
        # when the home battery is "full" per the user-configured threshold
        # (issue #39 — was hardcoded 100, inconsistent with the IDLE-entry guard
        # above which already uses battery_full_threshold; BMS systems can sit at
        # 98–99% for a long time before briefly touching 100%).
        if priority == PRIORITY_HOME:
            return False
        if priority == PRIORITY_EV_FREE:
            if soc_home < threshold:
                return False

        # Grid import must be valid
        is_valid, _ = validate_sensor(self.hass, self._grid_import, "Grid Import")
        if not is_valid:
            return False

        # Grid import smoothing — must stay below threshold/2 for entry smooth window
        grid_threshold = get_float(
            self.hass,
            self._grid_import_threshold_entity,
            default=DEFAULT_GRID_IMPORT_THRESHOLD,
        )
        if grid_import < grid_threshold / 2:
            if self._grid_import_below_threshold_since is None:
                self._grid_import_below_threshold_since = now
            elapsed = (now - self._grid_import_below_threshold_since).total_seconds()
            if elapsed < HYBRID_GRID_ENTRY_SMOOTH_SECONDS:
                return False
        else:
            self._grid_import_below_threshold_since = None
            return False

        return True

    async def tick(
        self,
        *,
        surplus_amps: float,
        surplus_watts: float,
        grid_import: float,
        charger_is_on: bool,
        current_amps: int,
        priority: str | None,
        now: datetime,
    ) -> bool:
        """Drive one cycle of the state machine. Returns True if handled."""
        try:
            # v2.1.0 (issue #29): cache the signed battery-discharge reading once
            # per tick (None when no sensor mapped) so the PROBING/RIDING_EDGE
            # masking checks and the diagnostic snapshot share one value.
            self._last_battery_discharge_w = self._power_model.read_battery_discharge(
                self.hass
            )

            # Sanity: re-check sensor on EVERY tick
            is_valid, err = validate_sensor(self.hass, self._grid_import, "Grid Import")
            if not is_valid and self._state != HYBRID_STATE_IDLE:
                self.logger.warning(
                    f"Hybrid: grid_import sensor invalid ({err}) — aborting + COOLDOWN_SHORT"
                )
                await self._fail_probe(now, reason="grid sensor invalid")
                return True

            # While active, re-check all exit conditions
            if self._state in (HYBRID_STATE_PROBING, HYBRID_STATE_RIDING_EDGE):
                exit_reason = await self._check_active_exit_conditions(
                    surplus_watts=surplus_watts,
                    priority=priority,
                    charger_is_on=charger_is_on,
                    now=now,
                )
                if exit_reason is not None:
                    await self._graceful_exit(now, reason=exit_reason)
                    return True

            # State-specific handlers
            if self._state == HYBRID_STATE_IDLE:
                # Caller guaranteed entry conditions are met (is_relevant returned True)
                await self._start_probe(now)
                return True

            if self._state == HYBRID_STATE_PROBING:
                await self._handle_probing(now, grid_import)
                return True

            if self._state == HYBRID_STATE_RIDING_EDGE:
                await self._handle_riding_edge(now, grid_import, current_amps)
                return True

            if self._state in (HYBRID_STATE_COOLDOWN_SHORT, HYBRID_STATE_COOLDOWN_LONG):
                await self._handle_cooldown(now)
                return True

            if self._state == HYBRID_STATE_HARD_EXIT:
                # Persisted across IDLE until sunrise — should not be reached here
                return True

            return False
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.error(f"Hybrid tick error: {exc}")
            # Try to leave the charger in a safe state
            await self._force_safe_state(now, reason=f"unhandled error: {exc}")
            return True

    async def async_force_exit(self, reason: str) -> None:
        """External forced exit (called from Solar Surplus early-return guards).

        Triggered by Forza Ricarica, Boost Charge, Charger Free, Profile change,
        Control loss. Stops the charger if active and resets to IDLE.
        """
        if self._state not in (HYBRID_STATE_PROBING, HYBRID_STATE_RIDING_EDGE):
            return
        self.logger.info(f"{self.logger.STOP} Hybrid forced exit: {reason}")
        await self._stop_charger(reason)
        await self._transition(HYBRID_STATE_IDLE, reason=f"forced exit: {reason}")

    def _battery_violation_amount(self) -> float | None:
        """Return discharge-over-limit watts, or None when the check is inactive.

        Inactive (returns None) when no battery-power sensor is mapped
        (``_last_battery_discharge_w`` is None) or the limit is 0/unset. Otherwise
        returns ``discharge - limit`` (positive = the battery is masking more than
        the user allows; <=0 = within budget). v2.1.0 (issue #29).
        """
        if self._last_battery_discharge_w is None:
            return None
        limit = get_float(self.hass, self._max_battery_discharge_entity, default=0)
        if limit <= 0:
            return None
        return self._last_battery_discharge_w - limit

    def get_diagnostic_snapshot(self) -> dict[str, Any]:
        """Return a serializable snapshot of the state machine."""
        now = dt_util.now()
        snapshot: dict[str, Any] = {
            "state": self._state,
            "failed_probes_in_window": len(self._failed_probes_window),
            "long_cooldowns_today": self._long_cooldowns_today,
            "current_target_amps": self._current_target_amps,
            "hard_exit_until_sunrise": self._hard_exit_until_sunrise,
            "last_check": now.isoformat(),
        }
        # v2.1.0 (issue #29): surface the battery-discharge reading. A flat 0 here
        # while the battery is known to be discharging is the user's cue that their
        # sensor sign is reversed (apply the template-sensor fix).
        if self._last_battery_discharge_w is not None:
            snapshot["battery_discharge_w"] = round(self._last_battery_discharge_w, 1)
        if self._state_entered_at is not None:
            snapshot["state_entered_at"] = self._state_entered_at.isoformat()
            snapshot["state_age_seconds"] = int(
                (now - self._state_entered_at).total_seconds()
            )
        if self._cooldown_until is not None:
            snapshot["cooldown_until"] = self._cooldown_until.isoformat()
            remaining = max(0, int((self._cooldown_until - now).total_seconds()))
            snapshot["cooldown_remaining_seconds"] = remaining
        if self._headroom_ok_since is not None:
            snapshot["headroom_ok_since"] = self._headroom_ok_since.isoformat()
        if self._import_violation_since is not None:
            snapshot["import_violation_since"] = self._import_violation_since.isoformat()
        if self._notification_sent_on_date is not None:
            snapshot["notification_sent_on_date"] = str(self._notification_sent_on_date)
        return snapshot

    # ─────────────────────────────────────────────────────────────
    # State machine internals
    # ─────────────────────────────────────────────────────────────

    async def _check_active_exit_conditions(
        self,
        *,
        surplus_watts: float,
        priority: str | None,
        charger_is_on: bool,
        now: datetime,
    ) -> str | None:
        """While PROBING/RIDING_EDGE, re-validate that we should still be active."""
        # Toggle still on?
        if not self._enabled_entity or not get_bool(self.hass, self._enabled_entity):
            return "Hybrid Mode toggle OFF"

        # Daytime + sunset buffer
        is_night = self._astral_service.is_nighttime(now)
        if is_night:
            return "nighttime"
        sunset = self._astral_service.get_sunset(now)
        if sunset is not None:
            buffer = timedelta(minutes=HYBRID_SUNSET_BUFFER_MIN)
            if now + buffer >= sunset:
                return f"within sunset buffer ({HYBRID_SUNSET_BUFFER_MIN} min)"

        # Battery still full?
        soc_home = get_float(self.hass, self._soc_home, default=None)
        threshold = get_int(
            self.hass,
            self._battery_full_threshold_entity,
            default=DEFAULT_HYBRID_BATTERY_FULL_THRESHOLD,
        )
        if soc_home is None or threshold is None or soc_home < threshold:
            return f"home SOC dropped below threshold ({soc_home}% < {threshold}%)"

        # Charger still plugged?
        status = get_state(self.hass, self._charger_status)
        if status in (CHARGER_STATUS_FREE, CHARGER_STATUS_END):
            return f"charger status now {status}"

        # 6A floor + plausibility
        if surplus_watts < self._max_negative_surplus_w:
            return f"surplus dropped below {self._max_negative_surplus_w}W (no plausible headroom)"

        # PRIORITY checks
        if priority == PRIORITY_HOME:
            return "Priority Balancer = HOME"
        # issue #39: use the configured battery_full_threshold, not a hardcoded
        # 100, to stay consistent with the IDLE-entry guard and the keep-alive
        # threshold check above.
        if priority == PRIORITY_EV_FREE and soc_home < threshold:
            return (
                f"EV_FREE override requires home SOC >= {threshold}% "
                "(battery_full_threshold)"
            )

        return None

    async def _start_probe(self, now: datetime) -> None:
        """Transition IDLE → PROBING and start the charger at 6A."""
        # Acquire control through Solar Surplus owner (coordinator-aware)
        if self._solar_surplus is not None:
            acquired = await self._solar_surplus._acquire_control(
                "turn_on", "Hybrid Mode: probing for curtailed PV"
            )
            if not acquired:
                self.logger.info("Coordinator denied probe — entering COOLDOWN_SHORT")
                self._cooldown_until = now + timedelta(seconds=HYBRID_COOLDOWN_SHORT_SECONDS)
                await self._transition(
                    HYBRID_STATE_COOLDOWN_SHORT, reason="coordinator denied"
                )
                return

        self.logger.separator()
        self.logger.start(f"{self.logger.SOLAR} Hybrid Mode: starting PROBE")
        result = await self.charger_controller.start_charger(
            target_amps=HYBRID_PROBE_AMPERAGE,
            reason="Hybrid Mode: probing for hidden solar headroom",
        )
        if not result.success:
            self.logger.warning(f"Probe start failed: {result.error_message}")
            await self._fail_probe(now, reason=f"start failed: {result.error_message}")
            return

        self._current_target_amps = HYBRID_PROBE_AMPERAGE
        self._probe_started_at = now
        self._import_violation_since = None
        self._battery_violation_since = None  # v2.1.0 (issue #29)
        self._headroom_ok_since = None
        await self._transition(HYBRID_STATE_PROBING, reason="probe started")

        # Single notification per session (sunrise→sunset)
        today = now.date()
        if self._notification_sent_on_date != today:
            await self._mobile_notifier.send_hybrid_mode_started_notification()
            self._notification_sent_on_date = today

    async def _handle_probing(self, now: datetime, grid_import: float) -> None:
        """During PROBING: two-phase observation of grid_import."""
        probe_duration = get_int(
            self.hass,
            self._probe_duration_entity,
            default=DEFAULT_HYBRID_PROBE_DURATION,
        )
        max_import_duration = get_int(
            self.hass,
            self._max_import_duration_entity,
            default=DEFAULT_HYBRID_MAX_IMPORT_DURATION,
        )
        grid_threshold = get_float(
            self.hass,
            self._grid_import_threshold_entity,
            default=DEFAULT_GRID_IMPORT_THRESHOLD,
        )

        if self._probe_started_at is None:
            self._probe_started_at = now
        elapsed = (now - self._probe_started_at).total_seconds()

        # Phase A: transient grace — ignore grid_import while inverter ramps
        if elapsed < HYBRID_TRANSIENT_GRACE_SECONDS:
            self.logger.info(
                f"PROBING Phase A: {elapsed:.0f}/{HYBRID_TRANSIENT_GRACE_SECONDS}s "
                f"transient grace (grid={grid_import:.0f}W, ignoring)"
            )
            await self._publish_diagnostic(reason=f"PROBING Phase A {elapsed:.0f}s")
            return

        # Phase B: steady-state observation
        if grid_import > grid_threshold:
            if self._import_violation_since is None:
                self._import_violation_since = now
                self.logger.info(
                    f"PROBING Phase B: grid_import {grid_import:.0f}W > "
                    f"{grid_threshold:.0f}W — starting violation timer"
                )
            violation_elapsed = (now - self._import_violation_since).total_seconds()
            if violation_elapsed >= max_import_duration:
                self.logger.warning(
                    f"PROBING FAIL: grid_import sustained for {violation_elapsed:.0f}s "
                    f"(limit {max_import_duration}s) — no headroom"
                )
                await self._fail_probe(now, reason="grid import sustained during probe")
                return
        else:
            self._import_violation_since = None

        # v2.1.0 (issue #29): battery-discharge masking check (closes Failure
        # mode 1). A near-full battery can silently cover the 6A EV load with
        # grid_import ≈ 0, so the grid check alone would "succeed" on pure
        # battery drain. Independent sustained timer; no-op when no sensor /
        # limit 0. Sustained (not point-in-time) → also tolerant of slow PV ramp.
        batt_over = self._battery_violation_amount()
        if batt_over is not None and batt_over > 0:
            if self._battery_violation_since is None:
                self._battery_violation_since = now
                self.logger.info(
                    f"PROBING Phase B: battery discharge over limit by "
                    f"{batt_over:.0f}W — starting masking timer"
                )
            batt_elapsed = (now - self._battery_violation_since).total_seconds()
            if batt_elapsed >= max_import_duration:
                self.logger.warning(
                    f"PROBING FAIL: battery masking sustained for {batt_elapsed:.0f}s "
                    f"(limit {max_import_duration}s) — PV never unlocked"
                )
                await self._fail_probe(now, reason="battery discharge masking during probe")
                return
        else:
            self._battery_violation_since = None

        # Probe window completed?
        if elapsed >= probe_duration:
            # v2.1.0 (issue #29): gate success on the battery NOT actively masking
            # at completion. With the default 60s tick and 60s probe_duration the
            # sustained timer above never accumulates (the first Phase B tick IS
            # the completion tick: batt_elapsed = 0), so a probe masked for its
            # whole run would otherwise "succeed" on pure battery drain — the exact
            # false positive this feature exists to catch. The user-set limit still
            # tolerates minor battery activity (only over-limit discharge blocks
            # success); a slow-ramp inverter that hasn't handed off by completion
            # is handled by raising probe_duration.
            if batt_over is not None and batt_over > 0:
                self.logger.warning(
                    f"PROBING FAIL: battery still masking "
                    f"({self._last_battery_discharge_w:.0f}W, over limit by "
                    f"{batt_over:.0f}W) at probe completion — PV headroom not confirmed"
                )
                await self._fail_probe(
                    now, reason="battery masking at probe completion"
                )
                return
            self.logger.success(
                f"PROBING SUCCESS: probe completed without sustained import — "
                f"transitioning to RIDING_EDGE"
            )
            self._headroom_ok_since = None
            self._import_violation_since = None
            self._battery_violation_since = None  # v2.1.0 (issue #29)
            self._riding_edge_entered_at = now
            await self._transition(HYBRID_STATE_RIDING_EDGE, reason="probe succeeded")
        else:
            await self._publish_diagnostic(
                reason=f"PROBING Phase B {elapsed:.0f}/{probe_duration}s"
            )

    async def _handle_riding_edge(
        self, now: datetime, grid_import: float, current_amps: int
    ) -> None:
        """During RIDING_EDGE: step amperage up/down based on grid_import."""
        max_import_duration = get_int(
            self.hass,
            self._max_import_duration_entity,
            default=DEFAULT_HYBRID_MAX_IMPORT_DURATION,
        )
        grid_threshold = get_float(
            self.hass,
            self._grid_import_threshold_entity,
            default=DEFAULT_GRID_IMPORT_THRESHOLD,
        )
        solar_max_amperage = get_int(
            self.hass,
            self._solar_max_amperage_entity,
            default=DEFAULT_SOLAR_MAX_AMPERAGE,
        )

        # Sync with reality — cached current_amps may be stale (e.g., charger
        # adjusted by a previous decrease sequence).
        actual_amps = await self.charger_controller.get_current_amperage()
        if actual_amps is not None and actual_amps > 0:
            self._current_target_amps = actual_amps
            current_amps = actual_amps
        elif current_amps <= 0:
            self.logger.warning(
                "RIDING_EDGE: charger reports 0A — treating as control loss"
            )
            await self._graceful_exit(now, reason="charger amperage = 0 in RIDING_EDGE")
            return

        # Sustained successful riding → reset failure window (the system is working)
        if (
            self._riding_edge_entered_at is not None
            and (now - self._riding_edge_entered_at).total_seconds()
            >= HYBRID_RIDING_EDGE_SUCCESS_DURATION
            and self._failed_probes_window
        ):
            self.logger.success(
                f"RIDING_EDGE sustained ≥ {HYBRID_RIDING_EDGE_SUCCESS_DURATION}s "
                f"— resetting failure window ({len(self._failed_probes_window)} entries)"
            )
            self._failed_probes_window.clear()

        # Decrease path
        if grid_import > grid_threshold:
            if self._import_violation_since is None:
                self._import_violation_since = now
            violation_elapsed = (now - self._import_violation_since).total_seconds()
            if violation_elapsed >= max_import_duration:
                next_down = AmperageCalculator.get_next_level_down(current_amps, self._amp_levels)
                if next_down >= 6:
                    self.logger.info(
                        f"{self.logger.ACTION} RIDING_EDGE: grid {grid_import:.0f}W "
                        f"sustained for {violation_elapsed:.0f}s — reducing "
                        f"{current_amps}A → {next_down}A"
                    )
                    result = await self.charger_controller.set_amperage(
                        target_amps=next_down,
                        reason=f"Hybrid: reducing for grid_import {grid_import:.0f}W",
                    )
                    if result.success:
                        self._current_target_amps = next_down
                        self._import_violation_since = None
                        self._headroom_ok_since = None
                        self._consecutive_stepup_count = 0  # issue #38
                        await self._publish_diagnostic(
                            reason=f"RIDING_EDGE @ {next_down}A (reduced)"
                        )
                    return
                else:
                    # At 6A and still violating → FAIL
                    self.logger.warning(
                        f"RIDING_EDGE FAIL: at 6A but grid still {grid_import:.0f}W "
                        f"for {violation_elapsed:.0f}s — no headroom"
                    )
                    await self._fail_probe(now, reason="6A floor reached, import persists")
                    return
            await self._publish_diagnostic(
                reason=f"RIDING_EDGE @ {current_amps}A (import {grid_import:.0f}W, "
                f"violation {violation_elapsed:.0f}/{max_import_duration}s)"
            )
            return

        # Reset violation tracking when we're back below threshold
        if grid_import <= grid_threshold / 2:
            self._import_violation_since = None

            # v2.1.0 (issue #29): battery-discharge masking step-down. With grid
            # import already low, a passing cloud can be covered silently by the
            # battery. Independent clock (_battery_violation_since) — never shares
            # storage with the grid timer. Step down (or FAIL at 6A) when the
            # over-limit discharge is sustained; while violating we never ramp up.
            batt_over = self._battery_violation_amount()
            if batt_over is not None and batt_over > 0:
                if self._battery_violation_since is None:
                    self._battery_violation_since = now
                    self.logger.info(
                        f"RIDING_EDGE: battery discharge over limit by "
                        f"{batt_over:.0f}W — starting masking timer"
                    )
                batt_elapsed = (now - self._battery_violation_since).total_seconds()
                if batt_elapsed >= max_import_duration:
                    next_down = AmperageCalculator.get_next_level_down(
                        current_amps, self._amp_levels
                    )
                    if next_down >= 6:
                        self.logger.info(
                            f"{self.logger.ACTION} RIDING_EDGE: battery masking "
                            f"sustained for {batt_elapsed:.0f}s — reducing "
                            f"{current_amps}A → {next_down}A"
                        )
                        result = await self.charger_controller.set_amperage(
                            target_amps=next_down,
                            reason=(
                                "Hybrid: reducing for battery discharge "
                                f"{self._last_battery_discharge_w:.0f}W"
                            ),
                        )
                        if result.success:
                            self._current_target_amps = next_down
                            self._battery_violation_since = None
                            self._headroom_ok_since = None
                            self._consecutive_stepup_count = 0  # issue #38
                            await self._publish_diagnostic(
                                reason=f"RIDING_EDGE @ {next_down}A (reduced, battery)"
                            )
                        return
                    self.logger.warning(
                        f"RIDING_EDGE FAIL: at 6A but battery masking "
                        f"{batt_elapsed:.0f}s — no PV headroom"
                    )
                    await self._fail_probe(
                        now, reason="6A floor reached, battery masking persists"
                    )
                    return
                # Violating but not yet sustained → hold, do NOT ramp up.
                await self._publish_diagnostic(
                    reason=(
                        f"RIDING_EDGE @ {current_amps}A (battery "
                        f"{self._last_battery_discharge_w:.0f}W, violation "
                        f"{batt_elapsed:.0f}/{max_import_duration}s)"
                    )
                )
                return
            self._battery_violation_since = None

            if self._headroom_ok_since is None:
                self._headroom_ok_since = now
            headroom_elapsed = (now - self._headroom_ok_since).total_seconds()
            # Increase path
            if (
                headroom_elapsed >= HYBRID_HEADROOM_STABLE_SECONDS
                and current_amps < solar_max_amperage
            ):
                next_up = AmperageCalculator.get_next_level_up(
                    current_amps, solar_max_amperage, self._amp_levels
                )
                # issue #38: self-tuning — on a Generic charger (1A levels), once
                # we've already stepped up twice in a row on stable headroom, jump
                # 2 levels per tick to converge faster. Tuya keeps single-level
                # steps (its levels are already coarse → avoid overshoot).
                if (
                    self._power_model.charger_model == CHARGER_MODEL_GENERIC
                    and self._consecutive_stepup_count >= 2
                    and next_up > current_amps
                    and next_up < solar_max_amperage
                ):
                    next_up = AmperageCalculator.get_next_level_up(
                        next_up, solar_max_amperage, self._amp_levels
                    )
                if next_up > current_amps:
                    self.logger.info(
                        f"{self.logger.ACTION} RIDING_EDGE: grid {grid_import:.0f}W "
                        f"stable for {headroom_elapsed:.0f}s — increasing "
                        f"{current_amps}A → {next_up}A"
                    )
                    result = await self.charger_controller.set_amperage(
                        target_amps=next_up,
                        reason=f"Hybrid: increasing on stable headroom",
                    )
                    if result.success:
                        self._current_target_amps = next_up
                        self._headroom_ok_since = None  # restart stability clock
                        self._consecutive_stepup_count += 1  # issue #38
                        await self._publish_diagnostic(
                            reason=f"RIDING_EDGE @ {next_up}A (increased)"
                        )
                    return
            await self._publish_diagnostic(
                reason=f"RIDING_EDGE @ {current_amps}A (stable {headroom_elapsed:.0f}s)"
            )
            return

        # Grid in the hysteresis band — hold position
        await self._publish_diagnostic(
            reason=f"RIDING_EDGE @ {current_amps}A (grid {grid_import:.0f}W, holding)"
        )

    async def _handle_cooldown(self, now: datetime) -> None:
        """During COOLDOWN_*: wait for the timer to expire."""
        if self._cooldown_until is None or now >= self._cooldown_until:
            self.logger.info(f"Cooldown expired — returning to IDLE")
            self._cooldown_until = None
            await self._transition(HYBRID_STATE_IDLE, reason="cooldown expired")
            return
        await self._publish_diagnostic(reason=self._format_cooldown_remaining(now))

    async def _fail_probe(self, now: datetime, reason: str) -> None:
        """Record a probe failure and decide between COOLDOWN_SHORT/LONG/HARD_EXIT."""
        await self._stop_charger(f"Hybrid probe failed: {reason}")

        # Roll daily counter
        self._maybe_reset_daily_counter(now)
        # Sliding window: prune old failures and append the new one
        cutoff = now - timedelta(seconds=HYBRID_FAILURE_WINDOW_SECONDS)
        self._failed_probes_window = [
            t for t in self._failed_probes_window if t > cutoff
        ]
        self._failed_probes_window.append(now)

        max_failed = get_int(
            self.hass,
            self._max_failed_probes_entity,
            default=DEFAULT_HYBRID_MAX_FAILED_PROBES,
        )

        if len(self._failed_probes_window) >= max_failed:
            self._long_cooldowns_today += 1
            self.logger.warning(
                f"Hybrid: {len(self._failed_probes_window)} fails in "
                f"{HYBRID_FAILURE_WINDOW_SECONDS // 60}min — entering COOLDOWN_LONG "
                f"({HYBRID_COOLDOWN_LONG_SECONDS // 60} min). "
                f"Daily long cooldown count: {self._long_cooldowns_today}/"
                f"{HYBRID_MAX_DAILY_LONG_COOLDOWNS}"
            )

            if self._long_cooldowns_today >= HYBRID_MAX_DAILY_LONG_COOLDOWNS:
                self.logger.warning(
                    f"{self.logger.ALERT} Hybrid: daily HARD_EXIT triggered — "
                    "no further probes until sunrise"
                )
                self._hard_exit_until_sunrise = True
                self._cooldown_until = None
                await self._transition(
                    HYBRID_STATE_HARD_EXIT, reason="daily HARD_EXIT reached"
                )
                # Route through _transition again so all probe-tracking fields
                # (_probe_started_at, _current_target_amps, ...) are zeroed.
                # HARD_EXIT is a guard for is_relevant(), not an active state.
                await self._transition(
                    HYBRID_STATE_IDLE,
                    reason="HARD_EXIT guard set, returning to IDLE",
                )
                return

            self._cooldown_until = now + timedelta(seconds=HYBRID_COOLDOWN_LONG_SECONDS)
            await self._transition(HYBRID_STATE_COOLDOWN_LONG, reason=reason)
        else:
            self.logger.info(
                f"Hybrid: probe failure {len(self._failed_probes_window)}/"
                f"{max_failed} in window — COOLDOWN_SHORT "
                f"({HYBRID_COOLDOWN_SHORT_SECONDS}s)"
            )
            self._cooldown_until = now + timedelta(seconds=HYBRID_COOLDOWN_SHORT_SECONDS)
            await self._transition(HYBRID_STATE_COOLDOWN_SHORT, reason=reason)

    async def _graceful_exit(self, now: datetime, reason: str) -> None:
        """Stop charger and return to IDLE — does NOT count as a failure."""
        self.logger.info(f"{self.logger.STOP} Hybrid graceful exit: {reason}")
        await self._stop_charger(f"Hybrid graceful exit: {reason}")
        # Check if sunset triggered → enter HARD_EXIT for the rest of the day
        sunset = self._astral_service.get_sunset(now)
        if sunset is not None and now + timedelta(
            minutes=HYBRID_SUNSET_BUFFER_MIN
        ) >= sunset:
            self._hard_exit_until_sunrise = True
        await self._transition(HYBRID_STATE_IDLE, reason=f"graceful: {reason}")

    async def _force_safe_state(self, now: datetime, reason: str) -> None:
        """Emergency stop when something went wrong."""
        try:
            await self._stop_charger(f"Hybrid emergency: {reason}")
        finally:
            self._cooldown_until = now + timedelta(seconds=HYBRID_COOLDOWN_SHORT_SECONDS)
            await self._transition(HYBRID_STATE_COOLDOWN_SHORT, reason=reason)

    async def _stop_charger(self, reason: str) -> None:
        """Stop the charger and release control.

        Guard release_control with an ownership check: when this is called from
        async_force_exit (scheduled as a task by Solar Surplus's
        _handle_control_loss), Solar Surplus has already released control
        synchronously. Without the guard, we would call release_control a
        second time on an automation that no longer owns the session — at best
        a no-op, at worst stripping ownership from whoever acquired it in the
        intervening event loop tick.
        """
        try:
            await self.charger_controller.stop_charger(reason=reason)
        except Exception as exc:
            self.logger.warning(f"stop_charger failed: {exc}")
        self._current_target_amps = 0
        if self._solar_surplus is not None:
            try:
                if self._solar_surplus._has_control():
                    self._solar_surplus._release_control(f"Hybrid stop: {reason}")
            except Exception as exc:  # pragma: no cover
                self.logger.debug(f"release_control skipped: {exc}")

    async def _transition(self, new_state: str, *, reason: str) -> None:
        """Centralized state transition with logging + diagnostic publish."""
        prev_state = self._state
        if prev_state == new_state:
            return
        self._state = new_state
        self._state_entered_at = dt_util.now()
        # issue #38: any real state change (enter/leave RIDING_EDGE, cooldown,
        # idle, fail) restarts the self-tuning ramp from single-level steps.
        # Step-ups/step-downs within RIDING_EDGE do NOT call _transition, so this
        # never clobbers the counter mid-ramp.
        self._consecutive_stepup_count = 0
        if new_state == HYBRID_STATE_IDLE:
            self._probe_started_at = None
            self._import_violation_since = None
            self._battery_violation_since = None  # v2.1.0 (issue #29)
            self._headroom_ok_since = None
            self._riding_edge_entered_at = None
            self._current_target_amps = 0
        self.logger.info(
            f"{self.logger.DECISION} Hybrid state: {prev_state} → {new_state} ({reason})"
        )
        await self._publish_diagnostic(reason=f"transition: {reason}")

    def _maybe_reset_daily_counter(self, now: datetime) -> None:
        """Reset long cooldown counter if a new day has begun."""
        today = now.date()
        if self._long_cooldowns_date != today:
            self._long_cooldowns_date = today
            self._long_cooldowns_today = 0

    def _format_cooldown_remaining(self, now: datetime) -> str:
        """Build a human-readable cooldown remaining string."""
        if self._cooldown_until is None:
            return self._state
        remaining = max(0, int((self._cooldown_until - now).total_seconds()))
        if self._state == HYBRID_STATE_COOLDOWN_LONG:
            return f"COOLDOWN_LONG ({remaining // 60}m {remaining % 60}s left)"
        return f"COOLDOWN_SHORT ({remaining}s left)"

    async def _publish_diagnostic(self, *, reason: str) -> None:
        """Update the diagnostic sensor (best-effort)."""
        if self._diagnostic_sensor is None and self._runtime_data is not None:
            # Late binding — try to resolve now
            self._diagnostic_sensor = self._runtime_data.get_entity(
                HELPER_HYBRID_DIAGNOSTIC_SUFFIX
            )
        if self._diagnostic_sensor is None:
            return

        snapshot = self.get_diagnostic_snapshot()
        snapshot["reason"] = reason
        state_str = self._build_state_string()
        try:
            await self._diagnostic_sensor.async_publish(state_str, snapshot)
        except Exception as exc:  # pragma: no cover
            self.logger.debug(f"diagnostic publish failed: {exc}")

    def _build_state_string(self) -> str:
        """Render the user-facing state value for the diagnostic sensor."""
        now = dt_util.now()
        if self._state == HYBRID_STATE_PROBING and self._probe_started_at is not None:
            elapsed = int((now - self._probe_started_at).total_seconds())
            probe_duration = get_int(
                self.hass,
                self._probe_duration_entity,
                default=DEFAULT_HYBRID_PROBE_DURATION,
            )
            return f"PROBING ({elapsed}/{probe_duration}s)"
        if self._state == HYBRID_STATE_RIDING_EDGE:
            return f"RIDING_EDGE @ {self._current_target_amps}A"
        if self._state in (HYBRID_STATE_COOLDOWN_SHORT, HYBRID_STATE_COOLDOWN_LONG):
            return self._format_cooldown_remaining(now)
        if self._hard_exit_until_sunrise:
            return "HARD_EXIT (until sunrise)"
        return self._state

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Resolve a helper entity ID by suffix from runtime data."""
        if self._runtime_data is None:
            return None
        return self._runtime_data.get_entity_id(suffix)
