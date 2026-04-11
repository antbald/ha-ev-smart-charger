"""The EV Smart Charger integration."""
from __future__ import annotations
import asyncio
import logging
from datetime import timedelta
from pathlib import Path

try:
    # HA 2024.8+ API
    from homeassistant.components.http import StaticPathConfig
except ImportError:  # pragma: no cover - compatibility branch for older HA cores
    StaticPathConfig = None
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_start

from .const import (
    DOMAIN,
    FRONTEND_CARD_FILENAME,
    FRONTEND_URL_BASE,
    PLATFORMS,
    TELEMETRY_PING_INTERVAL_HOURS,
    TOTAL_INTEGRATION_ENTITIES,
    VERSION,
)
from .automation_coordinator import AutomationCoordinator
from .charger_controller import ChargerController
from .ev_soc_monitor import EVSOCMonitor
from .priority_balancer import PriorityBalancer
from .night_smart_charge import NightSmartCharge
from .boost_charge import BoostCharge
from .automations import SmartChargerBlocker
from .solar_surplus import SolarSurplusAutomation
from .log_manager import LogManager
from .diagnostic_manager import DiagnosticManager
from .runtime import EVSCRuntimeData, get_runtime_data
from .telemetry import send_telemetry_ping, telemetry_logger

_LOGGER = logging.getLogger(__name__)
FRONTEND_DIR = Path(__file__).parent / "frontend"


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Expose the bundled dashboard frontend as a static module."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("_frontend_registered"):
        return

    if StaticPathConfig is not None and hasattr(hass.http, "async_register_static_paths"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL_BASE, str(FRONTEND_DIR), cache_headers=True)]
        )
    else:
        # Compatibility for HA cores exposing only register_static_path.
        await hass.async_add_executor_job(
            hass.http.register_static_path,
            FRONTEND_URL_BASE,
            str(FRONTEND_DIR),
            True,
        )

    domain_data["_frontend_registered"] = True

    _LOGGER.info(
        "🌐 EV Smart Charger dashboard frontend available at %s/%s",
        FRONTEND_URL_BASE,
        FRONTEND_CARD_FILENAME,
    )


