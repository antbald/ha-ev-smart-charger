"""Auto-bootstrap a ready-to-go Lovelace dashboard for EV Smart Charger.

This module wires the bundled `ev-smart-charger-dashboard.js` custom card into
Home Assistant with zero user action:

1. Registers the JS module as a Lovelace `resource` (so the custom element is
   loaded by the frontend).
2. Creates a dedicated storage-mode Lovelace dashboard that shows up in the
   sidebar as "EV Smart Charger".
3. Pre-populates the card config with the lowercased `entity_prefix` and every
   user-mapped sensor pulled directly from the config entry data.

Lovelace internals (`hass.data[LOVELACE_DATA]`) are technically not a public
API. Modern HA cores expose only `LovelaceData(resource_mode, dashboards,
resources, yaml_dashboards)` — the storage-mode `DashboardsCollection` is a
local variable in HA's lovelace.__init__ and cannot be reused from outside.

v1.9.1 strategy: bypass the collection entirely. We persist the dashboard
ourselves by writing two `Store` files (the same backend the collection uses)
and then live-register the sidebar panel via `frontend.async_register_built_in_panel`.
Persistence is performed **before** any live-wiring so even if the in-memory
hooks fail, a simple HA restart picks up the dashboard correctly.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from homeassistant.components import frontend
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

try:  # pragma: no cover - HassKey added in mid-2024 HA cores
    from homeassistant.components.lovelace.const import LOVELACE_DATA
except ImportError:  # pragma: no cover
    LOVELACE_DATA = "lovelace"

try:  # pragma: no cover - direct module access for in-memory renderer seed
    from homeassistant.components.lovelace.dashboard import LovelaceStorage
except ImportError:  # pragma: no cover
    LovelaceStorage = None  # type: ignore[assignment,misc]

from .const import (
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_FV_PRODUCTION,
    CONF_FV_PRODUCTION_L2,
    CONF_FV_PRODUCTION_L3,
    CONF_GRID_IMPORT,
    CONF_GRID_IMPORT_L2,
    CONF_GRID_IMPORT_L3,
    CONF_HOME_CONSUMPTION,
    CONF_HOME_CONSUMPTION_L2,
    CONF_HOME_CONSUMPTION_L3,
    CONF_PV_FORECAST,
    CONF_PV_FORECAST_TOMORROW,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    DASHBOARD_ICON,
    DASHBOARD_TITLE,
    DASHBOARD_URL_PATH,
    DOMAIN,
    FRONTEND_CARD_FILENAME,
    FRONTEND_URL_BASE,
    PHASE_MODE_SINGLE,
    PHASE_MODE_THREE,
    VERSION,
    get_charger_model,
    is_three_phase,
)

_LOGGER = logging.getLogger(__name__)

LOVELACE_REGISTRY_KEY = "lovelace_dashboards"
LOVELACE_REGISTRY_VERSION = 1
LOVELACE_PANEL_COMPONENT = "lovelace"

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_BUNDLE_PATH = _FRONTEND_DIR / FRONTEND_CARD_FILENAME

# Tracks whether the diagnostic probe has been logged for an entry already.
_PROBE_LOGGED: set[str] = set()


# ---------------------------------------------------------------------------
# Cache-busting helpers (v1.11.4)
# ---------------------------------------------------------------------------
#
# The Lovelace resource URL combines two cache busters:
#
#   ?v=<VERSION>    — manual SemVer bump in const.py (visible in logs, issues)
#   &h=<8 hex>      — SHA-256 of the bundle, auto-invalidates on every file change
#
# Both must be computed fresh on every async_ensure_resource() call: HACS upgrade
# swaps the file without re-importing this module, so caching the hash at module
# load would return a stale value after upgrade. The file I/O runs in the
# executor pool to keep the event loop free.


def _compute_bundle_hash() -> str:
    """Return first 8 hex chars of SHA-256 of the bundled JS file.

    Synchronous (runs in executor via _build_resource_url). Falls back to
    "unknown" if the file is missing — the next call will self-heal once the
    file is back in place, because the resulting URL will differ from the
    previously registered one and async_update_item will fire.
    """
    try:
        return hashlib.sha256(_BUNDLE_PATH.read_bytes()).hexdigest()[:8]
    except OSError as err:
        _LOGGER.warning(
            "Cannot read bundle for content hash (%s) — using fallback. "
            "URL will self-heal on next setup once the file is available.",
            err,
        )
        return "unknown"


async def _build_resource_url(hass: HomeAssistant) -> str:
    """Build the Lovelace resource URL with both cache busters.

    Recomputed on every call (no module-level cache, no @lru_cache) so that
    HACS upgrades that replace the JS file without restarting HA still
    propagate to clients on the next resource ensure.
    """
    bundle_hash = await hass.async_add_executor_job(_compute_bundle_hash)
    return (
        f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}"
        f"?v={VERSION}&h={bundle_hash}"
    )


# ---------------------------------------------------------------------------
# Lovelace data access helpers
# ---------------------------------------------------------------------------


def _lovelace_data(hass: HomeAssistant) -> Any:
    """Return the Lovelace data container.

    Tries the HassKey first (modern HA) then falls back to the legacy string
    key for older cores. They reference the same dict entry on HA versions
    where LOVELACE_DATA is a HassKey-subclassing-str.
    """
    return hass.data.get(LOVELACE_DATA) or hass.data.get("lovelace")


def _get_resources(hass: HomeAssistant) -> Any:
    """Resolve the Lovelace resources collection across HA versions."""
    lovelace = _lovelace_data(hass)
    if lovelace is None:
        return None
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    return resources


def _get_dashboards_map(hass: HomeAssistant) -> Any:
    """Resolve the live Lovelace dashboards mapping (url_path -> renderer)."""
    lovelace = _lovelace_data(hass)
    if lovelace is None:
        return None
    dashboards = getattr(lovelace, "dashboards", None)
    if dashboards is None and isinstance(lovelace, dict):
        dashboards = lovelace.get("dashboards")
    return dashboards


def _lovelace_resource_mode(hass: HomeAssistant) -> str | None:
    """Return the Lovelace resource_mode ('storage' / 'yaml') or None."""
    lovelace = _lovelace_data(hass)
    if lovelace is None:
        return None
    return getattr(lovelace, "resource_mode", None) or getattr(lovelace, "mode", None)


# ---------------------------------------------------------------------------
# Card / dashboard view builders
# ---------------------------------------------------------------------------


def _build_card_config(entry: ConfigEntry) -> dict[str, Any]:
    """Build the EV Smart Charger card config from the entry data.

    The card auto-discovers the actual entity prefix from `hass.states` at
    runtime (v1.9.1+), so passing the lowercased entry_id here is a best-guess
    fast-path — it works for new installs and the JS handles the rest.
    """
    data = entry.data
    entity_prefix = f"{DOMAIN}_{entry.entry_id.lower()}"

    config: dict[str, Any] = {
        "type": "custom:ev-smart-charger-dashboard",
        "title": DASHBOARD_TITLE,
        "entity_prefix": entity_prefix,
        # v1.11.4: runtime version injection. Single source of truth is
        # const.py:VERSION — the card logs this to the browser console so
        # users / maintainers can confirm which bundle is loaded.
        "_build_version": VERSION,
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
        # v1.11.14: distinct from pv_forecast_entity. Drives the
        # "Forecast Domani" / "Tomorrow Forecast" orange chip on the
        # hero card. Optional — chip is omitted if not mapped.
        "pv_forecast_tomorrow_entity": CONF_PV_FORECAST_TOMORROW,
    }
    for card_key, conf_key in mapping.items():
        value = data.get(conf_key)
        if value:
            config[card_key] = value

    # v2.0.0: phase mode + charger model. In three-phase, pass the per-phase
    # entity lists so the card sums them for the power tiles (and uses 690 V for
    # the derived charging-power reading). Single-phase keeps the single keys.
    config["phase_mode"] = PHASE_MODE_THREE if is_three_phase(data) else PHASE_MODE_SINGLE
    config["charger_model"] = get_charger_model(data)
    if is_three_phase(data):
        for card_key, conf_keys in (
            ("solar_power_entities", (CONF_FV_PRODUCTION, CONF_FV_PRODUCTION_L2, CONF_FV_PRODUCTION_L3)),
            ("home_consumption_entities", (CONF_HOME_CONSUMPTION, CONF_HOME_CONSUMPTION_L2, CONF_HOME_CONSUMPTION_L3)),
            ("grid_import_entities", (CONF_GRID_IMPORT, CONF_GRID_IMPORT_L2, CONF_GRID_IMPORT_L3)),
        ):
            entities = [data[k] for k in conf_keys if data.get(k)]
            if entities:
                config[card_key] = entities

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
    """Register the bundled card JS as a Lovelace resource. Idempotent.

    The URL embeds both `?v=<VERSION>` and `&h=<content-hash>`; the latter is
    recomputed on every call so HACS upgrades (which replace the JS file
    without re-importing this module) still produce a fresh URL and trigger
    async_update_item — invalidating the browser cache on next page reload.
    """
    resource_url = await _build_resource_url(hass)

    if _lovelace_resource_mode(hass) == "yaml":
        _LOGGER.info(
            "Lovelace runs in YAML mode — resource auto-registration skipped. "
            "Add manually: %s",
            resource_url,
        )
        return False

    resources = _get_resources(hass)
    if resources is None:
        _LOGGER.info(
            "Lovelace resources collection unavailable — resource will not be "
            "auto-registered. Manual URL: %s",
            resource_url,
        )
        return False

    if hasattr(resources, "async_load") and not getattr(resources, "loaded", True):
        try:
            await resources.async_load()
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.warning("Failed to load Lovelace resources: %s", err)
            return False

    items = _resource_items(resources)
    base_url = resource_url.split("?")[0]
    existing = next(
        (item for item in items if str(item.get("url", "")).split("?")[0] == base_url),
        None,
    )

    payload = {"res_type": "module", "url": resource_url}
    try:
        if existing is None:
            await resources.async_create_item(payload)
            _LOGGER.info("📌 Registered Lovelace resource: %s", resource_url)
        elif existing.get("url") != resource_url:
            await resources.async_update_item(existing["id"], payload)
            _LOGGER.info("🔄 Updated Lovelace resource: %s", resource_url)
        else:
            _LOGGER.debug("Lovelace resource already up to date: %s", resource_url)
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

    # Use bare path for dedup (ignores ?v=&h= so we find the resource regardless
    # of which version/hash registered it). We log the would-be-current URL for
    # readability — see _build_resource_url for the format.
    base_url = f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}"
    items = _resource_items(resources)
    existing = next(
        (item for item in items if str(item.get("url", "")).split("?")[0] == base_url),
        None,
    )
    if existing is None:
        return

    try:
        await resources.async_delete_item(existing["id"])
        _LOGGER.info("🗑️  Removed Lovelace resource: %s", existing.get("url"))
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Failed to remove Lovelace resource: %s", err)


def _resource_items(resources: Any) -> list[dict[str, Any]]:
    """Return the resource items list across collection implementations."""
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
# Dashboard registry (bypasses DashboardsCollection — see module docstring)
# ---------------------------------------------------------------------------


async def _load_registry(hass: HomeAssistant) -> tuple[Store, dict[str, Any]]:
    """Open the `lovelace_dashboards` Store and return (store, data).

    Data structure is HA StorageCollection's standard `{"items": [...]}` shape.
    Fresh stores load as None — we normalise to an empty items list.
    """
    store = Store(hass, LOVELACE_REGISTRY_VERSION, LOVELACE_REGISTRY_KEY)
    data = await store.async_load() or {}
    if not isinstance(data, dict):
        data = {}
    if "items" not in data or not isinstance(data["items"], list):
        data["items"] = []
    return store, data


def _upsert_registry_item(
    items: list[dict[str, Any]], url_path: str
) -> tuple[dict[str, Any], bool]:
    """Insert or refresh the dashboard registry entry.

    Returns ``(item_dict, created_new)``. For storage-mode dashboards HA uses
    ``id == url_path`` (see ``_get_suggested_id`` upstream). Existing items
    have their managed fields refreshed but any extra keys (added by HA in
    future versions, or by user edits) are preserved.
    """
    managed_fields = {
        "id": url_path,
        "url_path": url_path,
        "title": DASHBOARD_TITLE,
        "icon": DASHBOARD_ICON,
        "show_in_sidebar": True,
        "require_admin": False,
        "mode": "storage",
    }
    for item in items:
        if item.get("url_path") == url_path:
            # Refresh managed fields; preserve user-added keys.
            for key, value in managed_fields.items():
                if key == "id":
                    continue  # never touch the existing id
                item[key] = value
            return item, False
    items.append(managed_fields)
    return managed_fields, True


def _we_own_this_dashboard(item: dict[str, Any]) -> bool:
    """Safety gate: refuse to clobber a foreign dashboard at the same url_path.

    We "own" a dashboard only when its mode is storage AND its icon+title
    match our defaults. Users who rename the dashboard from the UI forfeit
    automatic updates — that is an acceptable tradeoff vs accidentally
    destroying their content.
    """
    if item.get("mode") != "storage":
        return False
    if item.get("icon") != DASHBOARD_ICON:
        return False
    if item.get("title") != DASHBOARD_TITLE:
        return False
    return True


# ---------------------------------------------------------------------------
# Lovelace dashboard creation
# ---------------------------------------------------------------------------


def _log_probe(
    entry_id: str,
    ll_data: Any,
    dashboards_map: Any,
    has_existing_item: bool,
) -> None:
    """Single-shot diagnostic line per entry. Helps remote triage of v1.9.x."""
    if entry_id in _PROBE_LOGGED:
        return
    _PROBE_LOGGED.add(entry_id)
    _LOGGER.info(
        "EVSC dashboard probe: ll_data=%s resource_mode=%s lovelace_storage_import=%s "
        "dashboards_map=%s registry_has_item=%s",
        type(ll_data).__name__ if ll_data is not None else "None",
        getattr(ll_data, "resource_mode", None) or getattr(ll_data, "mode", None),
        LovelaceStorage is not None,
        "present" if dashboards_map is not None else "missing",
        has_existing_item,
    )


async def async_ensure_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create or refresh the auto-generated EV Smart Charger dashboard.

    Persistence first (Store writes survive any live-wiring failure), live
    sidebar registration second. The dashboard is always available after at
    most one HA restart, even when the live calls fail.
    """
    ll_data = _lovelace_data(hass)

    # Step 1: hard prerequisite — Lovelace must have set up its data container.
    if ll_data is None:
        _LOGGER.info(
            "Lovelace data unavailable at setup time — auto-dashboard will "
            "appear at next HA restart if the resource is registered."
        )
        return False

    # Step 2: YAML mode rejects all mutations to dashboards/resources.
    resource_mode = _lovelace_resource_mode(hass)
    if resource_mode == "yaml":
        resource_url = await _build_resource_url(hass)
        _LOGGER.info(
            "Lovelace runs in YAML mode — auto-dashboard skipped. Add the "
            "resource %s and the card manually in your YAML config.",
            resource_url,
        )
        return False

    # Step 3: best-effort resource registration. Never blocks on this.
    await async_ensure_resource(hass)

    # Step 4–5: load the registry and prepare the upsert.
    try:
        store_reg, data = await _load_registry(hass)
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Failed to load dashboard registry: %s", err)
        return False

    items = data["items"]
    item, created_new = _upsert_registry_item(items, DASHBOARD_URL_PATH)

    # Diagnostic single-shot probe (helps remote debugging).
    dashboards_map = _get_dashboards_map(hass)
    _log_probe(entry.entry_id, ll_data, dashboards_map, not created_new)

    # Step 6: safety — refuse to touch a foreign dashboard at the same path.
    if not created_new and not _we_own_this_dashboard(item):
        _LOGGER.warning(
            "A dashboard at url_path '%s' already exists with title='%s' "
            "icon='%s' mode='%s' — refusing to overwrite. Disable the "
            "auto-dashboard option or rename the existing dashboard.",
            DASHBOARD_URL_PATH,
            item.get("title"),
            item.get("icon"),
            item.get("mode"),
        )
        return False

    # Step 7: persistence — registry. From here on the next HA restart
    # produces a working dashboard regardless of subsequent failures.
    try:
        await store_reg.async_save(data)
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Failed to save dashboard registry: %s", err)
        return False

    # Step 8: persistence — content.
    if not await _save_dashboard_config(hass, entry):
        # We still consider the dashboard "ensured" because the registry
        # entry is saved; HA will create an empty dashboard on first open.
        _LOGGER.info(
            "Dashboard registry saved but content write failed — "
            "dashboard may appear empty until next reload."
        )

    # Step 9: live in-memory seed of the LovelaceStorage renderer so the
    # websocket lovelace_config handler can serve it without a restart.
    if (
        dashboards_map is not None
        and LovelaceStorage is not None
        and DASHBOARD_URL_PATH not in dashboards_map
    ):
        try:
            dashboards_map[DASHBOARD_URL_PATH] = LovelaceStorage(hass, item)
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.info(
                "LovelaceStorage live seed failed (%s) — dashboard will "
                "appear at next HA restart.",
                err,
            )

    # Step 10: register the sidebar panel for live update.
    panel_kwargs = {
        "frontend_url_path": DASHBOARD_URL_PATH,
        "require_admin": False,
        "show_in_sidebar": True,
        "sidebar_title": DASHBOARD_TITLE,
        "sidebar_icon": DASHBOARD_ICON,
        "config": {"mode": "storage"},
    }
    try:
        frontend.async_register_built_in_panel(
            hass, LOVELACE_PANEL_COMPONENT, update=not created_new, **panel_kwargs
        )
        _LOGGER.info(
            "🆕 Dashboard '%s' ready in sidebar (created=%s)",
            DASHBOARD_TITLE,
            created_new,
        )
    except ValueError:
        # Stale panel registration from a previous failed run: remove + retry.
        try:
            frontend.async_remove_panel(
                hass, DASHBOARD_URL_PATH, warn_if_unknown=False
            )
            frontend.async_register_built_in_panel(
                hass, LOVELACE_PANEL_COMPONENT, update=False, **panel_kwargs
            )
            _LOGGER.info(
                "🆕 Dashboard '%s' re-registered in sidebar after stale state",
                DASHBOARD_TITLE,
            )
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.info(
                "Sidebar panel registration retry failed (%s) — dashboard "
                "will appear at next HA restart.",
                err,
            )
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.info(
            "Sidebar panel registration failed (%s) — dashboard will "
            "appear at next HA restart.",
            err,
        )

    return True


