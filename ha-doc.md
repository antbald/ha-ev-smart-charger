# Home Assistant Plugin Development Guide

**Comprehensive guide for developing Home Assistant integrations from scratch**

## Overview

Home Assistant is a Python-based home automation platform with an event-driven async architecture. **Integrations** (formerly called "components") are the fundamental building blocks that extend Home Assistant's functionality, allowing it to connect to devices, services, and platforms.

### Core architecture principles

Home Assistant runs on **Python's asyncio module**, using a single event loop to handle all operations concurrently without traditional threading complexity. The architecture underwent a major transformation in version 0.29 (September 2016) to adopt this async-first approach, providing backward compatibility while enabling modern async/await patterns.

The system consists of four fundamental components that work together to manage the entire platform:

**Event Bus** (`hass.bus`) serves as the central nervous system, facilitating event firing and listening throughout the system. Any component can fire events with arbitrary string names and JSON-serializable data, while other components listen for specific events to trigger actions.

**State Machine** (`hass.states`) tracks the current state of all entities in the system. When entity states change, it automatically fires `state_changed` events, enabling reactive programming patterns throughout the platform.

**Service Registry** (`hass.services`) manages callable services that provide standardized interfaces for controlling entities and performing actions. Services follow a `domain.service` naming convention (e.g., `light.turn_on`).

**Config** (`hass.config`) holds system-wide configuration including location data, temperature preferences, and the configuration directory path.

### The hass object

The `hass` object is the central Home Assistant instance providing access to all system components. This object is available in component setup functions, platform setup functions, and as `self.hass` within entity classes. Key methods include `hass.add_job()`, `hass.async_add_job()`, and `hass.async_create_task()` for managing asynchronous operations.

### Integration architecture

Each integration has a unique **domain** (identifier like "hue" or "mqtt") and can listen for events, trigger events, offer services, and maintain entity states. Integrations are written entirely in Python and follow a standardized structure that makes them easy to develop and maintain.

## Integration Types and Components

### Core integration types

Integrations specify their type in the manifest.json file:

**Device integrations** represent single physical or logical devices (e.g., ESPHome nodes). Each config entry typically maps to one device.

**Hub integrations** act as gateways to multiple devices (e.g., Philips Hue bridge, Z-Wave controller). These manage connections to hardware that controls multiple endpoints.

**Service integrations** provide single services without direct device control (e.g., DuckDNS, AdGuard). These often handle background tasks or external API interactions.

**Helper integrations** create utility entities for automations (e.g., input_boolean, groups). These enable complex automation logic without physical devices.

**Entity integrations** provide basic entity platforms for sensors, lights, and switches. These are rarely used directly—most integrations are device or hub types.

### Entities explained

Entities represent sensors, actuators, or data points in Home Assistant. Each entity has an `entity_id` formatted as `domain.object_id` (e.g., `light.kitchen_ceiling`). Entities abstract away Home Assistant's internal complexity, following predefined classes that standardize behavior across integrations.

Key entity types include sensors (read-only data), switches (on/off control), lights (with brightness/color), binary sensors (on/off state), and many others. Each entity type inherits from a base class that defines required methods and properties.

### Platforms vs integrations

The relationship between these concepts is hierarchical: **Integrations** are complete modules in directories like `custom_components/my_integration/`. **Platforms** are entity-specific implementation files within integrations (e.g., `hue/light.py` implements the light platform for Hue). **Domains** are standardized entity types defined by Home Assistant core (light, switch, sensor).

An integration like Philips Hue creates platforms for lights and sensors that hook into the respective domains, allowing Home Assistant to expose a unified interface for all lights regardless of their underlying integration.

### Core vs custom integrations

**Core integrations** live in `homeassistant/components/`, are bundled with Home Assistant, and require no version key in their manifest. They're maintained by the core team and automatically updated with Home Assistant releases.

**Custom integrations** reside in `<config_dir>/custom_components/`, must include a version key in manifest.json (mandatory since 2021.6), and are developed and maintained by community members. The architecture is identical between core and custom—the main differences are location, version requirements, and maintenance responsibility.

### Discovery mechanisms

Home Assistant supports multiple discovery protocols configured in manifest.json:

**Zeroconf** discovers devices via mDNS/DNS-SD, matching on service types and properties. **SSDP** uses Simple Service Discovery Protocol for UPnP devices. **Bluetooth** matches on local names, service UUIDs, and manufacturer IDs. **USB** detects devices by VID/PID, serial number, or manufacturer. **DHCP** identifies devices by hostname patterns and MAC addresses. **MQTT** subscribes to topics for MQTT-based device discovery.

## Development Environment Setup

### Prerequisites

**Python 3.13 is required** for current Home Assistant core development. Using incorrect Python versions will create incompatible virtual environments that must be rebuilt.

System dependencies vary by operating system:

**Ubuntu/Debian systems** require:
```bash
sudo apt-get update
sudo apt-get install python3-pip python3-dev python3-venv autoconf libssl-dev \
  libxml2-dev libxslt1-dev libjpeg-dev libffi-dev libudev-dev zlib1g-dev \
  pkg-config libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev \
  libswscale-dev libswresample-dev libavfilter-dev ffmpeg libgammu-dev build-essential
```

