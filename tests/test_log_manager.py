"""Tests for LogManager global file logging behavior."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from pathlib import Path

import pytest

from custom_components.ev_smart_charger.const import HELPER_ENABLE_FILE_LOGGING_SUFFIX
from custom_components.ev_smart_charger.log_manager import LogManager
from custom_components.ev_smart_charger.utils.logging_helper import EVSCLogger


@pytest.fixture(autouse=True)
def reset_global_file_logging():
    """Ensure no global file handler leaks between tests."""
    EVSCLogger.disable_global_file_logging()
    yield
    EVSCLogger.disable_global_file_logging()


def _flush_evsc_file_handlers() -> None:
    logger = logging.getLogger("custom_components.ev_smart_charger.utils.logging_helper")
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()


async def test_log_manager_uses_single_global_file_handler(hass):
    """Enabling file logging must attach exactly one file handler."""
    toggle_entity = f"switch.test_{HELPER_ENABLE_FILE_LOGGING_SUFFIX}"
    hass.states.async_set(toggle_entity, "on")

    manager = LogManager(hass, "test_entry")
    components = [EVSCLogger("A"), EVSCLogger("B"), EVSCLogger("C")]
    await manager.async_setup(components)

    assert EVSCLogger.is_global_file_logging_enabled() is True
    assert EVSCLogger.get_global_file_handler_count() == 1

    marker = f"SINGLE_HANDLER_CHECK_{datetime.now().timestamp()}"
    components[0].info(marker)
    _flush_evsc_file_handlers()

    log_path = EVSCLogger.get_global_log_file_path()
    assert log_path is not None
    log_contents = Path(log_path).read_text(encoding="utf-8")
    assert log_contents.count(marker) == 1

    await manager.async_remove()


async def test_log_manager_toggle_on_is_idempotent(hass):
    """Repeated ON application must not create extra handlers."""
    toggle_entity = f"switch.test_{HELPER_ENABLE_FILE_LOGGING_SUFFIX}"
    hass.states.async_set(toggle_entity, "on")

    manager = LogManager(hass, "test_entry")
    components = [EVSCLogger("A"), EVSCLogger("B")]
    await manager.async_setup(components)

    await manager._apply_logging_state()
    await manager._apply_logging_state()

    assert EVSCLogger.get_global_file_handler_count() == 1
    await manager.async_remove()


async def test_log_manager_midnight_rotation_keeps_single_handler(hass):
    """Midnight rotation should switch file path without duplicating handlers."""
    toggle_entity = f"switch.test_{HELPER_ENABLE_FILE_LOGGING_SUFFIX}"
    hass.states.async_set(toggle_entity, "on")

    manager = LogManager(hass, "test_entry")
    components = [EVSCLogger("A"), EVSCLogger("B")]
    await manager.async_setup(components)

    old_path = EVSCLogger.get_global_log_file_path()
    assert old_path is not None

    tomorrow = datetime.now() + timedelta(days=1)
    midnight_tomorrow = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0)
    await manager._handle_midnight(midnight_tomorrow)

    new_path = EVSCLogger.get_global_log_file_path()
    assert new_path is not None
    assert new_path != old_path
    assert EVSCLogger.get_global_file_handler_count() == 1

    await manager.async_remove()


async def test_log_manager_toggle_off_disables_global_handler(hass):
    """Turning logging OFF must remove the global file handler."""
    toggle_entity = f"switch.test_{HELPER_ENABLE_FILE_LOGGING_SUFFIX}"
    hass.states.async_set(toggle_entity, "on")

    manager = LogManager(hass, "test_entry")
    components = [EVSCLogger("A")]
    await manager.async_setup(components)
    assert EVSCLogger.is_global_file_logging_enabled() is True

    hass.states.async_set(toggle_entity, "off")
    await manager._apply_logging_state()

    assert EVSCLogger.is_global_file_logging_enabled() is False
    assert EVSCLogger.get_global_file_handler_count() == 0
    await manager.async_remove()
