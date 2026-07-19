"""Charging power model: single source of truth for phase mode + charger model.

Built once from the config entry data and stored on ``EVSCRuntimeData.power_model``
(see ``__init__.py``). Encapsulates the only two things three-phase / charger-model
support changes in the charging logic:

- the watt→amp conversion voltage (``effective_voltage`` = phase_count × 230 V), and
- the amperage level set (``amp_levels``: discrete Tuya levels vs 1 A generic steps).

Single-phase + Tuya (the defaults) reproduce the pre-v2.0.0 behaviour exactly:
``effective_voltage`` = 230, ``amp_levels`` = CHARGER_AMP_LEVELS, and the power
readers return the single configured sensor value.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant

from .const import (
    CHARGER_STATUS_END,
    CHARGER_STATUS_FREE,
    CHARGER_STATUS_WAIT,
    CHARGING_POWER_DRAWING_FLOOR_W,
    CONF_BATTERY_POWER,
    CONF_CHARGING_POWER,
    CONF_CHARGING_POWER_L2,
    CONF_CHARGING_POWER_L3,
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CONF_FV_PRODUCTION_L2,
    CONF_FV_PRODUCTION_L3,
    CONF_GRID_AVAILABLE,
    CONF_GRID_IMPORT,
    CONF_GRID_IMPORT_L2,
    CONF_GRID_IMPORT_L3,
    CONF_HOME_CONSUMPTION,
    CONF_HOME_CONSUMPTION_L2,
    CONF_HOME_CONSUMPTION_L3,
    get_amp_levels,
    get_charger_model,
    get_effective_voltage,
    get_phase_count,
    is_three_phase,
)
from .utils.state_helper import get_float, get_state

# States that mean "no usable numeric reading" for an otherwise-mapped sensor.
_UNAVAILABLE_STATES = (None, "unknown", "unavailable")
# Statuses that mean "not actively drawing" for the textual fallback. Anything
# NOT in this set (or the unavailable set) is treated as charging — a TOLERANT
# blocklist, matching the frontend `_isDrawingNow`, so non-Tuya wallboxes that
# report a brand-specific charging string (e.g. "Charging") still register.
_IDLE_OR_DONE_STATUSES = (CHARGER_STATUS_FREE, CHARGER_STATUS_END, CHARGER_STATUS_WAIT)

# ---------------------------------------------------------------------------
# v2.9.1 — brand-vocabulary status classifiers (SSOT)
#
# Non-Tuya wallboxes report brand-specific status strings. Two lifecycle
# questions keep coming up across components and were previously answered with
# exact Tuya-string comparisons (the root cause of the 2026-07-19 incident,
# where OCPP-style 'available' — which means NO EV connected — passed a
# "connected" gate that only rejected 'charger_free'):
#
#   1. "Is the cable disconnected?"  -> is_disconnected_status()
#   2. "Has the charge completed?"   -> is_charge_complete_status()
#
# Both are deliberately CONSERVATIVE allowlists of unambiguous synonyms
# (case-insensitive): an unknown brand string classifies as "connected / not
# complete", which is the safe failure mode — a wrong 'disconnected' verdict
# would block night charging entirely, while a wrong 'connected' verdict at
# worst runs a session with no draw (caught by the measured-power checks).
# OCPP reference: 'Available' = connector not occupied; 'Finishing' = session
# ended.
# ---------------------------------------------------------------------------
_DISCONNECTED_STATUSES = frozenset(
    {
        CHARGER_STATUS_FREE,  # Tuya
        "available",  # OCPP: connector not occupied
        "disconnected",
        "unplugged",
        "not_connected",
        "not connected",
        "no_car",
        "no car",
        "no_vehicle",
        "car_not_connected",
    }
)

_CHARGE_COMPLETE_STATUSES = frozenset(
    {
        CHARGER_STATUS_END,  # Tuya
        "charged",
        "complete",
        "completed",
        "finished",
        "finishing",  # OCPP: session wrap-up
        "full",
        "charge_complete",
        "charging_complete",
    }
)


def is_disconnected_status(status: str | None) -> bool:
    """True when the textual charger status unambiguously means 'no EV plugged'.

    Tolerant of brand vocabularies (case/whitespace-insensitive). Unknown
    strings return False (treated as connected — the safe default).
    """
    if not status:
        return False
    return str(status).strip().lower() in _DISCONNECTED_STATUSES


def is_charge_complete_status(status: str | None) -> bool:
    """True when the textual charger status unambiguously means 'charge done'.

    Tolerant of brand vocabularies (case/whitespace-insensitive). Unknown
    strings return False.
    """
    if not status:
        return False
    return str(status).strip().lower() in _CHARGE_COMPLETE_STATUSES

# Per-quantity config keys, ordered L1, L2, L3. L1 reuses the existing single-phase
# key so single-phase installs read exactly the same entity as before.
_PRODUCTION_KEYS = (CONF_FV_PRODUCTION, CONF_FV_PRODUCTION_L2, CONF_FV_PRODUCTION_L3)
_CONSUMPTION_KEYS = (CONF_HOME_CONSUMPTION, CONF_HOME_CONSUMPTION_L2, CONF_HOME_CONSUMPTION_L3)
_GRID_IMPORT_KEYS = (CONF_GRID_IMPORT, CONF_GRID_IMPORT_L2, CONF_GRID_IMPORT_L3)
# v2.2.0 — measured charging power. L1 is a NEW key (no single-phase predecessor),
# so _entities_for returns [] in single-phase when CONF_CHARGING_POWER is unmapped.
_CHARGING_POWER_KEYS = (CONF_CHARGING_POWER, CONF_CHARGING_POWER_L2, CONF_CHARGING_POWER_L3)


def _entities_for(config: dict, keys: tuple[str, ...]) -> list[str]:
    """Return the configured entity ids for a quantity.

    Single-phase → only L1 (``keys[0]``). Three-phase → L1/L2/L3, skipping any
    that are not mapped (defensive; the config flow makes L2/L3 required in
    three-phase, but a hand-edited entry might omit one).
    """
    if not is_three_phase(config):
        entity = config.get(keys[0])
        return [entity] if entity else []
    return [config[k] for k in keys if config.get(k)]


@dataclass
class ChargingModel:
    """Immutable view of phase mode + charger model derived from config."""

    phase_count: int
    effective_voltage: float
    amp_levels: list[int]
    charger_model: str
    _production_entities: list[str]
    _consumption_entities: list[str]
    _grid_import_entities: list[str]
    # v2.1.0 (issue #29) — optional signed battery-power sensor. Single (never
    # phase-summed, unlike the readers above): battery power is one inverter-level
    # aggregate, like SOC. None when the user did not map a sensor.
    _battery_power_entity: str | None = None
    # v2.2.0 — measured EV charging-power sensors ([] / [L1] / [L1,L2,L3]) and the
    # textual charger-status sensor used as the drawing-now FALLBACK. Both live on
    # the model so is_charging() is a genuine single source of truth.
    _charging_power_entities: list[str] = field(default_factory=list)
    _charger_status_entity: str | None = None
    # v2.6.0 (issue #36) — optional binary_sensor for grid availability
    # (on = grid present, off = grid lost). None when unmapped.
    _grid_available_entity: str | None = None

    @classmethod
    def from_config(cls, config: dict) -> "ChargingModel":
        """Build the model from config entry data."""
        return cls(
            phase_count=get_phase_count(config),
            effective_voltage=get_effective_voltage(config),
            amp_levels=get_amp_levels(config),
            charger_model=get_charger_model(config),
            _production_entities=_entities_for(config, _PRODUCTION_KEYS),
            _consumption_entities=_entities_for(config, _CONSUMPTION_KEYS),
            _grid_import_entities=_entities_for(config, _GRID_IMPORT_KEYS),
            _battery_power_entity=config.get(CONF_BATTERY_POWER),
            _charging_power_entities=_entities_for(config, _CHARGING_POWER_KEYS),
            _charger_status_entity=config.get(CONF_EV_CHARGER_STATUS),
            _grid_available_entity=config.get(CONF_GRID_AVAILABLE),
        )

    def is_grid_available(self, hass) -> bool | None:
        """Return grid availability from the optional binary_sensor (issue #36).

        Fail-safe: returns ``None`` when the sensor is unmapped OR its state is
        unknown/unavailable/None — callers must treat ``None`` as "don't act".
        Only an explicit ``on``/``off`` yields ``True``/``False``. This prevents
        a boot-time or inverter-integration-restart ``unavailable`` from being
        read as "grid lost" and spuriously stopping a night session.
        """
        if not self._grid_available_entity:
            return None
        state = get_state(hass, self._grid_available_entity)
        if state in _UNAVAILABLE_STATES:
            return None
        return str(state).lower() in ("on", "true", "1", "yes", "home", "present")

    # ----- entity lists (for validation / dashboard) -----
    def production_entities(self) -> list[str]:
        """Return mapped production sensors ([L1] or [L1, L2, L3])."""
        return list(self._production_entities)

    def consumption_entities(self) -> list[str]:
        """Return mapped home-consumption sensors."""
        return list(self._consumption_entities)

    def grid_import_entities(self) -> list[str]:
        """Return mapped grid-import sensors."""
        return list(self._grid_import_entities)

    def labelled_power_entities(self) -> list[tuple[str, str]]:
        """Return (entity_id, label) pairs for all power sensors, for validation.

        Labels gain an "Ln" suffix only in three-phase so single-phase log
        messages are unchanged.
        """
        out: list[tuple[str, str]] = []
        groups = (
            ("Solar Production", self._production_entities),
            ("Home Consumption", self._consumption_entities),
            ("Grid Import", self._grid_import_entities),
        )
        for base, entities in groups:
            for idx, entity in enumerate(entities):
                label = base if self.phase_count == 1 else f"{base} L{idx + 1}"
                out.append((entity, label))
        return out

    # ----- power readers (sum across phases) -----
    def read_production(self, hass: HomeAssistant) -> float:
        """Total PV production (W), summed across phases in three-phase mode."""
        return sum(get_float(hass, e) for e in self._production_entities)

    def read_consumption(self, hass: HomeAssistant) -> float:
        """Total home consumption (W), summed across phases."""
        return sum(get_float(hass, e) for e in self._consumption_entities)

    def read_grid_import(self, hass: HomeAssistant) -> float:
        """Total grid import (W, positive = importing), summed across phases."""
        return sum(get_float(hass, e) for e in self._grid_import_entities)

    def read_battery_discharge(self, hass: HomeAssistant) -> float | None:
        """Home-battery discharge in watts (>=0 = discharging), or None.

        Single sensor (not phase-summed). Convention: the sensor reports
        negative = discharging, positive = charging, so discharge is the
        clamped negation. Returns None when no sensor is configured — the
        explicit guard is what distinguishes "unconfigured" from a genuine 0 W
        reading (``get_float`` defaults to 0.0 for missing/unknown states).
        """
        if not self._battery_power_entity:
            return None
        return max(0.0, -get_float(hass, self._battery_power_entity, default=0.0))

    # ----- charging-state SSOT (v2.2.0) -----
    def charging_power_entities(self) -> list[str]:
        """Return mapped charging-power sensors ([] / [L1] / [L1, L2, L3])."""
        return list(self._charging_power_entities)

    def read_charging_power(self, hass: HomeAssistant) -> float | None:
        """Total measured EV charging power in watts, or None.

        Three-way, all-or-nothing (so a partial/lagging three-phase read can never
        produce a misleadingly-low sum that flips the drawing-now verdict):

        - no charging-power sensor mapped              -> None (unconfigured)
        - any *mapped* phase missing / unavailable     -> None (cannot measure)
        - every mapped phase readable                  -> float, clamped >= 0.0

        The ``max(0.0, ...)`` clamp means a reversed-sign sensor reads a flat 0 W
        and the caller falls through to the status string (the diagnostic surfaces
        the flat 0 as the user's cue to apply a ``| abs`` template fix). Returns
        None — not 0.0 — when unconfigured, so callers distinguish "no sensor"
        (use status fallback) from "genuinely 0 W" (not drawing).
        """
        if not self._charging_power_entities:
            return None
        total = 0.0
        for entity in self._charging_power_entities:
            state_obj = hass.states.get(entity)
            if state_obj is None or state_obj.state in _UNAVAILABLE_STATES:
                return None
            try:
                value = float(state_obj.state)
            except (ValueError, TypeError):
                return None
            # Normalize to watts by unit. Many HA wallbox integrations (Tuya,
            # Easee, Wallbox, go-e, …) expose charging power in kW; without this
            # the floor comparison (200 W) and the frontend (which already
            # normalizes in _powerW) would disagree, and a kW sensor would read
            # ~3.7 < floor → falsely "not charging". Unknown/missing unit →
            # assume watts (the config-flow field asks for watts).
            unit = (state_obj.attributes.get("unit_of_measurement") or "").lower()
            if unit == "kw":
                value *= 1000.0
            total += value
        return max(0.0, total)

    def is_charging(self, hass: HomeAssistant) -> bool:
        """Drawing-now SSOT: is the EV actually drawing current right now?

        STATELESS / instantaneous truth (no grace, no debounce — those belong to
        the consumers that need them). Resolution order:

        1. measured charging power available -> power > CHARGING_POWER_DRAWING_FLOOR_W
        2. else TOLERANT status fallback -> charging unless the status is an
           explicitly idle/done/unavailable value (matches the frontend
           `_isDrawingNow` so backend and dashboard agree on brand strings).
        3. else (no status sensor) -> False
        """
        power = self.read_charging_power(hass)
        if power is not None:
            return power > CHARGING_POWER_DRAWING_FLOOR_W
        status = get_state(hass, self._charger_status_entity)
        if status in _UNAVAILABLE_STATES or status in _IDLE_OR_DONE_STATUSES:
            return False
        # v2.9.1: brand synonyms (e.g. OCPP 'available', 'charged') are just as
        # explicitly not-drawing as the Tuya statuses above.
        if is_disconnected_status(status) or is_charge_complete_status(status):
            return False
        return True

    def is_plugged_in(self, hass: HomeAssistant) -> bool:
        """Lifecycle, NOT draw: is a cable plugged in?

        Read from the textual status (measured 0 W cannot tell "paused" from
        "unplugged"). Status present and not disconnected/unknown/unavailable.
        v2.9.1: uses the tolerant is_disconnected_status classifier so brand
        vocabularies (OCPP 'available', …) answer correctly.
        """
        state = get_state(hass, self._charger_status_entity)
        return state not in _UNAVAILABLE_STATES and not is_disconnected_status(state)

    # ----- conversion -----
    def watts_to_amps(self, watts: float) -> float:
        """Convert total watts to per-phase amperage using the effective voltage."""
        return watts / self.effective_voltage
