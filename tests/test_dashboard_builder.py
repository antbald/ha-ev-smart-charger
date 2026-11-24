"""Regression checks for opt-in staging and real Lovelace authorization."""
from unittest.mock import patch

from homeassistant.components import frontend
from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
from homeassistant.components.lovelace import async_setup as async_setup_lovelace
from homeassistant.const import CONF_MODE
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
import pytest

from custom_components.ev_smart_charger import dashboard_manager as manager
from custom_components.ev_smart_charger.button import BuildCustomDashboardButton
from custom_components.ev_smart_charger.runtime import EVSCRuntimeData
from custom_components.ev_smart_charger.config_flow import _dashboard_request, _dashboard_schema
from custom_components.ev_smart_charger.const import (
    CONF_CREATE_DASHBOARD, CONF_DASHBOARD_BUILD_REQUESTED, DOMAIN
)


def test_legacy_true_cannot_consent_again():
    schema = _dashboard_schema({CONF_CREATE_DASHBOARD: True})
    assert schema({})[CONF_CREATE_DASHBOARD] is False
    assert _dashboard_request({})[CONF_DASHBOARD_BUILD_REQUESTED] is False
    assert _dashboard_request({CONF_CREATE_DASHBOARD: False})[CONF_DASHBOARD_BUILD_REQUESTED] is False
    assert _dashboard_request({CONF_CREATE_DASHBOARD: True})[CONF_DASHBOARD_BUILD_REQUESTED] is True


async def test_admin_builder_and_native_websocket(hass, hass_ws_client, hass_read_only_access_token):
    """Use native registered HA callbacks instead of fake admin privilege."""
    assert await async_setup_lovelace(hass, {LOVELACE_DOMAIN: {CONF_MODE: "storage"}})
    first = MockConfigEntry(domain=DOMAIN, data={}, title="EV test")
    first.add_to_hass(hass)
    assert await manager.async_prepare_dashboard_builder(hass, first)
    path = manager._builder_path(first)
    panel = hass.data[frontend.DATA_PANELS][path]
    assert panel.require_admin is True
    assert not panel.sidebar_title
    assert "ev-smart-charger" not in hass.data[frontend.DATA_PANELS]

    admin = await hass_ws_client()
    nonadmin = await hass_ws_client(access_token=hass_read_only_access_token)
    url = "ev-smart-charger"
    create = {"type":"lovelace/dashboards/create","url_path":url,
        "title":"EV Smart Charger","show_in_sidebar":True,
        "require_admin":False,"icon":"mdi:ev-station"}
    await nonadmin.send_json({"id":1, **create})
    assert not (await nonadmin.receive_json())["success"]
    assert url not in hass.data[frontend.DATA_PANELS]

    await admin.send_json({"id":1, **create})
    accepted = await admin.receive_json()
    assert accepted["success"], accepted
    assert accepted["result"]["url_path"] == url
    await admin.send_json({"id":2,"type":"lovelace/config","url_path":url,"force":True})
    absent = await admin.receive_json()
    assert absent["error"]["code"] == "config_not_found", absent
    layout = {"views":[{"title":"Preserve my custom edits","cards":[]}]}
    await admin.send_json({"id":3,"type":"lovelace/config/save","url_path":url,"config":layout})
    assert (await admin.receive_json())["success"]

    # Repeated setup, multiple entries, teardown and duplicate native create
    # cannot rewrite or delete the existing dashboard.
    assert await manager.async_prepare_dashboard_builder(hass, first)
    second = MockConfigEntry(domain=DOMAIN, data={}, title="EV test 2")
    second.add_to_hass(hass)
    assert await manager.async_prepare_dashboard_builder(hass, second)
    manager.async_remove_dashboard_builder(hass, first)
    assert path not in hass.data[frontend.DATA_PANELS]
    assert url in hass.data[frontend.DATA_PANELS]
    await admin.send_json({"id":4, **create})
    assert not (await admin.receive_json())["success"]
    await admin.send_json({"id":5,"type":"lovelace/config","url_path":url,"force":True})
    assert (await admin.receive_json())["result"] == layout
    manager.async_remove_dashboard_builder(hass, second)
    await nonadmin.close()
    await admin.close()


async def test_button_stages_only_for_active_admin(hass, hass_admin_user, hass_read_only_user):
    entry = MockConfigEntry(domain=DOMAIN, data={}, title="EV test")
    entry.add_to_hass(hass)
    entry.runtime_data = EVSCRuntimeData(config={}, expected_entity_count=1)
    button = BuildCustomDashboardButton(entry)
    button.hass = hass
    assert await async_setup_lovelace(hass, {LOVELACE_DOMAIN: {CONF_MODE: "storage"}})
    for user_id in (None, hass_read_only_user.id):
        button.async_set_context(Context(user_id=user_id))
        with pytest.raises(HomeAssistantError, match="administrator"):
            await button.async_press()
    assert manager._builder_path(entry) not in hass.data[frontend.DATA_PANELS]

    button.async_set_context(Context(user_id=hass_admin_user.id))
    with patch.object(manager.persistent_notification, "async_create") as notify:
        await button.async_press()
    assert notify.call_args.args[1].startswith("[Open the dashboard builder]")
    assert "ev-smart-charger" not in hass.data[frontend.DATA_PANELS]
    manager.async_remove_dashboard_builder(hass, entry)