**Fedora systems** need:
```bash
sudo dnf update
sudo dnf install python3-pip python3-devel python3-virtualenv autoconf openssl-devel \
  libxml2-devel libxslt-devel libjpeg-turbo-devel libffi-devel systemd-devel \
  zlib-devel pkgconf-pkg-config libavformat-free-devel libavcodec-free-devel \
  libavdevice-free-devel libavutil-free-devel libswscale-free-devel ffmpeg-free-devel \
  libavfilter-free-devel ffmpeg-free gcc gcc-c++ cmake
```

**macOS installations** use Homebrew:
```bash
brew install python3 autoconf ffmpeg cmake make
```

**Windows developers** must use Windows Subsystem for Linux (WSL). Install WSL and Ubuntu from Windows Store, then follow Linux instructions within WSL. Keep all code and repositories in the WSL environment to avoid file permission issues.

### Development environment options

**VS Code Dev Container (recommended)** provides the easiest setup with a preconfigured environment including all tools:

1. Install Visual Studio Code, Docker Desktop, and the Dev Containers extension
2. Fork the home-assistant/core repository on GitHub
3. Open VS Code Command Palette (Ctrl+Shift+P / Cmd+Shift+P)
4. Select "Dev Containers: Clone Repository in Container Volume"
5. Paste your fork URL and wait for the container to build

Once built, press F5 to start debugging or use the "Run Home Assistant Core" task. Access Home Assistant at `http://localhost:8123`.

**Manual local environment** suits developers preferring traditional setups:

```bash
# Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/core
cd core
git remote add upstream https://github.com/home-assistant/core.git

# Run setup script
script/setup

# Activate virtual environment (required each session)
source .venv/bin/activate

# Run Home Assistant
hass -c config
```

The `config` directory at the repository root stores Home Assistant configuration files.

### Repository structure

Home Assistant looks for integrations in two locations, checked in order:

1. `<config directory>/custom_components/<domain>` (custom integrations)
2. `homeassistant/components/<domain>` (built-in integrations)

Custom integrations in the first location take precedence, allowing overrides of built-in integrations (though this is not recommended).

## Creating Your First Integration

### Directory structure

The minimal integration structure requires just two files:

```
custom_components/
└── your_integration/
    ├── manifest.json
    └── __init__.py
```

A complete integration with platforms looks like:

```
custom_components/
└── your_integration/
    ├── manifest.json
    ├── __init__.py
    ├── config_flow.py
    ├── const.py
    ├── coordinator.py
    ├── sensor.py
    ├── switch.py
    ├── light.py
    ├── services.yaml
    ├── strings.json
    └── translations/
        └── en.json
```

### Using the scaffold tool

The official scaffold generator creates a complete integration structure:

```bash
python3 -m script.scaffold integration
```

This interactive tool prompts for:
- Domain (unique identifier)
- Integration name
- GitHub handle
- PyPI dependencies
- Data gathering method (polling, push, etc.)
- Authentication requirements
- Discovery support
- OAuth2 support

The scaffold automatically creates manifest.json, __init__.py, config_flow.py, const.py, platform files, test files, and translation infrastructure.

### Minimal manifest.json

Every integration requires a manifest.json file with metadata:

```json
{
  "domain": "your_integration",
  "name": "Your Integration",
  "codeowners": ["@yourusername"],
  "dependencies": [],
  "documentation": "https://github.com/yourusername/your_integration",
  "integration_type": "service",
  "iot_class": "local_polling",
  "requirements": [],
  "version": "1.0.0"
}
```

**Key fields explained:**

**domain** is the unique identifier (lowercase, underscores only, cannot change after publication). This matches the directory name.

**name** provides the human-readable display name shown in the UI.

**version** is required for custom integrations (format: SemVer or CalVer like "1.0.0"), omitted for core integrations.

**codeowners** lists GitHub usernames (with @) responsible for the integration.

**requirements** specifies Python packages from PyPI (e.g., `["requests==2.28.0"]`).

**integration_type** must be one of: device, hub, service, helper, entity, system, or virtual.

**iot_class** describes communication method: assumed_state, cloud_polling, cloud_push, local_polling, local_push, or calculated.

**config_flow** set to true enables UI-based configuration (required for Bronze tier).

### Basic __init__.py implementation

Async setup (recommended):

```python
"""The Your Integration integration."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

DOMAIN = "your_integration"
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
```

### Config flow for UI setup

Config flows enable user-friendly UI configuration (required for core integrations):

```python
"""Config flow for Your Integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_API_KEY

from .const import DOMAIN

class YourIntegrationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""
    
    VERSION = 1
    
    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            try:
                # Validate input
                info = await self._test_credentials(
                    user_input[CONF_HOST],
                    user_input[CONF_API_KEY]
                )
                
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=user_input[CONF_HOST],
                    data=user_input
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_API_KEY): str,
            }),
            errors=errors,
        )
    
    async def _test_credentials(self, host, api_key):
        """Validate credentials."""
        # Implement validation logic
        return {"unique_id": "device_id"}
```

### Platform implementation

Sensor platform example:

```python
"""Sensor platform for Your Integration."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([YourSensor(data)], True)

class YourSensor(SensorEntity):
    """Your sensor entity."""
    
    def __init__(self, data):
        """Initialize the sensor."""
        self._attr_name = "Your Sensor"
        self._attr_unique_id = "your_sensor_1"
        self._attr_native_value = None
        self._data = data
    
    async def async_update(self):
        """Fetch new state data for the sensor."""
        self._attr_native_value = "Sample Value"
```

## Home Assistant API and Core Concepts

### The REST API

