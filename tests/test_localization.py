"""Localization coverage for EV Smart Charger."""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from custom_components.ev_smart_charger.utils.mobile_notification_service import (
    MobileNotificationService,
)

ROOT = Path(__file__).resolve().parents[1]
STRINGS_PATH = ROOT / "custom_components" / "ev_smart_charger" / "strings.json"
TRANSLATIONS_DIR = ROOT / "custom_components" / "ev_smart_charger" / "translations"
FRONTEND_PATH = (
    ROOT
    / "custom_components"
    / "ev_smart_charger"
    / "frontend"
    / "ev-smart-charger-dashboard.js"
)
RUNTIME_TEXT_FILES = [
    ROOT / "custom_components" / "ev_smart_charger" / "automations.py",
    ROOT / "custom_components" / "ev_smart_charger" / "boost_charge.py",
    ROOT / "custom_components" / "ev_smart_charger" / "night_smart_charge.py",
    ROOT
    / "custom_components"
    / "ev_smart_charger"
    / "utils"
    / "mobile_notification_service.py",
]
FORBIDDEN_ITALIAN_RUNTIME_SNIPPETS = (
    "Ricarica EV",
    "Previsione solare",
    "Impossibile avviare",
    "Boost disattivato manualmente",
    "Ritorno alla modalita",
    "SOC EV non disponibile",
    "Target SOC raggiunto",
)


def _flatten_keys(node: object, prefix: str = "") -> set[str]:
    """Return a flat set of dotted keys for nested JSON-like objects."""
    if isinstance(node, dict):
        keys: set[str] = set()
        for key, value in node.items():
            next_prefix = f"{prefix}.{key}" if prefix else key
            keys.add(next_prefix)
            keys.update(_flatten_keys(value, next_prefix))
        return keys
    return set()


def _load_json(path: Path) -> dict:
    """Load a JSON file from disk."""
    return json.loads(path.read_text())


def _load_frontend_locales() -> dict[str, dict[str, str]]:
    """Extract the frontend locale object from the dashboard source."""
    source = FRONTEND_PATH.read_text()
    match = re.search(r"const FRONTEND_LOCALES = (\{.*?\n\});", source, re.DOTALL)
    assert match is not None, "FRONTEND_LOCALES constant not found"
    return json.loads(match.group(1))


def test_translation_files_keep_key_parity() -> None:
    """strings.json and shipped locales must expose the same HA translation keys."""
    base_keys = _flatten_keys(_load_json(STRINGS_PATH))
    for locale in ("en", "it", "nl"):
        locale_keys = _flatten_keys(_load_json(TRANSLATIONS_DIR / f"{locale}.json"))
        assert locale_keys == base_keys, f"{locale}.json is out of sync with strings.json"


@pytest.mark.parametrize(
    ("language", "expected_fragment"),
    [
        ("en", "EV charging started via Grid"),
        ("nl", "EV-laden gestart via Net"),
        ("fr", "EV charging started via Grid"),
    ],
)
async def test_mobile_notifications_follow_hass_language(hass, language, expected_fragment):
    """Runtime mobile notification copy follows the HA language with English fallback."""
    hass.config.language = language
    hass.services.async_call = AsyncMock()

    service = MobileNotificationService(
        hass,
        notify_services=["mobile_app_test_phone"],
        entry_id="entry_123",
    )

    await service.send_night_charge_notification(
        mode="grid",
        reason="Reason text",
        amperage=16,
        forecast=12.5,
    )

    notify_call = hass.services.async_call.await_args
    assert notify_call.args[0] == "notify"
    assert notify_call.args[1] == "mobile_app_test_phone"
    assert expected_fragment in notify_call.args[2]["message"]
    assert notify_call.args[2]["title"] == "BORGO"


def test_frontend_locale_dictionary_has_parity_and_english_fallback() -> None:
    """Frontend dashboard locales must stay aligned and keep English fallback."""
    source = FRONTEND_PATH.read_text()
    assert 'const DEFAULT_LOCALE = "en";' in source

    locales = _load_frontend_locales()
    english_keys = set(locales["en"])
    assert english_keys, "English frontend locale is empty"
    for locale in ("it", "nl"):
        assert set(locales[locale]) == english_keys, f"Frontend locale {locale} is out of sync"


def test_runtime_modules_do_not_reintroduce_hardcoded_italian_user_copy() -> None:
    """User-facing runtime modules should route localized copy through the i18n layer."""
    for path in RUNTIME_TEXT_FILES:
        source = path.read_text()
        for snippet in FORBIDDEN_ITALIAN_RUNTIME_SNIPPETS:
            assert snippet not in source, f"Found hardcoded Italian runtime copy in {path.name}: {snippet}"
