"""Entity helper utilities for EVSC integration."""
from __future__ import annotations
from homeassistant.core import HomeAssistant


def find_by_suffix(hass: HomeAssistant, suffix: str) -> str | None:
    """
    Find entity by suffix.

    Args:
        hass: Home Assistant instance
        suffix: Entity suffix (e.g., "evsc_forza_ricarica")

    Returns:
        Full entity_id or None if not found
    """
    for entity_id in hass.states.async_entity_ids():
        if entity_id.endswith(suffix):
            return entity_id
    return None


def find_by_pattern(hass: HomeAssistant, pattern: str) -> list[str]:
    """
    Find all entities matching a pattern.

    Args:
        hass: Home Assistant instance
        pattern: Pattern to match (supports wildcards)

    Returns:
        List of matching entity_ids
    """
    import fnmatch

    matches = []
    for entity_id in hass.states.async_entity_ids():
        if fnmatch.fnmatch(entity_id, pattern):
            matches.append(entity_id)
    return matches


def get_helper_entity(hass: HomeAssistant, suffix: str, component_name: str) -> str:
    """
    Get helper entity by suffix with error handling.

    Args:
        hass: Home Assistant instance
        suffix: Entity suffix
        component_name: Component name for error logging

    Returns:
        Entity ID

    Raises:
        ValueError: If entity not found
    """
    entity_id = find_by_suffix(hass, suffix)
    if not entity_id:
        raise ValueError(f"[{component_name}] Helper entity not found: {suffix}")
    return entity_id


def is_entity_on(hass: HomeAssistant, entity_id: str) -> bool:
    """
    Check if entity is on.

    Args:
        hass: Home Assistant instance
        entity_id: Entity ID to check

    Returns:
        True if state is 'on', False otherwise
    """
    if not entity_id:
        return False
    state = hass.states.get(entity_id)
    return state.state == "on" if state else False
