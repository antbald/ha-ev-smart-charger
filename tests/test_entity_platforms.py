"""Platform entity coverage for EV Smart Charger."""
from __future__ import annotations

from datetime import datetime, time
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import types

import pytest
from homeassistant.core import State
from homeassistant.helpers.entity import EntityCategory
if "homeassistant.components.time" not in sys.modules:
    time_module = types.ModuleType("homeassistant.components.time")

    class TimeEntity:
        """Test stub for Home Assistant TimeEntity on older cores."""

    time_module.TimeEntity = TimeEntity
    sys.modules["homeassistant.components.time"] = time_module

from custom_components.ev_smart_charger import number as number_platform
from custom_components.ev_smart_charger import select as select_platform
from custom_components.ev_smart_charger import sensor as sensor_platform
from custom_components.ev_smart_charger import switch as switch_platform
from custom_components.ev_smart_charger import time as time_platform
from custom_components.ev_smart_charger.const import (
    CHARGING_PROFILES,
    CONF_SOC_CAR,
    DEFAULT_CAR_READY_TIME,
    LEGACY_CHARGING_PROFILES,
    PROFILE_MANUAL,
)
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData


def _mock_entry(runtime_data: EVSCRuntimeData) -> SimpleNamespace:
    """Create a minimal config-entry-like object for platform setup."""
    return SimpleNamespace(
        entry_id="entry_123",
        runtime_data=runtime_data,
        data={CONF_SOC_CAR: "sensor.cloud_ev_soc"},
    )


def _collector():
    """Collect entities from async_add_entities callbacks."""
    entities = []

    def _add_entities(new_entities, *_args):
        entities.extend(new_entities)

    return entities, _add_entities


async def _attach_entity(entity, hass, last_state: State | None = None) -> None:
    """Attach an entity to hass and patch restore-state access."""
    entity.hass = hass
    entity.async_get_last_state = AsyncMock(return_value=last_state)
    entity.async_write_ha_state = Mock()
    await entity.async_added_to_hass()


@pytest.fixture
def runtime_data() -> EVSCRuntimeData:
    """Create runtime data for platform entity tests."""
    return EVSCRuntimeData(config={}, expected_entity_count=100)


async def test_number_platform_setup_and_restore(hass, runtime_data):
    """Number platform exposes stable ids, config metadata, and restore logic."""
    entry = _mock_entry(runtime_data)
    entities, async_add_entities = _collector()

    await number_platform.async_setup_entry(hass, entry, async_add_entities)

    assert len(entities) == 24

    entity = entities[0]
    assert entity.entity_id == "number.ev_smart_charger_entry_123_evsc_check_interval"
    assert entity.unique_id == "ev_smart_charger_entry_123_evsc_check_interval"
    assert entity.entity_category is EntityCategory.CONFIG
    assert entity.has_entity_name is True
    assert entity.translation_key == "evsc_check_interval"
    assert entity.device_info["identifiers"] == {("ev_smart_charger", "entry_123")}

    await _attach_entity(
        entity,
        hass,
        State(entity.entity_id, "15"),
    )

    assert entity.native_value == 15.0
    assert runtime_data.get_entity_id("evsc_check_interval") == entity.entity_id
    assert runtime_data.get_entity("evsc_check_interval") is entity

    await entity.async_set_native_value(22)
    assert entity.native_value == 22

    await entity.async_set_native_value(1000)
    assert entity.native_value == 22


async def test_switch_platform_setup_restore_and_toggle(hass, runtime_data):
    """Switch platform preserves explicit ids, config category, and toggle behavior."""
    entry = _mock_entry(runtime_data)
    entities, async_add_entities = _collector()

    await switch_platform.async_setup_entry(hass, entry, async_add_entities)

    assert len(entities) == 17

    restored_switch = next(
        entity for entity in entities if entity.entity_id.endswith("evsc_forza_ricarica")
    )
    default_on_switch = next(
        entity
        for entity in entities
        if entity.entity_id.endswith("evsc_notify_smart_blocker_enabled")
    )

    await _attach_entity(
        restored_switch,
        hass,
        State(restored_switch.entity_id, "on"),
    )
    await _attach_entity(default_on_switch, hass, None)

    assert restored_switch.unique_id == "ev_smart_charger_entry_123_evsc_forza_ricarica"
    assert restored_switch.entity_category is EntityCategory.CONFIG
    assert restored_switch.translation_key == "evsc_forza_ricarica"
    assert restored_switch.is_on is True
    assert default_on_switch.is_on is True

    await restored_switch.async_turn_off()
    assert restored_switch.is_on is False
    await restored_switch.async_turn_on()
    assert restored_switch.is_on is True


async def test_select_platform_coerces_legacy_profiles_and_registers_runtime(
    hass,
    runtime_data,
):
    """Select platform keeps implemented profiles only and coerces legacy restore data."""
    entry = _mock_entry(runtime_data)
    entities, async_add_entities = _collector()

    await select_platform.async_setup_entry(hass, entry, async_add_entities)

    assert len(entities) == 1

    entity = entities[0]
    assert entity.options == CHARGING_PROFILES
    assert entity.entity_id == "select.ev_smart_charger_entry_123_evsc_charging_profile"
    assert entity.entity_category is EntityCategory.CONFIG
    assert entity.translation_key == "evsc_charging_profile"

    await _attach_entity(
        entity,
        hass,
        State(entity.entity_id, LEGACY_CHARGING_PROFILES[0]),
    )

    assert entity.current_option == PROFILE_MANUAL
    assert runtime_data.get_entity_id("evsc_charging_profile") == entity.entity_id

    await entity.async_select_option(CHARGING_PROFILES[-1])
    assert entity.current_option == CHARGING_PROFILES[-1]


