"""Astral Time Service for centralized sunset/sunrise calculations."""
from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.sun import get_astral_event_date


class AstralTimeService:
    """
    Centralized service for astral event calculations.

    Provides methods for calculating sunset, sunrise, and time windows
    based on astral events.
    """

    def __init__(self, hass: HomeAssistant):
        """
        Initialize Astral Time Service.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass

    def get_sunset(self, reference_date: datetime = None) -> datetime | None:
        """
        Get sunset time for a specific date.

        Args:
            reference_date: Date to calculate sunset for (defaults to today)

        Returns:
            Datetime of sunset or None if unavailable

        Example:
            >>> service = AstralTimeService(hass)
            >>> sunset = service.get_sunset()  # Today's sunset
            >>> sunset = service.get_sunset(datetime(2024, 10, 30))  # Specific date
        """
        if reference_date is None:
            reference_date = datetime.now()

        return get_astral_event_date(self.hass, "sunset", reference_date)

    def get_sunrise(self, reference_date: datetime = None) -> datetime | None:
        """
        Get sunrise time for a specific date.

        Args:
            reference_date: Date to calculate sunrise for (defaults to today)

        Returns:
            Datetime of sunrise or None if unavailable

        Example:
            >>> service = AstralTimeService(hass)
            >>> sunrise = service.get_sunrise()  # Today's sunrise
            >>> sunrise = service.get_sunrise(datetime(2024, 10, 31))  # Tomorrow
        """
        if reference_date is None:
            reference_date = datetime.now()

        return get_astral_event_date(self.hass, "sunrise", reference_date)

    def get_today_sunset(self) -> datetime | None:
        """Get today's sunset time."""
        return self.get_sunset(datetime.now())

    def get_today_sunrise(self) -> datetime | None:
        """Get today's sunrise time."""
        return self.get_sunrise(datetime.now())

    def get_tomorrow_sunrise(self) -> datetime | None:
        """Get tomorrow's sunrise time."""
        tomorrow = datetime.now() + timedelta(days=1)
        return self.get_sunrise(tomorrow)

    def get_yesterday_sunset(self) -> datetime | None:
        """Get yesterday's sunset time."""
        yesterday = datetime.now() - timedelta(days=1)
        return self.get_sunset(yesterday)

    def is_after_sunset(self, now: datetime = None) -> bool:
        """
        Check if current time is after sunset.

        Args:
            now: Reference time (defaults to current time)

        Returns:
            True if after sunset, False otherwise
        """
        if now is None:
            now = datetime.now()

        sunset = self.get_sunset(now)
        if sunset is None:
            return False

        return now >= sunset

    def is_before_sunrise(self, now: datetime = None) -> bool:
        """
        Check if current time is before sunrise.

        Args:
            now: Reference time (defaults to current time)

        Returns:
            True if before sunrise, False otherwise
        """
        if now is None:
            now = datetime.now()

        sunrise = self.get_sunrise(now)
        if sunrise is None:
            return False

        return now < sunrise

    def is_nighttime(self, now: datetime = None) -> bool:
        """
        Check if current time is nighttime (after sunset AND before sunrise).

        This handles the case where sunset is today and sunrise is tomorrow.

        Args:
            now: Reference time (defaults to current time)

        Returns:
            True if nighttime, False otherwise

        Example:
            >>> service = AstralTimeService(hass)
            >>> # At 22:00 (after sunset, before tomorrow's sunrise)
            >>> service.is_nighttime()  # Returns: True
            >>> # At 14:00 (after sunrise, before sunset)
            >>> service.is_nighttime()  # Returns: False
        """
        if now is None:
            now = datetime.now()

        # Check if after today's sunset OR before today's sunrise
        sunset_today = self.get_sunset(now)
        sunrise_today = self.get_sunrise(now)

        if sunset_today is None or sunrise_today is None:
            return False

        # Case 1: Current time is after sunset today
        if now >= sunset_today:
            return True

        # Case 2: Current time is before sunrise today
        # (means we're in the night period from yesterday's sunset)
        if now < sunrise_today:
            return True

        return False

    def get_next_sunrise_after(self, reference_time: datetime) -> datetime | None:
        """
        Get next sunrise occurrence after reference_time.

        If sunrise hasn't occurred yet today, returns today's sunrise.
        Otherwise returns tomorrow's sunrise.

        Args:
            reference_time: Reference datetime

        Returns:
            Next sunrise datetime or None if unavailable

        Example:
            >>> service = AstralTimeService(hass)
            >>> now = datetime(2024, 10, 30, 22, 0, 0)  # 22:00 (after sunrise)
            >>> next_sunrise = service.get_next_sunrise_after(now)
            >>> # Returns tomorrow's sunrise
        """
        sunrise_today = self.get_sunrise(reference_time)

        if sunrise_today is None:
            return None

        # If today's sunrise hasn't passed yet, return it
        if reference_time < sunrise_today:
            return sunrise_today

        # Otherwise return tomorrow's sunrise
        tomorrow = reference_time + timedelta(days=1)
        return self.get_sunrise(tomorrow)

    def get_blocking_window(
        self,
        reference_time: datetime,
        night_charge_enabled: bool = False,
        night_charge_time: datetime = None,
    ) -> tuple[datetime | None, datetime | None, str]:
        """
        Calculate Smart Blocker blocking window.

        Logic:
        - If Night Charge DISABLED: sunset → sunrise (next day)
        - If Night Charge ENABLED: sunset → night_charge_time

        Args:
            reference_time: Current time for calculation
            night_charge_enabled: Whether Night Smart Charge is enabled
            night_charge_time: Time when Night Smart Charge starts (as datetime)

        Returns:
            Tuple of (window_start, window_end, window_description)
            Returns (None, None, error_msg) if calculation fails

        Example:
            >>> service = AstralTimeService(hass)
            >>> now = datetime.now()
            >>> night_time = datetime(2024, 10, 31, 1, 0, 0)  # 01:00
            >>> start, end, desc = service.get_blocking_window(now, True, night_time)
            >>> # Returns: (sunset_yesterday, night_time, "sunset → night_charge_time")
        """
        # Determine which sunset to use based on current time
        # If we're in early morning (after midnight, before sunrise), use YESTERDAY's sunset
        # Otherwise, use TODAY's sunset

        sunrise_today = self.get_sunrise(reference_time)
        if sunrise_today is None:
            return None, None, "Unable to determine sunrise time"

        # Are we before today's sunrise (early morning)?
        if reference_time < sunrise_today:
            # We're in the nighttime period that started with YESTERDAY's sunset
            yesterday = reference_time - timedelta(days=1)
            sunset = self.get_sunset(yesterday)
        else:
            # We're after sunrise, so use TODAY's sunset
            sunset = self.get_sunset(reference_time)

        if sunset is None:
            return None, None, "Unable to determine sunset time"

        window_start = sunset

        # Determine window end based on Night Charge configuration
        if night_charge_enabled and night_charge_time:
            # Window ends at night_charge_time
            window_end = night_charge_time
            window_desc = "sunset → night_charge_time"
        else:
            # Window ends at next sunrise
            window_end = self.get_next_sunrise_after(reference_time)
            if window_end is None:
                return None, None, "Unable to determine sunrise time"
            window_desc = "sunset → sunrise"

        return window_start, window_end, window_desc

    def is_in_blocking_window(
        self,
        reference_time: datetime,
        night_charge_enabled: bool = False,
        night_charge_time: datetime = None,
    ) -> tuple[bool, str]:
        """
        Check if reference_time is within Smart Blocker blocking window.

        Args:
            reference_time: Time to check
            night_charge_enabled: Whether Night Smart Charge is enabled
            night_charge_time: Time when Night Smart Charge starts

        Returns:
            Tuple of (is_blocked, reason)

        Example:
            >>> service = AstralTimeService(hass)
            >>> now = datetime(2024, 10, 30, 22, 0, 0)  # 22:00 (nighttime)
            >>> is_blocked, reason = service.is_in_blocking_window(now, False, None)
            >>> # Returns: (True, "Nighttime blocking active (sunset → sunrise)")
        """
        window_start, window_end, window_desc = self.get_blocking_window(
            reference_time, night_charge_enabled, night_charge_time
        )

        if window_start is None or window_end is None:
            return False, f"Window calculation failed: {window_desc}"

        # Simple check: is reference_time between window_start and window_end?
        # get_blocking_window already handles the complexity of determining
        # which sunset to use (yesterday's or today's)

        is_blocked = window_start <= reference_time < window_end

        if is_blocked:
            return True, f"Nighttime blocking active ({window_desc})"
        else:
            if reference_time < window_start:
                return False, "Before blocking window"
            else:
                return False, "After blocking window (charging allowed)"
