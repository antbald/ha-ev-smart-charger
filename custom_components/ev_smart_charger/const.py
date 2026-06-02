"""Constants for the EV Smart Charger integration."""

# ========== INTEGRATION METADATA ==========
DOMAIN = "ev_smart_charger"
VERSION = "2.2.2"
DEFAULT_NAME = "EV Smart Charger"
FRONTEND_URL_BASE = "/api/ev_smart_charger/frontend"
FRONTEND_CARD_FILENAME = "ev-smart-charger-dashboard.js"

# ========== AUTO-GENERATED DASHBOARD (v1.9.0+) ==========
# When CONF_CREATE_DASHBOARD is True the integration auto-creates a Lovelace
# storage-mode dashboard preloaded with the EV Smart Charger card and the
# user-mapped energy sensors. Zero YAML, ready-to-go after setup.
DASHBOARD_URL_PATH = "ev-smart-charger"
DASHBOARD_TITLE = DEFAULT_NAME
DASHBOARD_ICON = "mdi:ev-station"
DASHBOARD_RESOURCE_KEY = f"{DOMAIN}_auto_dashboard"

# ========== PLATFORMS ==========
PLATFORMS = ["switch", "number", "select", "sensor", "time"]

# ========== AUTOMATION PRIORITIES ==========
PRIORITY_OVERRIDE = 1  # Forza Ricarica (kill switch)
PRIORITY_BOOST_CHARGE = 2  # Boost Charge override
PRIORITY_SMART_BLOCKER = 3  # Smart Charger Blocker
PRIORITY_NIGHT_CHARGE = 4  # Night Smart Charge
PRIORITY_BALANCER = 5  # Priority Balancer
PRIORITY_SOLAR_SURPLUS = 6  # Solar Surplus

# ========== PRIORITY BALANCER STATES ==========
PRIORITY_EV = "EV"  # EV charging priority
PRIORITY_HOME = "Home"  # Home battery charging priority
PRIORITY_EV_FREE = "EV_Free"  # Both targets met, opportunistic EV charging

# ========== CHARGER STATUS VALUES ==========
CHARGER_STATUS_CHARGING = "charger_charging"
CHARGER_STATUS_FREE = "charger_free"
CHARGER_STATUS_END = "charger_end"
CHARGER_STATUS_WAIT = "charger_wait"

# ========== NIGHT SMART CHARGE MODES ==========
NIGHT_CHARGE_MODE_BATTERY = "battery"  # Charging from home battery
NIGHT_CHARGE_MODE_GRID = "grid"  # Charging from grid
NIGHT_CHARGE_MODE_IDLE = "idle"  # Not active

# ========== CHARGING PROFILES ==========
PROFILE_MANUAL = "manual"
PROFILE_SOLAR_SURPLUS = "solar_surplus"
PROFILE_CHARGE_TARGET = "charge_target"  # Not implemented
PROFILE_CHEAPEST = "cheapest"  # Not implemented

CHARGING_PROFILES = [
    PROFILE_MANUAL,
    PROFILE_SOLAR_SURPLUS,
]

LEGACY_CHARGING_PROFILES = [
    PROFILE_CHARGE_TARGET,
    PROFILE_CHEAPEST,
]

# ========== CHARGER AMPERAGE LEVELS ==========
CHARGER_AMP_LEVELS = [6, 8, 10, 13, 16, 20, 24, 32]  # Tuya-style discrete levels
# Generic (non-Tuya) wallboxes accept any integer amperage → 1 A steps (v2.0.0)
GENERIC_AMP_LEVELS = list(range(6, 33))  # [6, 7, 8, ..., 32]
VOLTAGE_EU = 230  # European standard voltage (per phase)

