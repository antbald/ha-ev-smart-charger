from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from .const import DOMAIN, DEFAULT_NAME

class EVSCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title=user_input.get(CONF_NAME, DEFAULT_NAME), data={})
        schema = vol.Schema({vol.Optional(CONF_NAME, default=DEFAULT_NAME): str})
        return self.async_show_form(step_id="user", data_schema=schema)
