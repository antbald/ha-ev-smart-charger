"""Runtime data helpers for EV Smart Charger."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry


@dataclass
class LiveActivityState:
    """Shared state of the single EV charging Live Activity (v2.12.0).

    Every component builds its own MobileNotificationService, so before this
    existed each one throttled against its own clock: Night Charge (15s
    monitor), Boost (15s monitor) and the normal-charging monitor (60s) could
    each push the same tag independently. The tag is one shared resource on the
    phone, so its lifecycle and throttle live on the config entry instead.
    """

    active: bool = False
    signature: tuple | None = None
    last_update: datetime | None = None
    last_pushed_soc: float | None = None
    ended_at: datetime | None = None


@dataclass
class EVSCRuntimeData:
    """Per-config-entry runtime data."""

    config: dict[str, Any]
    expected_entity_count: int
    entity_ids_by_key: dict[str, str] = field(default_factory=dict)
    entities_by_key: dict[str, Any] = field(default_factory=dict)
    registration_event: asyncio.Event = field(default_factory=asyncio.Event)
    registered_entity_count: int = 0
    charger_controller: Any | None = None
    ev_soc_monitor: Any | None = None
    coordinator: Any | None = None
    priority_balancer: Any | None = None
    night_smart_charge: Any | None = None
    boost_charge: Any | None = None
    live_activity_monitor: Any | None = None
    smart_blocker: Any | None = None
    manual_stop: Any | None = None  # Manual Stop Charging control (v2.10.0 — issue #55)
    solar_surplus: Any | None = None
    hybrid_mode: Any | None = None  # Hybrid Inverter Mode (v1.8.0 — issue #20)
    log_manager: Any | None = None
    diagnostic_manager: Any | None = None
    power_model: Any | None = None  # ChargingModel (phase mode + charger model, v2.0.0)
    # Lifecycle + throttle of the shared EV charging Live Activity (v2.12.0)
    live_activity: LiveActivityState = field(default_factory=LiveActivityState)

    def register_entity(self, key: str, entity_id: str, entity: Any) -> None:
        """Register an integration-owned entity."""
        is_new = key not in self.entity_ids_by_key
        self.entity_ids_by_key[key] = entity_id
        self.entities_by_key[key] = entity

        if is_new:
            self.registered_entity_count += 1
            if self.registered_entity_count >= self.expected_entity_count:
                self.registration_event.set()

    def get_entity_id(self, key: str) -> str | None:
        """Get a registered entity ID by logical key."""
        return self.entity_ids_by_key.get(key)

    def get_entity(self, key: str) -> Any | None:
        """Get a registered entity instance by logical key."""
        return self.entities_by_key.get(key)


def get_runtime_data(entry: ConfigEntry) -> EVSCRuntimeData:
    """Return typed runtime data for a config entry."""
    runtime_data = entry.runtime_data
    if not isinstance(runtime_data, EVSCRuntimeData):
        raise RuntimeError("EV Smart Charger runtime data not initialized")
    return runtime_data
