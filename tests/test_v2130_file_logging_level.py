"""Tests for v2.13.0 — file logging produced an empty file (issue #59).

The daily file handler is attached to the ``custom_components.ev_smart_charger``
package logger, but a handler only ever receives records the logger itself lets
through. On installs whose ``logger:`` block sets ``default: warning`` (or
stricter) every EVSC INFO record was dropped at the logger, so switching the
toggle ON created the file and then wrote nothing to it — indistinguishable from
a broken feature.

Enabling file logging now lowers the package logger to INFO and restores the
previous explicit level on disable.
"""
import logging

import pytest

from custom_components.ev_smart_charger.utils.logging_helper import EVSCLogger

PACKAGE_LOGGER = logging.getLogger("custom_components.ev_smart_charger")


@pytest.fixture(autouse=True)
def _restore_logging_state():
    """Never leak handler/level state into other tests."""
    previous_level = PACKAGE_LOGGER.level
    yield
    EVSCLogger.disable_global_file_logging()
    PACKAGE_LOGGER.setLevel(previous_level)


def test_enabling_lowers_package_level_to_info(tmp_path):
    """A WARNING-only install must still get INFO records in the daily file."""
    PACKAGE_LOGGER.setLevel(logging.WARNING)

    EVSCLogger.enable_global_file_logging(str(tmp_path / "2026" / "09" / "07.log"))

    assert PACKAGE_LOGGER.getEffectiveLevel() <= logging.INFO


def test_records_actually_reach_the_file(tmp_path):
    """End-to-end: the reported symptom (empty log file) is gone."""
    PACKAGE_LOGGER.setLevel(logging.WARNING)
    log_file = tmp_path / "2026" / "09" / "07.log"

    EVSCLogger.enable_global_file_logging(str(log_file))
    EVSCLogger("SOLAR SURPLUS").info("periodic check")
    for handler in PACKAGE_LOGGER.handlers:
        handler.flush()

    assert "periodic check" in log_file.read_text(encoding="utf-8")


def test_disabling_restores_previous_level(tmp_path):
    """The user's own logger: configuration is not permanently overwritten."""
    PACKAGE_LOGGER.setLevel(logging.WARNING)

    EVSCLogger.enable_global_file_logging(str(tmp_path / "a.log"))
    EVSCLogger.disable_global_file_logging()

    assert PACKAGE_LOGGER.level == logging.WARNING


def test_explicit_debug_level_is_not_raised(tmp_path):
    """A user who asked for DEBUG keeps DEBUG in the file (never narrowed)."""
    PACKAGE_LOGGER.setLevel(logging.DEBUG)

    EVSCLogger.enable_global_file_logging(str(tmp_path / "a.log"))

    assert PACKAGE_LOGGER.level == logging.DEBUG


def test_repeated_enable_does_not_corrupt_saved_level(tmp_path):
    """Daily rotation re-enables with a new path; the saved level must survive."""
    PACKAGE_LOGGER.setLevel(logging.WARNING)

    EVSCLogger.enable_global_file_logging(str(tmp_path / "07.log"))
    EVSCLogger.enable_global_file_logging(str(tmp_path / "08.log"))  # midnight
    EVSCLogger.disable_global_file_logging()

    assert PACKAGE_LOGGER.level == logging.WARNING


def test_effective_level_is_exposed_for_diagnostics(tmp_path):
    """The log-file-path sensor surfaces this so an empty file is diagnosable."""
    PACKAGE_LOGGER.setLevel(logging.WARNING)
    assert EVSCLogger.get_effective_level_name() == "WARNING"

    EVSCLogger.enable_global_file_logging(str(tmp_path / "a.log"))
    assert EVSCLogger.get_effective_level_name() == "INFO"
