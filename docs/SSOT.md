# EV Smart Charger SSOT

This file is the single source of truth for the current architecture as of 2026-04-11.

If it conflicts with historical notes, release files, or old session summaries, this file wins for maintainer-facing architecture. `README.md` remains the user-facing guide.

## 1. Product scope

`ev_smart_charger` is a Home Assistant custom integration that orchestrates EV charging by driving existing Home Assistant entities:

- one switch to start or stop the charger
- one current-control entity
- one charger status sensor
- SOC, solar, load, grid, and optional forecast sensors

Phase mode (v2.0.0) is an opt-in chosen in the config flow. In **single-phase**
(default) production / home-consumption / grid-import are one sensor each and the
watt→amp conversion uses 230 V — identical to pre-v2.0.0. In **three-phase** they
are three sensors each (summed) and the conversion uses 3 × 230 = 690 V, so per-phase
amperage thresholds and levels stay valid downstream. SOC sensors stay single. Charger
model (v2.0.0) is also opt-in: see §4.

The public charging profiles exposed in the UI are:

- `manual`
- `solar_surplus`

Legacy profiles `charge_target` and `cheapest` remain compatibility-only restore values. They are coerced away from the active UI and are not implemented features.

Night Smart Charge, Boost Charge, Smart Blocker, and Priority Balancer are runtime automations controlled through dedicated helper entities.

## 2. Runtime model

Bootstrap lives in `custom_components/ev_smart_charger/__init__.py`.

The setup sequence is:

1. Register the bundled frontend asset path.
2. Create `EVSCRuntimeData` and attach it to `ConfigEntry.runtime_data`.
3. Forward entity platforms: `switch`, `number`, `select`, `sensor`, `time`.
4. Wait on the helper-registration barrier exposed by `runtime_data.registration_event`.
5. Instantiate core services:
   - `ChargerController`
   - `EVSOCMonitor`
   - `AutomationCoordinator`
   - `DiagnosticManager`
   - `PriorityBalancer`
   - `NightSmartCharge`
   - `BoostCharge`
   - `SmartChargerBlocker`
   - `SolarSurplusAutomation`
   - `LogManager`
6. Store service references back into `runtime_data`.

If the helper barrier does not complete in time, setup raises `ConfigEntryNotReady`.

Unload runs in reverse dependency order and clears `entry.runtime_data`.

## 3. Runtime source of truth

`ConfigEntry.runtime_data` is the only runtime registry for integration-owned helper and diagnostic entities.

`EVSCRuntimeData` owns:

- helper entity IDs keyed by logical suffix
- live entity object references keyed by logical suffix
- service object references for the integration runtime
- the registration barrier used during setup

Active runtime paths must not scan `hass.states` globally to rediscover integration entities. Legacy `entity_helper` and `EntityRegistryService` fallbacks have been removed from production code.

## 4. Charger control contract

`custom_components/ev_smart_charger/charger_controller.py` is the single actuator for charger commands.

Current controller guarantees:

- serialized operations instead of externally visible queueing
- no public-method reentry while holding the same lock
- synchronous completion semantics for public `start`, `stop`, `set_amperage`, `adjust_for_grid_import`, and `recover_to_target` operations
- `OperationResult.queued` preserved only for compatibility and expected to remain `False`

The current-control adapter supports:

- `number.set_value`
- `input_number.set_value`
- `select.select_option`
- `input_select.select_option`

The same native-service approach is used for external energy forecast targets. Integration-owned entities are no longer updated through `hass.states.async_set(...)`.

Charger model (v2.0.0) governs two controller behaviours, read from the config entry
and shared via `runtime_data.power_model` (a `ChargingModel`):

- **Amperage levels**: `tuya` (default) uses discrete `CHARGER_AMP_LEVELS`
  `[6,8,10,13,16,20,24,32]`; `generic` uses 1 A steps `range(6, 33)`.
- **Decrease sequence**: `tuya` lowers amperage with the safe stop → set → start
  sequence (Tuya/`select` chargers misbehave on a live current change); `generic`
  sets the lower value live, without toggling the switch.

## 5. Ownership and arbitration

`custom_components/ev_smart_charger/automation_coordinator.py` is the canonical ownership plane for any automation that may start, stop, or adjust the charger.

The enforced model is:

- `Forza Ricarica` remains the top manual override.
- `BoostCharge`, `SmartChargerBlocker`, `NightSmartCharge`, and `SolarSurplusAutomation` acquire coordinator ownership before controlling the charger.
- Only the current owner may keep adjusting amperage inside an active session.
- A higher-priority automation may preempt a lower-priority owner.
- An automation that loses ownership must stop its active monitor loops and return to an idle state.
- `PriorityBalancer` stays decision-only. It does not directly actuate the charger.

## 6. Config and reconfiguration

`custom_components/ev_smart_charger/config_flow.py` now exposes (v2.0.0):

- a 9-step initial setup flow: name → **phase_mode** → **charger_model** → entities →
  sensors (phase-aware) → pv_forecast → notifications → external_connectors → dashboard
- an 8-step native `async_step_reconfigure` path (entry point is phase_mode; charger
  entities moved to `async_step_reconfigure_entities`) so existing entries can opt in
- a matching 8-step compatibility `OptionsFlow` wrapper that reuses the same validation

Missing `phase_mode` / `charger_model` keys default to `single` / `tuya`, so existing
config entries are byte-for-byte unchanged with no migration.

The canonical unique ID is `ev_charger_switch`. Duplicate charger-switch mappings abort immediately.

Helper tuning values remain helper entities. They are not migrated into `entry.options`.

## 7. Entity layer

The entity platforms share a common runtime-aware base and register themselves into `runtime_data`.

Entity layer guarantees:

- deterministic entity registration per config entry
- no cross-entry helper lookup
- Home Assistant metadata applied consistently for config and diagnostic helpers
- frontend profile selector filtered to the supported profiles `manual` and `solar_surplus`

## 8. Canonical modules

Core runtime modules:

- `__init__.py`
- `runtime.py`
- `power_model.py` (v2.0.0 — `ChargingModel`: phase mode + charger model single source)
- `entity_base.py`
- `charger_controller.py`
- `automation_coordinator.py`
- `diagnostic_manager.py`
- `priority_balancer.py`
- `night_smart_charge.py`
- `boost_charge.py`
- `automations.py`
- `solar_surplus.py`
- `ev_soc_monitor.py`
- `log_manager.py`

Canonical maintainer docs:

- `docs/SSOT.md`
- `docs/CODEBASE_MAP.md`
- `docs/REFACTOR_PLAN.md`
- `README.md`

## 9. Quality baseline

Final validation run on 2026-03-11:

```bash
make test
```

Observed result:

- `130 passed`
- `2 warnings` from `pytest_cov`
- total coverage `69%`

v2.0.0 adds `tests/test_power_model_and_charger_model.py` (ChargingModel, const
helpers, parametrized `AmperageCalculator`, charger-model-gated decrease) and updates
the config-flow tests for the new 9-/8-step sequences.

Release bar now met:

- full `pytest` suite green
- coverage maintained above `65%`
- no active runtime fallback to global helper discovery
- no user-facing reference to unsupported charging profiles
