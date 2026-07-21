"""Test SolarSurplusAutomation logic."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta
from custom_components.ev_smart_charger.solar_surplus import SolarSurplusAutomation
from custom_components.ev_smart_charger.const import (
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
    CONF_SOC_HOME,
    CHARGER_STATUS_CHARGING,
    CHARGER_STATUS_FREE,
    PRIORITY_EV,
    PRIORITY_HOME,
    PRIORITY_EV_FREE,
)

@pytest.fixture
def automation(hass, mock_charger_controller, mock_priority_balancer):
    """Create a SolarSurplusAutomation instance."""
    config = {
        CONF_EV_CHARGER_STATUS: "sensor.charger_status",
        CONF_FV_PRODUCTION: "sensor.solar",
        CONF_HOME_CONSUMPTION: "sensor.consumption",
        CONF_GRID_IMPORT: "sensor.grid",
        CONF_SOC_HOME: "sensor.home_soc",
    }
    
    # Mock dependencies
    with patch("custom_components.ev_smart_charger.solar_surplus.AstralTimeService") as mock_astral:
        
        mock_astral.return_value.is_nighttime.return_value = False
        
        auto = SolarSurplusAutomation(
            hass, "test_entry", config, mock_priority_balancer, mock_charger_controller
        )
        
        # Mock helper entities discovery
        auto._charging_profile_entity = "select.profile"
        auto._check_interval_entity = "number.interval"
        auto._grid_import_threshold_entity = "number.grid_threshold"
        auto._grid_import_delay_entity = "number.grid_delay"
        auto._surplus_drop_delay_entity = "number.surplus_delay"
        auto._use_home_battery_entity = "switch.use_battery"
        auto._home_battery_min_soc_entity = "number.min_soc"
        auto._battery_support_amperage_entity = "number.battery_amps"
        auto._forza_ricarica_entity = "switch.force"
        auto.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)
        auto.priority_balancer.get_ev_current_soc = AsyncMock(return_value=40)
        auto.priority_balancer.get_ev_target_for_today = MagicMock(return_value=80)
        auto.priority_balancer._soc_car = "sensor.ev_soc"
        
        return auto

async def test_calculate_target_amperage(hass, automation):
    """Test target amperage calculation with hysteresis."""
    # 230V * 6A = 1380W
    # 230V * 10A = 2300W
    
    # Case 1: Surplus sufficient to start (>= 6.5A)
    # 7A * 230V = 1610W
    target = automation._calculate_target_amperage(1610, current_amperage=0)
    assert target == 6  # Should start at min level (6A)
    
    # Case 2: Surplus in dead band (6A) - Not charging
    # 6A * 230V = 1380W
    target = automation._calculate_target_amperage(1380, current_amperage=0)
    assert target == 0  # Should wait for start threshold
    
    # Case 3: Surplus in dead band (6A) - Charging
    target = automation._calculate_target_amperage(1380, current_amperage=6)
    assert target == 6  # Should maintain current
    
    # Case 4: Surplus below stop threshold (5A)
    # 5A * 230V = 1150W
    target = automation._calculate_target_amperage(1150, current_amperage=6)
    assert target == 0  # Should stop


async def test_battery_bridge_guard(hass, automation):
    """v2.1.0 (issue #29): the deadband battery bridge re-applies the
    battery-support safety guards (SOC floor / EV_FREE / sunset)."""
    # Disable the sunset guard for this test (no sunset → guard skipped).
    automation._astral_service.get_sunset = MagicMock(return_value=None)
    hass.states.async_set("sensor.home_soc", "80")
    hass.states.async_set("number.min_soc", "20")

    # Allowed: EV priority with SOC above the minimum...
    assert automation._is_battery_bridge_allowed(PRIORITY_EV) is True
    # ...and when the balancer is disabled (priority None) — opt-in is the limit.
    assert automation._is_battery_bridge_allowed(None) is True

    # Blocked when both targets are met (EV_FREE) — v1.3.24 over-discharge guard.
    assert automation._is_battery_bridge_allowed(PRIORITY_EV_FREE) is False

    # Blocked when home SOC is at/below the configured minimum.
    hass.states.async_set("sensor.home_soc", "20")
    assert automation._is_battery_bridge_allowed(PRIORITY_EV) is False

async def test_grid_import_protection(hass, automation):
    """Test grid import protection logic."""
    # Setup
    hass.states.async_set("number.grid_threshold", "50")
    hass.states.async_set("number.grid_delay", "30")
    
    # Initial high import - should start timer
    with patch("time.monotonic", return_value=1000):
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=16
        )
        assert automation._last_grid_import_high == 1000
        automation.charger_controller.set_amperage.assert_not_called()
    
    # Still high, delay not elapsed
    with patch("time.monotonic", return_value=1020): # +20s
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=16
        )
        automation.charger_controller.set_amperage.assert_not_called()
        
    # Delay elapsed - should reduce amperage
    with patch("time.monotonic", return_value=1031): # +31s
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=16
        )
        assert automation._last_grid_import_high is None
        automation.charger_controller.set_amperage.assert_called_with(13, "Grid import protection")


async def test_grid_import_protection_publishes_debug_diagnostics(hass, automation):
    """Grid import protection should publish diagnostic decisions and timing context."""
    automation._update_diagnostic_sensor = AsyncMock()

    with patch("time.monotonic", return_value=1000):
        await automation._handle_grid_import_protection(
            grid_import=400, grid_threshold=250, grid_import_delay=30, current_amps=24
        )

    first_call = automation._update_diagnostic_sensor.await_args_list[0]
    assert first_call.args[0] == "GRID_IMPORT_DELAY"
    assert first_call.args[1]["decision"] == "start_delay"
    assert first_call.args[1]["grid_import_w"] == 400
    assert first_call.args[1]["grid_threshold_w"] == 250
    assert first_call.args[1]["current_charging_a"] == 24
    assert first_call.args[1]["use_home_battery_enabled"] is False

    with patch("time.monotonic", return_value=1020):
        await automation._handle_grid_import_protection(
            grid_import=400, grid_threshold=250, grid_import_delay=30, current_amps=24
        )

    second_call = automation._update_diagnostic_sensor.await_args_list[1]
    assert second_call.args[0] == "GRID_IMPORT_DELAY"
    assert second_call.args[1]["decision"] == "waiting_delay"
    assert second_call.args[1]["grid_import_elapsed_s"] == 20.0
    assert second_call.args[1]["grid_import_remaining_s"] == 10.0

    with patch("time.monotonic", return_value=1031):
        await automation._handle_grid_import_protection(
            grid_import=400, grid_threshold=250, grid_import_delay=30, current_amps=24
        )

    third_call = automation._update_diagnostic_sensor.await_args_list[2]
    assert third_call.args[0] == "GRID_IMPORT_STEP_DOWN"
    assert third_call.args[1]["decision"] == "step_down"
    assert third_call.args[1]["current_charging_a"] == 24
    assert third_call.args[1]["target_charging_a"] == 20

async def test_grid_import_protection_keeps_charger_off_when_already_off(hass, automation):
    """When import is high and charger is OFF, protection must not start charging."""
    # Initial high import - start timer
    with patch("time.monotonic", return_value=2000):
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=0
        )
        assert automation._last_grid_import_high == 2000

    # Delay elapsed - charger should remain OFF
    with patch("time.monotonic", return_value=2031):
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=0
        )

    automation.charger_controller.set_amperage.assert_not_called()
    automation.charger_controller.stop_charger.assert_not_called()
    assert automation._last_grid_import_high is None

async def test_surplus_increase_stability(hass, automation):
    """Test surplus increase stability delay."""
    # Setup
    automation.charger_controller.is_charging.return_value = True
    
    # Initial increase detection. The code reads dt_util.now() (not
    # datetime.now()), so patch that symbol or the mock is a no-op.
    with patch("custom_components.ev_smart_charger.solar_surplus.dt_util") as mock_dt:
        mock_dt.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
        
        await automation._handle_surplus_increase(target_amps=16, current_amps=10)
        
        assert automation._surplus_stable_since == datetime(2023, 1, 1, 12, 0, 0)
        automation.charger_controller.set_amperage.assert_not_called()
        
        # Not enough time passed
        mock_dt.now.return_value = datetime(2023, 1, 1, 12, 0, 30)
        await automation._handle_surplus_increase(target_amps=16, current_amps=10)
        automation.charger_controller.set_amperage.assert_not_called()
        
        # Stability confirmed (> 60s) — issue #49: step ONE level (10A → 13A on
        # Tuya levels), not straight to the 16A target; timer re-armed.
        mock_dt.now.return_value = datetime(2023, 1, 1, 12, 1, 1)
        await automation._handle_surplus_increase(target_amps=16, current_amps=10)

        automation.charger_controller.set_amperage.assert_called_with(13, "Stable surplus step-up")
        assert automation._surplus_stable_since is None


async def test_grid_import_resets_surplus_stable_since(hass, automation):
    """issue #46: detecting grid import must invalidate pre-cloud stability credit.

    Otherwise _surplus_stable_since survives the cloud and, once it passes, the
    ramp jumps straight to full target amperage in one step (large battery draw)
    instead of re-earning a fresh 60s stability window.
    """
    # Pre-cloud: stability already accumulated.
    automation._surplus_stable_since = datetime(2023, 1, 1, 12, 0, 0)

    # First grid-import detection.
    with patch("time.monotonic", return_value=5000):
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=16
        )

    assert automation._surplus_stable_since is None  # credit invalidated

    # And again after the step-down (belt-and-suspenders).
    automation._surplus_stable_since = datetime(2023, 1, 1, 12, 5, 0)
    with patch("time.monotonic", return_value=5031):  # delay elapsed
        await automation._handle_grid_import_protection(
            grid_import=100, grid_threshold=50, grid_import_delay=30, current_amps=16
        )
    assert automation._surplus_stable_since is None


async def test_priority_home_skips_stop_when_charger_off(hass, automation):
    """issue #44: PRIORITY_HOME must not call stop_charger on an already-off charger."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)

    automation.priority_balancer.is_enabled.return_value = True
    automation.priority_balancer.calculate_priority = AsyncMock(return_value=PRIORITY_HOME)
    automation.charger_controller.is_charging = AsyncMock(return_value=False)
    automation._has_control = MagicMock(return_value=False)

    await automation._async_periodic_check()

    automation.charger_controller.stop_charger.assert_not_called()


async def test_priority_home_still_stops_when_charging(hass, automation):
    """issue #44: PRIORITY_HOME still stops a charger that IS charging."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)

    automation.priority_balancer.is_enabled.return_value = True
    automation.priority_balancer.calculate_priority = AsyncMock(return_value=PRIORITY_HOME)
    automation.charger_controller.is_charging = AsyncMock(return_value=True)
    automation._acquire_control = AsyncMock(return_value=True)

    await automation._async_periodic_check()

    automation.charger_controller.stop_charger.assert_called_once()


async def test_ev_free_does_not_stop_before_energy_checks(hass, automation):
    """Priority EV_FREE must not stop charging before Solar Surplus evaluates energy sensors."""
    # Preconditions for periodic flow
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)

    # Make energy sensors invalid: logic should still enforce target stop before validation
    hass.states.async_set("sensor.solar", "unavailable")
    hass.states.async_set("sensor.consumption", "unavailable")
    hass.states.async_set("sensor.grid", "unavailable")

    automation.priority_balancer.is_enabled.return_value = True
    automation.priority_balancer.calculate_priority = AsyncMock(return_value=PRIORITY_EV_FREE)
    automation.charger_controller.is_charging.return_value = True

    await automation._async_periodic_check()

    automation.charger_controller.stop_charger.assert_not_called()

async def test_no_start_when_grid_import_is_above_threshold(hass, automation):
    """Do not start charger in solar window when grid import is above threshold."""
    # Preconditions for periodic flow
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)
    hass.states.async_set("sensor.solar", "4000")
    hass.states.async_set("sensor.consumption", "1000")
    hass.states.async_set("sensor.grid", "200")
    hass.states.async_set("number.grid_threshold", "50")
    hass.states.async_set("number.grid_delay", "30")
    hass.states.async_set("number.surplus_delay", "30")
    hass.states.async_set("switch.use_battery", "off")

    automation.priority_balancer.is_enabled.return_value = False
    automation.charger_controller.is_charging.return_value = False
    automation.charger_controller.get_current_amperage.return_value = 0

    # Force a positive target amperage to verify start is blocked by grid import protection
    with patch.object(automation, "_calculate_target_amperage", return_value=6):
        await automation._async_periodic_check()

    automation.charger_controller.start_charger.assert_not_called()
    assert automation._last_grid_import_high is not None

async def test_periodic_check_skips_when_boost_active(hass, automation):
    """Solar Surplus should not take control while Boost Charge is active."""
    hass.states.async_set("switch.force", "off")
    automation._boost_charge = MagicMock()
    automation._boost_charge.is_active.return_value = True

    await automation._async_periodic_check()

    automation.charger_controller.start_charger.assert_not_called()


async def test_nighttime_sunset_transition_handover_accepted(hass, automation):
    """At sunset, active solar_surplus session should hand over to Night Smart Charge when accepted."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)

    automation._astral_service.is_nighttime.return_value = True
    automation.charger_controller.is_charging.return_value = True
    automation.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)

    automation._night_smart_charge = MagicMock()
    automation._night_smart_charge.async_try_handover_from_solar_surplus = AsyncMock(return_value=True)

    await automation._async_periodic_check()

    automation._night_smart_charge.async_try_handover_from_solar_surplus.assert_awaited_once_with(
        "sunset_transition"
    )
    automation.charger_controller.stop_charger.assert_not_called()


