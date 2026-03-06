# Hardening Cycle Status

This file records the closure state of the stabilization plan completed on 2026-03-06.

## 1. Implemented in this cycle

### Runtime and bootstrap

- Moved runtime state to `ConfigEntry.runtime_data` through `EVSCRuntimeData`.
- Added deterministic helper registration with a startup barrier.
- Replaced sleep-based setup synchronization with `ConfigEntryNotReady` on timeout.
- Removed active runtime fallback to global helper discovery.

### Charger safety

- Refactored `ChargerController` to avoid deadlock-prone public method reentry.
- Switched charger operations to serialized completion semantics.
- Added current-control adapter support for `number`, `input_number`, `select`, and `input_select`.
- Routed external energy forecast writes through native Home Assistant services.

### Control plane

- Completed coordinator ownership for the charger-driving automations.
- Enforced stand-down behavior on ownership loss or preemption.
- Kept `PriorityBalancer` as a decision component instead of a direct actuator.

### Config UX and surface cleanup

- Added native `reconfigure` flow support.
- Kept `OptionsFlow` as a compatibility wrapper for one release window.
- Preserved public entity IDs, unique IDs, prefixes, and config keys.
- Hid unsupported charging profiles from the frontend and translation surface.

### Entity layer and diagnostics

- Added shared entity base behavior for consistent metadata and registration.
- Removed production `hass.states.async_set(...)` updates for integration-owned entities.
- Scoped helper and diagnostic lookup per config entry.

### Tests and documentation

- Expanded test coverage across bootstrap, runtime, controller, config flow, coordinator, platform entities, and supporting services.
- Consolidated canonical maintainer docs under `docs/`.
- Archived noisy historical testing artifacts outside the active `tests/` contract.

## 2. Acceptance criteria

Final validation run:

```bash
./.venv/bin/python -m pytest -q
```

Observed result:

- `103 passed`
- `2 warnings` from `pytest_cov`
- total coverage `66%`

The hardening cycle acceptance criteria are therefore satisfied:

- full `pytest` suite green
- total coverage `>= 65%`
- no active runtime fallback to global helper discovery
- no user-facing reference to unsupported charging profiles

## 3. Residual backlog

The remaining backlog is intentionally small and non-blocking:

- incremental simplification of very large automation modules, especially `night_smart_charge.py` and `solar_surplus.py`
- further coverage growth above the stabilization target
- optional UX improvements in the dashboard card without changing the supported profile surface

These items are optimization work, not release blockers.