async def _async_cleanup_partial_setup(runtime_data: EVSCRuntimeData) -> None:
    """Clean up partially initialized runtime services after setup failures."""
    cleanup_order = [
        ("solar_surplus", "Solar Surplus automation"),
        ("smart_blocker", "Smart Charger Blocker"),
        ("boost_charge", "Boost Charge"),
        ("night_smart_charge", "Night Smart Charge"),
        ("priority_balancer", "Priority Balancer"),
        ("diagnostic_manager", "Diagnostic Manager"),
        ("log_manager", "Log Manager"),
        ("ev_soc_monitor", "EV SOC Monitor"),
    ]

    for attr_name, label in cleanup_order:
        component = getattr(runtime_data, attr_name, None)
        if component is None or not hasattr(component, "async_remove"):
            continue
        try:
            _LOGGER.info("🧹 Partial setup cleanup: removing %s", label)
            await component.async_remove()
        except Exception:
            _LOGGER.exception("Failed partial setup cleanup for %s", label)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EV Smart Charger from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_frontend(hass)
    runtime_data = EVSCRuntimeData(
        config=dict(entry.data),
        expected_entity_count=TOTAL_INTEGRATION_ENTITIES,
    )
    entry.runtime_data = runtime_data

    _LOGGER.info("=" * 64)
    _LOGGER.info(f"🚗 EV Smart Charger v{VERSION} - Starting setup")
    _LOGGER.info("=" * 64)

    # ========== PHASE 1: SETUP PLATFORMS (Helper Entities) ==========
    _LOGGER.info("📦 Phase 1: Setting up platforms (helper entities)")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info(f"✅ Platforms registered: {', '.join(PLATFORMS)}")

    # Wait for entity registration barrier
    try:
        await asyncio.wait_for(runtime_data.registration_event.wait(), timeout=10)
    except TimeoutError as err:
        entry.runtime_data = None
        raise ConfigEntryNotReady(
            "Timed out while waiting for EV Smart Charger helper entities registration"
        ) from err

    _LOGGER.info(
        "✅ %s helper entities registered",
        runtime_data.registered_entity_count,
    )

    try:
        # ========== PHASE 2: CREATE CHARGER CONTROLLER (Centralized Charger Control) ==========
        _LOGGER.info("🔌 Phase 2: Creating Charger Controller")
        charger_controller = ChargerController(
            hass, entry.entry_id, entry.data, runtime_data=runtime_data
        )
        try:
            await charger_controller.async_setup()
            _LOGGER.info("✅ Charger Controller setup complete")
            runtime_data.charger_controller = charger_controller
        except Exception as e:
            _LOGGER.error(f"❌ Failed to set up Charger Controller: {e}")
            _LOGGER.exception("Charger Controller setup error details:")
            raise

        # ========== PHASE 2.5: CREATE EV SOC MONITOR (Cache Reliability Layer) ==========
        _LOGGER.info("⏳ Phase 2.5: Creating EV SOC Monitor (cache reliability)")
        ev_soc_monitor = EVSOCMonitor(hass, entry.entry_id, entry.data, runtime_data=runtime_data)
        runtime_data.ev_soc_monitor = ev_soc_monitor
        try:
            await ev_soc_monitor.async_setup()
            _LOGGER.info("✅ EV SOC Monitor setup complete")
        except Exception as e:
            _LOGGER.error(f"❌ Failed to set up EV SOC Monitor: {e}")
            _LOGGER.exception("EV SOC Monitor setup error details:")
            raise

        # ========== PHASE 3: CREATE AUTOMATION COORDINATOR ==========
        _LOGGER.info("🔧 Phase 3: Creating Automation Coordinator")
        coordinator = AutomationCoordinator(hass, entry.entry_id, runtime_data=runtime_data)
        _LOGGER.info("✅ Automation Coordinator created")
        runtime_data.coordinator = coordinator

        # ========== PHASE 3.5: CREATE DIAGNOSTIC MANAGER ==========
        _LOGGER.info("🩺 Phase 3.5: Creating Diagnostic Manager")
        diagnostic_manager = DiagnosticManager(hass, entry.entry_id, runtime_data)
        runtime_data.diagnostic_manager = diagnostic_manager
        await diagnostic_manager.async_setup()
        _LOGGER.info("✅ Diagnostic Manager setup complete")

        # ========== PHASE 4: CREATE PRIORITY BALANCER (Independent Component) ==========
        _LOGGER.info("⚖️  Phase 4: Creating Priority Balancer")
        priority_balancer = PriorityBalancer(
            hass, entry.entry_id, entry.data, runtime_data=runtime_data
        )
        runtime_data.priority_balancer = priority_balancer
        try:
            await priority_balancer.async_setup()
            _LOGGER.info("✅ Priority Balancer setup complete")
        except Exception as e:
            _LOGGER.error(f"❌ Failed to set up Priority Balancer: {e}")
            _LOGGER.exception("Priority Balancer setup error details:")
            raise

        # ========== PHASE 5: CREATE NIGHT SMART CHARGE (depends on Priority Balancer & Charger Controller) ==========
        _LOGGER.info("🌙 Phase 5: Creating Night Smart Charge")
        night_smart_charge = NightSmartCharge(
            hass,
            entry.entry_id,
            entry.data,
            priority_balancer,
            charger_controller,
            runtime_data=runtime_data,
            coordinator=coordinator,
        )
        try:
            await night_smart_charge.async_setup()
            _LOGGER.info("✅ Night Smart Charge setup complete")
            runtime_data.night_smart_charge = night_smart_charge
        except Exception as e:
            _LOGGER.error(f"❌ Failed to set up Night Smart Charge: {e}")
            _LOGGER.exception("Night Smart Charge setup error details:")
            night_smart_charge = None

        # ========== PHASE 5.5: CREATE BOOST CHARGE ==========
        _LOGGER.info("⚡ Phase 5.5: Creating Boost Charge")
        boost_charge = BoostCharge(
            hass,
            entry.entry_id,
            entry.data,
            priority_balancer,
            charger_controller,
            runtime_data=runtime_data,
            coordinator=coordinator,
            night_smart_charge=night_smart_charge,
        )
        try:
            await boost_charge.async_setup()
            _LOGGER.info("✅ Boost Charge setup complete")
            runtime_data.boost_charge = boost_charge
        except Exception as e:
            _LOGGER.error(f"❌ Failed to set up Boost Charge: {e}")
            _LOGGER.exception("Boost Charge setup error details:")
            boost_charge = None

        # ========== PHASE 6: CREATE SMART BLOCKER (depends on Night Smart Charge & Charger Controller) ==========
        _LOGGER.info("🚫 Phase 6: Creating Smart Charger Blocker")
        smart_blocker = SmartChargerBlocker(
            hass,
            entry.entry_id,
            entry.data,
            night_smart_charge,
            charger_controller,
            runtime_data=runtime_data,
            coordinator=coordinator,
            boost_charge=boost_charge,
        )
        try:
            await smart_blocker.async_setup()
            _LOGGER.info("✅ Smart Charger Blocker setup complete")
            runtime_data.smart_blocker = smart_blocker
        except Exception as e:
            _LOGGER.error(f"❌ Failed to set up Smart Charger Blocker: {e}")
            _LOGGER.exception("Smart Blocker setup error details:")
            smart_blocker = None

        # ========== PHASE 7: CREATE SOLAR SURPLUS (depends on Priority Balancer & Charger Controller) ==========
        _LOGGER.info("☀️  Phase 7: Creating Solar Surplus automation")
        solar_surplus = SolarSurplusAutomation(
            hass,
            entry.entry_id,
            entry.data,
            priority_balancer,
            charger_controller,
            runtime_data=runtime_data,
            night_smart_charge=night_smart_charge,
            coordinator=coordinator,
            boost_charge=boost_charge,
        )
        try:
            await solar_surplus.async_setup()
            _LOGGER.info("✅ Solar Surplus automation setup complete")
            runtime_data.solar_surplus = solar_surplus
        except Exception as e:
            _LOGGER.error(f"❌ Failed to set up Solar Surplus: {e}")
            _LOGGER.exception("Solar Surplus setup error details:")
            solar_surplus = None

        if boost_charge:
            boost_charge.set_related_automations(
                night_smart_charge=night_smart_charge,
                solar_surplus=solar_surplus,
            )

        # ========== PHASE 7.5: SETUP FILE LOGGING (v1.3.25) ==========
        _LOGGER.info("📝 Phase 7.5: Setting up file logging manager")

        # Collect all EVSCLogger instances from components
        evsc_loggers = [
            charger_controller.logger,
            priority_balancer.logger,
        ]

        if night_smart_charge:
            evsc_loggers.append(night_smart_charge.logger)
        if smart_blocker:
            evsc_loggers.append(smart_blocker.logger)
        if solar_surplus:
            evsc_loggers.append(solar_surplus.logger)
        if boost_charge:
            evsc_loggers.append(boost_charge.logger)
        evsc_loggers.append(telemetry_logger)

        # Setup log manager with toggle listener
        log_manager = LogManager(hass, entry.entry_id, runtime_data=runtime_data)
        runtime_data.log_manager = log_manager
        await log_manager.async_setup(evsc_loggers)
        await diagnostic_manager.async_refresh()
    except Exception:
        await _async_cleanup_partial_setup(runtime_data)
        entry.runtime_data = None
        raise

    _LOGGER.info(f"✅ Log manager setup complete ({len(evsc_loggers)} loggers)")

    # ========== PHASE 8: STORE REFERENCES ==========
    _LOGGER.info("💾 Phase 8: Storing component references")
    runtime_data.charger_controller = charger_controller
    runtime_data.ev_soc_monitor = ev_soc_monitor
    runtime_data.coordinator = coordinator
    runtime_data.priority_balancer = priority_balancer
    runtime_data.night_smart_charge = night_smart_charge
    runtime_data.boost_charge = boost_charge
    runtime_data.smart_blocker = smart_blocker
    runtime_data.solar_surplus = solar_surplus
    runtime_data.log_manager = log_manager
    runtime_data.diagnostic_manager = diagnostic_manager

    # Register update listener
    entry.async_on_unload(entry.add_update_listener(_reload_on_update))

    # ========== PHASE 9: ANONYMOUS TELEMETRY ==========
    # async_at_start handles both scenarios correctly and is immune to the
    # CoreState/listener race condition that would otherwise drop the first ping
    # on integration reload / retry after ConfigEntryNotReady:
    #   - HA already running  → callback invoked immediately
    #   - HA still booting    → EVENT_HOMEASSISTANT_STARTED listener registered
    _LOGGER.info("📊 Phase 9: Scheduling telemetry ping")
    telemetry_logger.info(f"📊 Phase 9 reached — hass.state={hass.state}")

    @callback
    def _fire_startup_ping(_hass=None) -> None:
        """Fire telemetry ping once HA is fully started."""
        telemetry_logger.info("📊 _fire_startup_ping invoked — creating telemetry task")
        try:
            hass.async_create_task(send_telemetry_ping(hass))
            telemetry_logger.info("📊 Telemetry task created successfully")
        except Exception as err:
            telemetry_logger.info(f"📊 ❌ Failed to create telemetry task: {err}")
            _LOGGER.exception("Failed to schedule telemetry ping")

    try:
        cancel_start = async_at_start(hass, _fire_startup_ping)
        entry.async_on_unload(cancel_start)
        telemetry_logger.info("📊 async_at_start hook registered")
    except Exception as err:
        telemetry_logger.info(f"📊 ❌ async_at_start failed: {err}")
        _LOGGER.exception("Failed to register startup telemetry hook")

    @callback
    def _schedule_daily_ping(_now=None) -> None:
        telemetry_logger.info("📊 Daily ping timer fired")
        hass.async_create_task(send_telemetry_ping(hass))

    entry.async_on_unload(
        async_track_time_interval(
            hass,
            _schedule_daily_ping,
            timedelta(hours=TELEMETRY_PING_INTERVAL_HOURS),
        )
    )
    telemetry_logger.info(
        f"📊 Daily ping timer registered ({TELEMETRY_PING_INTERVAL_HOURS}h interval)"
    )

    _LOGGER.info("=" * 64)
    _LOGGER.info(f"✅ EV Smart Charger v{VERSION} - Setup completed successfully!")
    _LOGGER.info("=" * 64)

    return True