async def test_nighttime_sunset_transition_handover_rejected_stops_charger(hass, automation):
    """At sunset, if handover is rejected the charger must be stopped immediately."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)

    automation._astral_service.is_nighttime.return_value = True
    automation.charger_controller.is_charging.return_value = True
    automation.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)

    automation._night_smart_charge = MagicMock()
    automation._night_smart_charge.async_try_handover_from_solar_surplus = AsyncMock(return_value=False)

    await automation._async_periodic_check()

    automation.charger_controller.stop_charger.assert_awaited_once()
    stop_reason = automation.charger_controller.stop_charger.await_args.args[0]
    assert "Sunset transition safe stop" in stop_reason


async def test_periodic_check_does_not_enforce_daytime_target_hard_cap_before_energy_checks(hass, automation):
    """Daytime Solar Surplus must not stop charging just because the EV target is already met."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)
    hass.states.async_set("sensor.solar", "unavailable")
    hass.states.async_set("sensor.consumption", "unavailable")
    hass.states.async_set("sensor.grid", "unavailable")

    automation._astral_service.is_nighttime.return_value = False
    automation.charger_controller.is_charging.return_value = True
    automation.priority_balancer.is_ev_target_reached = AsyncMock(return_value=True)
    automation.priority_balancer.get_ev_current_soc = AsyncMock(return_value=60)
    automation.priority_balancer.get_ev_target_for_today = MagicMock(return_value=60)

    await automation._async_periodic_check()

    automation.priority_balancer.calculate_priority.assert_awaited_once()
    automation.charger_controller.stop_charger.assert_not_called()


