"""Anonymous telemetry beacon for EV Smart Charger.

Sends a privacy-preserving ping to count active installations, version
distribution, and approximate geographic spread. No personal data is
collected: only an anonymous UUID, integration version, HA version,
and timezone (used to derive a country code).

Opt-out: set the environment variable EVSC_DISABLE_TELEMETRY=true on
the Home Assistant host.
"""
from __future__ import annotations

import logging
import os
from uuid import uuid4

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import TELEMETRY_ENDPOINT, VERSION

_LOGGER = logging.getLogger(__name__)

_STORAGE_KEY = "ev_smart_charger.telemetry"
_STORAGE_VERSION = 1

# ---------------------------------------------------------------------------
# Timezone → ISO-3166-1 alpha-2 country code
# Covers the most common IANA timezones worldwide (~95% of real installs).
# ---------------------------------------------------------------------------
_TIMEZONE_TO_COUNTRY: dict[str, str] = {
    # ── Europe ──────────────────────────────────────────────────────────────
    "Europe/Rome": "IT", "Europe/Vatican": "IT", "Europe/San_Marino": "IT",
    "Europe/London": "GB", "Europe/Guernsey": "GB", "Europe/Jersey": "GB",
    "Europe/Isle_of_Man": "GB",
    "Europe/Paris": "FR", "Europe/Monaco": "MC",
    "Europe/Berlin": "DE", "Europe/Busingen": "DE",
    "Europe/Madrid": "ES", "Atlantic/Canary": "ES",
    "Europe/Amsterdam": "NL",
    "Europe/Brussels": "BE",
    "Europe/Vienna": "AT",
    "Europe/Vaduz": "LI",
    "Europe/Zurich": "CH",
    "Europe/Stockholm": "SE",
    "Europe/Oslo": "NO",
    "Europe/Helsinki": "FI", "Europe/Mariehamn": "FI",
    "Europe/Copenhagen": "DK",
    "Europe/Warsaw": "PL",
    "Europe/Prague": "CZ",
    "Europe/Bratislava": "SK",
    "Europe/Budapest": "HU",
    "Europe/Bucharest": "RO",
    "Europe/Sofia": "BG",
    "Europe/Athens": "GR",
    "Europe/Lisbon": "PT", "Atlantic/Azores": "PT", "Atlantic/Madeira": "PT",
    "Europe/Dublin": "IE",
    "Europe/Riga": "LV",
    "Europe/Tallinn": "EE",
    "Europe/Vilnius": "LT",
    "Europe/Ljubljana": "SI",
    "Europe/Zagreb": "HR",
    "Europe/Sarajevo": "BA",
    "Europe/Skopje": "MK",
    "Europe/Belgrade": "RS",
    "Europe/Podgorica": "ME",
    "Europe/Tirane": "AL",
    "Europe/Chisinau": "MD",
    "Europe/Kiev": "UA", "Europe/Uzhgorod": "UA", "Europe/Zaporozhye": "UA",
    "Europe/Minsk": "BY",
    "Europe/Moscow": "RU", "Europe/Kaliningrad": "RU", "Europe/Samara": "RU",
    "Europe/Saratov": "RU", "Europe/Volgograd": "RU", "Europe/Ulyanovsk": "RU",
    "Europe/Istanbul": "TR",
    "Europe/Nicosia": "CY", "Asia/Nicosia": "CY",
    "Europe/Malta": "MT",
    "Europe/Luxembourg": "LU",
    "Europe/Andorra": "AD",
    "Atlantic/Reykjavik": "IS",
    "Atlantic/Faroe": "FO",
    # ── Americas ────────────────────────────────────────────────────────────
    "America/New_York": "US", "America/Chicago": "US", "America/Denver": "US",
    "America/Los_Angeles": "US", "America/Anchorage": "US", "America/Phoenix": "US",
    "America/Honolulu": "US", "America/Juneau": "US", "America/Adak": "US",
    "America/Detroit": "US", "America/Indiana/Indianapolis": "US",
    "America/Indiana/Knox": "US", "America/Indiana/Marengo": "US",
    "America/Indiana/Tell_City": "US", "America/Indiana/Petersburg": "US",
    "America/Indiana/Vincennes": "US", "America/Indiana/Winamac": "US",
    "America/Kentucky/Louisville": "US", "America/Kentucky/Monticello": "US",
    "America/North_Dakota/Center": "US", "America/North_Dakota/New_Salem": "US",
    "America/North_Dakota/Beulah": "US", "America/Boise": "US",
    "America/Toronto": "CA", "America/Vancouver": "CA", "America/Edmonton": "CA",
    "America/Winnipeg": "CA", "America/Halifax": "CA", "America/St_Johns": "CA",
    "America/Regina": "CA", "America/Dawson_Creek": "CA", "America/Fort_Nelson": "CA",
    "America/Whitehorse": "CA", "America/Dawson": "CA", "America/Glace_Bay": "CA",
    "America/Goose_Bay": "CA", "America/Iqaluit": "CA", "America/Moncton": "CA",
    "America/Mexico_City": "MX", "America/Cancun": "MX", "America/Monterrey": "MX",
    "America/Merida": "MX", "America/Chihuahua": "MX", "America/Mazatlan": "MX",
    "America/Hermosillo": "MX", "America/Tijuana": "MX",
    "America/Sao_Paulo": "BR", "America/Manaus": "BR", "America/Fortaleza": "BR",
    "America/Belem": "BR", "America/Recife": "BR", "America/Bahia": "BR",
    "America/Cuiaba": "BR", "America/Campo_Grande": "BR", "America/Porto_Velho": "BR",
    "America/Boa_Vista": "BR", "America/Rio_Branco": "BR", "America/Noronha": "BR",
    "America/Araguaina": "BR", "America/Maceio": "BR",
    "America/Argentina/Buenos_Aires": "AR", "America/Argentina/Cordoba": "AR",
    "America/Argentina/Jujuy": "AR", "America/Argentina/Mendoza": "AR",
    "America/Argentina/Salta": "AR", "America/Argentina/San_Juan": "AR",
    "America/Argentina/San_Luis": "AR", "America/Argentina/Catamarca": "AR",
    "America/Argentina/La_Rioja": "AR", "America/Argentina/Rio_Gallegos": "AR",
    "America/Argentina/Tucuman": "AR", "America/Argentina/Ushuaia": "AR",
    "America/Santiago": "CL", "Pacific/Easter": "CL",
    "America/Bogota": "CO",
    "America/Lima": "PE",
    "America/Caracas": "VE",
    "America/La_Paz": "BO",
    "America/Montevideo": "UY",
    "America/Asuncion": "PY",
    "America/Guayaquil": "EC", "Pacific/Galapagos": "EC",
    "America/Paramaribo": "SR",
    "America/Guyana": "GY",
    "America/Cayenne": "GF",
    "America/Havana": "CU",
    "America/Jamaica": "JM",
    "America/Nassau": "BS",
    "America/Santo_Domingo": "DO",
    "America/Puerto_Rico": "PR",
    "America/Panama": "PA",
    "America/Costa_Rica": "CR",
    "America/Guatemala": "GT",
    "America/Managua": "NI",
    "America/Tegucigalpa": "HN",
    "America/El_Salvador": "SV",
    "America/Belize": "BZ",
    # ── Asia ────────────────────────────────────────────────────────────────
    "Asia/Tokyo": "JP",
    "Asia/Seoul": "KR",
    "Asia/Shanghai": "CN", "Asia/Urumqi": "CN", "Asia/Harbin": "CN",
    "Asia/Chongqing": "CN", "Asia/Kashgar": "CN",
    "Asia/Hong_Kong": "HK",
    "Asia/Macau": "MO",
    "Asia/Singapore": "SG",
    "Asia/Taipei": "TW",
    "Asia/Bangkok": "TH",
    "Asia/Jakarta": "ID", "Asia/Makassar": "ID", "Asia/Jayapura": "ID",
    "Asia/Pontianak": "ID",
    "Asia/Kuala_Lumpur": "MY", "Asia/Kuching": "MY",
    "Asia/Manila": "PH",
    "Asia/Ho_Chi_Minh": "VN", "Asia/Hanoi": "VN",
    "Asia/Phnom_Penh": "KH",
    "Asia/Vientiane": "LA",
    "Asia/Rangoon": "MM", "Asia/Yangon": "MM",
    "Asia/Dhaka": "BD",
    "Asia/Kolkata": "IN", "Asia/Calcutta": "IN",
    "Asia/Colombo": "LK",
    "Asia/Kathmandu": "NP", "Asia/Katmandu": "NP",
    "Asia/Karachi": "PK",
    "Asia/Kabul": "AF",
    "Asia/Tehran": "IR",
    "Asia/Baghdad": "IQ",
    "Asia/Kuwait": "KW",
    "Asia/Riyadh": "SA", "Asia/Aden": "YE",
    "Asia/Qatar": "QA",
    "Asia/Bahrain": "BH",
    "Asia/Dubai": "AE", "Asia/Muscat": "OM",
    "Asia/Jerusalem": "IL", "Asia/Tel_Aviv": "IL",
    "Asia/Beirut": "LB",
    "Asia/Damascus": "SY",
    "Asia/Amman": "JO",
    "Asia/Gaza": "PS", "Asia/Hebron": "PS",
    "Asia/Tbilisi": "GE",
    "Asia/Yerevan": "AM",
    "Asia/Baku": "AZ",
    "Asia/Almaty": "KZ", "Asia/Qyzylorda": "KZ", "Asia/Aqtau": "KZ",
    "Asia/Aqtobe": "KZ", "Asia/Atyrau": "KZ", "Asia/Oral": "KZ",
    "Asia/Tashkent": "UZ", "Asia/Samarkand": "UZ",
    "Asia/Bishkek": "KG",
    "Asia/Ashgabat": "TM", "Asia/Ashkhabad": "TM",
    "Asia/Dushanbe": "TJ",
    "Asia/Ulaanbaatar": "MN", "Asia/Ulan_Bator": "MN",
    "Asia/Yakutsk": "RU", "Asia/Vladivostok": "RU", "Asia/Sakhalin": "RU",
    "Asia/Magadan": "RU", "Asia/Srednekolymsk": "RU",
    "Asia/Kamchatka": "RU", "Asia/Anadyr": "RU",
    "Asia/Novosibirsk": "RU", "Asia/Omsk": "RU", "Asia/Krasnoyarsk": "RU",
    "Asia/Irkutsk": "RU", "Asia/Chita": "RU",
    "Asia/Yekaterinburg": "RU",
    "Asia/Colombo": "LK",
    "Asia/Thimphu": "BT", "Asia/Thimbu": "BT",
    "Asia/Brunei": "BN",
    "Asia/Dili": "TL",
    "Indian/Maldives": "MV",
    # ── Australia & Oceania ─────────────────────────────────────────────────
    "Australia/Sydney": "AU", "Australia/Melbourne": "AU",
    "Australia/Brisbane": "AU", "Australia/Perth": "AU",
    "Australia/Adelaide": "AU", "Australia/Darwin": "AU",
    "Australia/Hobart": "AU", "Australia/Lord_Howe": "AU",
    "Australia/Eucla": "AU", "Australia/Broken_Hill": "AU",
    "Pacific/Auckland": "NZ", "Pacific/Chatham": "NZ",
    "Pacific/Fiji": "FJ",
    "Pacific/Guam": "GU",
    "Pacific/Port_Moresby": "PG", "Pacific/Bougainville": "PG",
    "Pacific/Apia": "WS",
    "Pacific/Tongatapu": "TO",
    "Pacific/Honolulu": "US",
    # ── Africa ──────────────────────────────────────────────────────────────
    "Africa/Cairo": "EG",
    "Africa/Johannesburg": "ZA",
    "Africa/Lagos": "NG",
    "Africa/Abidjan": "CI",
    "Africa/Nairobi": "KE",
    "Africa/Casablanca": "MA",
    "Africa/Tunis": "TN",
    "Africa/Algiers": "DZ",
    "Africa/Addis_Ababa": "ET",
    "Africa/Accra": "GH",
    "Africa/Dar_es_Salaam": "TZ",
    "Africa/Khartoum": "SD",
    "Africa/Tripoli": "LY",
    "Africa/Luanda": "AO",
    "Africa/Maputo": "MZ",
    "Africa/Harare": "ZW",
    "Africa/Lusaka": "ZM",
    "Africa/Windhoek": "NA",
    "Africa/Gaborone": "BW",
    "Africa/Blantyre": "MW",
    "Africa/Kampala": "UG",
    "Africa/Kigali": "RW",
    "Africa/Bujumbura": "BI",
    "Africa/Kinshasa": "CD", "Africa/Lubumbashi": "CD",
    "Africa/Brazzaville": "CG",
    "Africa/Dakar": "SN",
    "Africa/Bamako": "ML",
    "Africa/Ouagadougou": "BF",
    "Africa/Nouakchott": "MR",
    "Africa/Conakry": "GN",
    "Africa/Freetown": "SL",
    "Africa/Monrovia": "LR",
    "Africa/Lome": "TG",
    "Africa/Cotonou": "BJ",
    "Africa/Niamey": "NE",
    "Africa/Ndjamena": "TD",
    "Africa/Douala": "CM",
    "Africa/Malabo": "GQ",
    "Africa/Libreville": "GA",
    "Africa/Bangui": "CF",
    "Africa/Djibouti": "DJ",
    "Africa/Mogadishu": "SO",
    "Africa/Asmara": "ER",
    "Africa/Juba": "SS",
    "Africa/Maseru": "LS",
    "Africa/Mbabane": "SZ",
    "Indian/Mauritius": "MU",
    "Indian/Reunion": "RE",
    "Indian/Antananarivo": "MG",
}

