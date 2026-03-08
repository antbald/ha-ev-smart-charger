# Release v1.5.5

## Fixed

- Fixed Night Smart Charge so `car_ready=OFF` can no longer start in GRID mode during the overnight evaluation.
- Night charging with `car_ready=OFF` is now battery-only: it uses the home battery until `EVSC Home Battery Min SOC`, then stops and waits for daytime Solar Surplus.
- Battery-mode notifications now report the battery-only policy explicitly when `car_ready=OFF`, instead of referring to solar forecast sufficiency.

## Changed

- Updated the Night Smart Charge decision path to treat `car_ready=OFF` as a hard "no overnight grid" rule.
- Clarified README documentation for `car_ready` behavior and weekend/off scenarios.
- Bumped integration version metadata to `1.5.5`.

## Tests

- `./.venv/bin/pytest -q tests/test_night_smart_charge.py`
- Result: `16 passed`

## Notes

- `car_ready=TRUE` behavior is unchanged: the EV may still use battery or grid as needed to reach target before `Car Ready Time`.
- This release aligns runtime behavior, tests, and documentation for overnight charging semantics.
