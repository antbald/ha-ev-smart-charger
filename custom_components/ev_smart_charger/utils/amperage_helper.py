"""Amperage calculation and management utilities.

This module provides reusable utilities for dynamic amperage management
used by both Solar Surplus and Night Smart Charge components.
"""
from datetime import datetime
from typing import Optional, Tuple

from ..const import (
    CHARGER_AMP_LEVELS,
    VOLTAGE_EU,
    SURPLUS_START_THRESHOLD,
    SURPLUS_STOP_THRESHOLD,
)


class AmperageCalculator:
    """Utilities for calculating optimal charging amperage."""

    @staticmethod
    def calculate_from_surplus(
        surplus_watts: float,
        current_amps: int = 0,
        battery_support_amps: Optional[int] = None,
    ) -> Tuple[int, str]:
        """Calculate target amperage from surplus with battery support fallback.

        Implements 3-case hysteresis logic to prevent oscillation:
        - CASE 1: Surplus >= 6.5A → Use surplus-based amperage (6-32A)
        - CASE 2: 5.5A ≤ Surplus < 6.5A → Hysteresis band (maintain or battery)
        - CASE 3: Surplus < 5.5A → Battery support or stop

        Args:
            surplus_watts: Current surplus in watts (solar - home consumption)
            current_amps: Current charging amperage (0 if not charging)
            battery_support_amps: Amperage to use when battery support active

        Returns:
            Tuple of (target_amps, reason) - Target amperage and calculation reason

        Example:
            >>> AmperageCalculator.calculate_from_surplus(2000, 0, 16)
            (8, 'Surplus-based (8.7A available)')

            >>> AmperageCalculator.calculate_from_surplus(500, 8, 16)
            (16, 'Battery fallback (2.2A)')
        """
        surplus_amps = surplus_watts / VOLTAGE_EU
        is_charging = current_amps > 0

        # CASE 1: Surplus sufficient to charge (>= 6.5A)
        if surplus_amps >= SURPLUS_START_THRESHOLD:
            # Find highest amp level that fits within surplus
            target = CHARGER_AMP_LEVELS[0]  # Start with minimum (6A)
            for level in CHARGER_AMP_LEVELS:
                if level <= surplus_amps:
                    target = level
                else:
                    break
            return target, f"Surplus-based ({surplus_amps:.1f}A available)"

        # CASE 2: Hysteresis band (5.5A - 6.5A)
        # Prevents oscillation when surplus near threshold
        if surplus_amps >= SURPLUS_STOP_THRESHOLD:
            if is_charging:
                # Continue at current level (prevent stop/start oscillation)
                return current_amps, f"Hysteresis: maintaining {current_amps}A"
            elif battery_support_amps:
                # Not charging yet, but battery support can activate
                return (
                    battery_support_amps,
                    f"Battery support ({battery_support_amps}A)",
                )
            # Not charging, wait for surplus to exceed START threshold
            return 0, "Hysteresis: waiting for 6.5A threshold"

        # CASE 3: Insufficient surplus (< 5.5A)
        # Fallback to battery support or stop
        if battery_support_amps:
            return (
                battery_support_amps,
                f"Battery fallback ({surplus_amps:.1f}A < {SURPLUS_STOP_THRESHOLD}A)",
            )

        return 0, f"Insufficient surplus ({surplus_amps:.1f}A < {SURPLUS_STOP_THRESHOLD}A)"

    @staticmethod
    def get_next_level_down(current_amps: int) -> int:
        """Calculate one level down for reduction (grid import protection).

        Args:
            current_amps: Current charging amperage

        Returns:
            Next lower amperage level, or 0 if at minimum

        Example:
            >>> AmperageCalculator.get_next_level_down(16)
            13
            >>> AmperageCalculator.get_next_level_down(6)
            0
        """
        try:
            current_index = CHARGER_AMP_LEVELS.index(current_amps)
            if current_index > 0:
                return CHARGER_AMP_LEVELS[current_index - 1]
        except ValueError:
            # Current amps not in standard levels, return 0
            pass
        return 0

    @staticmethod
    def get_next_level_up(current_amps: int, max_amps: int) -> int:
        """Calculate one level up for recovery (gradual ramp-up).

        Args:
            current_amps: Current charging amperage
            max_amps: Maximum allowed amperage (target)

        Returns:
            Next higher amperage level, capped at max_amps

        Example:
            >>> AmperageCalculator.get_next_level_up(6, 16)
            8
            >>> AmperageCalculator.get_next_level_up(13, 16)
            16
        """
        try:
            current_index = CHARGER_AMP_LEVELS.index(current_amps)
            if current_index < len(CHARGER_AMP_LEVELS) - 1:
                next_amps = CHARGER_AMP_LEVELS[current_index + 1]
                return min(next_amps, max_amps)
        except ValueError:
            # Current amps not in standard levels, return max
            pass
        return max_amps


