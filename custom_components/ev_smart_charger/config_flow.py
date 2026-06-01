from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_POWER,
    CONF_CAR_OWNER,
    CONF_CHARGER_MODEL,
    CONF_CREATE_DASHBOARD,
    CONF_ENERGY_FORECAST_TARGET,
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
    CONF_HYBRID_INVERTER_MODE,
    CONF_NOTIFY_SERVICES,
    CONF_PHASE_MODE,
    CONF_PV_FORECAST,
    CONF_PV_FORECAST_TOMORROW,
    CONF_SOC_CAR,
    CONF_SOC_HOME,
    CHARGER_MODEL_GENERIC,
    CHARGER_MODEL_TUYA,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_CHARGER_MODEL,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_HYBRID_INVERTER_MODE,
    DEFAULT_NAME,
    DEFAULT_PHASE_MODE,
    DOMAIN,
    MAX_BATTERY_CAPACITY,
    MIN_BATTERY_CAPACITY,
    PHASE_MODE_SINGLE,
    PHASE_MODE_THREE,
    is_three_phase,
)

CURRENT_CONTROL_DOMAINS = ["number", "select", "input_number", "input_select"]
ENERGY_TARGET_DOMAINS = ["input_number", "number"]


def _get_mobile_notify_services(hass) -> list[str]:
    """Get list of available mobile_app notify services."""
    notify_services = hass.services.async_services().get("notify", {})
    return sorted(
        service
        for service in notify_services
        if service.startswith("mobile_app_")
    )


def _validate_external_connectors(hass, user_input: dict[str, Any]) -> dict[str, str]:
    """Validate shared external connector settings."""
    errors: dict[str, str] = {}

    battery_capacity = user_input.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
    if battery_capacity < MIN_BATTERY_CAPACITY or battery_capacity > MAX_BATTERY_CAPACITY:
        errors["battery_capacity"] = "invalid_battery_capacity"

    energy_target = user_input.get(CONF_ENERGY_FORECAST_TARGET)
    if energy_target:
        state = hass.states.get(energy_target)
        if state is None:
            errors["energy_forecast_target"] = "entity_not_found"
        elif state.domain not in ENERGY_TARGET_DOMAINS:
            errors["energy_forecast_target"] = "invalid_domain"

    return errors


def _is_duplicate_charger_switch(
    hass,
    charger_switch: str,
    *,
    exclude_entry_id: str | None = None,
) -> bool:
    """Return True when another entry already owns the same charger switch."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if exclude_entry_id is not None and entry.entry_id == exclude_entry_id:
            continue
        if entry.data.get(CONF_EV_CHARGER_SWITCH) == charger_switch:
            return True
    return False


def _merge_entry_data(base_data: dict[str, Any], *sections: dict[str, Any]) -> dict[str, Any]:
    """Merge config sections into a single payload."""
    merged = dict(base_data)
    for section in sections:
        merged.update(section)
    return merged


def _entity_selector(domains: str | list[str]) -> selector.EntitySelector:
    """Create an entity selector for one or more domains."""
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domains))


def _field_config(default: Any) -> dict[str, Any]:
    """Return voluptuous field kwargs only when a real default is available."""
    if default is None:
        return {}
    return {"default": default}


def _charger_schema(current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the charger entities schema."""
    current_data = current_data or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_EV_CHARGER_SWITCH,
                **_field_config(current_data.get(CONF_EV_CHARGER_SWITCH)),
            ): _entity_selector("switch"),
            vol.Required(
                CONF_EV_CHARGER_CURRENT,
                **_field_config(current_data.get(CONF_EV_CHARGER_CURRENT)),
            ): _entity_selector(CURRENT_CONTROL_DOMAINS),
            vol.Required(
                CONF_EV_CHARGER_STATUS,
                **_field_config(current_data.get(CONF_EV_CHARGER_STATUS)),
            ): _entity_selector("sensor"),
        }
    )