# ========== CHARGING-STATE SSOT (v2.2.0) ==========
# Drawing-now threshold on the TOTAL measured charging power (single absolute
# value on the summed watts — NOT scaled by phase count). The minimum real
# charging session is ~1380 W single-phase / ~4140 W three-phase total, both far
# above this floor; the floor only rejects EVSE standby / CT noise (5-40 W).
# "Is a session intended / plugged in" is answered by status/command, never the
# floor. Tunable in beta against real wallbox standby observations.
CHARGING_POWER_DRAWING_FLOOR_W = 200
# Command-wins grace window. Measured charging power lags the commanded state
# (ramp-up at start, decay at stop, and the Tuya stop→set→start decrease), so a
# naive ``power > floor`` would oscillate against the rate-limited command loop.
# Within this many seconds of a start/stop command, the command wins.
CHARGING_POWER_GRACE_SECONDS = 15
# Night-charge GRID mode: suppress the measured-power blind-spot stop for this
# long after the session starts. An EV can take tens of seconds to begin drawing
# after the wallbox reports 'charging' (cold battery, scheduled charging,
# preconditioning, contactor delay); without this window the 15 s low-draw
# debounce would false-terminate a legitimate session ~30 s in.
NIGHT_GRID_DRAW_START_GRACE_SECONDS = 90

# ========== PHASE MODE & CHARGER MODEL (v2.0.0, opt-in) ==========
# Phase mode: single-phase (default, unchanged behaviour) or three-phase.
# In three-phase, production/consumption/grid are THREE sensors each (summed)
# and the watt→amp conversion uses 3 × VOLTAGE_EU = 690 V, so per-phase amperage
# thresholds and amp levels stay valid downstream.
PHASE_MODE_SINGLE = "single"
PHASE_MODE_THREE = "three"
DEFAULT_PHASE_MODE = PHASE_MODE_SINGLE

# Charger model: tuya (discrete CHARGER_AMP_LEVELS, safe stop/set/start on decrease,
# default = current behaviour) or generic (1 A steps, live amperage decrease without
# stopping the charger).
CHARGER_MODEL_TUYA = "tuya"
CHARGER_MODEL_GENERIC = "generic"
DEFAULT_CHARGER_MODEL = CHARGER_MODEL_TUYA

# ========== CONFIGURATION FLOW KEYS ==========
CONF_EV_CHARGER_SWITCH = "ev_charger_switch"
CONF_EV_CHARGER_CURRENT = "ev_charger_current"
CONF_EV_CHARGER_STATUS = "ev_charger_status"
CONF_SOC_CAR = "soc_car"
CONF_SOC_HOME = "soc_home"
CONF_FV_PRODUCTION = "fv_production"
CONF_HOME_CONSUMPTION = "home_consumption"
CONF_GRID_IMPORT = "grid_import"
CONF_PV_FORECAST = "pv_forecast"

# Phase mode + per-phase sensors (v2.0.0). The existing keys above act as L1
# (so single-phase installs are byte-for-byte unchanged); L2/L3 are only mapped
# and read when CONF_PHASE_MODE == PHASE_MODE_THREE. NOTE: only power quantities
# are per-phase — soc_car / soc_home stay single (they are battery percentages).
CONF_PHASE_MODE = "phase_mode"
CONF_CHARGER_MODEL = "charger_model"
CONF_FV_PRODUCTION_L2 = "fv_production_l2"
CONF_FV_PRODUCTION_L3 = "fv_production_l3"
CONF_HOME_CONSUMPTION_L2 = "home_consumption_l2"
CONF_HOME_CONSUMPTION_L3 = "home_consumption_l3"
CONF_GRID_IMPORT_L2 = "grid_import_l2"
CONF_GRID_IMPORT_L3 = "grid_import_l3"

# v2.2.0 — Measured EV charging power (W) sensor(s). The SSOT for "is the car
# drawing current right now" (drawing_now). Unlike production/consumption/grid,
# L1 is a NEW key (no pre-v2.2 single-phase equivalent). Single-phase = 1 sensor;
# three-phase = 3 sensors summed. Optional: when unmapped, the charging-state
# answer falls back to the textual CONF_EV_CHARGER_STATUS sensor → existing
# installs are byte-for-byte unchanged. Unsigned positive watts (no sign toggle;
# reversed-sign sensors read a flat 0 W after the clamp in read_charging_power).
CONF_CHARGING_POWER = "charging_power"
CONF_CHARGING_POWER_L2 = "charging_power_l2"
CONF_CHARGING_POWER_L3 = "charging_power_l3"
# v1.11.14: distinct from CONF_PV_FORECAST. Optional sensor that reports
# the *next-day* solar production forecast in kWh. Consumed only by the
# auto-dashboard "Forecast Domani" chip — Night Smart Charge stays wired
# to CONF_PV_FORECAST so existing installs keep their current behaviour.
CONF_PV_FORECAST_TOMORROW = "pv_forecast_tomorrow"