Home Assistant exposes a comprehensive REST API at `http://IP_ADDRESS:8123/api/`. All requests require bearer token authentication:

```python
import requests

headers = {
    "Authorization": "Bearer YOUR_TOKEN",
    "content-type": "application/json"
}

# Get all states
response = requests.get("http://localhost:8123/api/states", headers=headers)

# Get specific entity
response = requests.get("http://localhost:8123/api/states/light.kitchen", headers=headers)

# Call a service
payload = {"entity_id": "light.kitchen", "brightness": 255}
response = requests.post("http://localhost:8123/api/services/light/turn_on", 
                        json=payload, headers=headers)

# Fire an event
response = requests.post("http://localhost:8123/api/events/my_event", 
                        json={"data": "value"}, headers=headers)
```

Key endpoints include `/api/config`, `/api/states`, `/api/services/<domain>/<service>`, `/api/events/<event_type>`, and `/api/history/period/<timestamp>`.

### Entity base classes

All entities inherit from `homeassistant.helpers.entity.Entity` and implement required properties:

```python
from homeassistant.helpers.entity import Entity

class MyEntity(Entity):
    """Example entity implementation."""
    
    # Naming (new integrations must set has_entity_name)
    _attr_has_entity_name = True
    _attr_name = None  # For main device feature
    
    # Identity
    _attr_unique_id = "unique_identifier"
    
    # State
    _attr_available = True
    _attr_should_poll = True
    
    # Device association
    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": "Device Name",
            "manufacturer": "Manufacturer",
            "model": "Model",
            "sw_version": "1.0.0",
        }
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        return {
            "custom_attribute": "value"
        }
```

### Entity types and their classes

**Sensor entities** represent read-only data:

```python
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature

class MySensor(SensorEntity):
    """Temperature sensor example."""
    
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    
    @property
    def native_value(self):
        """Return the sensor value."""
        return self._temperature
```

**Switch entities** provide binary on/off control:

```python
from homeassistant.components.switch import SwitchEntity

class MySwitch(SwitchEntity):
    """Switch example."""
    
    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._api.turn_on()
        self._is_on = True
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._api.turn_off()
        self._is_on = False
```

**Light entities** support brightness and color:

```python
from homeassistant.components.light import (
    LightEntity,
    ColorMode,
    ATTR_BRIGHTNESS,
)

class MyLight(LightEntity):
    """Light with brightness support."""
    
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    
    @property
    def brightness(self):
        """Return brightness."""
        return self._brightness
    
    @property
    def is_on(self):
        """Return true if light is on."""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn light on."""
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]
            await self._api.set_brightness(self._brightness)
        else:
            await self._api.turn_on()
        self._is_on = True
```

### State management

The state machine tracks all entity states in memory and persists them to the database. State objects contain:

```python
{
    "entity_id": "light.kitchen",
    "state": "on",
    "attributes": {
        "brightness": 255,
        "friendly_name": "Kitchen Light"
    },
    "last_changed": "2024-01-01T12:00:00+00:00",
    "last_updated": "2024-01-01T12:00:00+00:00",
    "context": {...}
}
```

Direct state manipulation (not recommended—use entities instead):

```python
# Set state
hass.states.async_set("sensor.example", "25", {
    "unit_of_measurement": "°C"
})

# Get state
state = hass.states.get("light.kitchen")
if state:
    is_on = state.state == "on"
    brightness = state.attributes.get("brightness")
```

### Event system

The event bus enables decoupled communication throughout Home Assistant:

```python
from homeassistant.core import callback

# Fire event
hass.bus.async_fire("custom_event", {"key": "value"})

# Listen to event
@callback
def handle_event(event):
    """Handle the event."""
    data = event.data.get("key")
    # Process event

hass.bus.async_listen("custom_event", handle_event)
```

Built-in events include `state_changed` (most common), `service_called`, `homeassistant_start`, `homeassistant_started`, `homeassistant_stop`, and `component_loaded`.

### Service implementation

Services provide callable actions for entities:

```python
async def async_setup(hass, config):
    """Set up services."""
    
    async def handle_my_service(call):
        """Handle the service call."""
        name = call.data.get("name", "World")
        await do_something(name)
    
    hass.services.async_register(
        DOMAIN,
        "my_service",
        handle_my_service
    )
    
    return True
```

Service schema defined in services.yaml:

```yaml
my_service:
  name: My Service
  description: Does something useful
  target:
    entity:
      domain: switch
  fields:
    name:
      required: true
      example: "Kitchen"
      selector:
        text:
```

Entity-specific services:

```python
from homeassistant.helpers import entity_platform

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up platform."""
    # ... entity setup ...
    
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "set_timer",
        {vol.Required("duration"): cv.time_period},
        "async_set_timer",
    )

# In entity class
async def async_set_timer(self, duration):
    """Set timer service method."""
    await self._api.set_timer(duration)
```

### DataUpdateCoordinator pattern

The DataUpdateCoordinator centralizes API calls for multiple entities, handling rate limiting and error recovery:

