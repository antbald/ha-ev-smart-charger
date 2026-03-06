# Testing Guide for EV Smart Charger

## Quick Start

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests
PYTHONPATH=. pytest tests/ -vv

# Run tests with coverage
PYTHONPATH=. pytest tests/ -vv --cov=custom_components/ev_smart_charger

# Run specific test file
PYTHONPATH=. pytest tests/test_night_smart_charge.py -vv

# Run specific test
PYTHONPATH=. pytest tests/test_night_smart_charge.py::test_is_in_active_window_case1 -vv
```

## Current Test Status

See **[TEST_PROGRESS.md](./TEST_PROGRESS.md)** for detailed tracking of:
- ✅ Completed tests
- 📋 Test patterns and gotchas
- 🎯 Next tests to implement
- 📊 Coverage goals

## Test Files

| File | Tests | Coverage | Status |
|------|-------|----------|--------|
| `test_night_smart_charge.py` | 6 | 44% | ✅ Passing |
| `test_priority_balancer.py` | 0 | 16% | 📝 To Do |
| `test_charger_controller.py` | 0 | 16% | 📝 To Do |
| `test_solar_surplus.py` | 0 | 7% | 📝 To Do |

## Key Testing Patterns

### Async Testing
```python
import pytest

@pytest.mark.asyncio
async def test_something(hass):
    # All async tests must use async def
    result = await some_async_function()
    assert result == expected
```

### Mocking Home Assistant States
```python
# Set entity state (values are always strings)
hass.states.async_set("sensor.example", "42")

# Get state
state = hass.states.get("sensor.example")
assert state.state == "42"
```

### Mocking Async Methods
```python
from unittest.mock import AsyncMock
import asyncio

# Method 1: AsyncMock
obj.method = AsyncMock(return_value=42)

# Method 2: Future (for MagicMock compatibility)
future = asyncio.Future()
future.set_result(42)
obj.method.return_value = future
```

### Time Mocking
```python
from unittest.mock import patch
from datetime import datetime

with patch("module.dt_util.now", return_value=datetime(2023, 1, 1, 12, 0, 0)):
    # Code that uses dt_util.now() will get mocked time
    result = await function_that_uses_time()
```

## Common Issues

### 1. TypeError: object int can't be used in 'await' expression
**Solution:** Use `AsyncMock` or `asyncio.Future` for async methods
```python
# Wrong
obj.async_method.return_value = 42

# Right
obj.async_method = AsyncMock(return_value=42)
```

### 2. AttributeError: module has no attribute 'X'
**Solution:** Check imports and ensure function exists in the module

### 3. Tests passing but coverage low
**Solution:** Add tests for edge cases, error paths, and different conditions

## Fixtures

See `conftest.py` for available fixtures:
- `hass` - Home Assistant instance
- `mock_priority_balancer` - Mocked PriorityBalancer
- `mock_charger_controller` - Mocked ChargerController
- `night_charge` - Configured NightSmartCharge instance

## Contributing Tests

1. **Check TEST_PROGRESS.md** for what needs testing
2. **Follow existing test patterns** in the test files
3. **Update TEST_PROGRESS.md** when adding tests
4. **Ensure tests are isolated** and don't depend on each other
5. **Add descriptive docstrings** to each test function

## Coverage Reports

Generate HTML coverage report:
```bash
PYTHONPATH=. pytest tests/ --cov=custom_components/ev_smart_charger --cov-report=html
open htmlcov/index.html
```

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Home Assistant testing](https://developers.home-assistant.io/docs/development_testing)
- [Python unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
