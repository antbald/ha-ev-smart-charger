"""Solar Surplus Charging Profile automation."""
from __future__ import annotations
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CHARGER_AMP_LEVELS,
    CHARGER_STATUS_FREE,
    VOLTAGE_EU,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_CHARGER_CURRENT,
    CONF_EV_CHARGER_STATUS,
    CONF_FV_PRODUCTION,
    CONF_HOME_CONSUMPTION,
    CONF_GRID_IMPORT,
)

_LOGGER = logging.getLogger(__name__)


class SolarSurplusAutomation:
    """Manages Solar Surplus charging profile."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
    ) -> None:
        """Initialize the Solar Surplus automation."""
        self.hass = hass
        self.entry_id = entry_id
        self.config = config

        # User-configured entities
        self._charger_switch = config.get(CONF_EV_CHARGER_SWITCH)
        self._charger_current = config.get(CONF_EV_CHARGER_CURRENT)
        self._charger_status = config.get(CONF_EV_CHARGER_STATUS)
        self._fv_production = config.get(CONF_FV_PRODUCTION)
        self._home_consumption = config.get(CONF_HOME_CONSUMPTION)
        self._grid_import = config.get(CONF_GRID_IMPORT)

        # Helper entities (will be discovered)
        self._forza_ricarica_entity = None
        self._charging_profile_entity = None
        self._check_interval_entity = None
        self._grid_import_threshold_entity = None

        # Timer for periodic checks
        self._timer_unsub = None

        # Current charger state tracking
        self._current_amperage = 6  # Always start with 6A

    def _find_entity_by_suffix(self, suffix: str) -> str | None:
        """Find an entity by its suffix."""
        for entity_id in self.hass.states.async_entity_ids():
            if entity_id.endswith(suffix):
                return entity_id
        return None

    async def async_setup(self) -> None:
        """Set up the Solar Surplus automation."""
        # Find helper entities
        self._forza_ricarica_entity = self._find_entity_by_suffix("evsc_forza_ricarica")
        self._charging_profile_entity = self._find_entity_by_suffix("evsc_charging_profile")
        self._check_interval_entity = self._find_entity_by_suffix("evsc_check_interval")
        self._grid_import_threshold_entity = self._find_entity_by_suffix("evsc_grid_import_threshold")

        if not all([
            self._forza_ricarica_entity,
            self._charging_profile_entity,
            self._check_interval_entity,
            self._grid_import_threshold_entity,
        ]):
            _LOGGER.error("❌ Solar Surplus: Required helper entities not found")
            return

        _LOGGER.info("✅ Solar Surplus automation initialized")

        # Start the periodic check timer
        await self._start_timer()

    async def _start_timer(self) -> None:
        """Start the periodic check timer."""
        # Get check interval from helper (in minutes)
        check_interval_state = self.hass.states.get(self._check_interval_entity)
        if check_interval_state:
            try:
                interval_minutes = int(float(check_interval_state.state))
            except (ValueError, TypeError):
                interval_minutes = 1  # Default to 1 minute
        else:
            interval_minutes = 1

        # Convert to timedelta
        interval = timedelta(minutes=interval_minutes)

        # Cancel existing timer if any
        if self._timer_unsub:
            self._timer_unsub()

        # Start new timer
        self._timer_unsub = async_track_time_interval(
            self.hass,
            self._async_periodic_check,
            interval,
        )

        _LOGGER.info(f"⏱️ Solar Surplus: Timer started with {interval_minutes} minute interval")

    @callback
    async def _async_periodic_check(self, now=None) -> None:
        """Periodic check for solar surplus charging."""
        # Check if Forza Ricarica is ON (kill switch)
        forza_state = self.hass.states.get(self._forza_ricarica_entity)
        if forza_state and forza_state.state == "on":
            _LOGGER.debug("Solar Surplus: Forza Ricarica is ON, skipping check")
            return

        # Check if Solar Surplus profile is selected
        profile_state = self.hass.states.get(self._charging_profile_entity)
        if not profile_state or profile_state.state != "solar_surplus":
            _LOGGER.debug("Solar Surplus: Profile not selected, skipping check")
            return

        # Check charger status - only skip if charger_free
        charger_status_state = self.hass.states.get(self._charger_status)
        if not charger_status_state:
            _LOGGER.warning("Solar Surplus: Charger status unavailable")
            return

        if charger_status_state.state == CHARGER_STATUS_FREE:
            _LOGGER.debug("Solar Surplus: Charger is free (not connected), skipping")
            return

        # Get sensor values
        fv_state = self.hass.states.get(self._fv_production)
        consumption_state = self.hass.states.get(self._home_consumption)
        grid_import_state = self.hass.states.get(self._grid_import)
        grid_threshold_state = self.hass.states.get(self._grid_import_threshold_entity)

        if not all([fv_state, consumption_state, grid_import_state, grid_threshold_state]):
            _LOGGER.warning("Solar Surplus: One or more sensors unavailable")
            return

        try:
            fv_production = float(fv_state.state)
            home_consumption = float(consumption_state.state)
            grid_import = float(grid_import_state.state)
            grid_threshold = float(grid_threshold_state.state)
        except (ValueError, TypeError):
            _LOGGER.warning("Solar Surplus: Invalid sensor values")
            return

        # Calculate surplus
        surplus_watts = fv_production - home_consumption

        _LOGGER.debug(
            f"Solar Surplus: FV={fv_production}W, Consumption={home_consumption}W, "
            f"Surplus={surplus_watts}W, Grid Import={grid_import}W"
        )

        # Check grid import guard rail
        if grid_import > grid_threshold:
            _LOGGER.info(
                f"Solar Surplus: Grid import ({grid_import}W) exceeds threshold ({grid_threshold}W), "
                "reducing charging"
            )
            await self._adjust_amperage_down()
            return

        # Convert surplus to amperes (European 230V)
        surplus_amps = surplus_watts / VOLTAGE_EU

        # Find the appropriate amperage level
        target_amps = self._find_target_amperage(surplus_amps)

        # Get current amperage setting
        current_setting_state = self.hass.states.get(self._charger_current)
        if current_setting_state:
            try:
                current_amps = int(float(current_setting_state.state))
            except (ValueError, TypeError):
                current_amps = 6
        else:
            current_amps = 6

        _LOGGER.debug(
            f"Solar Surplus: Surplus={surplus_amps:.2f}A, Current={current_amps}A, Target={target_amps}A"
        )

        # Adjust amperage if needed
        if target_amps > current_amps:
            # Increase: instant
            await self._set_amperage(target_amps)
        elif target_amps < current_amps:
            # Decrease: stop → wait 5s → set → wait 1s → start
            await self._adjust_amperage_down(target_amps)

    def _find_target_amperage(self, surplus_amps: float) -> int:
        """Find the appropriate amperage level from available steps."""
        # If surplus is less than minimum (6A), return 0 (stop charging)
        if surplus_amps < CHARGER_AMP_LEVELS[0]:
            return 0

        # Find the highest level that doesn't exceed surplus
        target = CHARGER_AMP_LEVELS[0]  # Start with minimum
        for level in CHARGER_AMP_LEVELS:
            if level <= surplus_amps:
                target = level
            else:
                break

        return target

    async def _set_amperage(self, amps: int) -> None:
        """Set charger amperage (instant increase)."""
        if amps == 0:
            # Stop charging
            _LOGGER.info("Solar Surplus: Insufficient surplus, stopping charger")
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": self._charger_switch},
                blocking=True,
            )
            return

        _LOGGER.info(f"Solar Surplus: Setting amperage to {amps}A")
        await self.hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": self._charger_current, "value": amps},
            blocking=True,
        )

        # Ensure charger is on
        charger_state = self.hass.states.get(self._charger_switch)
        if charger_state and charger_state.state == "off":
            _LOGGER.info("Solar Surplus: Starting charger")
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": self._charger_switch},
                blocking=True,
            )

    async def _adjust_amperage_down(self, target_amps: int = None) -> None:
        """Decrease amperage with proper sequence: stop → wait 5s → set → wait 1s → start."""
        import asyncio

        # If no target specified, step down one level
        if target_amps is None:
            current_setting_state = self.hass.states.get(self._charger_current)
            if current_setting_state:
                try:
                    current_amps = int(float(current_setting_state.state))
                except (ValueError, TypeError):
                    current_amps = 6
            else:
                current_amps = 6

            # Find current level index
            try:
                current_index = CHARGER_AMP_LEVELS.index(current_amps)
                if current_index > 0:
                    target_amps = CHARGER_AMP_LEVELS[current_index - 1]
                else:
                    target_amps = 0
            except ValueError:
                target_amps = 6

        _LOGGER.info(f"Solar Surplus: Decreasing amperage to {target_amps}A")

        # Step 1: Stop charger
        await self.hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": self._charger_switch},
            blocking=True,
        )

        # Step 2: Wait 5 seconds
        await asyncio.sleep(5)

        # Step 3: Set new amperage
        if target_amps > 0:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": self._charger_current, "value": target_amps},
                blocking=True,
            )

            # Step 4: Wait 1 second
            await asyncio.sleep(1)

            # Step 5: Start charger
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": self._charger_switch},
                blocking=True,
            )
        else:
            _LOGGER.info("Solar Surplus: Target is 0A, keeping charger off")

    async def async_remove(self) -> None:
        """Remove the automation."""
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None
        _LOGGER.info("Solar Surplus automation removed")