async def test_periodic_check_starts_opportunistic_charging_when_both_targets_met(hass, automation):
    """Priority EV_FREE should still start charging when surplus is available."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)
    hass.states.async_set("sensor.solar", "4000")
    hass.states.async_set("sensor.consumption", "1000")
    hass.states.async_set("sensor.grid", "0")
    hass.states.async_set("number.grid_threshold", "50")
    hass.states.async_set("number.grid_delay", "30")
    hass.states.async_set("number.surplus_delay", "30")
    hass.states.async_set("switch.use_battery", "off")

    automation.priority_balancer.is_enabled.return_value = True
    automation.priority_balancer.calculate_priority = AsyncMock(return_value=PRIORITY_EV_FREE)
    automation.charger_controller.is_charging.return_value = False
    automation.charger_controller.get_current_amperage.return_value = 0

    with patch.object(automation, "_calculate_target_amperage", return_value=6):
        await automation._async_periodic_check()

    automation.charger_controller.start_charger.assert_awaited_once_with(
        6,
        "Solar surplus available",
    )
    automation.charger_controller.stop_charger.assert_not_called()


async def test_periodic_check_keeps_opportunistic_charging_when_both_targets_met(hass, automation):
    """Priority EV_FREE should continue charging based on surplus instead of forcing a stop."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)
    hass.states.async_set("sensor.solar", "6000")
    hass.states.async_set("sensor.consumption", "1000")
    hass.states.async_set("sensor.grid", "0")
    hass.states.async_set("number.grid_threshold", "50")
    hass.states.async_set("number.grid_delay", "30")
    hass.states.async_set("number.surplus_delay", "30")
    hass.states.async_set("switch.use_battery", "off")

    automation.priority_balancer.is_enabled.return_value = True
    automation.priority_balancer.calculate_priority = AsyncMock(return_value=PRIORITY_EV_FREE)
    automation.charger_controller.is_charging.return_value = True
    automation.charger_controller.get_current_amperage.return_value = 6

    with patch.object(automation, "_calculate_target_amperage", return_value=10):
        await automation._async_periodic_check()

    automation.charger_controller.stop_charger.assert_not_called()
    automation.charger_controller.set_amperage.assert_not_called()