# Hybrid Inverter Mode (v2.1.0 — issue #29). Optional signed battery-power (W)
# sensor used to detect battery-discharge masking. Convention: negative =
# discharging, positive = charging (normalised in ChargingModel.read_battery_discharge).
# Single sensor (never per-phase, like SOC). CONF_HYBRID_INVERTER_MODE is a config
# key that seeds the evsc_hybrid_inverter_mode switch's first-run state (NOT a new entity).
CONF_BATTERY_POWER = "battery_power"
CONF_HYBRID_INVERTER_MODE = "hybrid_inverter_mode"
DEFAULT_HYBRID_INVERTER_MODE = False

# Mobile Notifications
CONF_NOTIFY_SERVICES = "notify_services"
CONF_CAR_OWNER = "car_owner"  # Person entity for car owner (v1.3.19+)

# Energy Forecast Configuration (v1.4.8+)
CONF_BATTERY_CAPACITY = "battery_capacity"
CONF_ENERGY_FORECAST_TARGET = "energy_forecast_target"

# Auto-generated Dashboard (v1.9.0+)
CONF_CREATE_DASHBOARD = "create_dashboard"
DEFAULT_CREATE_DASHBOARD = True

# Energy Forecast Defaults
DEFAULT_BATTERY_CAPACITY = 50.0  # kWh
MIN_BATTERY_CAPACITY = 10.0
MAX_BATTERY_CAPACITY = 200.0

# ========== HELPER ENTITY SUFFIXES ==========

# Switches
HELPER_FORZA_RICARICA_SUFFIX = "evsc_forza_ricarica"
HELPER_BOOST_CHARGE_ENABLED_SUFFIX = "evsc_boost_charge_enabled"
HELPER_SMART_BLOCKER_ENABLED_SUFFIX = "evsc_smart_charger_blocker_enabled"
HELPER_USE_HOME_BATTERY_SUFFIX = "evsc_use_home_battery"
HELPER_PRIORITY_BALANCER_ENABLED_SUFFIX = "evsc_priority_balancer_enabled"
HELPER_NIGHT_CHARGE_ENABLED_SUFFIX = "evsc_night_smart_charge_enabled"
HELPER_PRESERVE_HOME_BATTERY_SUFFIX = "evsc_preserve_home_battery"

# Notification Switches
HELPER_NOTIFY_SMART_BLOCKER_SUFFIX = "evsc_notify_smart_blocker_enabled"
HELPER_NOTIFY_PRIORITY_BALANCER_SUFFIX = "evsc_notify_priority_balancer_enabled"
HELPER_NOTIFY_NIGHT_CHARGE_SUFFIX = "evsc_notify_night_charge_enabled"

# File Logging Switch (v1.3.25)
HELPER_ENABLE_FILE_LOGGING_SUFFIX = "evsc_enable_file_logging"
HELPER_TRACE_LOGGING_ENABLED_SUFFIX = "evsc_trace_logging_enabled"

# Numbers - Solar Surplus
HELPER_CHECK_INTERVAL_SUFFIX = "evsc_check_interval"
HELPER_GRID_IMPORT_THRESHOLD_SUFFIX = "evsc_grid_import_threshold"
HELPER_GRID_IMPORT_DELAY_SUFFIX = "evsc_grid_import_delay"
HELPER_SURPLUS_DROP_DELAY_SUFFIX = "evsc_surplus_drop_delay"
HELPER_HOME_BATTERY_MIN_SOC_SUFFIX = "evsc_home_battery_min_soc"
HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX = "evsc_battery_support_amperage"
HELPER_BATTERY_SUPPORT_SUNSET_BUFFER_SUFFIX = "evsc_battery_support_sunset_buffer"
HELPER_SOLAR_MAX_AMPERAGE_SUFFIX = "evsc_solar_max_amperage"
# v2.1.0 (issue #29) — max home-battery discharge (W) allowed to cover the EV
# charging floor (deadband buffer + Hybrid Mode masking checks). 0 = feature off.
# Battery-only helper (meaningless without a home battery).
HELPER_MAX_BATTERY_DISCHARGE_FOR_EV_SUFFIX = "evsc_max_battery_discharge_for_ev"