```python
from datetime import timedelta
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
    CoordinatorEntity,
)
import async_timeout

class MyCoordinator(DataUpdateCoordinator):
    """Manage fetching data from API."""
    
    def __init__(self, hass, client):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="my_integration",
            update_interval=timedelta(seconds=30),
        )
        self.client = client
    
    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            async with async_timeout.timeout(10):
                return await self.client.async_get_data()
        except ApiAuthError as err:
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            raise UpdateFailed(f"Error: {err}") from err

# Setup coordinator
coordinator = MyCoordinator(hass, client)
await coordinator.async_config_entry_first_refresh()

# Entity using coordinator
class MySensor(CoordinatorEntity, SensorEntity):
    """Sensor using coordinator."""
    
    def __init__(self, coordinator):
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "sensor_1"
    
    @property
    def native_value(self):
        """Return sensor value."""
        return self.coordinator.data["temperature"]
    
    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success
```

## Best Practices and Coding Standards

### Code style requirements

Home Assistant enforces strict PEP8 compliance via Ruff with a **maximum line length of 79 characters** (non-negotiable). All code must follow PEP 257 docstring conventions.

**Type hints are mandatory** for all functions. Fully typed modules should be added to the `.strict-typing` file.

**String formatting uses f-strings:**

```python
# Correct
message = f"{some_value} {some_other_value}"

# Exception: Logging uses % formatting
_LOGGER.info("Can't connect to %s at %s", host, port)

# Wrong - don't use
message = "{} {}".format("New", "style")
message = "%s %s" % ("Old", "style")
```

### Logging best practices

Logger configuration:

```python
import logging

_LOGGER = logging.getLogger(__name__)
```

**Logging rules:**
- Never add platform/component name to messages (added automatically)
- No period at end of log messages (syslog style)
- Never log credentials, API keys, tokens, or passwords
- Restrict `_LOGGER.info` to user-facing messages
- Use `_LOGGER.debug` for developer information

```python
# Good
_LOGGER.error("No route to device: %s", self._resource)
_LOGGER.debug("API response: %s", response)

# Bad
_LOGGER.info("my_integration: Device connected.")  # Redundant prefix
_LOGGER.error("Connection failed.")  # No period, but missing context
```

### Integration quality scale

Home Assistant uses a four-tier quality scale for integrations:

**Bronze tier** (minimum for all new integrations):
- UI-based setup (config flow)
- Adheres to coding standards
- Automated tests for config entry setup
- Basic end-user documentation

**Silver tier** (reliability and robustness):
- One or more active code owners
- Stable experience under various conditions
- Automatic recovery from connection errors
- Re-authentication on auth failures
- Detailed documentation with troubleshooting

**Gold tier** (best user experience):
- Automatic discovery support
- UI reconfiguration
- Translation support
- Full automated test coverage
- Extensive documentation with examples
- Required for "Works with Home Assistant" program

**Platinum tier** (technical excellence):
- Fully typed with complete type annotations
- Fully asynchronous codebase
- Efficient data handling
- Clear code comments

### Async/await patterns

All core methods have async versions (`async_*`) for use within the event loop. When to use async:

```python
# Async setup
async def async_setup_entry(hass, entry):
    """Set up from a config entry."""
    # Async code here
    return True

# Async entity update
class MyEntity(Entity):
    async def async_update(self):
        """Retrieve latest state."""
        self._state = await async_fetch_state()

# Call sync functions from async
result = await hass.async_add_executor_job(blocking_function, arg1, arg2)

# Create async tasks
hass.async_create_task(async_function())
```

**Critical rule:** Entity properties must NEVER do I/O. All data must be fetched in `async_update()`, cached on the entity, and read from cache in properties to prevent blocking the event loop.

### Error handling

Handle setup failures gracefully with appropriate exceptions:

```python
async def async_setup_entry(hass, entry):
    """Setup the config entry."""
    device = MyDevice(entry.data[CONF_HOST])
    
    try:
        await device.async_setup()
    except AuthFailed as ex:
        # Triggers automatic reauth flow
        raise ConfigEntryAuthFailed(
            f"Credentials expired for {device.name}"
        ) from ex
    except (asyncio.TimeoutError, TimeoutException) as ex:
        # Retries automatically
        raise ConfigEntryNotReady(
            f"Timeout connecting to {device.ipaddr}"
        ) from ex
    
    return True
```

**Exception types:**
- `ConfigEntryNotReady`: Automatically retries setup later (device offline/unavailable)
- `ConfigEntryAuthFailed`: Triggers reauth flow (expired credentials)
- `UpdateFailed`: Indicates update failure in DataUpdateCoordinator

### DataUpdateCoordinator best practices

Always use CoordinatorEntity with DataUpdateCoordinator:

```python
class MyEntity(CoordinatorEntity, SensorEntity):
    """Entity with coordinator."""
    
    # should_poll automatically set to False by CoordinatorEntity
    
    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
    
    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from coordinator."""
        # Update entity attributes from coordinator.data
        self._attr_native_value = self.coordinator.data["value"]
        self.async_write_ha_state()
```

Set `always_update=False` in coordinator if data can be compared with `__eq__` to avoid unnecessary callbacks.

### Common pitfalls to avoid

1. **Using tabs in YAML** - Use 2 spaces for indentation
2. **Blocking I/O in async context** - Always use `await hass.async_add_executor_job()`
3. **Not using CoordinatorEntity with DataUpdateCoordinator** - Results in unnecessary polling
4. **Logging during retries** - Let built-in exception handling manage it
5. **Not setting `should_poll = False` with coordinator** - Causes double updates
6. **Doing I/O in entity properties** - Cache data in `async_update()` instead
7. **Accessing integration internals in tests** - Use public interfaces (state machine, service registry)

## Testing and Debugging

### Test framework setup

Home Assistant uses pytest for testing. Install test requirements:

