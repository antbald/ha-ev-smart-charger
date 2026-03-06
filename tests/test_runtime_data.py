"""Tests for EVSC runtime data helpers."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_smart_charger.const import DOMAIN
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData, get_runtime_data


def test_register_entity_sets_event_when_expected_count_reached() -> None:
    """Registration barrier is released only when all expected entities are registered."""
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=2)

    runtime_data.register_entity("one", "sensor.one", object())
    assert runtime_data.registered_entity_count == 1
    assert runtime_data.registration_event.is_set() is False

    entity = object()
    runtime_data.register_entity("two", "sensor.two", entity)
    assert runtime_data.registered_entity_count == 2
    assert runtime_data.registration_event.is_set() is True
    assert runtime_data.get_entity_id("two") == "sensor.two"
    assert runtime_data.get_entity("two") is entity


def test_register_entity_does_not_increment_for_duplicate_key() -> None:
    """Replacing an entity registration keeps the count stable."""
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=2)

    runtime_data.register_entity("one", "sensor.one", object())
    runtime_data.register_entity("one", "sensor.one_replaced", object())

    assert runtime_data.registered_entity_count == 1
    assert runtime_data.get_entity_id("one") == "sensor.one_replaced"


def test_get_runtime_data_returns_typed_runtime_data() -> None:
    """Typed helper returns the runtime data stored on the config entry."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    runtime_data = EVSCRuntimeData(config={}, expected_entity_count=1)
    entry.runtime_data = runtime_data

    assert get_runtime_data(entry) is runtime_data


def test_get_runtime_data_raises_for_missing_runtime_data() -> None:
    """Typed helper rejects entries without EVSC runtime data."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.runtime_data = None

    with pytest.raises(RuntimeError, match="runtime data not initialized"):
        get_runtime_data(entry)