async def test_time_platform_restore_invalid_restore_and_set_value(hass, runtime_data):
    """Time platform restores valid values and falls back to defaults on invalid state."""
    entry = _mock_entry(runtime_data)
    entities, async_add_entities = _collector()

    await time_platform.async_setup_entry(hass, entry, async_add_entities)

    assert len(entities) == 2

    restored_time = entities[0]
    default_time = entities[1]

    await _attach_entity(
        restored_time,
        hass,
        State(restored_time.entity_id, "07:45:30"),
    )
    await _attach_entity(
        default_time,
        hass,
        State(default_time.entity_id, "not:valid:time"),
    )

    assert restored_time.entity_category is EntityCategory.CONFIG
    assert restored_time.translation_key == "evsc_night_charge_time"
    assert restored_time.native_value == time(7, 45, 30)
    car_ready_parts = [int(part) for part in DEFAULT_CAR_READY_TIME.split(":")]
    assert default_time.native_value == time(*car_ready_parts)

    await restored_time.async_set_value(time(9, 15, 0))
    assert restored_time.native_value == time(9, 15, 0)


async def test_sensor_platform_setup_publish_restore_and_log_manager(hass, runtime_data):
    """Sensor platform exposes diagnostic metadata, restore behavior, and publish helpers."""
    runtime_data.log_manager = Mock(
        get_log_file_path=Mock(return_value="/tmp/evsc.log"),
        get_logs_directory=Mock(return_value="/tmp"),
    )
    entry = _mock_entry(runtime_data)
    entities, async_add_entities = _collector()

    await sensor_platform.async_setup_entry(hass, entry, async_add_entities)

    assert len(entities) == 7

    diagnostic = next(entity for entity in entities if entity.entity_id.endswith("evsc_diagnostic"))
    priority = next(
        entity for entity in entities if entity.entity_id.endswith("evsc_priority_daily_state")
    )
    solar_surplus = next(
        entity
        for entity in entities
        if entity.entity_id.endswith("evsc_solar_surplus_diagnostic")
    )
    log_path = next(
        entity for entity in entities if entity.entity_id.endswith("evsc_log_file_path")
    )
    today_ev = next(entity for entity in entities if entity.entity_id.endswith("evsc_today_ev_target"))
    today_home = next(
        entity for entity in entities if entity.entity_id.endswith("evsc_today_home_target")
    )
    cached_soc = next(entity for entity in entities if entity.entity_id.endswith("evsc_cached_ev_soc"))

    await _attach_entity(
        diagnostic,
        hass,
        State(diagnostic.entity_id, "Ready"),
    )
    await _attach_entity(
        priority,
        hass,
        State(priority.entity_id, "EV", {"reason": "Below target"}),
    )
    await _attach_entity(
        solar_surplus,
        hass,
        State(solar_surplus.entity_id, "Stable surplus", {"watts": 2400}),
    )
    await _attach_entity(
        today_ev,
        hass,
        State(today_ev.entity_id, "80", {"day": "Friday"}),
    )
    await _attach_entity(
        today_home,
        hass,
        State(today_home.entity_id, "55", {"day": "Friday"}),
    )
    await _attach_entity(
        cached_soc,
        hass,
        State(
            cached_soc.entity_id,
            "64",
            {
                "source_entity": "sensor.cloud_ev_soc",
                "last_valid_update": "2026-03-06T10:00:00+00:00",
                "is_cached": True,
            },
        ),
    )
    log_path.hass = hass
    await log_path.async_added_to_hass()

    assert diagnostic.entity_category is EntityCategory.DIAGNOSTIC
    assert diagnostic.translation_key == "evsc_diagnostic"
    assert diagnostic.native_value == "Ready"
    assert priority.extra_state_attributes == {"reason": "Below target"}
    assert today_ev.native_value == 80.0
    assert cached_soc.native_value == 64.0
    assert cached_soc.extra_state_attributes["is_cached"] is True
    assert log_path.native_value == "/tmp/evsc.log"
    assert log_path.extra_state_attributes["logs_directory"] == "/tmp"

    await priority.async_publish("HOME", {"reason": "House battery low"})
    assert priority.native_value == "HOME"
    assert priority.extra_state_attributes == {"reason": "House battery low"}

    now = datetime(2026, 3, 6, 12, 30, 0)
    await cached_soc.async_publish_cache(
        72.0,
        last_valid_update=now,
        is_cached=False,
        cache_age_seconds=0,
    )
    assert cached_soc.native_value == 72.0
    assert cached_soc.extra_state_attributes["last_valid_update"] == now.isoformat()
    assert cached_soc.extra_state_attributes["is_cached"] is False

    runtime_keys = {
        "evsc_diagnostic",
        "evsc_priority_daily_state",
        "evsc_solar_surplus_diagnostic",
        "evsc_log_file_path",
        "evsc_today_ev_target",
        "evsc_today_home_target",
        "evsc_cached_ev_soc",
    }
    assert runtime_keys.issubset(runtime_data.entity_ids_by_key)