# Numbers - Night Smart Charge
HELPER_NIGHT_CHARGE_AMPERAGE_SUFFIX = "evsc_night_charge_amperage"
HELPER_MIN_SOLAR_FORECAST_THRESHOLD_SUFFIX = "evsc_min_solar_forecast_threshold"

# Numbers - Boost Charge
HELPER_BOOST_CHARGE_AMPERAGE_SUFFIX = "evsc_boost_charge_amperage"
HELPER_BOOST_TARGET_SOC_SUFFIX = "evsc_boost_target_soc"

# Switches - Schedule Boost Charge
HELPER_BOOST_SCHEDULE_ENABLED_SUFFIX = "evsc_boost_schedule_enabled"

# Times - Schedule Boost Charge
HELPER_BOOST_SCHEDULE_START_TIME_SUFFIX = "evsc_boost_schedule_start_time"
HELPER_BOOST_SCHEDULE_END_TIME_SUFFIX = "evsc_boost_schedule_end_time"

# Numbers - Daily SOC targets (EV)
HELPER_EV_MIN_SOC_MONDAY_SUFFIX = "evsc_ev_min_soc_monday"
HELPER_EV_MIN_SOC_TUESDAY_SUFFIX = "evsc_ev_min_soc_tuesday"
HELPER_EV_MIN_SOC_WEDNESDAY_SUFFIX = "evsc_ev_min_soc_wednesday"
HELPER_EV_MIN_SOC_THURSDAY_SUFFIX = "evsc_ev_min_soc_thursday"
HELPER_EV_MIN_SOC_FRIDAY_SUFFIX = "evsc_ev_min_soc_friday"
HELPER_EV_MIN_SOC_SATURDAY_SUFFIX = "evsc_ev_min_soc_saturday"
HELPER_EV_MIN_SOC_SUNDAY_SUFFIX = "evsc_ev_min_soc_sunday"

# Numbers - Daily SOC targets (Home)
HELPER_HOME_MIN_SOC_MONDAY_SUFFIX = "evsc_home_min_soc_monday"
HELPER_HOME_MIN_SOC_TUESDAY_SUFFIX = "evsc_home_min_soc_tuesday"
HELPER_HOME_MIN_SOC_WEDNESDAY_SUFFIX = "evsc_home_min_soc_wednesday"
HELPER_HOME_MIN_SOC_THURSDAY_SUFFIX = "evsc_home_min_soc_thursday"
HELPER_HOME_MIN_SOC_FRIDAY_SUFFIX = "evsc_home_min_soc_friday"
HELPER_HOME_MIN_SOC_SATURDAY_SUFFIX = "evsc_home_min_soc_saturday"
HELPER_HOME_MIN_SOC_SUNDAY_SUFFIX = "evsc_home_min_soc_sunday"

# Switches - Car Ready Flags (daily)
HELPER_CAR_READY_MONDAY_SUFFIX = "evsc_car_ready_monday"
HELPER_CAR_READY_TUESDAY_SUFFIX = "evsc_car_ready_tuesday"
HELPER_CAR_READY_WEDNESDAY_SUFFIX = "evsc_car_ready_wednesday"
HELPER_CAR_READY_THURSDAY_SUFFIX = "evsc_car_ready_thursday"
HELPER_CAR_READY_FRIDAY_SUFFIX = "evsc_car_ready_friday"
HELPER_CAR_READY_SATURDAY_SUFFIX = "evsc_car_ready_saturday"
HELPER_CAR_READY_SUNDAY_SUFFIX = "evsc_car_ready_sunday"

# Selects
HELPER_CHARGING_PROFILE_SUFFIX = "evsc_charging_profile"

# Time
HELPER_NIGHT_CHARGE_TIME_SUFFIX = "evsc_night_charge_time"
HELPER_CAR_READY_TIME_SUFFIX = "evsc_car_ready_time"

