DOMAIN = "ev_smart_charger"
DEFAULT_NAME = "EV Smart Charger"

# Configuration keys
CONF_EV_CHARGER_SWITCH = "ev_charger_switch"
CONF_EV_CHARGER_CURRENT = "ev_charger_current"
CONF_EV_CHARGER_STATUS = "ev_charger_status"
CONF_SOC_CAR = "soc_car"
CONF_SOC_HOME = "soc_home"
CONF_FV_PRODUCTION = "fv_production"
CONF_HOME_CONSUMPTION = "home_consumption"

# EV Charger current amp levels
CHARGER_AMP_LEVELS = [6, 8, 10, 13, 16, 20, 24, 32]

# EV Charger status states
CHARGER_STATUS_CHARGING = "charger_charging"
CHARGER_STATUS_FREE = "charger_free"
CHARGER_STATUS_END = "charger_end"

# Helper entity IDs (auto-created by integration)
HELPER_FORZA_RICARICA = "input_boolean.evsc_forza_ricarica"
HELPER_SMART_BLOCKER_ENABLED = "input_boolean.evsc_smart_charger_blocker_enabled"
HELPER_SOLAR_THRESHOLD = "input_number.evsc_solar_production_threshold"

# Automation IDs
AUTOMATION_SMART_BLOCKER = "automation.evsc_smart_charger_blocker"

# Default values
DEFAULT_SOLAR_THRESHOLD = 50  # Watts
