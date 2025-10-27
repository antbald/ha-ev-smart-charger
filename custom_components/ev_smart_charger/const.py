DOMAIN = "ev_smart_charger"
DEFAULT_NAME = "EV Smart Charger"
PLATFORMS = ["switch", "number", "select"]

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

# Default values
DEFAULT_SOLAR_THRESHOLD = 50  # Watts
DEFAULT_CHECK_INTERVAL = 1  # Minutes
DEFAULT_GRID_IMPORT_THRESHOLD = 50  # Watts
VOLTAGE_EU = 230  # Volts (European standard)
