# Release v2.7.3

## Added

- Added EV charging Live Activities / Live Updates for configured `notify.mobile_app_*` services.
- Added live updates for Boost Charge, Night Smart Charge battery/grid sessions, Solar Surplus, Force Charge, and normal charging detected by the shared charging-state SSOT.
- Added a runtime `EVChargingLiveActivityMonitor` that polls normal charging every 60 seconds and closes the live notification only after two inactive ticks.
- Added Live Activity payload tests and normal-charging monitor tests.

## Changed

- Mobile notification payloads now support the Companion App `live_update` fields: SOC progress, target, state, charging speed, colors, icon, and dashboard tap target.
- Bumped integration version metadata to `2.7.3`.
- Updated README and maintainer docs for Live Activity behavior and lifecycle.

## Notes

- No new helper entities or config-flow fields are introduced.
- The feature is active by default when mobile notify services are configured.
- Boost Charge and Night Smart Charge own the Live Activity while active; the normal monitor skips them and resumes on the next tick if charging continues.
- Updates are intentionally throttled to avoid exhausting the iOS Live Activity push budget.

## Tests

- `./.venv/bin/python -m pytest -q`
- Result: passed (`244 passed`)
