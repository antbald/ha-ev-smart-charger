DOMAIN = "ev_smart_charger"
DEFAULT_NAME = "EV Smart Charger"
PLATFORMS = ["switch", "number", "select", "sensor"]

# Configuration keys
CONF_EV_CHARGER_SWITCH = "ev_charger_switch"
CONF_EV_CHARGER_CURRENT = "ev_charger_current"
CONF_EV_CHARGER_STATUS = "ev_charger_status"
CONF_SOC_CAR = "soc_car"
CONF_SOC_HOME = "soc_home"
CONF_FV_PRODUCTION = "fv_production"
CONF_HOME_CONSUMPTION = "home_consumption"
CONF_GRID_IMPORT = "grid_import"

# EV Charger current amp levels
CHARGER_AMP_LEVELS = [6, 8, 10, 13, 16, 20, 24, 32]

# EV Charger status states
CHARGER_STATUS_CHARGING = "charger_charging"
CHARGER_STATUS_FREE = "charger_free"
CHARGER_STATUS_END = "charger_end"
CHARGER_STATUS_WAIT = "charger_wait"

# Charging Profiles
PROFILE_MANUAL = "manual"
PROFILE_SOLAR_SURPLUS = "solar_surplus"
PROFILE_CHARGE_TARGET = "charge_target"
PROFILE_CHEAPEST = "cheapest"
CHARGING_PROFILES = [PROFILE_MANUAL, PROFILE_SOLAR_SURPLUS, PROFILE_CHARGE_TARGET, PROFILE_CHEAPEST]

# Helper entity suffixes (auto-created by integration)
HELPER_FORZA_RICARICA_SUFFIX = "evsc_forza_ricarica"
HELPER_SMART_BLOCKER_ENABLED_SUFFIX = "evsc_smart_charger_blocker_enabled"
HELPER_SOLAR_THRESHOLD_SUFFIX = "evsc_solar_production_threshold"
HELPER_CHARGING_PROFILE_SUFFIX = "evsc_charging_profile"
HELPER_CHECK_INTERVAL_SUFFIX = "evsc_check_interval"
HELPER_GRID_IMPORT_THRESHOLD_SUFFIX = "evsc_grid_import_threshold"
HELPER_GRID_IMPORT_DELAY_SUFFIX = "evsc_grid_import_delay"
HELPER_SURPLUS_DROP_DELAY_SUFFIX = "evsc_surplus_drop_delay"
HELPER_USE_HOME_BATTERY_SUFFIX = "evsc_use_home_battery"
HELPER_HOME_BATTERY_MIN_SOC_SUFFIX = "evsc_home_battery_min_soc"
HELPER_PRIORITY_BALANCER_ENABLED_SUFFIX = "evsc_priority_balancer_enabled"
HELPER_EV_MIN_SOC_MONDAY_SUFFIX = "evsc_ev_min_soc_monday"
HELPER_EV_MIN_SOC_TUESDAY_SUFFIX = "evsc_ev_min_soc_tuesday"
HELPER_EV_MIN_SOC_WEDNESDAY_SUFFIX = "evsc_ev_min_soc_wednesday"
HELPER_EV_MIN_SOC_THURSDAY_SUFFIX = "evsc_ev_min_soc_thursday"
HELPER_EV_MIN_SOC_FRIDAY_SUFFIX = "evsc_ev_min_soc_friday"
HELPER_EV_MIN_SOC_SATURDAY_SUFFIX = "evsc_ev_min_soc_saturday"
HELPER_EV_MIN_SOC_SUNDAY_SUFFIX = "evsc_ev_min_soc_sunday"
HELPER_PRIORITY_STATE_SUFFIX = "evsc_priority_daily_state"

# Default values
DEFAULT_SOLAR_THRESHOLD = 50  # Watts
DEFAULT_CHECK_INTERVAL = 1  # Minutes
DEFAULT_GRID_IMPORT_THRESHOLD = 50  # Watts
DEFAULT_GRID_IMPORT_DELAY = 30  # Seconds
DEFAULT_SURPLUS_DROP_DELAY = 30  # Seconds
DEFAULT_HOME_BATTERY_MIN_SOC = 20  # Percent
DEFAULT_EV_MIN_SOC_WEEKDAY = 50  # Percent (Monday-Friday)
DEFAULT_EV_MIN_SOC_WEEKEND = 80  # Percent (Saturday-Sunday)
VOLTAGE_EU = 230  # Volts (European standard)
FALLBACK_AMPERAGE_WITH_BATTERY = 16  # Fixed amperage when using battery support

# Priority Daily Charging Balancer states
PRIORITY_EV = "EV"
PRIORITY_HOME = "Home"
PRIORITY_EV_FREE = "EV_Free"