async def test_sunset_transition_logs_stale_soc_but_continues_by_policy(hass, automation, caplog):
    """Sunset handover should log stale EV SOC warnings without forcing a target stop."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)
    hass.states.async_set("sensor.ev_soc", "55")

    ev_state = hass.states.get("sensor.ev_soc")
    stale_now = ev_state.last_updated + timedelta(minutes=15)

    automation._astral_service.is_nighttime.return_value = True
    automation.charger_controller.is_charging.return_value = True
    automation.priority_balancer.is_ev_target_reached = AsyncMock(return_value=False)
    automation.priority_balancer.get_ev_current_soc = AsyncMock(return_value=55)
    automation.priority_balancer.get_ev_target_for_today = MagicMock(return_value=80)
    automation._night_smart_charge = MagicMock()
    automation._night_smart_charge.async_try_handover_from_solar_surplus = AsyncMock(return_value=True)
    caplog.set_level("WARNING")

    with patch(
        "custom_components.ev_smart_charger.solar_surplus.dt_util.now",
        return_value=stale_now,
    ):
        await automation._async_periodic_check()

    assert any("SOC stale (continue)" in rec.message for rec in caplog.records)
    automation.charger_controller.stop_charger.assert_not_called()


async def test_periodic_check_does_not_start_without_coordinator_ownership(hass, automation):
    """Solar Surplus must not start charging if the coordinator denies ownership."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)
    hass.states.async_set("sensor.solar", "4000")
    hass.states.async_set("sensor.consumption", "1000")
    hass.states.async_set("sensor.grid", "0")
    hass.states.async_set("number.grid_threshold", "50")
    hass.states.async_set("number.grid_delay", "30")
    hass.states.async_set("number.surplus_delay", "30")
    hass.states.async_set("switch.use_battery", "off")

    automation._coordinator = MagicMock()
    automation._coordinator.is_automation_active.return_value = False
    automation._coordinator.request_charger_action = AsyncMock(return_value=(False, "Boost active"))
    automation.priority_balancer.is_enabled.return_value = False
    automation.charger_controller.is_charging.return_value = False
    automation.charger_controller.get_current_amperage.return_value = 0

    with patch.object(automation, "_calculate_target_amperage", return_value=6):
        await automation._async_periodic_check()

    automation._coordinator.request_charger_action.assert_awaited_once()
    automation.charger_controller.start_charger.assert_not_called()