# Sensors
HELPER_DIAGNOSTIC_SENSOR_SUFFIX = "evsc_diagnostic"
HELPER_PRIORITY_STATE_SUFFIX = "evsc_priority_daily_state"
HELPER_SOLAR_SURPLUS_DIAGNOSTIC_SUFFIX = "evsc_solar_surplus_diagnostic"
HELPER_LOG_FILE_PATH_SUFFIX = "evsc_log_file_path"  # v1.3.25
HELPER_TODAY_EV_TARGET_SUFFIX = "evsc_today_ev_target"  # v1.3.26
HELPER_TODAY_HOME_TARGET_SUFFIX = "evsc_today_home_target"  # v1.3.26
HELPER_CACHED_EV_SOC_SUFFIX = "evsc_cached_ev_soc"  # v1.4.0
HELPER_NIGHT_SESSION_STATE_SUFFIX = "evsc_night_session_state"  # v1.11.9 — runtime session state for hero banner

# Hybrid Inverter Mode (v1.8.0 — issue #20)
HELPER_HYBRID_INVERTER_MODE_SUFFIX = "evsc_hybrid_inverter_mode"
HELPER_HYBRID_BATTERY_FULL_THRESHOLD_SUFFIX = "evsc_hybrid_battery_full_threshold"
HELPER_HYBRID_PROBE_DURATION_SUFFIX = "evsc_hybrid_probe_duration"
HELPER_HYBRID_MAX_IMPORT_DURATION_SUFFIX = "evsc_hybrid_max_import_duration"
HELPER_HYBRID_MAX_FAILED_PROBES_SUFFIX = "evsc_hybrid_max_failed_probes"
HELPER_HYBRID_DIAGNOSTIC_SUFFIX = "evsc_hybrid_inverter_diagnostic"

# ========== DEFAULT VALUES - SOLAR SURPLUS ==========
DEFAULT_CHECK_INTERVAL = 1  # minutes
DEFAULT_GRID_IMPORT_THRESHOLD = 50  # watts
DEFAULT_GRID_IMPORT_DELAY = 30  # seconds
DEFAULT_SURPLUS_DROP_DELAY = 30  # seconds

# ========== SURPLUS HYSTERESIS SETTINGS ==========
SURPLUS_START_THRESHOLD = 6.5  # amps - minimum surplus to START charging (with margin)
SURPLUS_STOP_THRESHOLD = 5.5   # amps - minimum surplus to CONTINUE charging
SURPLUS_INCREASE_DELAY = 60  # seconds - delay before increasing amperage (cloud protection)
SURPLUS_DEADBAND_START_DELAY = 120  # seconds - persistent dead band surplus before opportunistic start

# ========== DEFAULT VALUES - HOME BATTERY SUPPORT ==========
DEFAULT_HOME_BATTERY_MIN_SOC = 20  # percent
DEFAULT_BATTERY_SUPPORT_AMPERAGE = 16  # amps (user configurable)
DEFAULT_BATTERY_SUPPORT_SUNSET_BUFFER_MIN = 60  # minutes before sunset (block battery support when close to sunset)
DEFAULT_SOLAR_MAX_AMPERAGE = 32  # amps (user configurable, default = no cap)
DEFAULT_MAX_BATTERY_DISCHARGE_FOR_EV = 0  # watts (0 = feature off, current behaviour)

# ========== DEFAULT VALUES - PRIORITY BALANCER ==========
DEFAULT_EV_MIN_SOC_WEEKDAY = 50  # percent (Monday-Friday)
DEFAULT_EV_MIN_SOC_WEEKEND = 80  # percent (Saturday-Sunday)
DEFAULT_HOME_MIN_SOC = 50  # percent (all days)

# ========== DEFAULT VALUES - NIGHT SMART CHARGE ==========
DEFAULT_NIGHT_CHARGE_TIME = "01:00:00"
DEFAULT_MIN_SOLAR_FORECAST_THRESHOLD = 20  # kWh
DEFAULT_NIGHT_CHARGE_AMPERAGE = 16  # amps
DEFAULT_CAR_READY_TIME = "08:00:00"  # Default deadline when car must be ready
NIGHT_CHARGE_COOLDOWN_SECONDS = 3600  # 1 hour - prevent re-evaluation after completion

# ========== NIGHT SMART CHARGE RETRY SETTINGS (v1.6.1) ==========
NIGHT_CHARGE_START_MAX_RETRIES = 3  # Maximum attempts to start charger
NIGHT_CHARGE_START_RETRY_DELAYS = [5, 15, 30]  # Seconds between retry attempts (backoff)