```bash
# Install test dependencies
uv pip install -r requirements_test_all.txt

# Or in VS Code
# Task: "Install all Test Requirements"
```

### Running tests

```bash
# Run full test suite
pytest tests

# Run specific integration tests with coverage
pytest ./tests/components/your_integration/ \
  --cov=homeassistant.components.your_integration \
  --cov-report term-missing -vv

# Run single test
pytest tests/components/your_integration/test_init.py -k test_setup

# Show 10 slowest tests
pytest tests/test_core.py --duration=10

# Stop on first failure
pytest tests/test_core.py -x
```

### Test structure and fixtures

Use `pytest-homeassistant-custom-component` for custom integrations:

```bash
pip install pytest-homeassistant-custom-component
```

Available fixtures:
- `hass`: Home Assistant instance
- `aioclient_mock`: Mock aiohttp client responses
- `enable_custom_integrations`: Required for custom components

Test example:

```python
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.async_mock import AsyncMock

async def test_async_setup_entry(hass):
    """Test setting up an entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.168.1.1", "api_key": "test_key"},
        unique_id="test_id"
    )
    entry.add_to_hass(hass)
    
    with patch("custom_components.my_integration.MyApi") as mock_api:
        mock_api.return_value.connect = AsyncMock(return_value=True)
        
        assert await async_setup_entry(hass, entry)
        await hass.async_block_till_done()
        
        assert DOMAIN in hass.data
        assert len(hass.states.async_all()) > 0
```

### Testing config flows

```python
async def test_config_flow(hass):
    """Test config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    
    # Submit form
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "192.168.1.1", "api_key": "test"}
    )
    
    assert result["type"] == "create_entry"
    assert result["title"] == "My Device"
```

### Mocking async functions

```python
from pytest_homeassistant_custom_component.async_mock import AsyncMock

async def test_async_update_failed():
    """Test failed async_update."""
    api = MagicMock()
    api.get_data = AsyncMock(side_effect=ApiException)
    
    sensor = MySensor(api)
    await sensor.async_update()
    
    assert sensor.available is False
```

### Snapshot testing

```python
from syrupy.assertion import SnapshotAssertion

async def test_sensor(hass: HomeAssistant, snapshot: SnapshotAssertion):
    """Test the sensor state."""
    state = hass.states.get("sensor.whatever")
    assert state == snapshot

# Create/update snapshot:
# pytest tests/components/example/test_sensor.py --snapshot-update
```

### Debugging techniques

**Enable debug logging:**

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.your_integration: debug
    homeassistant.components.your_integration: debug
```

**VS Code debugging:**
- Set breakpoints in code
- Press F5 to start debugging
- Debugger stops at breakpoints

**System log monitoring:**

```yaml
automation:
  - alias: "Alert on errors"
    trigger:
      - platform: event
        event_type: system_log_event
        event_data:
          level: ERROR
    action:
      - service: notify.mobile_app
        data:
          message: "{{ trigger.event.data.message[0] }}"
```

### Linting and code quality

```bash
# Run all linters
pre-commit run --all-files

# Individual linters
ruff check homeassistant/components/your_integration/
pylint homeassistant/components/your_integration/

# In VS Code
# Task: "Pre-commit"
```

## Publishing and Distribution

### HACS (Home Assistant Community Store)

HACS is the primary distribution method for custom integrations. Requirements:

**Repository structure:**
- ONE integration per repository
- All files in `ROOT_OF_REPO/custom_components/INTEGRATION_NAME/`
- Public GitHub repository only

**Required files:**
- `__init__.py` - Integration initialization
- `manifest.json` - Integration metadata
- `README.md` - User documentation
- `hacs.json` - HACS configuration

### HACS configuration

Create `hacs.json` in repository root:

```json
{
  "name": "My Awesome Integration",
  "homeassistant": "2024.4.1",
  "content_in_root": false,
  "country": ["US", "CA"]
}
```

**Key fields:**
- `name` (required): Display name in HACS UI
- `homeassistant`: Minimum HA version (e.g., "2021.12.0")
- `content_in_root`: Set true if files are in root vs subdirectory
- `zip_release`: Content in zipped archive for releases
- `country`: ISO 3166-1 alpha-2 country codes

### Versioning and releases

Use GitHub Releases (not just tags) for version management:

```bash
# Update version in manifest.json
# Update CHANGELOG.md
git add .
git commit -m "Release version 1.2.3"

# Create and push tag
git tag -a v1.2.3 -m "Version 1.2.3"
git push --tags

