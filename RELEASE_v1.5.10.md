# Release v1.5.10

## Changed

- Solar Surplus no longer treats the EV daily target as a daytime hard maximum during periodic checks.
- When both EV and Home minimum SOC targets are reached (`PRIORITY_EV_FREE`), Solar Surplus now allows opportunistic EV charging from real solar surplus instead of forcing a stop.
- Preserved the existing `PRIORITY_HOME` protection path so the EV still yields when the home battery is below its minimum target.
- Bumped integration version metadata to `1.5.10`.

## Fixed

- Fixed a daytime Solar Surplus bug where the charger could stop immediately after plug-in even though the home battery minimum had already been satisfied and solar production was available.
- Fixed the mismatch between the documented charging policy and the Solar Surplus runtime behavior once both minimum SOC targets were met.

## Tests

- `./.venv/bin/python -m pytest -q tests/test_solar_surplus.py`
- Result: passed
- `./.venv/bin/python -m pytest -q`
- Result: passed (`138 passed`)

## Notes

- This release restores the intended 3-step daytime policy: reach EV minimum, then Home minimum, then divert surplus solar production to the EV while connected.
- Night Smart Charge target-stop behavior and sunset handover remain unchanged in this release.
