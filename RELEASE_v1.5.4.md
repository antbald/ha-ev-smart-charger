# Release v1.5.4

## Added

- Added full runtime localization support driven by the active Home Assistant language.
- Added Dutch (`nl`) translation coverage for the integration and dashboard.
- Added a Dutch user guide under `docs/README.nl.md`.

## Changed

- Home Assistant helper entity names are now translation-backed through `strings.json`.
- Mobile notifications and persistent Boost/Smart Blocker notifications now use localized copy with English fallback.
- The Lovelace dashboard now localizes labels and profile names using `hass.language`.

## Tests

- `./.venv/bin/python -m pytest -q tests/test_localization.py tests/test_entity_platforms.py`
- `./.venv/bin/python -m pytest -q tests/test_boost_charge.py tests/test_smart_charger_blocker.py`
- Result: `22 passed`

## Notes

- `strings.json` is now the canonical English source for Home Assistant translation-surface copy.
- English, Italian, and Dutch translation files are kept in parity by test coverage.
