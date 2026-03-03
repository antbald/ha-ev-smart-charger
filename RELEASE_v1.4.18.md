# Release v1.4.18

## Features

- Added `Boost Charge`, a dedicated manual override with:
  - fixed charging amperage
  - configurable EV target SOC
  - automatic stop when the EV reaches the configured target
  - automatic return to normal automations after completion
- Added new helper entities for Boost Charge:
  - `switch.evsc_boost_charge_enabled`
  - `number.evsc_boost_charge_amperage`
  - `number.evsc_boost_target_soc`
- Added Boost Charge start/completion notifications using the existing Night Charge notification toggle.

## Automation integration

- Smart Charger Blocker now allows an active Boost Charge session.
- Solar Surplus now skips its control loop while Boost Charge is active.
- Night Smart Charge now skips evaluation while Boost Charge is active.
- Added immediate post-boost re-evaluation hooks so normal automations resume right away.

## Documentation

- Updated the README feature list and charging modes with Boost Charge.
- Extended the example dashboard YAML with dedicated Boost Charge controls.
- Corrected the documented entity count to match the actual integration output.

## Validation

- `./.venv/bin/pytest -q tests/test_boost_charge.py tests/test_smart_charger_blocker.py tests/test_solar_surplus.py tests/test_night_smart_charge.py`
- Result: `23 passed`
- `python3 -m py_compile custom_components/ev_smart_charger/boost_charge.py ...`
