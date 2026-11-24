"""Build an optional dashboard using Home Assistant's live Lovelace collection.

Never open dashboard storage or remove, replace, or repair an existing panel.
The shared resource can be installed separately for users who only want the card.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from homeassistant.components import frontend, panel_custom, persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
try:  # pragma: no cover - HassKey added in mid-2024 HA cores
    from homeassistant.components.lovelace.const import LOVELACE_DATA
except ImportError:  # pragma: no cover
    LOVELACE_DATA = "lovelace"

from .const import (
    CONF_BATTERY_POWER,
    CONF_CHARGING_POWER,
    CONF_CHARGING_POWER_L2,
    CONF_CHARGING_POWER_L3,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_EV_CHARGER_SWITCH,
    CONF_FV_PRODUCTION,
    CONF_FV_PRODUCTION_L2,
    CONF_FV_PRODUCTION_L3,
    CONF_GRID_AVAILABLE,
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

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_BUNDLE_PATH = _FRONTEND_DIR / FRONTEND_CARD_FILENAME
_BUILDER_COMPONENT = "evsc-dashboard-builder"
_BUILDER_FILENAME = "evsc-dashboard-builder.js"
_BUILDER_OWNER = "_dashboard_builders"


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
    if isinstance(lovelace, dict):
        return lovelace.get("resource_mode") or lovelace.get("mode")
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
        # v2.2.0: measured charging power → single-phase SSOT for the card's
        # drawing-now (banner / ring / tile). Three-phase uses the summed array
        # below instead; this single key is the L1 / single-phase mapping.
        "charging_power_entity": CONF_CHARGING_POWER,
        "charger_switch_entity": CONF_EV_CHARGER_SWITCH,
        "pv_forecast_entity": CONF_PV_FORECAST,
        # v1.11.14: distinct from pv_forecast_entity. Drives the
        # "Forecast Domani" / "Tomorrow Forecast" orange chip on the
        # hero card. Optional — chip is omitted if not mapped.
        "pv_forecast_tomorrow_entity": CONF_PV_FORECAST_TOMORROW,
        # v2.1.0 (issue #29): optional signed battery-power sensor.
        "battery_power_entity": CONF_BATTERY_POWER,
        # v2.6.0 (issue #36): optional grid-availability binary_sensor.
        "grid_available_entity": CONF_GRID_AVAILABLE,
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
            # v2.2.0: per-phase charging power, summed by the card for drawing-now.
            ("charging_power_entities", (CONF_CHARGING_POWER, CONF_CHARGING_POWER_L2, CONF_CHARGING_POWER_L3)),
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



def _builder_path(entry: ConfigEntry) -> str:
    """Stable private-builder route, independent of the actual dashboard."""
    return f"evsc-dashboard-builder-{entry.entry_id.lower()}"


async def async_prepare_dashboard_builder(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Register a hidden, administrator-only panel; never write Lovelace data."""
    if _get_dashboards_map(hass) is None or _lovelace_resource_mode(hass) == "yaml":
        return False
    path = _builder_path(entry)
    owned = hass.data.setdefault(DOMAIN, {}).setdefault(_BUILDER_OWNER, {})
    panels = hass.data.get(frontend.DATA_PANELS, {})
    if path in panels:
        return owned.get(path) is panels[path]
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=path,
        webcomponent_name=_BUILDER_COMPONENT,
        module_url=f"{FRONTEND_URL_BASE}/{_BUILDER_FILENAME}?v={VERSION}",
        require_admin=True,
        config={
            "dashboardPath": DASHBOARD_URL_PATH,
            "title": DASHBOARD_TITLE,
            "icon": DASHBOARD_ICON,
            "layout": _build_dashboard_view(entry),
        },
    )
    owned[path] = hass.data[frontend.DATA_PANELS][path]
    return True


def async_remove_dashboard_builder(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Release only the integration's transient setup panel, never a dashboard."""
    path = _builder_path(entry)
    owned = hass.data.get(DOMAIN, {}).get(_BUILDER_OWNER, {})
    panel = owned.pop(path, None)
    if panel is not None and hass.data.get(frontend.DATA_PANELS, {}).get(path) is panel:
        frontend.async_remove_panel(hass, path)
    persistent_notification.async_dismiss(hass, path)


def async_offer_dashboard_builder(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Link the administrator to the native, authenticated creation step."""
    path = _builder_path(entry)
    persistent_notification.async_create(
        hass,
        f"[Open the dashboard builder](/{path}), then select **Create dashboard**. "
        "This uses your Home Assistant administrator session. If the dashboard "
        "already exists, the builder leaves it unchanged.",
        title="EV Smart Charger: finish dashboard setup",
        notification_id=path,
    )
