"""Auto-bootstrap a ready-to-go Lovelace dashboard for EV Smart Charger.

This module wires the bundled `ev-smart-charger-dashboard.js` custom card into
Home Assistant with zero user action:

1. Registers the JS module as a Lovelace `resource` (so the custom element is
   loaded by the frontend).
2. Creates a dedicated storage-mode Lovelace dashboard that shows up in the
   sidebar as "EV Smart Charger".
3. Pre-populates the card config with the lowercased `entity_prefix` and every
   user-mapped sensor pulled directly from the config entry data, so the user
   never has to type a single YAML line.

Lovelace internals (`hass.data["lovelace"]`) are technically not a public API,
but they have been stable for years. All access goes through defensive helpers
that log a warning and degrade gracefully if Home Assistant runs Lovelace in
YAML mode or the API surface changes.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

try:  # pragma: no cover - import guarded across HA versions
    from homeassistant.components.lovelace.const import (
        CONFIG_STORAGE_VERSION_MAJOR,
        CONFIG_STORAGE_VERSION_MINOR,
    )
except ImportError:  # pragma: no cover
    CONFIG_STORAGE_VERSION_MAJOR = 1
    CONFIG_STORAGE_VERSION_MINOR = 1

from .const import (
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_FV_PRODUCTION,
    CONF_GRID_IMPORT,
    CONF_HOME_CONSUMPTION,
    CONF_PV_FORECAST,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    DASHBOARD_ICON,
    DASHBOARD_RESOURCE_KEY,
    DASHBOARD_TITLE,
    DASHBOARD_URL_PATH,
    DOMAIN,
    FRONTEND_CARD_FILENAME,
    FRONTEND_URL_BASE,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

RESOURCE_URL = f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}?v={VERSION}"


def _lovelace_data(hass: HomeAssistant) -> Any:
    """Return the Lovelace data container (or None if Lovelace is YAML-mode)."""
    return hass.data.get("lovelace")


def _get_resources(hass: HomeAssistant) -> Any:
    """Resolve the Lovelace resources collection across HA versions."""
    lovelace = _lovelace_data(hass)
    if lovelace is None:
        return None

    # HA 2024+: `lovelace` is a LovelaceData dataclass with `.resources`.
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        # Older cores expose it via a dict.
        resources = lovelace.get("resources")
    return resources


def _get_dashboards_collection(hass: HomeAssistant) -> Any:
    """Resolve the Lovelace dashboards collection across HA versions."""
    lovelace = _lovelace_data(hass)
    if lovelace is None:
        return None

    # Storage-mode dashboards have a separate collection used for CRUD.
    collection = getattr(lovelace, "dashboards_collection", None)
    if collection is None and isinstance(lovelace, dict):
        collection = lovelace.get("dashboards_collection")
    return collection


def _get_dashboards_map(hass: HomeAssistant) -> Any:
    """Resolve the live Lovelace dashboards mapping (url_path -> renderer)."""
    lovelace = _lovelace_data(hass)
    if lovelace is None:
        return None

    dashboards = getattr(lovelace, "dashboards", None)
    if dashboards is None and isinstance(lovelace, dict):
        dashboards = lovelace.get("dashboards")
    return dashboards


def _build_card_config(entry: ConfigEntry) -> dict[str, Any]:
    """Build the EV Smart Charger card config from the entry data.

    The card expects `entity_prefix` lowercased (since v1.6.23) and accepts a
    list of optional user-mapped entities for the hero metrics row.
    """
    data = entry.data
    entity_prefix = f"{DOMAIN}_{entry.entry_id.lower()}"

    config: dict[str, Any] = {
        "type": f"custom:ev-smart-charger-dashboard",
        "title": DASHBOARD_TITLE,
        "entity_prefix": entity_prefix,
    }

    mapping = {
        "ev_soc_entity": CONF_SOC_CAR,
        "home_battery_soc_entity": CONF_SOC_HOME,
        "solar_power_entity": CONF_FV_PRODUCTION,
        "home_consumption_entity": CONF_HOME_CONSUMPTION,
        "grid_import_entity": CONF_GRID_IMPORT,
        "charger_status_entity": CONF_EV_CHARGER_STATUS,
        "current_entity": CONF_EV_CHARGER_CURRENT,
        "charger_switch_entity": CONF_EV_CHARGER_SWITCH,
        "pv_forecast_entity": CONF_PV_FORECAST,
    }
    for card_key, conf_key in mapping.items():
        value = data.get(conf_key)
        if value:
            config[card_key] = value

    return config


def _build_dashboard_view(entry: ConfigEntry) -> dict[str, Any]:
    """Build the full Lovelace storage config (single view, single card)."""
    return {
        "title": DASHBOARD_TITLE,
        "views": [
            {
                "title": DASHBOARD_TITLE,
                "path": "main",
                "icon": DASHBOARD_ICON,
                "type": "panel",
                "cards": [_build_card_config(entry)],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Lovelace resource registration
# ---------------------------------------------------------------------------


async def async_ensure_resource(hass: HomeAssistant) -> bool:
    """Register the bundled card JS as a Lovelace resource. Idempotent."""
    resources = _get_resources(hass)
    if resources is None:
        _LOGGER.warning(
            "Lovelace resources collection unavailable — running in YAML mode? "
            "Add the resource manually: %s",
            RESOURCE_URL,
        )
        return False

    # Older cores require explicit load before mutating.
    if hasattr(resources, "async_load") and not getattr(resources, "loaded", True):
        try:
            await resources.async_load()
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.warning("Failed to load Lovelace resources: %s", err)
            return False

    items = _resource_items(resources)
    base_url = RESOURCE_URL.split("?")[0]
    existing = next(
        (item for item in items if str(item.get("url", "")).split("?")[0] == base_url),
        None,
    )

    payload = {"res_type": "module", "url": RESOURCE_URL}
    try:
        if existing is None:
            await resources.async_create_item(payload)
            _LOGGER.info("📌 Registered Lovelace resource: %s", RESOURCE_URL)
        elif existing.get("url") != RESOURCE_URL:
            await resources.async_update_item(existing["id"], payload)
            _LOGGER.info("🔄 Updated Lovelace resource: %s", RESOURCE_URL)
        else:
            _LOGGER.debug("Lovelace resource already up to date: %s", RESOURCE_URL)
        return True
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Failed to register Lovelace resource: %s", err)
        return False


async def async_remove_resource_if_unused(hass: HomeAssistant) -> None:
    """Remove the resource only when no EV Smart Charger entry remains."""
    other_entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if not e.disabled_by
    ]
    if other_entries:
        _LOGGER.debug(
            "Keeping Lovelace resource — %d other %s entries still active",
            len(other_entries),
            DOMAIN,
        )
        return

    resources = _get_resources(hass)
    if resources is None:
        return

    items = _resource_items(resources)
    base_url = RESOURCE_URL.split("?")[0]
    existing = next(
        (item for item in items if str(item.get("url", "")).split("?")[0] == base_url),
        None,
    )
    if existing is None:
        return

    try:
        await resources.async_delete_item(existing["id"])
        _LOGGER.info("🗑️  Removed Lovelace resource: %s", RESOURCE_URL)
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Failed to remove Lovelace resource: %s", err)


def _resource_items(resources: Any) -> list[dict[str, Any]]:
    """Return the resource items list across collection implementations."""
    # ResourceStorageCollection exposes `async_items()` (newer) or `.data`.
    if hasattr(resources, "async_items"):
        try:
            return list(resources.async_items())
        except Exception:  # pragma: no cover - defensive
            pass
    data = getattr(resources, "data", None)
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return items
    if isinstance(data, list):
        return data
    return []


# ---------------------------------------------------------------------------
# Lovelace dashboard creation / removal
# ---------------------------------------------------------------------------


async def async_ensure_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create or refresh the auto-generated EV Smart Charger dashboard."""
    await async_ensure_resource(hass)

    collection = _get_dashboards_collection(hass)
    dashboards_map = _get_dashboards_map(hass)
    if collection is None or dashboards_map is None:
        _LOGGER.warning(
            "Lovelace dashboards collection unavailable — auto-dashboard "
            "disabled. Add the resource %s manually and create a panel-mode "
            "dashboard with the `custom:ev-smart-charger-dashboard` card.",
            RESOURCE_URL,
        )
        return False

    existing = _find_existing_dashboard(collection)

    try:
        if existing is None:
            await collection.async_create_item(
                {
                    "url_path": DASHBOARD_URL_PATH,
                    "title": DASHBOARD_TITLE,
                    "icon": DASHBOARD_ICON,
                    "show_in_sidebar": True,
                    "require_admin": False,
                    "mode": "storage",
                }
            )
            _LOGGER.info(
                "🆕 Created Lovelace dashboard '%s' in sidebar", DASHBOARD_TITLE
            )
        else:
            _LOGGER.debug(
                "Lovelace dashboard '%s' already exists — refreshing content",
                DASHBOARD_TITLE,
            )
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Failed to create Lovelace dashboard: %s", err)
        return False

    # Save / overwrite the dashboard view definition with our preconfigured card.
    return await _save_dashboard_config(hass, entry)