# v2.0.0: radio option labels per language. The longer per-option explanations
# live in strings.json step `description` (which HA localizes normally); these are
# just the short radio labels. Localized in Python — instead of a selector
# `translation_key` — so it works across HA versions (older cores reject
# translation_key on a SelectSelectorConfig during form serialization).
_RADIO_LABELS: dict[str, dict[str, dict[str, str]]] = {
    CONF_PHASE_MODE: {
        "en": {PHASE_MODE_SINGLE: "Single-phase", PHASE_MODE_THREE: "Three-phase"},
        "it": {PHASE_MODE_SINGLE: "Monofase", PHASE_MODE_THREE: "Trifase"},
        "nl": {PHASE_MODE_SINGLE: "Eénfase", PHASE_MODE_THREE: "Driefase"},
    },
    CONF_CHARGER_MODEL: {
        "en": {CHARGER_MODEL_TUYA: "Tuya (standard)", CHARGER_MODEL_GENERIC: "Generic (1 A steps)"},
        "it": {CHARGER_MODEL_TUYA: "Tuya (standard)", CHARGER_MODEL_GENERIC: "Generica (scatti da 1 A)"},
        "nl": {CHARGER_MODEL_TUYA: "Tuya (standaard)", CHARGER_MODEL_GENERIC: "Generiek (stappen van 1 A)"},
    },
}