_COUNTRY_TO_CONTINENT: dict[str, str] = {
    # Europe
    "IT": "EU", "GB": "EU", "FR": "EU", "DE": "EU", "ES": "EU",
    "NL": "EU", "BE": "EU", "AT": "EU", "LI": "EU", "CH": "EU",
    "SE": "EU", "NO": "EU", "FI": "EU", "DK": "EU", "PL": "EU",
    "CZ": "EU", "SK": "EU", "HU": "EU", "RO": "EU", "BG": "EU",
    "GR": "EU", "PT": "EU", "IE": "EU", "LV": "EU", "EE": "EU",
    "LT": "EU", "SI": "EU", "HR": "EU", "BA": "EU", "MK": "EU",
    "RS": "EU", "ME": "EU", "AL": "EU", "MD": "EU", "UA": "EU",
    "BY": "EU", "TR": "EU", "CY": "EU", "MT": "EU", "LU": "EU",
    "MC": "EU", "SM": "EU", "AD": "EU", "IS": "EU", "FO": "EU",
    "RU": "EU",  # geographically both EU and AS; EU for analytics
    # North America
    "US": "NA", "CA": "NA", "MX": "NA", "CU": "NA", "JM": "NA",
    "BS": "NA", "DO": "NA", "PR": "NA", "PA": "NA", "CR": "NA",
    "GT": "NA", "NI": "NA", "HN": "NA", "SV": "NA", "BZ": "NA",
    "GF": "SA",  # French Guiana → South America
    # South America
    "BR": "SA", "AR": "SA", "CL": "SA", "CO": "SA", "PE": "SA",
    "VE": "SA", "BO": "SA", "UY": "SA", "PY": "SA", "EC": "SA",
    "SR": "SA", "GY": "SA",
    # Asia
    "JP": "AS", "KR": "AS", "CN": "AS", "HK": "AS", "MO": "AS",
    "SG": "AS", "TW": "AS", "TH": "AS", "ID": "AS", "MY": "AS",
    "PH": "AS", "VN": "AS", "KH": "AS", "LA": "AS", "MM": "AS",
    "BD": "AS", "IN": "AS", "LK": "AS", "NP": "AS", "PK": "AS",
    "AF": "AS", "IR": "AS", "IQ": "AS", "KW": "AS", "SA": "AS",
    "YE": "AS", "QA": "AS", "BH": "AS", "AE": "AS", "OM": "AS",
    "IL": "AS", "LB": "AS", "SY": "AS", "JO": "AS", "PS": "AS",
    "GE": "AS", "AM": "AS", "AZ": "AS", "KZ": "AS", "UZ": "AS",
    "KG": "AS", "TM": "AS", "TJ": "AS", "MN": "AS", "BT": "AS",
    "BN": "AS", "TL": "AS", "MV": "AS",
    # Oceania
    "AU": "OC", "NZ": "OC", "FJ": "OC", "GU": "OC", "PG": "OC",
    "WS": "OC", "TO": "OC",
    # Africa
    "EG": "AF", "ZA": "AF", "NG": "AF", "CI": "AF", "KE": "AF",
    "MA": "AF", "TN": "AF", "DZ": "AF", "ET": "AF", "GH": "AF",
    "TZ": "AF", "SD": "AF", "LY": "AF", "AO": "AF", "MZ": "AF",
    "ZW": "AF", "ZM": "AF", "NA": "AF", "BW": "AF", "MW": "AF",
    "UG": "AF", "RW": "AF", "BI": "AF", "CD": "AF", "CG": "AF",
    "SN": "AF", "ML": "AF", "BF": "AF", "MR": "AF", "GN": "AF",
    "SL": "AF", "LR": "AF", "TG": "AF", "BJ": "AF", "NE": "AF",
    "TD": "AF", "CM": "AF", "GQ": "AF", "GA": "AF", "CF": "AF",
    "DJ": "AF", "SO": "AF", "ER": "AF", "SS": "AF", "LS": "AF",
    "SZ": "AF", "MU": "AF", "RE": "AF", "MG": "AF",
}


