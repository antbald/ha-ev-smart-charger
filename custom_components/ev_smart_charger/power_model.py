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

from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from .const import (
    CONF_BATTERY_POWER,
    CONF_FV_PRODUCTION,
    CONF_FV_PRODUCTION_L2,
    CONF_FV_PRODUCTION_L3,
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
from .utils.state_helper import get_float

# Per-quantity config keys, ordered L1, L2, L3. L1 reuses the existing single-phase
# key so single-phase installs read exactly the same entity as before.
_PRODUCTION_KEYS = (CONF_FV_PRODUCTION, CONF_FV_PRODUCTION_L2, CONF_FV_PRODUCTION_L3)
_CONSUMPTION_KEYS = (CONF_HOME_CONSUMPTION, CONF_HOME_CONSUMPTION_L2, CONF_HOME_CONSUMPTION_L3)
_GRID_IMPORT_KEYS = (CONF_GRID_IMPORT, CONF_GRID_IMPORT_L2, CONF_GRID_IMPORT_L3)


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
        )

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

    # ----- conversion -----
    def watts_to_amps(self, watts: float) -> float:
        """Convert total watts to per-phase amperage using the effective voltage."""
        return watts / self.effective_voltage
