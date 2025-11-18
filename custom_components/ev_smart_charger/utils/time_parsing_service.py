"""Time Parsing Service for centralized time string handling."""
from datetime import datetime, timedelta


class TimeParsingService:
    """
    Centralized service for time parsing and conversion.

    Provides standardized methods for parsing time strings and
    converting them to datetime objects.
    """

    @staticmethod
    def parse_time_string(time_str: str) -> tuple[int, int, int]:
        """
        Parse 'HH:MM:SS' time string.

        Args:
            time_str: Time string in format "HH:MM:SS"

        Returns:
            Tuple of (hour, minute, second)

        Raises:
            ValueError: If time string is invalid format
            TypeError: If time_str is not a string

        Example:
            >>> hour, minute, second = TimeParsingService.parse_time_string("01:30:00")
            >>> # Returns: (1, 30, 0)
        """
        if not isinstance(time_str, str):
            raise TypeError(f"Expected string, got {type(time_str).__name__}")

        parts = time_str.split(":")

        if len(parts) != 3:
            raise ValueError(
                f"Invalid time format '{time_str}'. Expected 'HH:MM:SS'"
            )

        try:
            hour = int(parts[0])
            minute = int(parts[1])
            second = int(parts[2])
        except ValueError as e:
            raise ValueError(
                f"Invalid time components in '{time_str}': {e}"
            ) from e

        # Validate ranges
        if not (0 <= hour <= 23):
            raise ValueError(f"Hour must be 0-23, got {hour}")
        if not (0 <= minute <= 59):
            raise ValueError(f"Minute must be 0-59, got {minute}")
        if not (0 <= second <= 59):
            raise ValueError(f"Second must be 0-59, got {second}")

        return hour, minute, second

    @staticmethod
    def time_string_to_datetime(
        time_str: str, reference_date: datetime
    ) -> datetime:
        """
        Convert time string to datetime using reference date.

        Creates a datetime object by combining the time from time_str
        with the date from reference_date.

        Args:
            time_str: Time string in format "HH:MM:SS"
            reference_date: Reference datetime to use for the date component

        Returns:
            Datetime object with time from time_str and date from reference_date

        Raises:
            ValueError: If time string is invalid format

        Example:
            >>> ref = datetime(2024, 10, 30, 12, 0, 0)
            >>> dt = TimeParsingService.time_string_to_datetime("01:30:00", ref)
            >>> # Returns: datetime(2024, 10, 30, 1, 30, 0)
        """
        hour, minute, second = TimeParsingService.parse_time_string(time_str)

        return reference_date.replace(
            hour=hour, minute=minute, second=second, microsecond=0
        )

    @staticmethod
    def time_string_to_next_occurrence(
        time_str: str, reference_time: datetime
    ) -> datetime:
        """
        Convert time string to next occurrence after reference_time.

        If the time has already passed today, returns tomorrow's occurrence.
        If the time hasn't passed yet today, returns today's occurrence.

        Args:
            time_str: Time string in format "HH:MM:SS"
            reference_time: Current datetime to compare against

        Returns:
            Datetime of next occurrence (today or tomorrow)

        Example:
            >>> now = datetime(2024, 10, 30, 12, 0, 0)  # Noon
            >>> # Morning time (already passed)
            >>> dt1 = TimeParsingService.time_string_to_next_occurrence("08:00:00", now)
            >>> # Returns: datetime(2024, 10, 31, 8, 0, 0)  # Tomorrow
            >>>
            >>> # Evening time (not yet passed)
            >>> dt2 = TimeParsingService.time_string_to_next_occurrence("18:00:00", now)
            >>> # Returns: datetime(2024, 10, 30, 18, 0, 0)  # Today
        """
        target_time = TimeParsingService.time_string_to_datetime(
            time_str, reference_time
        )

        # If time has strictly passed today (not equal), add one day
        # v1.3.26: Changed from <= to < to allow equality (01:00:00 at 01:00:01 = today)
        if target_time < reference_time:
            target_time += timedelta(days=1)

        return target_time

    @staticmethod
    def is_valid_time_string(time_str: str) -> bool:
        """
        Check if time string is valid format without raising exception.

        Args:
            time_str: Time string to validate

        Returns:
            True if valid "HH:MM:SS" format, False otherwise

        Example:
            >>> TimeParsingService.is_valid_time_string("01:30:00")  # True
            >>> TimeParsingService.is_valid_time_string("25:00:00")  # False
            >>> TimeParsingService.is_valid_time_string("invalid")  # False
        """
        try:
            TimeParsingService.parse_time_string(time_str)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def format_time_string(hour: int, minute: int, second: int = 0) -> str:
        """
        Format time components into 'HH:MM:SS' string.

        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
            second: Second (0-59), defaults to 0

        Returns:
            Formatted time string "HH:MM:SS"

        Raises:
            ValueError: If components are out of range

        Example:
            >>> TimeParsingService.format_time_string(1, 30, 0)
            >>> # Returns: "01:30:00"
        """
        if not (0 <= hour <= 23):
            raise ValueError(f"Hour must be 0-23, got {hour}")
        if not (0 <= minute <= 59):
            raise ValueError(f"Minute must be 0-59, got {minute}")
        if not (0 <= second <= 59):
            raise ValueError(f"Second must be 0-59, got {second}")

        return f"{hour:02d}:{minute:02d}:{second:02d}"