# Create GitHub Release from tag with release notes
```

**Version formats:**
- Semantic Versioning: MAJOR.MINOR.PATCH (e.g., 1.2.3)
- Calendar Versioning: YYYY.MM.MICRO (e.g., 2024.10.1)
- Beta versions: Append `b0` (e.g., "2024.10.0b0")

HACS shows the 5 latest releases to users for version selection.

### Brand assets

Add integration icons and logos to home-assistant/brands repository:

**Directory structure:**
```
custom_integrations/your_integration/
├── icon.png (256x256)
├── icon@2x.png (512x512)
├── logo.png (128-256 shortest side)
└── logo@2x.png (256-512 shortest side)
```

**Requirements:**
- Icons: 1:1 aspect ratio, PNG format
- Logos: Respect brand's aspect ratio, landscape preferred
- Dark mode variants optional (icon-dark.png, logo-dark.png)

### Submitting to Home Assistant Core

Core submission requires meeting Bronze tier minimum:

1. Fork home-assistant/core repository
2. Develop in devcontainer or local environment
3. Create manifest.json (NO version key for core)
4. Implement config flow (required)
5. Write comprehensive tests (required)
6. Add documentation to home-assistant.io
7. Add brand assets to home-assistant/brands
8. Sign Contributor License Agreement (Apache 2.0)
9. Create PR from dev branch (not master)
10. Address review feedback

**PR requirements:**
- All CI checks passing (hassfest, pytest, linters)
- Code follows Home Assistant standards
- Documentation complete
- Tests provide adequate coverage
- No blocking issues from code owners

### CI/CD setup

**GitHub Actions workflow for validation:**

```yaml
name: Validate
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: HACS Validation
        uses: hacs/action@main
        with:
          category: integration
      - name: Hassfest
        uses: home-assistant/actions/hassfest@master
```

**Testing workflow:**

```yaml
name: Tests
on: [push, pull_request]
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install pytest pytest-homeassistant-custom-component
      - name: Run tests
        run: pytest tests/
```

### Pre-commit configuration

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v3.0.0
    hooks:
      - id: prettier
```

### License requirements

**Core integrations:** Apache License 2.0 required. Contributors must sign CLA.

**Custom integrations:** Flexible choice. Common licenses:
- MIT License (permissive, popular)
- Apache 2.0 (same as HA core)
- GPL v3 (copyleft)

Include LICENSE file in repository root.

## Documentation Standards

### README requirements (custom integrations)

Comprehensive README must include:

- Clear description of integration functionality
- Installation instructions (HACS and manual)
- Configuration instructions
- Usage examples and screenshots
- Troubleshooting section
- Link to issue tracker
- Credits and license information

**Optional but recommended:**
- Feature list
- Compatibility information
- Known issues
- Changelog
- Contribution guidelines
- HACS badge

**HACS badge code:**
```markdown
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
```

### Documentation for core integrations

Located at https://www.home-assistant.io/integrations/{domain}. Follow Microsoft Style Guide and write for non-technical users.

**Content by tier:**

**Bronze:** Step-by-step UI setup guide, basic configuration

**Silver:** What integration provides, troubleshooting section, error recovery information

**Gold:** Extensive documentation, example use cases, compatible devices list, entity descriptions, available actions with examples, automation examples, dashboard examples, external resource links

**Style guidelines:**
- Use terminology tooltips: `{% term automation %}`
- Format all examples for configuration.yaml unless stated
- Include version info when features added
- Add redirects when pages renamed

### Translation support

**strings.json** in integration root:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Set up My Integration",
        "description": "Enter your device information",
        "data": {
          "host": "Host",
          "api_key": "API Key"
        }
      }
    },
    "error": {
      "cannot_connect": "Failed to connect",
      "invalid_auth": "Invalid authentication"
    }
  }
}
```

**translations/en.json** mirrors strings.json structure with English translations. Additional language files follow the same pattern (de.json, fr.json, etc.).

## Common Patterns and Examples

### Polling integration pattern

Standard pattern for devices polled at regular intervals:

```python
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity

class MyCoordinator(DataUpdateCoordinator):
    """Coordinator for polling device."""
    
    def __init__(self, hass, api):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="my_device",
            update_interval=timedelta(seconds=30),
        )
        self.api = api
    
    async def _async_update_data(self):
        """Fetch data from API."""
        async with async_timeout.timeout(10):
            return await self.api.fetch_data()

# Setup
coordinator = MyCoordinator(hass, api)
await coordinator.async_config_entry_first_refresh()

# Entity
class MyEntity(CoordinatorEntity, SensorEntity):
    """Polling entity."""
    
    _attr_should_poll = False  # Coordinator handles polling
    
    @property
    def native_value(self):
        """Return value from coordinator data."""
        return self.coordinator.data["value"]
```

### Push integration pattern

For event-driven integrations that receive updates:

```python
class MyPushEntity(SensorEntity):
    """Push-based entity."""
    
    _attr_should_poll = False  # No polling
    
    async def async_added_to_hass(self):
        """Subscribe to updates when added."""
        self._api.register_callback(self._handle_update)
    
    async def async_will_remove_from_hass(self):
        """Unsubscribe when removed."""
        self._api.unregister_callback(self._handle_update)
    
    @callback
    def _handle_update(self, data):
        """Handle pushed update."""
        self._attr_native_value = data["value"]
        self.async_write_ha_state()
```

### OAuth2 integration pattern

Generate OAuth2 integration structure:

```bash
python3 -m script.scaffold config_flow_oauth2
```

OAuth2 config flow implementation:

```python
from homeassistant.helpers import config_entry_oauth2_flow

class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN
):
    """Config flow to handle OAuth2 authentication."""
    
    DOMAIN = DOMAIN
    
    @property
    def logger(self):
        """Return logger."""
        return _LOGGER
    
    async def async_oauth_create_entry(self, data):
        """Create entry from OAuth data."""
        user_id = data["token"]["user_id"]
        await self.async_set_unique_id(user_id)
        self._abort_if_unique_id_configured()
        
        return await super().async_oauth_create_entry(data)
