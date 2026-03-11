# Release v1.5.9

## Added

- Added `switch.evsc_preserve_home_battery` to Night Smart Charge.
- Added localized UI copy and dashboard controls for preserving the home battery in EN, IT, and NL.
- Added a dedicated Night Smart Charge skip notification and diagnostic reason for home-battery preservation.

## Changed

- Night Smart Charge now skips overnight charging when `car_ready` is off and the preserve-home-battery flag is enabled.
- Solar Surplus now publishes detailed grid import protection diagnostics, including timing, thresholds, battery-support state, current amperage, and step-down decisions.
- Bumped integration version metadata to `1.5.9`.

## Fixed

- Improved traceability for cases where Solar Surplus appears not to reduce charging speed during grid import.

## Tests

- `python3 -m py_compile custom_components/ev_smart_charger/solar_surplus.py tests/test_solar_surplus.py`
- Result: passed

## Notes

- This release introduces a new user-facing charging safeguard for Night Smart Charge.
- The enhanced Solar Surplus diagnostics are intended to capture the exact decision path during future grid import events.
