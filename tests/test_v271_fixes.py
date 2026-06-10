"""Isolated unit tests for the v2.7.1 release.

The behavioural fixes (#49 single-step ramp, #51 dead-band floor, #47/#48 sensor
debounce) live in test_solar_surplus.py where the component fixture exists. This
file covers the standalone logging change.

- issue #50B: EVSCLogger.debug() must carry an emoji prefix like every other
  log level, so DEBUG lines don't break the visual scan of an interleaved log.
"""
from __future__ import annotations

import logging

from custom_components.ev_smart_charger.utils.logging_helper import EVSCLogger


def test_debug_has_trace_emoji_prefix(caplog):
    log = EVSCLogger("UNIT TEST")
    with caplog.at_level(logging.DEBUG):
        log.debug("hello world")
    assert any("🔍" in rec.getMessage() and "hello world" in rec.getMessage()
               for rec in caplog.records)


def test_trace_constant_distinct_from_info():
    # 🔍 must not collide with the INFO emoji set.
    assert EVSCLogger.TRACE == "🔍"
    assert EVSCLogger.TRACE not in {
        EVSCLogger.INFO, EVSCLogger.SUCCESS, EVSCLogger.ACTION,
        EVSCLogger.DECISION, EVSCLogger.SKIP, EVSCLogger.WARNING,
        EVSCLogger.ERROR, EVSCLogger.START, EVSCLogger.STOP,
    }
