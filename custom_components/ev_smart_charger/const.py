"""Constants for the EV Smart Charger integration."""

# ========== INTEGRATION METADATA ==========
DOMAIN = "ev_smart_charger"
VERSION = "1.3.15"
DEFAULT_NAME = "EV Smart Charger"

# ========== PLATFORMS ==========
PLATFORMS = ["switch", "number", "select", "sensor", "time"]

# ========== AUTOMATION PRIORITIES ==========
PRIORITY_OVERRIDE = 1  # Forza Ricarica (kill switch)
PRIORITY_SMART_BLOCKER = 2  # Smart Charger Blocker
PRIORITY_NIGHT_CHARGE = 3  # Night Smart Charge
PRIORITY_BALANCER = 4  # Priority Balancer
PRIORITY_SOLAR_SURPLUS = 5  # Solar Surplus

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
    PROFILE_CHARGE_TARGET,
    PROFILE_CHEAPEST,
]

# ========== CHARGER AMPERAGE LEVELS ==========
CHARGER_AMP_LEVELS = [6, 8, 10, 13, 16, 20, 24, 32]
VOLTAGE_EU = 230  # European standard voltage

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

# Mobile Notifications
CONF_NOTIFY_SERVICES = "notify_services"

# ========== HELPER ENTITY SUFFIXES ==========

# Switches
HELPER_FORZA_RICARICA_SUFFIX = "evsc_forza_ricarica"
HELPER_SMART_BLOCKER_ENABLED_SUFFIX = "evsc_smart_charger_blocker_enabled"
HELPER_USE_HOME_BATTERY_SUFFIX = "evsc_use_home_battery"
HELPER_PRIORITY_BALANCER_ENABLED_SUFFIX = "evsc_priority_balancer_enabled"
HELPER_NIGHT_CHARGE_ENABLED_SUFFIX = "evsc_night_smart_charge_enabled"

# Notification Switches
HELPER_NOTIFY_SMART_BLOCKER_SUFFIX = "evsc_notify_smart_blocker_enabled"
HELPER_NOTIFY_PRIORITY_BALANCER_SUFFIX = "evsc_notify_priority_balancer_enabled"
HELPER_NOTIFY_NIGHT_CHARGE_SUFFIX = "evsc_notify_night_charge_enabled"

# Numbers - Solar Surplus
HELPER_CHECK_INTERVAL_SUFFIX = "evsc_check_interval"
HELPER_GRID_IMPORT_THRESHOLD_SUFFIX = "evsc_grid_import_threshold"
HELPER_GRID_IMPORT_DELAY_SUFFIX = "evsc_grid_import_delay"
HELPER_SURPLUS_DROP_DELAY_SUFFIX = "evsc_surplus_drop_delay"
HELPER_HOME_BATTERY_MIN_SOC_SUFFIX = "evsc_home_battery_min_soc"
HELPER_BATTERY_SUPPORT_AMPERAGE_SUFFIX = "evsc_battery_support_amperage"

# Numbers - Night Smart Charge
HELPER_NIGHT_CHARGE_AMPERAGE_SUFFIX = "evsc_night_charge_amperage"
HELPER_MIN_SOLAR_FORECAST_THRESHOLD_SUFFIX = "evsc_min_solar_forecast_threshold"

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

# Sensors
HELPER_DIAGNOSTIC_SENSOR_SUFFIX = "evsc_diagnostic"
HELPER_PRIORITY_STATE_SUFFIX = "evsc_priority_daily_state"
HELPER_SOLAR_SURPLUS_DIAGNOSTIC_SUFFIX = "evsc_solar_surplus_diagnostic"

# ========== DEFAULT VALUES - SOLAR SURPLUS ==========
DEFAULT_CHECK_INTERVAL = 1  # minutes
DEFAULT_GRID_IMPORT_THRESHOLD = 50  # watts
DEFAULT_GRID_IMPORT_DELAY = 30  # seconds
DEFAULT_SURPLUS_DROP_DELAY = 30  # seconds

# ========== SURPLUS HYSTERESIS SETTINGS ==========
SURPLUS_START_THRESHOLD = 6.5  # amps - minimum surplus to START charging (with margin)
SURPLUS_STOP_THRESHOLD = 5.5   # amps - minimum surplus to CONTINUE charging
SURPLUS_HYSTERESIS_MARGIN = 1.0  # amps - dead band to prevent oscillation (6.5 - 5.5)
SURPLUS_STABLE_DURATION = 15  # seconds - required stable surplus before starting
SURPLUS_INCREASE_DELAY = 60  # seconds - delay before increasing amperage (cloud protection)

# ========== DEFAULT VALUES - HOME BATTERY SUPPORT ==========
DEFAULT_HOME_BATTERY_MIN_SOC = 20  # percent
DEFAULT_BATTERY_SUPPORT_AMPERAGE = 16  # amps (user configurable)

# ========== DEFAULT VALUES - PRIORITY BALANCER ==========
DEFAULT_EV_MIN_SOC_WEEKDAY = 50  # percent (Monday-Friday)
DEFAULT_EV_MIN_SOC_WEEKEND = 80  # percent (Saturday-Sunday)
DEFAULT_HOME_MIN_SOC = 50  # percent (all days)

# ========== DEFAULT VALUES - NIGHT SMART CHARGE ==========
DEFAULT_NIGHT_CHARGE_TIME = "01:00:00"
DEFAULT_MIN_SOLAR_FORECAST_THRESHOLD = 20  # kWh
DEFAULT_NIGHT_CHARGE_AMPERAGE = 16  # amps
NIGHT_CHARGE_COOLDOWN_SECONDS = 3600  # 1 hour - prevent re-evaluation after completion

# ========== DEFAULT VALUES - CAR READY FLAGS ==========
DEFAULT_CAR_READY_WEEKDAY = True  # Monday-Friday (car needed for work)
DEFAULT_CAR_READY_WEEKEND = False  # Saturday-Sunday (car not urgently needed)

# ========== SMART BLOCKER SETTINGS ==========
SMART_BLOCKER_ENFORCEMENT_TIMEOUT = 1800  # 30 minutes in seconds
SMART_BLOCKER_RETRY_ATTEMPTS = 3
SMART_BLOCKER_RETRY_DELAYS = [2, 4, 6]  # seconds

# ========== RATE LIMITING ==========
SOLAR_SURPLUS_MIN_CHECK_INTERVAL = 30  # seconds between checks
SOLAR_SURPLUS_MAX_CHECKS_PER_MINUTE = 10  # warning threshold

# ========== CHARGER CONTROLLER SETTINGS ==========
CHARGER_MIN_OPERATION_INTERVAL = 30  # seconds between charger operations (rate limiting)
CHARGER_QUEUE_MAX_SIZE = 10  # maximum operations in queue

# ========== DELAYS ==========
CHARGER_COMMAND_DELAY = 2  # seconds to wait after charger commands
CHARGER_START_SEQUENCE_DELAY = 2  # seconds between turn_on and set amperage
CHARGER_STOP_SEQUENCE_DELAY = 5  # seconds after stop before setting amperage
CHARGER_AMPERAGE_STABILIZATION_DELAY = 1  # seconds after setting amperage

# ========== TIMEOUTS ==========
SERVICE_CALL_TIMEOUT = 10  # seconds for service calls
