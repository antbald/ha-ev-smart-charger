# Codebase Map

This file maps the active repository structure and points to the modules that own each concern.

## 1. Top-level layout

```text
custom_components/
  ev_smart_charger/
    __init__.py
    const.py
    config_flow.py
    runtime.py
    entity_base.py
    automation_coordinator.py
    diagnostic_manager.py
    charger_controller.py
    priority_balancer.py
    night_smart_charge.py
    boost_charge.py
    automations.py
    solar_surplus.py
    ev_soc_monitor.py
    log_manager.py
    switch.py
    number.py
    select.py
    sensor.py
    time.py
    frontend/
    utils/
tests/
docs/
README.md
Makefile
```

## 2. Bootstrap and runtime

| File | Responsibility |
| --- | --- |
| `custom_components/ev_smart_charger/__init__.py` | Config-entry setup, runtime bootstrap, unload order, platform forwarding |
| `custom_components/ev_smart_charger/runtime.py` | Canonical `EVSCRuntimeData` dataclass and runtime access helpers |
| `custom_components/ev_smart_charger/entity_base.py` | Shared entity registration, metadata, and runtime-aware base behavior |
| `custom_components/ev_smart_charger/const.py` | Shared constants, helper suffixes, defaults, and automation priorities |
| `custom_components/ev_smart_charger/config_flow.py` | Initial setup flow, native reconfigure flow, compatibility options wrapper |
| `custom_components/ev_smart_charger/diagnostic_manager.py` | Unified diagnostics publisher for runtime events and coordinator snapshots |

## 3. Charger control and orchestration

| File | Responsibility | Notes |
| --- | --- | --- |
| `custom_components/ev_smart_charger/charger_controller.py` | Serialized charger start, stop, and current changes | Owns current-control adapter for `number`, `input_number`, `select`, `input_select` |
| `custom_components/ev_smart_charger/automation_coordinator.py` | Ownership arbitration across charger-driving automations | Single control plane for Boost, Blocker, Night, and Solar |
| `custom_components/ev_smart_charger/priority_balancer.py` | EV vs home battery decision logic | Decision-only, not a charger actuator |
| `custom_components/ev_smart_charger/boost_charge.py` | Fixed-current override with SOC auto-stop | High-priority automation |
| `custom_components/ev_smart_charger/automations.py` | Smart Charger Blocker | Can preempt lower-priority charging |
| `custom_components/ev_smart_charger/night_smart_charge.py` | Overnight charging workflow with battery or grid mode | Owns night-session logic and handoff paths |
| `custom_components/ev_smart_charger/solar_surplus.py` | Daytime solar-surplus charging and dynamic current control | Owns daytime adaptive loop |

## 4. Supporting services

| File | Responsibility |
| --- | --- |
| `custom_components/ev_smart_charger/ev_soc_monitor.py` | Cached EV SOC layer for unreliable cloud sensors |
| `custom_components/ev_smart_charger/diagnostic_manager.py` | Unified diagnostic sensor state, recent event history, and trace toggle handling |
| `custom_components/ev_smart_charger/log_manager.py` | File logging toggle and log file path handling |
| `custom_components/ev_smart_charger/utils/amperage_helper.py` | Amperage math and surplus-control helpers |
| `custom_components/ev_smart_charger/utils/astral_time_service.py` | Sunrise and sunset window calculations |
| `custom_components/ev_smart_charger/utils/time_parsing_service.py` | Parsing helper for time values |
| `custom_components/ev_smart_charger/utils/logging_helper.py` | Shared logging setup |
| `custom_components/ev_smart_charger/utils/notification_service.py` | Persistent notifications |
| `custom_components/ev_smart_charger/utils/mobile_notification_service.py` | Mobile-app notifications with optional car-owner presence gating |

Removed from active architecture:

- `custom_components/ev_smart_charger/helpers.py`
- `custom_components/ev_smart_charger/utils/entity_helper.py`
- `custom_components/ev_smart_charger/utils/entity_registry_service.py`

## 5. Entity platforms

| File | Platform | Main role |
| --- | --- | --- |
| `custom_components/ev_smart_charger/switch.py` | `switch` | Feature toggles, overrides, notification switches, day flags |
| `custom_components/ev_smart_charger/number.py` | `number` | Thresholds, amperage settings, SOC targets |
| `custom_components/ev_smart_charger/select.py` | `select` | Charging profile selector restricted to supported profiles |
| `custom_components/ev_smart_charger/sensor.py` | `sensor` | Diagnostics, cached EV SOC, target summaries, log path |
| `custom_components/ev_smart_charger/time.py` | `time` | Night-charge and car-ready schedule helpers |

## 6. Frontend

| File | Responsibility |
| --- | --- |
| `custom_components/ev_smart_charger/frontend/ev-smart-charger-dashboard.js` | Dashboard card served by the integration; filters profile chips to `manual` and `solar_surplus` |

## 7. Tests

Active suites are under `tests/` and cover:

- bootstrap and runtime data
- charger controller
- automation coordinator
- config and reconfigure flows
- platform entities
- EV SOC monitor and astral time service
- boost, blocker, night charge, solar surplus, and scenarios

Historical test artifacts are archived under `docs/historical/` and are not part of the active pytest contract.

## 8. Documentation

Canonical documents:

- `README.md`
- `docs/SSOT.md`
- `docs/CODEBASE_MAP.md`
- `docs/REFACTOR_PLAN.md`

Historical notes, bug analyses, and archived test-session material live under `docs/historical/`.
