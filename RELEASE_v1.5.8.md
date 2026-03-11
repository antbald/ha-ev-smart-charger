# Release v1.5.8

## Fixed

- Fixed stale coordinator ownership visibility across Smart Charger Blocker, Night Smart Charge, and Solar Surplus.
- Fixed blocker periodic enforcement re-check so it safely releases stale ownership and handles enforcement timeout checks without naive/aware datetime crashes.
- Fixed diagnostic reporting so `sensor.evsc_diagnostic` does not advertise a file path when file logging is disabled.

## Changed

- Added unified diagnostic publishing through the new runtime `DiagnosticManager`.
- Added `switch.evsc_trace_logging_enabled` for on-demand trace logging.
- Expanded coordinator snapshots, recent history, and denial/release reporting.
- Standardized the maintainer test entrypoint with `make test`, which runs the suite via the repo-local `.venv`.
- Bumped integration version metadata to `1.5.8`.

## Tests

- `make test`
- Result: `130 passed, 2 warnings`

## Notes

- This release is primarily about observability and ownership recovery, not a user-facing charging-strategy change.
- The new diagnostics are intended to make future charging bugs attributable to a concrete decision path instead of ambiguous log fragments.
