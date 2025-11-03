"""Entity Registry Service for centralized entity discovery."""
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


class EntityRegistryService:
    """
    Centralized service for entity registry operations.

    Provides caching and helper methods for entity discovery,
    filtering by config_entry_id.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str):
        """
        Initialize Entity Registry Service.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for filtering
        """
        self.hass = hass
        self.entry_id = entry_id
        self._registry = None

    def get_registry(self):
        """
        Get entity registry singleton with caching.

        Returns:
            Entity registry instance
        """
        if self._registry is None:
            self._registry = er.async_get(self.hass)
        return self._registry

    def find_by_suffix_filtered(self, suffix: str) -> str | None:
        """
        Find entity by suffix, filtered by config_entry_id.

        This method finds helper entities created by this integration
        by matching the unique_id suffix and config_entry_id.

        Args:
            suffix: Entity suffix (e.g., "evsc_forza_ricarica")

        Returns:
            Full entity_id or None if not found

        Example:
            >>> service = EntityRegistryService(hass, entry_id)
            >>> entity_id = service.find_by_suffix_filtered("evsc_forza_ricarica")
            >>> # Returns: "switch.ev_smart_charger_abc123_evsc_forza_ricarica"
        """
        registry = self.get_registry()

        for entity in registry.entities.values():
            # Filter by config_entry_id
            if entity.config_entry_id != self.entry_id:
                continue

            # Match suffix in unique_id
            if entity.unique_id and entity.unique_id.endswith(suffix):
                return entity.entity_id

        return None

    def find_multiple_by_pattern(self, pattern_suffix: str) -> list[str]:
        """
        Find multiple entities matching a pattern suffix.

        Args:
            pattern_suffix: Pattern to match (e.g., "evsc_ev_min_soc_")

        Returns:
            List of matching entity_ids

        Example:
            >>> service = EntityRegistryService(hass, entry_id)
            >>> entities = service.find_multiple_by_pattern("evsc_ev_min_soc_")
            >>> # Returns: ["number.evsc_ev_min_soc_monday", "number.evsc_ev_min_soc_tuesday", ...]
        """
        registry = self.get_registry()
        matches = []

        for entity in registry.entities.values():
            # Filter by config_entry_id
            if entity.config_entry_id != self.entry_id:
                continue

            # Match pattern in unique_id
            if entity.unique_id and pattern_suffix in entity.unique_id:
                matches.append(entity.entity_id)

        return matches

    def get_all_integration_entities(self) -> list[str]:
        """
        Get all entity_ids for this integration.

        Returns:
            List of all entity_ids belonging to this config entry
        """
        registry = self.get_registry()
        entities = []

        for entity in registry.entities.values():
            if entity.config_entry_id == self.entry_id:
                entities.append(entity.entity_id)

        return entities

    def entity_exists(self, entity_id: str) -> bool:
        """
        Check if entity exists in registry for this config entry.

        Args:
            entity_id: Entity ID to check

        Returns:
            True if entity exists and belongs to this config entry
        """
        registry = self.get_registry()
        entity = registry.async_get(entity_id)

        if not entity:
            return False

        return entity.config_entry_id == self.entry_id