# ========== DEFAULT VALUES - BOOST CHARGE ==========
DEFAULT_BOOST_CHARGE_AMPERAGE = 16  # amps
DEFAULT_BOOST_TARGET_SOC = 80  # percent
DEFAULT_BOOST_SCHEDULE_START_TIME = "07:00:00"
DEFAULT_BOOST_SCHEDULE_END_TIME = "08:00:00"

# ========== NIGHT SMART CHARGE WINDOW ACTIVATION SETTINGS (v1.4.4) ==========
ACTIVATION_GRACE_BEFORE_MINUTES = 2  # Activate 2 minutes before scheduled time (handles clock drift)
ACTIVATION_GRACE_AFTER_MINUTES = 5   # Continue accepting activation up to 5 minutes after scheduled time

# ========== DEFAULT VALUES - CAR READY FLAGS ==========
DEFAULT_CAR_READY_WEEKDAY = True  # Monday-Friday (car needed for work)
DEFAULT_CAR_READY_WEEKEND = False  # Saturday-Sunday (car not urgently needed)

# ========== SMART BLOCKER SETTINGS ==========
SMART_BLOCKER_ENFORCEMENT_TIMEOUT = 1800  # 30 minutes in seconds

# ========== RATE LIMITING ==========
SOLAR_SURPLUS_MIN_CHECK_INTERVAL = 30  # seconds between checks
SOLAR_SURPLUS_MAX_CHECKS_PER_MINUTE = 10  # warning threshold

# ========== CHARGER CONTROLLER SETTINGS ==========
CHARGER_MIN_OPERATION_INTERVAL = 30  # seconds between charger operations (rate limiting)

# ========== DELAYS ==========
CHARGER_COMMAND_DELAY = 2  # seconds to wait after charger commands
CHARGER_START_SEQUENCE_DELAY = 2  # seconds between turn_on and set amperage
CHARGER_STOP_SEQUENCE_DELAY = 5  # seconds after stop before setting amperage
CHARGER_AMPERAGE_STABILIZATION_DELAY = 1  # seconds after setting amperage

# ========== TIMEOUTS ==========
SERVICE_CALL_TIMEOUT = 10  # seconds for service calls

# ========== FILE LOGGING SETTINGS (v1.4.15) ==========
# Date-based log structure: logs/<year>/<month>/<day>.log
# Example: logs/2025/12/29.log
# No rotation needed - new file each day, automatic midnight transition

# ========== EV SOC MONITOR SETTINGS (v1.4.0) ==========
EV_SOC_MONITOR_INTERVAL = 5  # seconds - polling frequency for cloud sensor reliability

# ========== HYBRID INVERTER MODE (v1.8.0 — issue #20) ==========
# User-configurable defaults
DEFAULT_HYBRID_BATTERY_FULL_THRESHOLD = 95  # percent — minimum home SOC to consider "battery full"
DEFAULT_HYBRID_PROBE_DURATION = 60  # seconds — total probing window length
DEFAULT_HYBRID_MAX_IMPORT_DURATION = 60  # seconds — max sustained grid import before backoff
DEFAULT_HYBRID_MAX_FAILED_PROBES = 5  # sliding window count before COOLDOWN_LONG

# Internal constants (not user-configurable)
HYBRID_COOLDOWN_SHORT_SECONDS = 120  # 2 min after a failed probe
HYBRID_COOLDOWN_LONG_SECONDS = 900   # 15 min after N consecutive fails (sliding window)
HYBRID_FAILURE_WINDOW_SECONDS = 1800  # 30 min sliding window for failure counting
HYBRID_HEADROOM_STABLE_SECONDS = 60  # how long grid_import must stay low before stepping up
HYBRID_SUNSET_BUFFER_MIN = 90  # minutes before sunset — do not probe when sun is too low
HYBRID_TRANSIENT_GRACE_SECONDS = 20  # first N seconds of PROBING: ignore grid_import (inverter ramp)
HYBRID_GRID_ENTRY_SMOOTH_SECONDS = 60  # how long grid_import must stay low BEFORE entering PROBING
HYBRID_RIDING_EDGE_SUCCESS_DURATION = 300  # 5 min sustained RIDING_EDGE → reset failure window
HYBRID_MAX_DAILY_LONG_COOLDOWNS = 3  # after 3 long cooldowns, HARD_EXIT until next sunrise
HYBRID_MAX_NEGATIVE_SURPLUS_W = -500  # entry blocked if surplus is below this (house >> PV ceiling)
HYBRID_PROBE_AMPERAGE = 6  # initial probing amperage (always the minimum charger level)