async def _reload_on_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when config entry is updated."""
    _LOGGER.info("🔄 Configuration updated - reloading integration")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("=" * 64)
    _LOGGER.info("🔄 EV Smart Charger - Starting unload")
    _LOGGER.info("=" * 64)

    runtime_data = get_runtime_data(entry)

    # Remove automations in reverse order (opposite of setup)
    solar_surplus = runtime_data.solar_surplus
    if solar_surplus:
        _LOGGER.info("🗑️  Removing Solar Surplus automation")
        await solar_surplus.async_remove()

    smart_blocker = runtime_data.smart_blocker
    if smart_blocker:
        _LOGGER.info("🗑️  Removing Smart Charger Blocker")
        await smart_blocker.async_remove()

    boost_charge = runtime_data.boost_charge
    if boost_charge:
        _LOGGER.info("🗑️  Removing Boost Charge")
        await boost_charge.async_remove()

    night_smart_charge = runtime_data.night_smart_charge
    if night_smart_charge:
        _LOGGER.info("🗑️  Removing Night Smart Charge")
        await night_smart_charge.async_remove()

    priority_balancer = runtime_data.priority_balancer
    if priority_balancer:
        _LOGGER.info("🗑️  Removing Priority Balancer")
        await priority_balancer.async_remove()

    diagnostic_manager = runtime_data.diagnostic_manager
    if diagnostic_manager:
        _LOGGER.info("🗑️  Removing Diagnostic Manager")
        await diagnostic_manager.async_remove()

    log_manager = runtime_data.log_manager
    if log_manager:
        _LOGGER.info("🗑️  Removing Log Manager")
        await log_manager.async_remove()

    ev_soc_monitor = runtime_data.ev_soc_monitor
    if ev_soc_monitor:
        _LOGGER.info("🗑️  Removing EV SOC Monitor")
        await ev_soc_monitor.async_remove()

    charger_controller = runtime_data.charger_controller
    if charger_controller:
        _LOGGER.info("🗑️  Removing Charger Controller")
        # ChargerController doesn't need explicit cleanup, just logging

    # Unload platforms
    _LOGGER.info("🗑️  Unloading platforms")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry.runtime_data = None
        _LOGGER.info("=" * 64)
        _LOGGER.info("✅ EV Smart Charger - Unloaded successfully")
        _LOGGER.info("=" * 64)
    else:
        _LOGGER.error("❌ Failed to unload some platforms")

    return unload_ok