# === v2.5.0 (issue #35): Priority Balancer disabled visibility ===

async def test_balancer_disabled_warns_once_per_day(hass, automation):
    """Balancer OFF + home battery + home target → one WARNING notification, throttled."""
    automation._has_home_battery = True
    automation.priority_balancer.has_active_home_soc_target = MagicMock(return_value=True)
    automation._notification_service.send_warning = AsyncMock()

    await automation._maybe_warn_balancer_disabled()
    await automation._maybe_warn_balancer_disabled()  # same day → throttled

    assert automation._notification_service.send_warning.await_count == 1
    _, kwargs = automation._notification_service.send_warning.call_args
    assert kwargs["notification_id"] == "evsc_priority_balancer_disabled"
    assert automation._balancer_disabled_warned_date is not None


async def test_balancer_disabled_no_home_target_no_warning(hass, automation):
    """No home SOC target configured → no notification (acceptable case)."""
    automation._has_home_battery = True
    automation.priority_balancer.has_active_home_soc_target = MagicMock(return_value=False)
    automation._notification_service.send_warning = AsyncMock()

    await automation._maybe_warn_balancer_disabled()

    automation._notification_service.send_warning.assert_not_called()


async def test_balancer_disabled_pv_only_no_warning(hass, automation):
    """PV-only mode → no notification even if a target value exists."""
    automation._has_home_battery = False
    automation.priority_balancer.has_active_home_soc_target = MagicMock(return_value=True)
    automation._notification_service.send_warning = AsyncMock()

    await automation._maybe_warn_balancer_disabled()

    automation._notification_service.send_warning.assert_not_called()