async def _get_or_create_installation_id(hass: HomeAssistant) -> str:
    """Load or generate a persistent anonymous installation UUID.

    Stored in HA's .storage directory as ev_smart_charger.telemetry.
    A new UUID is created only on the very first run.
    """
    store: Store = Store(hass, _STORAGE_VERSION, _STORAGE_KEY)
    data = await store.async_load()
    if data and "installation_id" in data:
        return str(data["installation_id"])
    new_id = str(uuid4())
    await store.async_save({"installation_id": new_id})
    _LOGGER.debug("📊 Telemetry: new installation_id generated")
    return new_id


async def send_telemetry_ping(hass: HomeAssistant) -> None:
    """Send a fire-and-forget anonymous ping to the telemetry endpoint.

    Failures are silently swallowed — the ping must never affect integration
    startup or normal operation.
    """
    if os.environ.get("EVSC_DISABLE_TELEMETRY", "").lower() in ("1", "true", "yes"):
        _LOGGER.debug("📊 Telemetry disabled via EVSC_DISABLE_TELEMETRY")
        return

    try:
        installation_id = await _get_or_create_installation_id(hass)
        timezone = hass.config.time_zone or "Unknown"
        country = _TIMEZONE_TO_COUNTRY.get(timezone, "XX")
        continent = _COUNTRY_TO_CONTINENT.get(country, "XX")

        payload = {
            "installation_id": installation_id,
            "version": VERSION,
            "ha_version": str(hass.config.version),
            "timezone": timezone,
            "country": country,
            "continent": continent,
        }

        session = async_get_clientsession(hass)
        async with session.post(
            TELEMETRY_ENDPOINT,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=8),
            allow_redirects=True,
        ) as resp:
            _LOGGER.debug("📊 Telemetry ping sent (HTTP %s)", resp.status)

    except Exception:  # noqa: BLE001
        _LOGGER.debug("📊 Telemetry ping skipped (network or server unavailable)")