```

### Hub with multiple devices

Hub-based architecture for gateways controlling multiple devices:

```python
# __init__.py
async def async_setup_entry(hass, config_entry):
    """Set up hub."""
    hub = MyHub(config_entry.data)
    await hub.authenticate()
    
    devices = await hub.get_devices()
    
    coordinator = MyCoordinator(hass, config_entry, hub)
    await coordinator.async_config_entry_first_refresh()
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
        "devices": devices,
    }
    
    await hass.config_entries.async_forward_entry_setups(
        config_entry, PLATFORMS
    )
    
    return True

# Platform file
from homeassistant.helpers import device_registry as dr

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up devices from hub."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    
    entities = []
    for device_id, device_data in devices.items():
        # Register device in device registry
        device_registry = dr.async_get(hass)
        device = device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, device_id)},
            manufacturer=device_data["manufacturer"],
            model=device_data["model"],
            name=device_data["name"],
            sw_version=device_data.get("firmware"),
        )
        
        entities.append(MyEntity(coordinator, device_id))
    
    async_add_entities(entities)

# Entity with device info
class MyEntity(CoordinatorEntity):
    """Entity linked to device."""
    
    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "Manufacturer",
            "model": "Model",
            "via_device": (DOMAIN, self._hub_id),  # Link to hub
        }
```

### Service implementation pattern

```python
from homeassistant.helpers import entity_platform
import voluptuous as vol

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up platform with services."""
    # Entity setup...
    
    platform = entity_platform.async_get_current_platform()
    
    platform.async_register_entity_service(
        "set_mode",
        {
            vol.Required("mode"): vol.In(["auto", "manual"]),
        },
        "async_set_mode",
    )

# In entity class
async def async_set_mode(self, mode):
    """Set operation mode."""
    await self._api.set_mode(self._device_id, mode)
    await self.coordinator.async_request_refresh()
```

### Discovery integration pattern

Config flow with Zeroconf discovery:

```python
async def async_step_zeroconf(self, discovery_info):
    """Handle zeroconf discovery."""
    # Extract unique ID from discovery
    unique_id = discovery_info.properties["serial"]
    await self.async_set_unique_id(unique_id)
    
    # Abort if already configured, but update host
    self._abort_if_unique_id_configured(
        updates={CONF_HOST: discovery_info.host}
    )
    
    # Store for confirmation step
    self.context["title_placeholders"] = {
        "name": discovery_info.properties.get("name", "Device")
    }
    
    return await self.async_step_confirm()

async def async_step_confirm(self, user_input=None):
    """Confirm discovery."""
    if user_input is not None:
        return self.async_create_entry(
            title=self.context["title_placeholders"]["name"],
            data={CONF_HOST: self.context[CONF_HOST]}
        )
    
    return self.async_show_form(step_id="confirm")
```

Manifest configuration for discovery:

```json
{
  "domain": "my_integration",
  "zeroconf": [
    {"type": "_my-device._tcp.local.", "properties": {"model": "my-*"}}
  ],
  "ssdp": [
    {"st": "urn:schemas-upnp-org:device:MyDevice:1"}
  ],
  "bluetooth": [
    {"local_name": "MyDevice_*"}
  ]
}
```

## Complete Working Example

### Directory structure

```
custom_components/example_api/
├── __init__.py
├── manifest.json
├── config_flow.py
├── const.py
├── coordinator.py
├── sensor.py
├── switch.py
├── services.yaml
├── strings.json
└── translations/
    └── en.json
```

### manifest.json

```json
{
  "domain": "example_api",
  "name": "Example API",
  "codeowners": ["@yourusername"],
  "config_flow": true,
  "dependencies": [],
  "documentation": "https://github.com/yourusername/example_api",
  "integration_type": "service",
  "iot_class": "cloud_polling",
  "requirements": ["aiohttp>=3.8.0"],
  "version": "1.0.0"
}
```

### const.py

```python
"""Constants for Example API."""
DOMAIN = "example_api"
CONF_API_KEY = "api_key"
DEFAULT_SCAN_INTERVAL = 30
```

### __init__.py

```python
"""The Example API integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ExampleCoordinator

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Example API from a config entry."""
    # Create coordinator
    coordinator = ExampleCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
```

### coordinator.py

```python
"""Data coordinator for Example API."""
from datetime import timedelta
import logging
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

class ExampleCoordinator(DataUpdateCoordinator):
    """Coordinator to manage fetching data."""
    
    def __init__(self, hass: HomeAssistant, config_entry):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.config_entry = config_entry
        self._api_key = config_entry.data["api_key"]
    
    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            async with async_timeout.timeout(10):
                # Replace with actual API call
                return {
                    "temperature": 25.0,
                    "humidity": 45,
                    "switch_state": True
                }
        except AuthError as err:
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
```

### config_flow.py

```python
"""Config flow for Example API."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST

from .const import DOMAIN, CONF_API_KEY

class ExampleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""
    
    VERSION = 1
    
    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            try:
                # Validate input
                await self._test_credentials(
                    user_input[CONF_HOST],
                    user_input[CONF_API_KEY]
                )
                
                return self.async_create_entry(
                    title=user_input[CONF_HOST],
                    data=user_input
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_API_KEY): str,
            }),
            errors=errors,
        )
    
    async def _test_credentials(self, host, api_key):
        """Validate credentials."""
        # Implement validation
        pass
```

### sensor.py

```python
"""Sensor platform for Example API."""
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        ExampleTemperatureSensor(coordinator),
        ExampleHumiditySensor(coordinator),
    ])

class ExampleTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Temperature sensor."""
    
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True
    
    def __init__(self, coordinator):
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_temperature"
        self._attr_name = "Temperature"
    
    @property
    def native_value(self):
        """Return sensor value."""
        return self.coordinator.data.get("temperature")

class ExampleHumiditySensor(CoordinatorEntity, SensorEntity):
    """Humidity sensor."""
    
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True
    
    def __init__(self, coordinator):
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_humidity"
        self._attr_name = "Humidity"
    
    @property
    def native_value(self):
        """Return sensor value."""
        return self.coordinator.data.get("humidity")
```

### switch.py

```python
"""Switch platform for Example API."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ExampleSwitch(coordinator)])

class ExampleSwitch(CoordinatorEntity, SwitchEntity):
    """Example switch."""
    
    _attr_has_entity_name = True
    
    def __init__(self, coordinator):
        """Initialize switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_switch"
        self._attr_name = "Switch"
    
    @property
    def is_on(self):
        """Return true if switch is on."""
        return self.coordinator.data.get("switch_state", False)
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        # Call API to turn on
        # await self.coordinator.api.turn_on()
        await self.coordinator.async_request_refresh()
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        # Call API to turn off
        # await self.coordinator.api.turn_off()
        await self.coordinator.async_request_refresh()
```

### strings.json

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Set up Example API",
        "description": "Enter your API credentials",
        "data": {
          "host": "Host",
          "api_key": "API Key"
        }
      }
    },
    "error": {
      "cannot_connect": "Failed to connect to the API",
      "invalid_auth": "Invalid API key"
    }
  }
}
```

## Essential Resources

### Official documentation

- **Developer Documentation**: https://developers.home-assistant.io/
- **Creating Your First Integration**: https://developers.home-assistant.io/docs/creating_component_index/
- **Integration Manifest**: https://developers.home-assistant.io/docs/creating_integration_manifest/
- **Config Flow**: https://developers.home-assistant.io/docs/config_entries_config_flow_handler/
- **Entity Documentation**: https://developers.home-assistant.io/docs/core/entity/
- **REST API**: https://developers.home-assistant.io/docs/api/rest/
- **Testing Guide**: https://developers.home-assistant.io/docs/development_testing/
- **Quality Scale**: https://developers.home-assistant.io/docs/core/integration-quality-scale/

### Code repositories

- **Home Assistant Core**: https://github.com/home-assistant/core
- **Home Assistant Brands**: https://github.com/home-assistant/brands
- **Integration Blueprint**: https://github.com/ludeeus/integration_blueprint
- **Example Custom Config**: https://github.com/home-assistant/example-custom-config
- **Architecture ADRs**: https://github.com/home-assistant/architecture

### Community resources

- **Home Assistant Community Forum**: https://community.home-assistant.io/
- **Discord**: https://discord.gg/home-assistant
- **HACS Documentation**: https://hacs.xyz/docs/publish/

### Example integrations to study

**Core integrations** (in homeassistant/components/):
- **hue**: Hub pattern with discovery
- **esphome**: Push-based pattern
- **mqtt**: Message-based pattern
- **template**: Shows all entity types

**Popular custom integrations**:
- **HACS**: https://github.com/hacs/integration
- **Frigate**: https://github.com/blakeblackshear/frigate-hass-integration
- **Alexa Media Player**: https://github.com/custom-components/alexa_media_player

### Development tools

- **pytest-homeassistant-custom-component**: Testing framework for custom integrations
- **Ruff**: Code formatter and linter
- **pre-commit**: Automated code quality checks
- **Hassfest**: Integration validation tool

## Quick Start Checklist

### For custom integrations

- [ ] Use integration_blueprint template or scaffold tool
- [ ] Create manifest.json with version key
- [ ] Create hacs.json for HACS compatibility
- [ ] Implement config flow for UI setup
- [ ] Use DataUpdateCoordinator for polling
- [ ] Inherit from CoordinatorEntity
- [ ] Set unique_id on all entities
- [ ] Write comprehensive tests
- [ ] Create detailed README
- [ ] Add brand assets to home-assistant/brands
- [ ] Set up CI/CD with GitHub Actions
- [ ] Create GitHub Release
- [ ] Users add as custom repository in HACS

### For core integrations

- [ ] Fork home-assistant/core repository
- [ ] Set up VS Code Dev Container
- [ ] Create integration with scaffold tool
- [ ] Implement config flow (required)
- [ ] Meet Bronze tier requirements minimum
- [ ] Write comprehensive tests (required)
- [ ] Add documentation to home-assistant.io
- [ ] Add brand assets to home-assistant/brands
- [ ] Ensure all CI checks pass
- [ ] Sign CLA (Apache 2.0)
- [ ] Create PR from dev branch
- [ ] Review two other open PRs
- [ ] Address review feedback
- [ ] Wait for core team approval

## Conclusion

Home Assistant's architecture provides a powerful, flexible foundation for integration development. The async-first approach, standardized entity patterns, and comprehensive tooling make it possible to create high-quality integrations efficiently.

The key to success: start with the scaffold tool, use DataUpdateCoordinator for polling integrations, inherit from CoordinatorEntity, implement proper error handling, write comprehensive tests, and follow the coding standards strictly. The quality scale provides a clear path from basic Bronze tier to exemplary Platinum tier.

Whether building a simple sensor integration or a complex hub managing multiple devices, Home Assistant's patterns and best practices guide developers toward maintainable, user-friendly integrations that seamlessly integrate into the broader ecosystem.
