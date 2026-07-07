# Release v2.7.4

## Changed

- EV charging Live Activities / Live Updates are now opt-in instead of automatic.
- Added `evsc_live_activities_enabled`, default OFF, to control Live Activities from the generated dashboard.
- The normal charging monitor clears the existing `evsc_ev_charging` activity once when the toggle is turned OFF.
- Bumped integration version metadata to `2.7.4`.

## Documentation

- Updated README, frontend dashboard docs, and maintainer docs for the new default-OFF behavior.

## Tests

- `./.venv/bin/python -m pytest -q`