def _radio_schema(hass, key: str, options: list[str], current_value: str) -> vol.Schema:
    """Build a single-field radio (SelectSelector LIST) schema with i18n labels."""
    lang = (getattr(hass.config, "language", None) or "en") if hass else "en"
    labels = _RADIO_LABELS[key].get(lang) or _RADIO_LABELS[key]["en"]
    return vol.Schema(
        {
            vol.Required(key, default=current_value): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": opt, "label": labels.get(opt, opt)} for opt in options
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


def _phase_mode_schema(hass, current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the phase-mode radio schema (single / three) — v2.0.0."""
    current_data = current_data or {}
    return _radio_schema(
        hass,
        CONF_PHASE_MODE,
        [PHASE_MODE_SINGLE, PHASE_MODE_THREE],
        current_data.get(CONF_PHASE_MODE, DEFAULT_PHASE_MODE),
    )


def _charger_model_schema(hass, current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the charger-model radio schema (tuya / generic) — v2.0.0."""
    current_data = current_data or {}
    return _radio_schema(
        hass,
        CONF_CHARGER_MODEL,
        [CHARGER_MODEL_TUYA, CHARGER_MODEL_GENERIC],
        current_data.get(CONF_CHARGER_MODEL, DEFAULT_CHARGER_MODEL),
    )


def _sensor_schema(
    current_data: dict[str, Any] | None = None,
    three_phase: bool = False,
) -> vol.Schema:
    """Build the sensor mapping schema.

    v2.0.0: in three-phase mode, production / home-consumption / grid-import are
    asked as three sensors each (L1 reuses the existing single-phase key, L2/L3
    are required). SOC sensors stay single (battery percentages, not per-phase).
    """
    current_data = current_data or {}

    # v1.7.0: `soc_home` is optional. To prevent orphan helper entities, once a
    # home battery sensor has been configured we keep the field Required so the
    # user cannot silently drop it during reconfigure / options. New entries
    # and entries that never had a home battery see it as Optional.
    existing_soc_home = current_data.get(CONF_SOC_HOME)
    soc_home_marker = vol.Required if existing_soc_home else vol.Optional

    fields: dict[Any, Any] = {
        vol.Required(CONF_SOC_CAR, **_field_config(current_data.get(CONF_SOC_CAR))): _entity_selector("sensor"),
        soc_home_marker(CONF_SOC_HOME, **_field_config(existing_soc_home)): _entity_selector("sensor"),
    }

    # Per-quantity power sensors, grouped L1[/L2/L3]. Single-phase = L1 only.
    for l1, l2, l3 in (
        (CONF_FV_PRODUCTION, CONF_FV_PRODUCTION_L2, CONF_FV_PRODUCTION_L3),
        (CONF_HOME_CONSUMPTION, CONF_HOME_CONSUMPTION_L2, CONF_HOME_CONSUMPTION_L3),
        (CONF_GRID_IMPORT, CONF_GRID_IMPORT_L2, CONF_GRID_IMPORT_L3),
    ):
        fields[vol.Required(l1, **_field_config(current_data.get(l1)))] = _entity_selector("sensor")
        if three_phase:
            fields[vol.Required(l2, **_field_config(current_data.get(l2)))] = _entity_selector("sensor")
            fields[vol.Required(l3, **_field_config(current_data.get(l3)))] = _entity_selector("sensor")

    return vol.Schema(fields)


def _pv_forecast_schema(current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the PV forecast schema.

    Two independent optional sensors:
      - CONF_PV_FORECAST: drives Night Smart Charge's battery-vs-grid
        decision. Semantically the "next-day" forecast for that logic,
        but kept named generically because existing installs map various
        sensor flavours (remaining-today, tomorrow, custom templates).
      - CONF_PV_FORECAST_TOMORROW (v1.11.14): dedicated to the dashboard
        "Forecast Domani" chip. Lets users map a true tomorrow-forecast
        sensor (e.g. `sensor.solcast_pv_forecast_forecast_tomorrow`)
        without disturbing their existing Night Smart Charge wiring.
    """
    current_data = current_data or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_PV_FORECAST,
                **_field_config(current_data.get(CONF_PV_FORECAST)),
            ): _entity_selector("sensor"),
            vol.Optional(
                CONF_PV_FORECAST_TOMORROW,
                **_field_config(current_data.get(CONF_PV_FORECAST_TOMORROW)),
            ): _entity_selector("sensor"),
        }
    )


def _hybrid_inverter_schema(
    current_data: dict[str, Any] | None = None,
    *,
    include_toggle: bool = False,
) -> vol.Schema:
    """Build the Hybrid Inverter Mode step schema (v2.1.0 — issue #29).

    Always offers the optional signed battery-power sensor (CONF_BATTERY_POWER,
    single — never per-phase, like SOC). The enable toggle is shown only in the
    initial flow (``include_toggle=True``): it seeds the first-run state of the
    ``evsc_hybrid_inverter_mode`` switch. In reconfigure/options the switch is
    the live source of truth, so only the sensor is editable there (omitting the
    toggle key preserves the existing entry.data value via ``_merge_entry_data``).
    """
    current_data = current_data or {}
    fields: dict[Any, Any] = {}
    if include_toggle:
        fields[
            vol.Optional(
                CONF_HYBRID_INVERTER_MODE,
                default=current_data.get(
                    CONF_HYBRID_INVERTER_MODE, DEFAULT_HYBRID_INVERTER_MODE
                ),
            )
        ] = selector.BooleanSelector()
    fields[
        vol.Optional(
            CONF_BATTERY_POWER,
            **_field_config(current_data.get(CONF_BATTERY_POWER)),
        )
    ] = _entity_selector("sensor")
    return vol.Schema(fields)


def _notifications_schema(hass, current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the notifications schema."""
    current_data = current_data or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_NOTIFY_SERVICES,
                **_field_config(current_data.get(CONF_NOTIFY_SERVICES, [])),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_get_mobile_notify_services(hass),
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_CAR_OWNER,
                **_field_config(current_data.get(CONF_CAR_OWNER)),
            ): _entity_selector("person"),
        }
    )


def _external_connectors_schema(current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the external connectors schema."""
    current_data = current_data or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BATTERY_CAPACITY,
                **_field_config(
                    current_data.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
                ),
            ): vol.All(
                vol.Coerce(float),
                vol.Range(min=MIN_BATTERY_CAPACITY, max=MAX_BATTERY_CAPACITY),
            ),
            vol.Optional(
                CONF_ENERGY_FORECAST_TARGET,
                **_field_config(current_data.get(CONF_ENERGY_FORECAST_TARGET)),
            ): _entity_selector(ENERGY_TARGET_DOMAINS),
        }
    )


def _dashboard_schema(current_data: dict[str, Any] | None = None) -> vol.Schema:
    """Build the auto-generated dashboard schema (v1.9.0+)."""
    current_data = current_data or {}
    current_value = current_data.get(CONF_CREATE_DASHBOARD, DEFAULT_CREATE_DASHBOARD)
    return vol.Schema(
        {
            vol.Optional(
                CONF_CREATE_DASHBOARD,
                default=current_value,
            ): selector.BooleanSelector(),
        }
    )


class EVSCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the EV Smart Charger config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize mutable flow state."""
        self.init_info: dict[str, Any] = {}
        self.mode_info: dict[str, Any] = {}  # v2.0.0: phase_mode + charger_model
        self.charger_info: dict[str, Any] = {}
        self.sensor_info: dict[str, Any] = {}
        self.hybrid_info: dict[str, Any] = {}  # v2.1.0 (issue #29)
        self.pv_forecast_info: dict[str, Any] = {}
        self.notifications_info: dict[str, Any] = {}
        self.external_info: dict[str, Any] = {}
        self._reconfigure_entry = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step where user provides a name."""
        if user_input is not None:
            self.init_info = user_input
            return await self.async_step_phase_mode()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_NAME, default=DEFAULT_NAME): str}),
            errors={},
            description_placeholders={"step": "1", "total_steps": "10"},
        )

    async def async_step_phase_mode(self, user_input: dict[str, Any] | None = None):
        """Handle the phase-mode selection step (single / three) — v2.0.0."""
        if user_input is not None:
            self.mode_info.update(user_input)
            return await self.async_step_charger_model()

        return self.async_show_form(
            step_id="phase_mode",
            data_schema=_phase_mode_schema(self.hass),
            errors={},
            description_placeholders={"step": "2", "total_steps": "10"},
        )

    async def async_step_charger_model(self, user_input: dict[str, Any] | None = None):
        """Handle the charger-model selection step (tuya / generic) — v2.0.0."""
        if user_input is not None:
            self.mode_info.update(user_input)
            return await self.async_step_entities()

        return self.async_show_form(
            step_id="charger_model",
            data_schema=_charger_model_schema(self.hass),
            errors={},
            description_placeholders={"step": "3", "total_steps": "10"},
        )

    async def async_step_entities(self, user_input: dict[str, Any] | None = None):
        """Handle charger entity selection step."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EV_CHARGER_SWITCH])
            self._abort_if_unique_id_configured()
            self.charger_info = user_input
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="entities",
            data_schema=_charger_schema(),
            errors=errors,
            description_placeholders={"step": "4", "total_steps": "10"},
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        """Handle sensor entity selection step."""
        if user_input is not None:
            self.sensor_info = user_input
            return await self.async_step_hybrid_inverter()

        return self.async_show_form(
            step_id="sensors",
            data_schema=_sensor_schema(three_phase=is_three_phase(self.mode_info)),
            errors={},
            description_placeholders={"step": "5", "total_steps": "10"},
        )

    async def async_step_hybrid_inverter(self, user_input: dict[str, Any] | None = None):
        """Hybrid Inverter Mode: enable toggle + battery-power sensor (v2.1.0)."""
        if user_input is not None:
            self.hybrid_info = user_input
            return await self.async_step_pv_forecast()

        return self.async_show_form(
            step_id="hybrid_inverter",
            data_schema=_hybrid_inverter_schema(include_toggle=True),
            errors={},
            description_placeholders={"step": "6", "total_steps": "10"},
        )

    async def async_step_pv_forecast(self, user_input: dict[str, Any] | None = None):
        """Handle PV forecast entity selection step."""
        if user_input is not None:
            self.pv_forecast_info = user_input
            return await self.async_step_notifications()

        return self.async_show_form(
            step_id="pv_forecast",
            data_schema=_pv_forecast_schema(),
            errors={},
            description_placeholders={"step": "7", "total_steps": "10"},
        )

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None):
        """Handle mobile notification services selection step."""
        if user_input is not None:
            self.notifications_info = user_input
            return await self.async_step_external_connectors()

        return self.async_show_form(
            step_id="notifications",
            data_schema=_notifications_schema(self.hass),
            errors={},
            description_placeholders={"step": "8", "total_steps": "10"},
        )

    async def async_step_external_connectors(self, user_input: dict[str, Any] | None = None):
        """Handle external connector configuration step."""
        errors = {}

        if user_input is not None:
            errors = _validate_external_connectors(self.hass, user_input)
            if not errors:
                self.external_info = user_input
                return await self.async_step_dashboard()

        return self.async_show_form(
            step_id="external_connectors",
            data_schema=_external_connectors_schema(),
            errors=errors,
            description_placeholders={"step": "9", "total_steps": "10"},
        )

    async def async_step_dashboard(self, user_input: dict[str, Any] | None = None):
        """Final step: auto-generate the Lovelace dashboard (v1.9.0+)."""
        if user_input is not None:
            data = _merge_entry_data(
                {},
                self.init_info,
                self.mode_info,
                self.charger_info,
                self.sensor_info,
                self.hybrid_info,
                self.pv_forecast_info,
                self.notifications_info,
                self.external_info,
                user_input,
            )
            title = self.init_info.get(CONF_NAME, DEFAULT_NAME)
            return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="dashboard",
            data_schema=_dashboard_schema(),
            errors={},
            description_placeholders={"step": "10", "total_steps": "10"},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Reconfigure entry point: phase-mode selection (v2.0.0)."""
        self._reconfigure_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if self._reconfigure_entry is None:
            return self.async_abort(reason="unknown_entry")

        if user_input is not None:
            self.mode_info.update(user_input)
            return await self.async_step_reconfigure_charger_model()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_phase_mode_schema(self.hass, self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "1", "total_steps": "9"},
        )

    async def async_step_reconfigure_charger_model(self, user_input: dict[str, Any] | None = None):
        """Charger-model selection during reconfigure (v2.0.0)."""
        if user_input is not None:
            self.mode_info.update(user_input)
            return await self.async_step_reconfigure_entities()

        return self.async_show_form(
            step_id="reconfigure_charger_model",
            data_schema=_charger_model_schema(self.hass, self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "2", "total_steps": "9"},
        )

    async def async_step_reconfigure_entities(self, user_input: dict[str, Any] | None = None):
        """Charger entity remapping during reconfigure."""
        if user_input is not None:
            if _is_duplicate_charger_switch(
                self.hass,
                user_input[CONF_EV_CHARGER_SWITCH],
                exclude_entry_id=self._reconfigure_entry.entry_id,
            ):
                return self.async_abort(reason="already_configured")
            self.charger_info = user_input
            return await self.async_step_reconfigure_sensors()

        return self.async_show_form(
            step_id="reconfigure_entities",
            data_schema=_charger_schema(self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "3", "total_steps": "9"},
        )

    async def async_step_reconfigure_sensors(self, user_input: dict[str, Any] | None = None):
        """Handle sensor remapping during reconfigure."""
        if user_input is not None:
            self.sensor_info = user_input
            return await self.async_step_reconfigure_hybrid_inverter()

        return self.async_show_form(
            step_id="reconfigure_sensors",
            data_schema=_sensor_schema(
                self._reconfigure_entry.data,
                three_phase=is_three_phase(self.mode_info),
            ),
            errors={},
            description_placeholders={"step": "4", "total_steps": "9"},
        )

    async def async_step_reconfigure_hybrid_inverter(
        self, user_input: dict[str, Any] | None = None
    ):
        """Hybrid Inverter Mode battery-power sensor remap (v2.1.0).

        Sensor only — the enable toggle lives on the live switch, not entry.data,
        so it is omitted here (omission preserves the existing value via merge).
        """
        if user_input is not None:
            self.hybrid_info = user_input
            return await self.async_step_reconfigure_pv_forecast()

        return self.async_show_form(
            step_id="reconfigure_hybrid_inverter",
            data_schema=_hybrid_inverter_schema(self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "5", "total_steps": "9"},
        )

    async def async_step_reconfigure_pv_forecast(self, user_input: dict[str, Any] | None = None):
        """Handle PV forecast remapping during reconfigure."""
        if user_input is not None:
            self.pv_forecast_info = user_input
            return await self.async_step_reconfigure_notifications()

        return self.async_show_form(
            step_id="reconfigure_pv_forecast",
            data_schema=_pv_forecast_schema(self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "6", "total_steps": "9"},
        )

    async def async_step_reconfigure_notifications(self, user_input: dict[str, Any] | None = None):
        """Handle notification remapping during reconfigure."""
        if user_input is not None:
            self.notifications_info = user_input
            return await self.async_step_reconfigure_external_connectors()

        return self.async_show_form(
            step_id="reconfigure_notifications",
            data_schema=_notifications_schema(self.hass, self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "7", "total_steps": "9"},
        )

    async def async_step_reconfigure_external_connectors(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Handle external connector remapping during reconfigure."""
        errors = {}

        if user_input is not None:
            errors = _validate_external_connectors(self.hass, user_input)
            if not errors:
                self.external_info = user_input
                return await self.async_step_reconfigure_dashboard()

        return self.async_show_form(
            step_id="reconfigure_external_connectors",
            data_schema=_external_connectors_schema(self._reconfigure_entry.data),
            errors=errors,
            description_placeholders={"step": "8", "total_steps": "9"},
        )

    async def async_step_reconfigure_dashboard(
        self, user_input: dict[str, Any] | None = None
    ):
        """Final step of reconfigure: auto-generated dashboard toggle."""
        if user_input is not None:
            updated_data = _merge_entry_data(
                self._reconfigure_entry.data,
                self.mode_info,
                self.charger_info,
                self.sensor_info,
                self.hybrid_info,
                self.pv_forecast_info,
                self.notifications_info,
                self.external_info,
                user_input,
            )
            self.hass.config_entries.async_update_entry(
                self._reconfigure_entry,
                data=updated_data,
                unique_id=updated_data[CONF_EV_CHARGER_SWITCH],
            )
            return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure_dashboard",
            data_schema=_dashboard_schema(self._reconfigure_entry.data),
            errors={},
            description_placeholders={"step": "9", "total_steps": "9"},
        )

    def _get_mobile_notify_services(self) -> list[str]:
        """Get list of available mobile_app notify services."""
        return _get_mobile_notify_services(self.hass)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return EVSCOptionsFlow(config_entry)


class EVSCOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Compatibility wrapper around the canonical reconfigure fields."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        super().__init__(config_entry)
        self.mode_info: dict[str, Any] = {}  # v2.0.0: phase_mode + charger_model
        self.charger_info: dict[str, Any] = {}
        self.sensor_info: dict[str, Any] = {}
        self.hybrid_info: dict[str, Any] = {}  # v2.1.0 (issue #29)
        self.pv_forecast_info: dict[str, Any] = {}
        self.notifications_info: dict[str, Any] = {}
        self.external_info: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Options entry point: phase-mode selection (v2.0.0)."""
        if user_input is not None:
            self.mode_info.update(user_input)
            return await self.async_step_charger_model()

        return self.async_show_form(
            step_id="init",
            data_schema=_phase_mode_schema(self.hass, self.config_entry.data),
            description_placeholders={"step": "1", "total_steps": "9"},
        )

    async def async_step_charger_model(self, user_input: dict[str, Any] | None = None):
        """Charger-model selection (tuya / generic) — v2.0.0."""
        if user_input is not None:
            self.mode_info.update(user_input)
            return await self.async_step_entities()

        return self.async_show_form(
            step_id="charger_model",
            data_schema=_charger_model_schema(self.hass, self.config_entry.data),
            description_placeholders={"step": "2", "total_steps": "9"},
        )

    async def async_step_entities(self, user_input: dict[str, Any] | None = None):
        """Manage charger entities options."""
        if user_input is not None:
            if _is_duplicate_charger_switch(
                self.hass,
                user_input[CONF_EV_CHARGER_SWITCH],
                exclude_entry_id=self.config_entry.entry_id,
            ):
                return self.async_abort(reason="already_configured")
            self.charger_info = user_input
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="entities",
            data_schema=_charger_schema(self.config_entry.data),
            description_placeholders={"step": "3", "total_steps": "9"},
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        """Manage sensor entities options."""
        if user_input is not None:
            self.sensor_info = user_input
            return await self.async_step_hybrid_inverter()

        return self.async_show_form(
            step_id="sensors",
            data_schema=_sensor_schema(
                self.config_entry.data,
                three_phase=is_three_phase(self.mode_info),
            ),
            description_placeholders={"step": "4", "total_steps": "9"},
        )

    async def async_step_hybrid_inverter(self, user_input: dict[str, Any] | None = None):
        """Manage the Hybrid Inverter Mode battery-power sensor (v2.1.0).

        Sensor only (the enable toggle lives on the live switch).
        """
        if user_input is not None:
            self.hybrid_info = user_input
            return await self.async_step_pv_forecast()

        return self.async_show_form(
            step_id="hybrid_inverter",
            data_schema=_hybrid_inverter_schema(self.config_entry.data),
            description_placeholders={"step": "5", "total_steps": "9"},
        )

    async def async_step_pv_forecast(self, user_input: dict[str, Any] | None = None):
        """Manage PV forecast entity options."""
        if user_input is not None:
            self.pv_forecast_info = user_input
            return await self.async_step_notifications()

        return self.async_show_form(
            step_id="pv_forecast",
            data_schema=_pv_forecast_schema(self.config_entry.data),
            description_placeholders={"step": "6", "total_steps": "9"},
        )

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None):
        """Manage mobile notification services options."""
        if user_input is not None:
            self.notifications_info = user_input
            return await self.async_step_external_connectors()

        return self.async_show_form(
            step_id="notifications",
            data_schema=_notifications_schema(self.hass, self.config_entry.data),
            description_placeholders={"step": "7", "total_steps": "9"},
        )

    async def async_step_external_connectors(self, user_input: dict[str, Any] | None = None):
        """Handle external connector updates from the compatibility options flow."""
        errors = {}

        if user_input is not None:
            errors = _validate_external_connectors(self.hass, user_input)
            if not errors:
                self.external_info = user_input
                return await self.async_step_dashboard()

        return self.async_show_form(
            step_id="external_connectors",
            data_schema=_external_connectors_schema(self.config_entry.data),
            errors=errors,
            description_placeholders={"step": "8", "total_steps": "9"},
        )

    async def async_step_dashboard(self, user_input: dict[str, Any] | None = None):
        """Final options step: auto-generated dashboard toggle."""
        if user_input is not None:
            updated_data = _merge_entry_data(
                self.config_entry.data,
                self.mode_info,
                self.charger_info,
                self.sensor_info,
                self.hybrid_info,
                self.pv_forecast_info,
                self.notifications_info,
                self.external_info,
                user_input,
            )
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=updated_data,
                unique_id=updated_data[CONF_EV_CHARGER_SWITCH],
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="dashboard",
            data_schema=_dashboard_schema(self.config_entry.data),
            description_placeholders={"step": "9", "total_steps": "9"},
        )

    def _get_mobile_notify_services(self) -> list[str]:
        """Get list of available mobile_app notify services."""
        return _get_mobile_notify_services(self.hass)
