"""Boost Charge override automation for EV Smart Charger."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import (
    CONF_CAR_OWNER,
    CONF_NOTIFY_SERVICES,
    HELPER_BOOST_CHARGE_ENABLED_SUFFIX,
    HELPER_BOOST_CHARGE_AMPERAGE_SUFFIX,
    HELPER_BOOST_TARGET_SOC_SUFFIX,
    PRIORITY_BOOST_CHARGE,
)
from .localization import translate_runtime
from .runtime import EVSCRuntimeData
from .utils import state_helper
from .utils.logging_helper import EVSCLogger
from .utils.mobile_notification_service import MobileNotificationService
from .utils.notification_service import NotificationService

BOOST_MONITOR_INTERVAL_SECONDS = 15
BOOST_MAX_SOC_READ_FAILURES = 4


class BoostCharge:
    """Manage a manual boost charge session with auto-stop on EV SOC target."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        priority_balancer,
        charger_controller,
        runtime_data: EVSCRuntimeData | None = None,
        coordinator=None,
        night_smart_charge=None,
        solar_surplus=None,
    ) -> None:
        """Initialize Boost Charge automation."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.priority_balancer = priority_balancer
        self.charger_controller = charger_controller
        self._runtime_data = runtime_data
        self._coordinator = coordinator
        self._night_smart_charge = night_smart_charge
        self._solar_surplus = solar_surplus

        self.logger = EVSCLogger("BOOST CHARGE")
        self._notification_service = NotificationService(hass)
        self._mobile_notifier = MobileNotificationService(
            hass,
            config.get(CONF_NOTIFY_SERVICES, []),
            entry_id,
            config.get(CONF_CAR_OWNER),
            runtime_data=runtime_data,
        )

        self._boost_switch_entity = None
        self._boost_amperage_entity = None
        self._boost_target_soc_entity = None
        self._boost_switch_entity_obj = None

        self._boost_active = False
        self._monitor_unsub = None
        self._boost_switch_unsub = None
        self._soc_read_failures = 0

    async def async_setup(self) -> None:
        """Set up Boost Charge automation."""
        self._boost_switch_entity = self._resolve_entity(HELPER_BOOST_CHARGE_ENABLED_SUFFIX)
        self._boost_amperage_entity = self._resolve_entity(HELPER_BOOST_CHARGE_AMPERAGE_SUFFIX)
        self._boost_target_soc_entity = self._resolve_entity(HELPER_BOOST_TARGET_SOC_SUFFIX)
        if self._runtime_data is not None:
            self._boost_switch_entity_obj = self._runtime_data.get_entity(
                HELPER_BOOST_CHARGE_ENABLED_SUFFIX
            )

        missing_entities = []
        if not self._boost_switch_entity:
            missing_entities.append(HELPER_BOOST_CHARGE_ENABLED_SUFFIX)
        if not self._boost_amperage_entity:
            missing_entities.append(HELPER_BOOST_CHARGE_AMPERAGE_SUFFIX)
        if not self._boost_target_soc_entity:
            missing_entities.append(HELPER_BOOST_TARGET_SOC_SUFFIX)

        if missing_entities:
            self.logger.warning(
                f"Helper entities not found: {', '.join(missing_entities)} - "
                "Boost Charge will remain inactive until entities are available."
            )
            return

        self._boost_switch_unsub = async_track_state_change_event(
            self.hass,
            self._boost_switch_entity,
            self._async_boost_switch_changed,
        )

        if state_helper.get_bool(self.hass, self._boost_switch_entity):
            self.logger.warning("Boost switch restored ON after restart - resetting to OFF")
            await self._set_boost_switch(False)

        self.logger.success("Boost Charge setup completed")

    def _resolve_entity(self, key: str) -> str | None:
        """Resolve an integration-owned helper entity."""
        if self._runtime_data is None:
            return None
        return self._runtime_data.get_entity_id(key)

    async def async_remove(self) -> None:
        """Remove Boost Charge automation."""
        if self._boost_switch_unsub:
            self._boost_switch_unsub()
            self._boost_switch_unsub = None

        if self._monitor_unsub:
            self._monitor_unsub()
            self._monitor_unsub = None

        self._boost_active = False
        self.logger.info("Boost Charge removed")

    def set_related_automations(self, night_smart_charge=None, solar_surplus=None) -> None:
        """Set or update references used for post-boost re-evaluation."""
        if night_smart_charge is not None:
            self._night_smart_charge = night_smart_charge
        if solar_surplus is not None:
            self._solar_surplus = solar_surplus

    def is_active(self) -> bool:
        """Return True when Boost Charge currently owns the charging session."""
        return self._boost_active

    def get_target_soc(self) -> int | None:
        """Return configured boost target SOC."""
        return state_helper.get_int(self.hass, self._boost_target_soc_entity, default=None)

    def get_target_amperage(self) -> int | None:
        """Return configured boost amperage."""
        return state_helper.get_int(self.hass, self._boost_amperage_entity, default=None)

    @callback
    async def _async_boost_switch_changed(self, event) -> None:
        """Handle boost switch state changes."""
        new_state: State = event.data.get("new_state")
        old_state: State = event.data.get("old_state")

        if not new_state:
            return

        if new_state.state == STATE_ON and (not old_state or old_state.state != STATE_ON):
            await self._start_boost_charge()
            return

        if (
            old_state
            and old_state.state == STATE_ON
            and new_state.state != STATE_ON
            and self._boost_active
        ):
            await self._complete_boost(
                translate_runtime(self.hass, "boost.reason.manual_stop"),
                stop_charger=True,
                notify=True,
                success=False,
            )

    async def _start_boost_charge(self) -> None:
        """Start a boost charge session if validation passes."""
        if self._boost_active:
            self.logger.debug("Boost Charge already active - ignoring duplicate start")
            return

        target_soc = self.get_target_soc()
        target_amps = self.get_target_amperage()

        if target_soc is None or target_amps is None:
            await self._handle_start_failure(
                translate_runtime(self.hass, "boost.reason.missing_configuration")
            )
            return

        current_soc = await self._read_ev_soc()
        if current_soc is None:
            await self._handle_start_failure(
                translate_runtime(self.hass, "boost.reason.missing_soc")
            )
            return

        if target_soc <= current_soc:
            await self._set_boost_switch(False)
            await self._notification_service.send_info(
                translate_runtime(self.hass, "boost.title.not_started"),
                translate_runtime(
                    self.hass,
                    "boost.reason.not_started_target_reached",
                    current_soc=current_soc,
                    target_soc=target_soc,
                ),
            )
            return

        if self._night_smart_charge and hasattr(
            self._night_smart_charge, "async_pause_for_external_override"
        ):
            await self._night_smart_charge.async_pause_for_external_override("Boost Charge started")

        if self._coordinator:
            allowed, reason = await self._coordinator.request_charger_action(
                automation_name="Boost Charge",
                action="turn_on",
                reason=f"Boost Charge toward {target_soc}%",
                priority=PRIORITY_BOOST_CHARGE,
            )
            if not allowed:
                await self._handle_start_failure(
                    translate_runtime(
                        self.hass,
                        "boost.reason.coordinator_denied",
                        reason=reason,
                    )
                )
                return

        self._boost_active = True
        self._soc_read_failures = 0

        if self._monitor_unsub:
            self._monitor_unsub()

        result = await self.charger_controller.start_charger(target_amps, "Boost charge")
        if not self._operation_succeeded(result):
            await self._complete_boost(
                translate_runtime(self.hass, "boost.reason.start_failed"),
                stop_charger=False,
                notify=False,
                success=False,
                request_recheck=False,
            )
            await self._handle_start_failure(
                translate_runtime(self.hass, "boost.reason.command_rejected")
            )
            return

        self._monitor_unsub = async_track_time_interval(
            self.hass,
            self._async_monitor_boost_charge,
            timedelta(seconds=BOOST_MONITOR_INTERVAL_SECONDS),
        )

        await self._mobile_notifier.send_boost_charge_started_notification(
            amperage=target_amps,
            start_soc=current_soc,
            target_soc=target_soc,
        )

        self.logger.success(
            f"Boost Charge started at {target_amps}A toward target {target_soc}%"
        )

    @callback
    async def _async_monitor_boost_charge(self, now) -> None:
        """Monitor active boost session."""
        if not self._boost_active:
            return

        target_soc = self.get_target_soc()
        target_amps = self.get_target_amperage()

        if target_soc is None or target_amps is None:
            await self._complete_boost(
                translate_runtime(self.hass, "boost.reason.session_config_missing"),
                stop_charger=True,
                notify=True,
                success=False,
            )
            return

        current_amps = await self.charger_controller.get_current_amperage()
        if current_amps is not None and current_amps != target_amps:
            await self.charger_controller.set_amperage(
                target_amps, "Boost configuration updated"
            )

        current_soc = await self._read_ev_soc()
        if current_soc is None:
            self._soc_read_failures += 1
            self.logger.warning(
                f"EV SOC unavailable during Boost Charge "
                f"({self._soc_read_failures}/{BOOST_MAX_SOC_READ_FAILURES})"
            )
            if self._soc_read_failures >= BOOST_MAX_SOC_READ_FAILURES:
                await self._complete_boost(
                    translate_runtime(self.hass, "boost.reason.session_soc_missing"),
                    stop_charger=True,
                    notify=True,
                    success=False,
                )
            return

        self._soc_read_failures = 0

        if current_soc >= target_soc:
            await self._complete_boost(
                translate_runtime(
                    self.hass,
                    "boost.reason.target_reached",
                    current_soc=current_soc,
                    target_soc=target_soc,
                ),
                stop_charger=True,
                notify=True,
                success=True,
                end_soc=current_soc,
            )

    async def _complete_boost(
        self,
        reason: str,
        stop_charger: bool,
        notify: bool,
        success: bool,
        end_soc: float | None = None,
        request_recheck: bool = True,
    ) -> None:
        """Complete the current boost session and restore normal behavior."""
        was_active = self._boost_active

        if self._monitor_unsub:
            self._monitor_unsub()
            self._monitor_unsub = None

        self._boost_active = False
        self._soc_read_failures = 0

        if stop_charger and was_active:
            await self.charger_controller.stop_charger(f"Boost Charge: {reason}")

        await self._set_boost_switch(False)

        if self._coordinator:
            self._coordinator.release_control("Boost Charge", reason)

        if notify:
            await self._mobile_notifier.send_boost_charge_completed_notification(
                end_soc=end_soc,
                target_soc=self.get_target_soc(),
                reason=reason,
            )

            if success:
                await self._notification_service.send_success(
                    translate_runtime(self.hass, "boost.title.completed"),
                    translate_runtime(
                        self.hass,
                        "boost.message.completed",
                        reason=reason,
                    ),
                )
            else:
                await self._notification_service.send_warning(
                    translate_runtime(self.hass, "boost.title.stopped"),
                    translate_runtime(
                        self.hass,
                        "boost.message.stopped",
                        reason=reason,
                    ),
                )

        if request_recheck:
            await self._request_normal_recheck()

        self.logger.info(f"Boost Charge completed: {reason}")

    async def _handle_start_failure(self, message: str) -> None:
        """Reset boost switch and notify when start validation fails."""
        await self._set_boost_switch(False)
        await self._notification_service.send_warning(
            translate_runtime(self.hass, "boost.title.not_started"),
            message,
        )

    async def _request_normal_recheck(self) -> None:
        """Trigger immediate re-evaluation of normal automations."""
        if self._night_smart_charge and hasattr(
            self._night_smart_charge, "async_request_immediate_check"
        ):
            await self._night_smart_charge.async_request_immediate_check(
                "Boost Charge completed"
            )

        if self._solar_surplus and hasattr(
            self._solar_surplus, "async_request_immediate_check"
        ):
            await self._solar_surplus.async_request_immediate_check(
                "Boost Charge completed"
            )

    async def _set_boost_switch(self, enabled: bool) -> None:
        """Synchronize helper switch state."""
        if not self._boost_switch_entity:
            return

        desired_state = STATE_ON if enabled else "off"
        current_state = state_helper.get_state(self.hass, self._boost_switch_entity)
        if current_state == desired_state:
            return

        service = "turn_on" if enabled else "turn_off"

        if self.hass.services.has_service("switch", service):
            try:
                await self.hass.services.async_call(
                    "switch",
                    service,
                    {"entity_id": self._boost_switch_entity},
                    blocking=True,
                )
            except Exception as ex:
                self.logger.debug(f"Switch service call failed, falling back to state set: {ex}")

        if state_helper.get_state(self.hass, self._boost_switch_entity) != desired_state:
            if self._boost_switch_entity_obj is not None:
                if enabled:
                    await self._boost_switch_entity_obj.async_turn_on()
                else:
                    await self._boost_switch_entity_obj.async_turn_off()
            else:
                self.logger.warning(
                    "Boost helper state did not update via service and no entity object is registered"
                )

    async def _read_ev_soc(self) -> float | None:
        """Read EV SOC and gracefully handle transient failures."""
        try:
            sensor_entity = getattr(self.priority_balancer, "_soc_car", None)
            if not sensor_entity:
                return None

            sensor_state = state_helper.get_state(self.hass, sensor_entity)
            if sensor_state in (None, "unknown", "unavailable"):
                return None

            return await self.priority_balancer.get_ev_current_soc()
        except Exception as ex:
            self.logger.warning(f"Failed to read EV SOC: {ex}")
            return None

    @staticmethod
    def _operation_succeeded(result) -> bool:
        """Handle both OperationResult and boolean-like mocks."""
        if hasattr(result, "success"):
            return result.success
        return bool(result)
