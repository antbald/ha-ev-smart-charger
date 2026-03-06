# EV Smart Charger Dashboard Frontend

This integration now serves a bundled Lovelace module at:

- `/api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js`

Add it as a dashboard resource:

```yaml
lovelace:
  resources:
    - url: /api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js
      type: module
```

Then add the card:

```yaml
type: custom:ev-smart-charger-dashboard
title: Tesla Charge Deck
entity_prefix: ev_smart_charger_<entry_id>
charging_power_entity: sensor.current_charging_power_tesla
ev_soc_entity: sensor.tesla_battery
home_battery_soc_entity: sensor.stato_batteria_luxpower
solar_power_entity: sensor.produzione_solare_totale
grid_import_entity: sensor.grid_power_import_w
current_entity: number.wallbox_current
```

Notes:

- `entity_prefix` is required and must match the helper entity prefix created by this integration.
- Optional telemetry entities (`charging_power_entity`, `ev_soc_entity`, etc.) enrich the hero metrics but are not required.
- The card calls native Home Assistant services directly (`switch.toggle`, `number.set_value`, `select.select_option`, `time.set_value`).