# State string constants
HYBRID_STATE_IDLE = "IDLE"
HYBRID_STATE_PROBING = "PROBING"
HYBRID_STATE_RIDING_EDGE = "RIDING_EDGE"
HYBRID_STATE_COOLDOWN_SHORT = "COOLDOWN_SHORT"
HYBRID_STATE_COOLDOWN_LONG = "COOLDOWN_LONG"
HYBRID_STATE_HARD_EXIT = "HARD_EXIT"

# ========== ENTITY REGISTRATION ==========
# Verified count (v2.1.0): 66 entities when home battery is configured.
# v1.8.0 set the baseline to 64 (added 6 Hybrid Mode entities). v1.11.9 added
# 1 sensor (evsc_night_session_state) → 65. v2.1.0 (issue #29) adds 1 battery-only
# number (evsc_max_battery_discharge_for_ev) → 66.
# COUPLING (issue #22): the disabled-helper tolerance in
# __init__._async_wait_for_helper_registration assumes this equals the number
# of entities actually created when nothing is disabled. If it drifts above
# reality (cf. v1.6.20), a single user-disabled entity turns the tolerant
# startup path back into a hard ConfigEntryNotReady. Keep this in sync.
TOTAL_INTEGRATION_ENTITIES = 66
# Verified count (v1.11.9): 52 entities when running in PV-only mode.
# Unchanged in v2.1.0: the new number is battery-only (skipped in PV-only mode).
# Skipped helpers (13): 2 switches (use_home_battery, preserve_home_battery),
# 3 numbers (home_battery_min_soc, battery_support_amperage, battery_support_sunset_buffer),
# 7 daily home min SOC numbers (Monday–Sunday), 1 sensor (today_home_target).
# Hybrid Mode entities are still created in PV-only mode but stay IDLE (requires soc_home).
TOTAL_INTEGRATION_ENTITIES_NO_BATTERY = 52


def has_home_battery(config: dict) -> bool:
    """Return True if the user configured a home battery SOC sensor (v1.7.0)."""
    return bool(config.get(CONF_SOC_HOME))


def is_three_phase(config: dict) -> bool:
    """Return True if the install is configured as three-phase (v2.0.0)."""
    return config.get(CONF_PHASE_MODE, DEFAULT_PHASE_MODE) == PHASE_MODE_THREE


def get_phase_count(config: dict) -> int:
    """Return the number of phases (1 single, 3 three-phase) (v2.0.0)."""
    return 3 if is_three_phase(config) else 1


def get_effective_voltage(config: dict) -> float:
    """Return the watt→amp conversion voltage (phase_count × VOLTAGE_EU).

    Single-phase → 230 V (unchanged). Three-phase → 690 V, so that
    ``surplus_watts / effective_voltage`` yields the per-phase amperage a
    balanced three-phase charger can sustain (P = 3 · V · I).
    """
    return get_phase_count(config) * VOLTAGE_EU


def get_charger_model(config: dict) -> str:
    """Return the configured charger model (v2.0.0)."""
    return config.get(CONF_CHARGER_MODEL, DEFAULT_CHARGER_MODEL)


def get_amp_levels(config: dict) -> list[int]:
    """Return the amperage level set for the configured charger model (v2.0.0).

    ``tuya`` → discrete CHARGER_AMP_LEVELS (default, unchanged).
    ``generic`` → GENERIC_AMP_LEVELS (1 A steps, 6–32 A).
    """
    if get_charger_model(config) == CHARGER_MODEL_GENERIC:
        return GENERIC_AMP_LEVELS
    return CHARGER_AMP_LEVELS

# ========== ANONYMOUS TELEMETRY ==========
# Google Apps Script Web App endpoint (insert-only, no personal data).
# Opt-out: set env var EVSC_DISABLE_TELEMETRY=true on the HA host.
TELEMETRY_ENDPOINT = (
    "https://script.google.com/macros/s/"
    "AKfycbyMG7ALlmvOC1ao2WTTpuLvFgiinapPtJPFwDUGYuMdHdImhunJjQ3GjXFe-wOsXpR-"
    "/exec"
)
TELEMETRY_PING_INTERVAL_HOURS = 24