class GridImportProtection:
    """Grid import protection logic with hysteresis."""

    @staticmethod
    def should_reduce(
        grid_import: float,
        threshold: float,
        delay_seconds: int,
        last_trigger_time: Optional[datetime] = None,
    ) -> bool:
        """Check if amperage should reduce due to grid import.

        Implements delay-based protection to avoid reacting to brief spikes.

        Args:
            grid_import: Current grid import in watts (positive = importing)
            threshold: Maximum allowed grid import
            delay_seconds: Required delay before acting (typically 30s)
            last_trigger_time: When grid import first exceeded threshold

        Returns:
            True if should reduce amperage now

        Example:
            >>> # First detection
            >>> GridImportProtection.should_reduce(80, 50, 30, None)
            True  # Start delay tracking

            >>> # 15 seconds later
            >>> GridImportProtection.should_reduce(80, 50, 30, time_15s_ago)
            False  # Delay not elapsed

            >>> # 30 seconds later
            >>> GridImportProtection.should_reduce(80, 50, 30, time_30s_ago)
            True  # Delay elapsed, apply reduction
        """
        if grid_import <= threshold:
            return False  # Grid import normal

        if last_trigger_time is None:
            return True  # First detection - start tracking

        # Check if delay elapsed
        elapsed = (datetime.now() - last_trigger_time).total_seconds()
        return elapsed >= delay_seconds

    @staticmethod
    def should_recover(
        grid_import: float, threshold: float, hysteresis_factor: float = 0.5
    ) -> bool:
        """Check if amperage can recover (with hysteresis to prevent oscillation).

        Uses hysteresis to prevent rapid on/off cycling:
        - Reduce at 100% threshold (e.g., 50W)
        - Recover at 50% threshold (e.g., 25W)

        Args:
            grid_import: Current grid import in watts
            threshold: Maximum allowed grid import
            hysteresis_factor: Factor for recovery threshold (default 50%)

        Returns:
            True if can start recovery

        Example:
            >>> # After reduction at 80W (threshold 50W)
            >>> GridImportProtection.should_recover(45, 50)
            False  # Still too high (45W > 25W recovery threshold)

            >>> GridImportProtection.should_recover(20, 50)
            True  # Safe to recover (20W < 25W recovery threshold)
        """
        recovery_threshold = threshold * hysteresis_factor
        return grid_import < recovery_threshold


class StabilityTracker:
    """Track stability periods for amperage changes.

    Used to ensure stable conditions before increasing amperage
    (cloud protection, load spike protection).
    """

    def __init__(self):
        """Initialize tracker."""
        self._stable_since: Optional[datetime] = None

    def start_tracking(self):
        """Start stability tracking if not already started."""
        if self._stable_since is None:
            self._stable_since = datetime.now()

    def reset(self):
        """Reset stability tracking."""
        self._stable_since = None

    def is_stable(self, required_seconds: int) -> bool:
        """Check if stable period elapsed.

        Args:
            required_seconds: Required stability duration

        Returns:
            True if stable for at least required_seconds

        Example:
            >>> tracker = StabilityTracker()
            >>> tracker.start_tracking()
            >>> time.sleep(30)
            >>> tracker.is_stable(60)
            False  # Only 30 seconds elapsed
            >>> time.sleep(30)
            >>> tracker.is_stable(60)
            True  # 60 seconds elapsed
        """
        if self._stable_since is None:
            return False

        elapsed = (datetime.now() - self._stable_since).total_seconds()
        return elapsed >= required_seconds

    def get_elapsed(self) -> float:
        """Get elapsed stability time in seconds.

        Returns:
            Elapsed time in seconds, or 0 if not tracking

        Example:
            >>> tracker = StabilityTracker()
            >>> tracker.start_tracking()
            >>> time.sleep(15)
            >>> tracker.get_elapsed()
            15.0
        """
        if self._stable_since is None:
            return 0
        return (datetime.now() - self._stable_since).total_seconds()
