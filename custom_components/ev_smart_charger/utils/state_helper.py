"""State helper utilities for EVSC integration."""
from homeassistant.core import HomeAssistant
import logging

_LOGGER = logging.getLogger(__name__)


def get_state(hass: HomeAssistant, entity_id: str) -> str | None:
    """Get entity state safely."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    return state.state if state else None


def get_float(hass: HomeAssistant, entity_id: str, default: float = 0.0) -> float:
    """
    Get entity state as float with error handling.

    Args:
        hass: Home Assistant instance
        entity_id: Entity ID to read
        default: Default value if read fails

    Returns:
        Float value or default
    """
    try:
        state = get_state(hass, entity_id)
        if state in [None, "unknown", "unavailable"]:
            _LOGGER.warning(
                f"Entity {entity_id} state is {state}, using default {default}"
            )
            return default
        return float(state)
    except (ValueError, TypeError) as e:
        _LOGGER.error(
            f"Error converting {entity_id} state to float: {e}, using default {default}"
        )
        return default


def get_int(hass: HomeAssistant, entity_id: str, default: int = 0) -> int:
    """Get entity state as int with error handling."""
    return int(get_float(hass, entity_id, float(default)))


def get_bool(hass: HomeAssistant, entity_id: str, default: bool = False) -> bool:
    """Get entity state as boolean."""
    state = get_state(hass, entity_id)
    if state is None:
        return default
    return state.lower() in ["on", "true", "1", "yes"]


def validate_sensor(
    hass: HomeAssistant, entity_id: str, sensor_name: str
) -> tuple[bool, str | None]:
    """
    Validate sensor state.

    Returns:
        (is_valid, error_message)
    """
    state = get_state(hass, entity_id)

    if state is None:
        return False, f"Sensor {sensor_name} ({entity_id}) not found"

    if state in ["unknown", "unavailable"]:
        return False, f"Sensor {sensor_name} ({entity_id}) state is '{state}'"

    try:
        float(state)
        return True, None
    except (ValueError, TypeError):
        return False, f"Sensor {sensor_name} ({entity_id}) has invalid value '{state}'"