async def _save_dashboard_config(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Persist the panel-mode view + card config into the dashboard store.

    Strategy:
    1. If the live `LovelaceStorage` renderer is already loaded, use its
       `async_save()` so the in-memory config matches the persisted one.
    2. Otherwise write directly through `Store`, which is the same backend
       `LovelaceStorage` uses — the renderer will pick it up on first fetch.
    """
    config = _build_dashboard_view(entry)

    dashboards_map = _get_dashboards_map(hass)
    dashboard = None
    if dashboards_map is not None:
        try:
            dashboard = dashboards_map.get(DASHBOARD_URL_PATH)
        except Exception:  # pragma: no cover - defensive
            dashboard = None

    if dashboard is not None and hasattr(dashboard, "async_save"):
        try:
            await dashboard.async_save(config)
            _LOGGER.info(
                "✏️  Dashboard '%s' content populated via live renderer",
                DASHBOARD_TITLE,
            )
            return True
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.debug(
                "Live dashboard save failed (%s), falling back to Store", err
            )

    # Direct Store write — matches LovelaceStorage's own backend.
    # We build the key manually (`lovelace.<url_path>`) instead of pulling
    # CONFIG_STORAGE_KEY from HA: in older cores the constant uses printf
    # style ('lovelace.%s') and `.format()` would silently produce garbage.
    # The literal `lovelace.<url_path>` filename has been stable since 2019.
    storage_key = f"lovelace.{DASHBOARD_URL_PATH}"
    try:
        store = Store(
            hass,
            CONFIG_STORAGE_VERSION_MAJOR,
            storage_key,
            minor_version=CONFIG_STORAGE_VERSION_MINOR,
        )
    except TypeError:
        # Older HA cores did not accept minor_version kwarg.
        store = Store(hass, CONFIG_STORAGE_VERSION_MAJOR, storage_key)

    try:
        # LovelaceStorage wraps the Lovelace config under a {"config": ...} key
        # before saving — match that exact shape so the renderer reads it back
        # transparently.
        await store.async_save({"config": config})
        _LOGGER.info(
            "✏️  Dashboard '%s' content written to .storage/%s",
            DASHBOARD_TITLE,
            storage_key,
        )
        return True
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Failed to persist dashboard config to store: %s", err)
        return False


def _find_existing_dashboard(collection: Any) -> dict[str, Any] | None:
    """Return the stored dashboard item if already present."""
    items = []
    if hasattr(collection, "async_items"):
        try:
            items = list(collection.async_items())
        except Exception:  # pragma: no cover - defensive
            items = []
    if not items:
        data = getattr(collection, "data", None)
        if isinstance(data, dict):
            raw = data.get("items")
            if isinstance(raw, list):
                items = raw

    for item in items:
        if item.get("url_path") == DASHBOARD_URL_PATH:
            return item
    return None


async def async_remove_dashboard(
    hass: HomeAssistant, *, remove_resource: bool = False
) -> None:
    """Remove the auto-generated dashboard (and optionally the resource)."""
    collection = _get_dashboards_collection(hass)
    if collection is not None:
        existing = _find_existing_dashboard(collection)
        if existing is not None:
            try:
                await collection.async_delete_item(existing["id"])
                _LOGGER.info(
                    "🗑️  Removed Lovelace dashboard '%s'", DASHBOARD_TITLE
                )
            except Exception as err:  # pragma: no cover - defensive
                _LOGGER.warning("Failed to remove dashboard: %s", err)

    if remove_resource:
        await async_remove_resource_if_unused(hass)
