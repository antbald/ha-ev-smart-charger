"""Isolated unit tests for the v2.7.0 bug-fix release.

Covers the issues whose fix is easiest to verify without the fragile full-HA
harness. The behavioural fixes (#44 PRIORITY_HOME guard, #45 night-charge enabled
ordering, #46 stability-timer reset) live in test_solar_surplus.py /
test_night_smart_charge.py where the component fixtures already exist.

- issue #43: no Jinja `{{ }}` left in any config-flow data_description (HA's
  translation engine treats it as an interpolation placeholder → MALFORMED_ARGUMENT).
"""
from __future__ import annotations

import json
import os

import pytest

_HERE = os.path.dirname(__file__)
_COMP = os.path.join(_HERE, "..", "custom_components", "ev_smart_charger")
_FILES = [
    os.path.join(_COMP, "strings.json"),
    os.path.join(_COMP, "translations", "en.json"),
    os.path.join(_COMP, "translations", "it.json"),
    os.path.join(_COMP, "translations", "nl.json"),
]


@pytest.mark.parametrize("path", _FILES)
def test_translation_files_are_valid_json(path):
    with open(path, encoding="utf-8") as fh:
        json.load(fh)


def _iter_data_descriptions(obj):
    """Yield every data_description string anywhere in the translation tree."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "data_description" and isinstance(value, dict):
                for text in value.values():
                    if isinstance(text, str):
                        yield text
            else:
                yield from _iter_data_descriptions(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_data_descriptions(item)


@pytest.mark.parametrize("path", _FILES)
def test_no_jinja_placeholder_in_data_descriptions(path):
    """issue #43: a raw `{{ ... }}` in a data_description makes HA throw
    MALFORMED_ARGUMENT and replace the whole help text with the error label."""
    with open(path, encoding="utf-8") as fh:
        tree = json.load(fh)
    offenders = [t for t in _iter_data_descriptions(tree) if "{{" in t or "}}" in t]
    assert not offenders, f"Jinja placeholder left in {path}: {offenders}"
