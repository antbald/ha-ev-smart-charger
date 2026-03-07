# Release v1.5.3

## Fixes

- Fixed Night Smart Charge battery-mode behavior when `car_ready=OFF` and grid import persists.
- Night sessions that start from home battery now stop terminally instead of continuing to import from the public grid on non-urgent days.
- Added a dedicated terminal stop reason for persistent grid import with `car_ready=OFF`.

## Tests

- `./.venv/bin/python -m pytest -q tests/test_night_smart_charge.py -k 'persistent_grid_import_when_car_ready_off or monitor_battery_stops_terminal_when_car_ready_off'`
- Result: `2 passed`

## Notes

- Added a regression test covering the Saturday/non-urgent scenario with persistent grid import during battery mode.
