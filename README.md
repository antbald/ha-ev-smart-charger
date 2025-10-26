# EV Smart Charger

A Home Assistant integration for smart EV charging control.

## Features

- **EVSC State** sensor: Displays current charging state
- **EVSC Mode** selector: Choose between charging modes:
  - `off` - Charger disabled
  - `cheap` - Charge during cheapest electricity hours
  - `pv_hybrid` - Charge using solar PV with grid backup

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "EV Smart Charger" in HACS
3. Click Install
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/ev_smart_charger` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration
4. Search for "EV Smart Charger"

## Configuration

The integration is configured through the UI:

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "EV Smart Charger"
4. Follow the setup wizard

## Version

Current version: 0.1.0
