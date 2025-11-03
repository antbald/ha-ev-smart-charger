"""Notification Service for centralized persistent notifications."""
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


class NotificationService:
    """
    Centralized service for sending persistent notifications.

    Provides standardized notification methods with consistent formatting.
    """

    def __init__(self, hass: HomeAssistant, integration_name: str = "EV Smart Charger"):
        """
        Initialize Notification Service.

        Args:
            hass: Home Assistant instance
            integration_name: Name to display in notification titles
        """
        self.hass = hass
        self.integration_name = integration_name

    async def send_success(
        self,
        title: str,
        message: str,
        notification_id: str = None,
        additional_data: dict = None,
    ) -> None:
        """
        Send success notification.

        Args:
            title: Notification title
            message: Notification message (supports markdown)
            notification_id: Optional custom notification ID (auto-generated if None)
            additional_data: Additional data to append to message
        """
        full_title = f"✅ {self.integration_name}: {title}"
        full_message = self._build_message(message, additional_data)
        notif_id = notification_id or self._generate_notification_id("success")

        await self._send_notification(full_title, full_message, notif_id)

    async def send_error(
        self,
        title: str,
        message: str,
        error: str = None,
        notification_id: str = None,
        additional_data: dict = None,
    ) -> None:
        """
        Send error notification.

        Args:
            title: Notification title
            message: Notification message (supports markdown)
            error: Error details to display
            notification_id: Optional custom notification ID (auto-generated if None)
            additional_data: Additional data to append to message
        """
        full_title = f"⚠️ {self.integration_name}: {title}"
        full_message = self._build_message(message, additional_data)

        if error:
            full_message += f"\n\n**Error:** {error}"

        notif_id = notification_id or self._generate_notification_id("error")

        await self._send_notification(full_title, full_message, notif_id)

    async def send_warning(
        self,
        title: str,
        message: str,
        notification_id: str = None,
        additional_data: dict = None,
    ) -> None:
        """
        Send warning notification.

        Args:
            title: Notification title
            message: Notification message (supports markdown)
            notification_id: Optional custom notification ID (auto-generated if None)
            additional_data: Additional data to append to message
        """
        full_title = f"⚠️ {self.integration_name}: {title}"
        full_message = self._build_message(message, additional_data)
        notif_id = notification_id or self._generate_notification_id("warning")

        await self._send_notification(full_title, full_message, notif_id)

    async def send_info(
        self,
        title: str,
        message: str,
        notification_id: str = None,
        additional_data: dict = None,
    ) -> None:
        """
        Send info notification.

        Args:
            title: Notification title
            message: Notification message (supports markdown)
            notification_id: Optional custom notification ID (auto-generated if None)
            additional_data: Additional data to append to message
        """
        full_title = f"ℹ️ {self.integration_name}: {title}"
        full_message = self._build_message(message, additional_data)
        notif_id = notification_id or self._generate_notification_id("info")

        await self._send_notification(full_title, full_message, notif_id)

    def _build_message(self, base_message: str, additional_data: dict = None) -> str:
        """
        Build complete notification message with optional additional data.

        Args:
            base_message: Base message content
            additional_data: Dictionary of additional key-value pairs to append

        Returns:
            Complete formatted message
        """
        message = base_message

        if additional_data:
            message += "\n\n"
            for key, value in additional_data.items():
                message += f"**{key}:** {value}\n"

        return message

    def _generate_notification_id(self, notification_type: str) -> str:
        """
        Generate unique notification ID based on timestamp.

        Args:
            notification_type: Type of notification (success, error, warning, info)

        Returns:
            Unique notification ID
        """
        timestamp = int(dt_util.now().timestamp())
        return f"evsc_{notification_type}_{timestamp}"

    async def _send_notification(
        self, title: str, message: str, notification_id: str
    ) -> None:
        """
        Internal method to send persistent notification.

        Args:
            title: Notification title
            message: Notification message
            notification_id: Unique notification ID
        """
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": title,
                "message": message,
                "notification_id": notification_id,
            },
            blocking=False,
        )

    async def dismiss(self, notification_id: str) -> None:
        """
        Dismiss a notification by ID.

        Args:
            notification_id: Notification ID to dismiss
        """
        await self.hass.services.async_call(
            "persistent_notification",
            "dismiss",
            {"notification_id": notification_id},
            blocking=False,
        )