async def _save_dashboard_config(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Persist the panel-mode view + card config into the dashboard store.

    Strategy:
    1. If the live `LovelaceStorage` renderer is already loaded, call its
       `async_save()` so in-memory state matches the persisted file.
    2. Otherwise write directly through `Store(hass, 1, "lovelace.<url>")`
       wrapping as `{"config": ...}` — the same shape `LovelaceStorage` uses.
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

    storage_key = f"lovelace.{DASHBOARD_URL_PATH}"
    try:
        store = Store(
            hass,
            CONFIG_STORAGE_VERSION_MAJOR,
            storage_key,
            minor_version=CONFIG_STORAGE_VERSION_MINOR,
        )
    except TypeError:
        store = Store(hass, CONFIG_STORAGE_VERSION_MAJOR, storage_key)

    try:
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


# ---------------------------------------------------------------------------
# Lovelace dashboard removal
# ---------------------------------------------------------------------------


async def async_remove_dashboard(
    hass: HomeAssistant, *, remove_resource: bool = False
) -> None:
    """Remove the auto-generated dashboard (and optionally the resource).

    Each step is wrapped independently — a partial failure in one block does
    not strand the next. Order reverses ``async_ensure_dashboard``.
    """
    # Step 1: unregister sidebar panel (live update).
    try:
        frontend.async_remove_panel(
            hass, DASHBOARD_URL_PATH, warn_if_unknown=False
        )
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.debug("async_remove_panel raised (ignored): %s", err)

    # Step 2: pop in-memory LovelaceStorage renderer + delete content file
    # via its own async_delete (cleanest path).
    dashboards_map = _get_dashboards_map(hass)
    content_handled = False
    if dashboards_map is not None:
        try:
            dashboard_obj = dashboards_map.pop(DASHBOARD_URL_PATH, None)
            if dashboard_obj is not None and hasattr(dashboard_obj, "async_delete"):
                await dashboard_obj.async_delete()
                content_handled = True
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.debug("Live dashboard async_delete failed: %s", err)

    # Step 3: fallback content-file removal if step 2 didn't run async_delete.
    if not content_handled:
        try:
            content_store = Store(
                hass,
                CONFIG_STORAGE_VERSION_MAJOR,
                f"lovelace.{DASHBOARD_URL_PATH}",
            )
            await content_store.async_remove()
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.debug("Content store async_remove failed: %s", err)

    # Step 4: registry — drop our item and save back the surviving list.
    try:
        store_reg, data = await _load_registry(hass)
        items = data["items"]
        new_items = [i for i in items if i.get("url_path") != DASHBOARD_URL_PATH]
        if len(new_items) != len(items):
            data["items"] = new_items
            await store_reg.async_save(data)
            _LOGGER.info(
                "🗑️  Removed Lovelace dashboard '%s' from registry",
                DASHBOARD_TITLE,
            )
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Failed to update dashboard registry on remove: %s", err)

    # Step 5: optional resource cleanup (only when this was the last entry).
    if remove_resource:
        try:
            await async_remove_resource_if_unused(hass)
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.warning("Resource cleanup failed: %s", err)