async def test_balancer_clear_dismiss_once_per_setup(hass, automation):
    """Fresh setup dismisses any stale notification once, then stays quiet."""
    automation._notification_service.dismiss = AsyncMock()

    await automation._clear_balancer_disabled_warning()
    assert automation._notification_service.dismiss.await_count == 1
    assert automation._balancer_dismiss_done is True

    await automation._clear_balancer_disabled_warning()  # nothing to clear
    assert automation._notification_service.dismiss.await_count == 1


async def test_balancer_clear_after_warn_resets_guard(hass, automation):
    """After a warning, re-enabling dismisses the notification and resets the guard."""
    automation._has_home_battery = True
    automation.priority_balancer.has_active_home_soc_target = MagicMock(return_value=True)
    automation._notification_service.send_warning = AsyncMock()
    automation._notification_service.dismiss = AsyncMock()

    await automation._maybe_warn_balancer_disabled()
    assert automation._balancer_disabled_warned_date is not None

    await automation._clear_balancer_disabled_warning()
    automation._notification_service.dismiss.assert_awaited_once()
    assert automation._balancer_disabled_warned_date is None


async def test_nighttime_skip_exposes_astral_times(hass, automation):
    """SKIPPED: Nighttime must expose now/sunrise/sunset for self-diagnosis (issue #34)."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "manual")

    automation._astral_service.is_nighttime.return_value = True
    automation.charger_controller.is_charging.return_value = False

    sunrise = datetime(2026, 6, 4, 4, 33)
    sunset = datetime(2026, 6, 4, 21, 33)
    automation._astral_service.get_sunrise.return_value = sunrise
    automation._astral_service.get_sunset.return_value = sunset

    captured = {}

    async def _capture(state, attributes):
        captured["state"] = state
        captured["attributes"] = attributes

    automation._update_diagnostic_sensor = _capture

    await automation._async_periodic_check()

    assert captured["state"] == "SKIPPED: Nighttime"
    attrs = captured["attributes"]
    assert attrs["sunrise_today"] == sunrise.isoformat()
    assert attrs["sunset_today"] == sunset.isoformat()
    assert "now" in attrs


async def test_start_timer_runs_initial_check(hass, automation):
    """_start_timer must run one immediate check so the sensor is never stale (issue #34)."""
    automation._async_periodic_check = AsyncMock()

    with patch(
        "custom_components.ev_smart_charger.solar_surplus.async_track_time_interval"
    ) as mock_track:
        mock_track.return_value = MagicMock()
        await automation._start_timer()

    automation._async_periodic_check.assert_awaited_once_with(ignore_rate_limit=True)


async def test_dead_band_steps_down_above_floor(hass, automation):
    """issue #51: in the hysteresis dead band, maintain ONLY at the floor.
    Above the floor a band-level surplus is a deficit → step one level down."""
    # surplus 1288W → 5.6A, inside the 5.5–6.5A dead band.
    # Tuya levels [6,8,10,13,16,20,24,32]: 20A is above floor → step to 16A.
    assert automation._calculate_target_amperage(1288, current_amperage=20) == 16
    # At the floor (6A): maintain (original anti-oscillation intent).
    assert automation._calculate_target_amperage(1288, current_amperage=6) == 6


async def test_surplus_increase_steps_one_level(hass, automation):
    """issue #49: confirmed-stable increase steps ONE level, not to full target."""
    import homeassistant.util.dt as dt_util
    automation._ensure_control = AsyncMock(return_value=True)
    automation._surplus_stable_since = dt_util.now() - timedelta(seconds=70)
    await automation._handle_surplus_increase(target_amps=23, current_amps=13)
    # next level up from 13 (Tuya) is 16, capped at target 23 → 16.
    automation.charger_controller.set_amperage.assert_called_with(16, "Stable surplus step-up")
    assert automation._surplus_stable_since is None


async def test_surplus_increase_clears_stale_drop_timer(hass, automation):
    """issue #52: a recovering surplus must clear the surplus-drop debounce.

    _handle_surplus_decrease arms _last_surplus_sufficient and only clears it
    after a step-down fires. If surplus recovers (increase path) the timer used
    to survive, so the next dip fired an immediate step-down against a stale
    timestamp, bypassing evsc_surplus_drop_delay and ratcheting downward.

    This covers the "stability timer just started" path (returns early, before
    the post-step-up reset): only the entry-point clear reaches it.
    """
    import homeassistant.util.dt as dt_util
    # A stale drop timer left over from an earlier sub-current tick.
    automation._last_surplus_sufficient = 5000.0
    automation._surplus_stable_since = None

    # Already charging; surplus recovered → increase path. This sets the
    # stability timer and returns at the "waiting" branch without reaching the
    # post-step-up reset (the line unreachable per the issue's instance 2).
    await automation._handle_surplus_increase(target_amps=16, current_amps=10)

    assert automation._last_surplus_sufficient is None
    automation.charger_controller.set_amperage.assert_not_called()


async def test_sensor_error_debounce_waiting_then_error(hass, automation):
    """issue #47/#48: soft WAITING for the first ticks, ERROR only after the
    sensors stay unavailable for SENSOR_UNAVAILABLE_ERROR_TICKS consecutive ticks."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)
    automation._astral_service.is_nighttime.return_value = False
    automation.priority_balancer.is_enabled.return_value = False
    hass.states.async_set("sensor.solar", "unavailable")
    hass.states.async_set("sensor.consumption", "unavailable")
    hass.states.async_set("sensor.grid", "unavailable")

    captured = []

    async def _cap(state, attrs):
        captured.append(state)

    automation._update_diagnostic_sensor = _cap

    for _ in range(3):
        await automation._async_periodic_check(ignore_rate_limit=True)

    assert captured[0].startswith("WAITING")
    assert captured[1].startswith("WAITING")
    assert captured[2].startswith("ERROR")


async def test_sensor_error_counter_resets_on_recovery(hass, automation):
    """issue #47/#48: the debounce counter resets once sensors are valid again."""
    automation._sensor_error_consecutive = 5
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_CHARGING)
    automation._astral_service.is_nighttime.return_value = False
    automation.priority_balancer.is_enabled.return_value = False
    hass.states.async_set("sensor.solar", "3000")
    hass.states.async_set("sensor.consumption", "1000")
    hass.states.async_set("sensor.grid", "0")
    hass.states.async_set("number.grid_threshold", "50")
    hass.states.async_set("number.grid_delay", "30")
    hass.states.async_set("number.surplus_delay", "30")
    hass.states.async_set("switch.use_battery", "off")
    automation._update_diagnostic_sensor = AsyncMock()

    await automation._async_periodic_check(ignore_rate_limit=True)

    assert automation._sensor_error_consecutive == 0


async def test_periodic_check_skips_on_brand_disconnected_status(hass, automation):
    """v2.9.2: OCPP 'available' (= no EV connected) must skip the tick like
    'charger_free'. Regression for 2026-07-21: the exact-match gate let
    'available' pass as connected, producing a 125-tick battery-support
    start loop (05:38-07:46) against an empty plug."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", "available")

    automation.priority_balancer.is_enabled.return_value = True
    automation._has_control = MagicMock(return_value=False)

    await automation._async_periodic_check()

    automation.charger_controller.start_charger.assert_not_called()
    automation.charger_controller.set_amperage.assert_not_called()


async def test_periodic_check_still_skips_on_charger_free(hass, automation):
    """Tuya vocabulary unchanged: 'charger_free' still skips the tick."""
    hass.states.async_set("switch.force", "off")
    hass.states.async_set("select.profile", "solar_surplus")
    hass.states.async_set("sensor.charger_status", CHARGER_STATUS_FREE)

    automation.priority_balancer.is_enabled.return_value = True
    automation._has_control = MagicMock(return_value=False)

    await automation._async_periodic_check()

    automation.charger_controller.start_charger.assert_not_called()
    automation.charger_controller.set_amperage.assert_not_called()
