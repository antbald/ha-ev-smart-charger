# Release v1.5.6

## Fixed

- Fixed the integration options/config flow to use Home Assistant's config-entry-aware options flow base class.
- This resolves the `500 Internal Server Error` that could appear when opening the integration settings to change configured entities such as sensors.

## Changed

- Added regression coverage for the real Home Assistant options flow manager path.
- Added regression coverage for the native reconfigure flow manager path.
- Kept compatibility coverage for legacy entries that still store `sensor.*` as the charger current entity.
- Bumped integration version metadata to `1.5.6`.

## Tests

- `./.venv/bin/pytest -q tests/test_config_flow.py tests/test_config_flow_extended.py`
- Result: `14 passed`

## Notes

- The functional behavior of the charging logic is unchanged in this release.
- This is a compatibility and stability fix for the configuration UI flow.
