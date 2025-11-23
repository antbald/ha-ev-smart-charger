"""Global fixtures for ev_smart_charger integration tests."""
import pytest
from unittest.mock import patch, AsyncMock, Mock

pytest_plugins = "pytest_homeassistant_custom_component"

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    yield

@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with patch("homeassistant.components.persistent_notification.async_create"), \
         patch("homeassistant.components.persistent_notification.async_dismiss"):
        yield

@pytest.fixture
def mock_charger_controller():
    """Mock ChargerController."""
    with patch("custom_components.ev_smart_charger.charger_controller.ChargerController") as mock:
        instance = mock.return_value
        instance.start_charger = AsyncMock(return_value=True)
        instance.stop_charger = AsyncMock(return_value=True)
        instance.set_amperage = AsyncMock(return_value=True)
        instance.is_charging = AsyncMock(return_value=False)
        instance.get_current_amperage = AsyncMock(return_value=0)
        yield instance

@pytest.fixture
def mock_priority_balancer():
    """Mock PriorityBalancer."""
    with patch("custom_components.ev_smart_charger.priority_balancer.PriorityBalancer") as mock:
        instance = mock.return_value
        instance.is_enabled = Mock(return_value=True)
        instance.calculate_priority = AsyncMock(return_value="EV")
        instance.is_ev_target_reached = AsyncMock(return_value=False)
        instance.is_home_target_reached = AsyncMock(return_value=False)
        yield instance
