// EV Smart Charger Dashboard — Lovelace custom card
// v1.10.0 — Split-view rendering: Dashboard (operational) + Settings (configuration
// accordions). Hero ring with EV label inside and CHARGING pill below. Bento-style
// Night Smart Charge card with crescent illustration. Language detection inherited
// from this._hass.language (no manual picker). Exposes all 64 helper entities
// (51 in PV-only mode).
const DEFAULT_TITLE = "EV Smart Charger";
const SUPPORTED_PROFILES = ["manual", "solar_surplus"];
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const DAY_INITIALS_BY_LOCALE = {
  en: ["M", "T", "W", "T", "F", "S", "S"],
  it: ["L", "M", "M", "G", "V", "S", "D"],
  nl: ["M", "D", "W", "D", "V", "Z", "Z"],
};
/* v1.11.0: full weekday names for the day-grouped mobile cards. The
   editorial italic display font really sings on "Wednesday" / "Mercoledì"
   — far more characterful than a single-letter chip. */
const DAY_FULL_NAMES_BY_LOCALE = {
  en: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
  it: ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
  nl: ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"],
};
const DOMAIN_SUFFIXES = {
  // ── Core controls
  forceCharge: ["switch", "evsc_forza_ricarica"],
  chargingProfile: ["select", "evsc_charging_profile"],

  // ── Boost Charge (manual + scheduled)
  boostEnabled: ["switch", "evsc_boost_charge_enabled"],
  boostAmperage: ["number", "evsc_boost_charge_amperage"],
  boostTargetSoc: ["number", "evsc_boost_target_soc"],
  boostScheduleEnabled: ["switch", "evsc_boost_schedule_enabled"],
  boostScheduleStartTime: ["time", "evsc_boost_schedule_start_time"],
  boostScheduleEndTime: ["time", "evsc_boost_schedule_end_time"],

  // ── Night Smart Charge
  nightEnabled: ["switch", "evsc_night_smart_charge_enabled"],
  preserveHomeBattery: ["switch", "evsc_preserve_home_battery"],
  nightTime: ["time", "evsc_night_charge_time"],
  carReadyTime: ["time", "evsc_car_ready_time"],
  minSolarForecast: ["number", "evsc_min_solar_forecast_threshold"],
  nightAmperage: ["number", "evsc_night_charge_amperage"],

  // ── Solar Surplus
  checkInterval: ["number", "evsc_check_interval"],
  gridImportThreshold: ["number", "evsc_grid_import_threshold"],
  gridImportDelay: ["number", "evsc_grid_import_delay"],
  surplusDropDelay: ["number", "evsc_surplus_drop_delay"],
  solarMaxAmperage: ["number", "evsc_solar_max_amperage"],
  useHomeBattery: ["switch", "evsc_use_home_battery"],
  homeBatteryMinSoc: ["number", "evsc_home_battery_min_soc"],
  batterySupportAmperage: ["number", "evsc_battery_support_amperage"],
  batterySupportSunsetBuffer: ["number", "evsc_battery_support_sunset_buffer"],

  // ── Hybrid Inverter Mode (v1.8.0 — issue #20)
  hybridMode: ["switch", "evsc_hybrid_inverter_mode"],
  hybridBatteryFullThreshold: ["number", "evsc_hybrid_battery_full_threshold"],
  hybridProbeDuration: ["number", "evsc_hybrid_probe_duration"],
  hybridMaxImportDuration: ["number", "evsc_hybrid_max_import_duration"],
  hybridMaxFailedProbes: ["number", "evsc_hybrid_max_failed_probes"],
  hybridDiagnostic: ["sensor", "evsc_hybrid_inverter_diagnostic"],

  // ── Safety / Protection
  priorityBalancer: ["switch", "evsc_priority_balancer_enabled"],
  smartBlocker: ["switch", "evsc_smart_charger_blocker_enabled"],

  // ── Notifications (v1.3.20)
  notifySmartBlocker: ["switch", "evsc_notify_smart_blocker_enabled"],
  notifyPriorityBalancer: ["switch", "evsc_notify_priority_balancer_enabled"],
  notifyNightCharge: ["switch", "evsc_notify_night_charge_enabled"],

  // ── Logging (v1.3.25 / v1.4.15)
  traceLogging: ["switch", "evsc_trace_logging_enabled"],
  enableFileLogging: ["switch", "evsc_enable_file_logging"],
  logFilePath: ["sensor", "evsc_log_file_path"],

  // ── Diagnostic sensors
  priorityState: ["sensor", "evsc_priority_daily_state"],
  todayEvTarget: ["sensor", "evsc_today_ev_target"],
  todayHomeTarget: ["sensor", "evsc_today_home_target"],
  cachedEvSoc: ["sensor", "evsc_cached_ev_soc"],
  diagnostic: ["sensor", "evsc_diagnostic"],
  solarDiagnostic: ["sensor", "evsc_solar_surplus_diagnostic"],
};

// Daily helper entities — generated programmatically (saves ~50 lines of boilerplate).
for (const day of DAYS) {
  DOMAIN_SUFFIXES[`carReady_${day}`] = ["switch", `evsc_car_ready_${day}`];
  DOMAIN_SUFFIXES[`evMinSoc_${day}`] = ["number", `evsc_ev_min_soc_${day}`];
  DOMAIN_SUFFIXES[`homeMinSoc_${day}`] = ["number", `evsc_home_min_soc_${day}`];
}

// =====================================================================
// v1.10.0 reorganization: Settings catalog with inline translations.
// Single source of truth for the Settings view accordions. Each item
// has a kind ("toggle" | "stepper" | "time" | "info"), an entityKey
// resolved via DOMAIN_SUFFIXES, and EN/IT/NL strings for the labels.
// =====================================================================
const SETTINGS_CATALOG = [
  {
    id: "solar", iconClass: "sun", icon: "☀",
    name: { en: "Solar Surplus", it: "Surplus solare", nl: "Zonneoverschot" },
    desc: {
      en: "Solar surplus calculation, grid import protection, daytime home battery fallback",
      it: "Calcolo surplus PV, protezione import rete, fallback batteria di casa diurno",
      nl: "Berekening overschot, beveiliging tegen netinvoer, gebruik thuisbatterij overdag",
    },
    items: [
      { entityKey: "checkInterval", kind: "stepper",
        name: { en: "Check Interval", it: "Intervallo di controllo", nl: "Controle-interval" },
        desc: {
          en: "How often Solar Surplus recalculates amperage and decision. Lower = more reactive but more wallbox writes.",
          it: "Ogni quanto Solar Surplus ricalcola amperaggio e decisione. Piu basso = piu reattivo ma piu scritture sul wallbox.",
          nl: "Hoe vaak Solar Surplus stroom en beslissing herberekent. Lager = reactiever maar meer wallbox-schrijfacties.",
        },
        hint: { en: "Default 1 min · Range 1–60 min", it: "Default 1 min · Range 1–60 min", nl: "Standaard 1 min · Bereik 1–60 min" } },
      { entityKey: "gridImportThreshold", kind: "stepper",
        name: { en: "Grid Import Threshold", it: "Soglia prelievo rete", nl: "Drempel netinvoer" },
        desc: {
          en: "Max watts importable from grid before reducing amperage. Above this, the protection delay timer starts.",
          it: "Watt massimi importabili dalla rete prima di ridurre l'amperaggio. Sopra questo valore parte il delay di protezione.",
          nl: "Max watt netinvoer voordat de stroom wordt verlaagd. Daarboven start de beschermingsvertraging.",
        },
        hint: { en: "Default 50 W · Hysteresis recovery 25 W", it: "Default 50 W · Recovery isteresi 25 W", nl: "Standaard 50 W · Hysterese-herstel 25 W" } },
      { entityKey: "gridImportDelay", kind: "stepper",
        name: { en: "Grid Import Delay", it: "Ritardo prelievo rete", nl: "Vertraging netinvoer" },
        desc: {
          en: "Tolerance seconds before reducing amperage. Filters short spikes (fridge, oven, microwave).",
          it: "Secondi di tolleranza prima di ridurre l'amperaggio. Filtra picchi momentanei (frigo, forno, microonde).",
          nl: "Tolerantiesecondes voordat de stroom wordt verlaagd. Filtert korte pieken (koelkast, oven, magnetron).",
        },
        hint: { en: "Default 30 s", it: "Default 30 s", nl: "Standaard 30 s" } },
      { entityKey: "surplusDropDelay", kind: "stepper",
        name: { en: "Surplus Drop Delay", it: "Ritardo calo surplus", nl: "Vertraging overschotdaling" },
        desc: {
          en: "Wait seconds before stopping the wallbox when surplus drops. Protects against passing clouds.",
          it: "Secondi di attesa prima di fermare il wallbox quando il surplus cala. Protegge da nuvole di passaggio.",
          nl: "Wachtseconden voordat de wallbox stopt bij overschotdaling. Beschermt tegen voorbijtrekkende wolken.",
        },
        hint: { en: "Default 30 s · Cloud filter", it: "Default 30 s · Filtro nuvole", nl: "Standaard 30 s · Wolkenfilter" } },
      { entityKey: "solarMaxAmperage", kind: "stepper",
        name: { en: "Solar Max Amperage", it: "Amperaggio max solare", nl: "Maximale zonnestroom" },
        desc: {
          en: "Maximum current Solar Surplus can request. Caps wallbox usage below the physical limit.",
          it: "Tetto massimo di corrente che Solar Surplus puo richiedere. Limita l'uso del wallbox al di sotto della portata fisica.",
          nl: "Maximale stroom die Solar Surplus mag opvragen. Beperkt wallboxgebruik onder de fysieke limiet.",
        },
        hint: { en: "Default 32 A · Levels 6/8/10/13/16/20/24/32", it: "Default 32 A · Livelli 6/8/10/13/16/20/24/32", nl: "Standaard 32 A · Niveaus 6/8/10/13/16/20/24/32" } },
    ],
  },
  {
    id: "night", iconClass: "moon", icon: "🌙",
    name: { en: "Night Smart Charge", it: "Night Smart Charge", nl: "Slim nachtelijk laden" },
    desc: {
      en: "Overnight charging strategy driven by next-day PV forecast",
      it: "Strategia di ricarica notturna basata sul forecast PV del giorno successivo",
      nl: "Strategie voor nachtelijk laden op basis van PV-voorspelling voor morgen",
    },
    items: [
      { entityKey: "nightEnabled", kind: "toggle",
        name: { en: "Enable Night Smart Charge", it: "Abilita Night Smart Charge", nl: "Slim nachtelijk laden inschakelen" },
        desc: {
          en: "Master switch for the nighttime charging logic.",
          it: "Interruttore principale per la logica di ricarica notturna.",
          nl: "Hoofdschakelaar voor de nachtelijke laadlogica.",
        },
        hint: { en: "Default on", it: "Default on", nl: "Standaard aan" } },
      { entityKey: "nightTime", kind: "time",
        name: { en: "Night Charge Start Time", it: "Ora di avvio Night Charge", nl: "Starttijd nachtelijk laden" },
        desc: {
          en: "Time at which the nightly recharge begins. After this hour, if conditions are met, Night Charge takes control.",
          it: "Ora di inizio della ricarica notturna. Dopo questa ora, se le condizioni sono soddisfatte, Night Charge prende il controllo del wallbox.",
          nl: "Tijdstip waarop nachtelijk laden begint. Na dit uur neemt Night Charge de controle over indien aan de voorwaarden is voldaan.",
        },
        hint: { en: "Default 01:00", it: "Default 01:00", nl: "Standaard 01:00" } },
      { entityKey: "carReadyTime", kind: "time",
        name: { en: "Car Ready Deadline", it: "Deadline auto pronta", nl: "Auto-klaar deadline" },
        desc: {
          en: "Latest hour by which the car must be ready on days with the Car Ready flag enabled. After this time charging stops.",
          it: "Ora entro la quale l'auto deve essere pronta nei giorni con flag Car Ready attivo. Oltre questa ora la ricarica si ferma.",
          nl: "Uiterste tijd waarop de auto klaar moet zijn op dagen met Car Ready aan. Daarna stopt het laden.",
        },
        hint: { en: "Default 08:00", it: "Default 08:00", nl: "Standaard 08:00" } },
      { entityKey: "minSolarForecast", kind: "stepper",
        name: { en: "Min Solar Forecast", it: "Forecast solare minimo", nl: "Min. PV-voorspelling" },
        desc: {
          en: "Next-day PV forecast below which Night Charge switches to GRID mode instead of waiting for sun.",
          it: "Forecast PV del giorno successivo sotto cui Night Charge passa in modalita GRID anziche aspettare il sole.",
          nl: "PV-voorspelling van morgen waaronder Night Charge naar GRID schakelt in plaats van op de zon te wachten.",
        },
        hint: { en: "Default 20 kWh", it: "Default 20 kWh", nl: "Standaard 20 kWh" } },
      { entityKey: "nightAmperage", kind: "stepper",
        name: { en: "Night Charge Amperage", it: "Amperaggio Night Charge", nl: "Nachtelijke stroom" },
        desc: {
          en: "Fixed current during nighttime charging in BATTERY or GRID mode.",
          it: "Corrente fissa durante la ricarica notturna in modalita BATTERY o GRID.",
          nl: "Vaste stroom tijdens nachtelijk laden in BATTERY- of GRID-modus.",
        },
        hint: { en: "Default 16 A", it: "Default 16 A", nl: "Standaard 16 A" } },
      { entityKey: "preserveHomeBattery", kind: "toggle",
        name: { en: "Preserve Home Battery", it: "Preserva batteria di casa", nl: "Thuisbatterij sparen" },
        desc: {
          en: "Skip overnight charging when the car does not need to be ready by morning, preserving home battery for daytime.",
          it: "Salta la ricarica notturna quando l'auto non deve essere pronta al mattino, preservando la batteria di casa per il giorno.",
          nl: "Sla nachtelijk laden over wanneer de auto 's ochtends niet klaar hoeft te zijn, om de thuisbatterij overdag te sparen.",
        },
        hint: { en: "Default off", it: "Default off", nl: "Standaard uit" } },
    ],
  },
  {
    id: "battery", iconClass: "bat", icon: "🔋",
    name: { en: "Home Battery Support", it: "Supporto batteria di casa", nl: "Thuisbatterij-ondersteuning" },
    desc: {
      en: "Fallback on home battery when solar surplus is insufficient",
      it: "Fallback su batteria di casa quando il surplus solare e insufficiente",
      nl: "Terugval op thuisbatterij wanneer overschot onvoldoende is",
    },
    items: [
      { entityKey: "useHomeBattery", kind: "toggle",
        name: { en: "Use Home Battery", it: "Usa batteria di casa", nl: "Thuisbatterij gebruiken" },
        desc: {
          en: "When solar surplus is below 6 A and Priority Balancer is in EV mode, drain home battery to top up the EV.",
          it: "Quando il surplus e sotto 6 A e Priority Balancer e in PRIORITY_EV, scarica la batteria di casa per integrare la ricarica EV.",
          nl: "Wanneer het overschot onder 6 A is en Priority Balancer in EV-stand staat, gebruik thuisbatterij om de EV bij te laden.",
        },
        hint: { en: "Default on", it: "Default on", nl: "Standaard aan" } },
      { entityKey: "homeBatteryMinSoc", kind: "stepper",
        name: { en: "Min SOC Reserve", it: "Riserva SOC minimo", nl: "Minimale SOC-reserve" },
        desc: {
          en: "Home battery level below which support automatically disables to preserve reserve.",
          it: "Livello batteria di casa sotto il quale il supporto si disattiva automaticamente per preservare la riserva.",
          nl: "Niveau van de thuisbatterij waaronder ondersteuning automatisch wordt uitgeschakeld om reserve te behouden.",
        },
        hint: { en: "Default 20 %", it: "Default 20 %", nl: "Standaard 20 %" } },
      { entityKey: "batterySupportAmperage", kind: "stepper",
        name: { en: "Battery Support Amperage", it: "Amperaggio supporto batteria", nl: "Stroom thuisbatterij-ondersteuning" },
        desc: {
          en: "Current used when battery support is active and solar surplus is below 6 A.",
          it: "Corrente usata quando il battery support e attivo e il surplus solare non basta.",
          nl: "Stroom die wordt gebruikt wanneer thuisbatterij-ondersteuning actief is en het overschot onder 6 A is.",
        },
        hint: { en: "Default 16 A", it: "Default 16 A", nl: "Standaard 16 A" } },
      { entityKey: "batterySupportSunsetBuffer", kind: "stepper",
        name: { en: "Sunset Buffer", it: "Buffer tramonto", nl: "Zonsondergangbuffer" },
        desc: {
          en: "Minutes before sunset in which battery support is blocked to avoid draining the home in the evening.",
          it: "Minuti prima del tramonto in cui il battery support viene bloccato per evitare di drenare la casa quando il sole sta finendo.",
          nl: "Minuten voor zonsondergang waarin ondersteuning wordt geblokkeerd om de woning 's avonds niet leeg te trekken.",
        },
        hint: { en: "Default 60 min · 0 = disable", it: "Default 60 min · 0 = disabilita", nl: "Standaard 60 min · 0 = uitschakelen" } },
    ],
  },
  {
    id: "hybrid", iconClass: "hyb", icon: "⚡",
    name: { en: "Hybrid Inverter Mode", it: "Hybrid Inverter Mode", nl: "Hybride-omvormermodus" },
    desc: {
      en: "Curtailment discovery for zero-export hybrid inverters (Deye, Sunsynk, Solis…)",
      it: "Curtailment discovery per inverter ibridi zero-export (Deye, Sunsynk, Solis…)",
      nl: "Curtailment-detectie voor hybride zero-export-omvormers (Deye, Sunsynk, Solis…)",
    },
    items: [
      { entityKey: "hybridMode", kind: "toggle",
        name: { en: "Enable Hybrid Mode", it: "Abilita Hybrid Mode", nl: "Hybride-modus inschakelen" },
        desc: {
          en: "Empirical 6 A probing to discover hidden PV capacity in zero-export hybrid systems. Opt-in.",
          it: "Probing empirico a 6 A per scoprire capacita PV nascosta in sistemi hybrid zero-export. Opt-in.",
          nl: "Empirisch probing op 6 A om verborgen PV-capaciteit te ontdekken in zero-export hybride systemen. Opt-in.",
        },
        hint: { en: "Default off", it: "Default off", nl: "Standaard uit" } },
      { entityKey: "hybridBatteryFullThreshold", kind: "stepper",
        name: { en: "Battery Full Threshold", it: "Soglia batteria piena", nl: "Drempel batterij vol" },
        desc: {
          en: "Home battery SOC above which the system considers the inverter in curtailment and attempts probing.",
          it: "SOC batteria di casa sopra il quale il sistema considera l'inverter in curtailment e tenta il probing.",
          nl: "SOC van de thuisbatterij waarboven het systeem aanneemt dat de omvormer terugregelt en probing start.",
        },
        hint: { en: "Default 95 % · Range 80–100", it: "Default 95 % · Range 80–100", nl: "Standaard 95 % · Bereik 80–100" } },
      { entityKey: "hybridProbeDuration", kind: "stepper",
        name: { en: "Probe Duration", it: "Durata probing", nl: "Probing-duur" },
        desc: {
          en: "Total probing window length at 6 A. Below this threshold the probe is too short to be significant.",
          it: "Durata totale della finestra di test a 6 A. Sotto questa soglia il probing e troppo breve per essere significativo.",
          nl: "Totale duur van het probing-venster op 6 A. Korter dan dit is het probing-resultaat niet betekenisvol.",
        },
        hint: { en: "Default 60 s · Range 30–180", it: "Default 60 s · Range 30–180", nl: "Standaard 60 s · Bereik 30–180" } },
      { entityKey: "hybridMaxImportDuration", kind: "stepper",
        name: { en: "Max Import Duration", it: "Durata max import", nl: "Max. importduur" },
        desc: {
          en: "Maximum grid-import time tolerated during probing before aborting and entering cooldown.",
          it: "Tempo massimo di import dalla rete tollerato durante probing prima di abortire e tornare in cooldown.",
          nl: "Maximale netinvoertijd tijdens probing voordat wordt afgebroken en in cooldown wordt gegaan.",
        },
        hint: { en: "Default 60 s · Range 30–120", it: "Default 60 s · Range 30–120", nl: "Standaard 60 s · Bereik 30–120" } },
      { entityKey: "hybridMaxFailedProbes", kind: "stepper",
        name: { en: "Max Failed Probes", it: "Probing falliti max", nl: "Max. mislukte probings" },
        desc: {
          en: "Maximum failed probes in a 30-minute window before entering long cooldown (15 min).",
          it: "Numero massimo di probe falliti in una finestra di 30 minuti prima di entrare in cooldown lungo (15 min).",
          nl: "Maximaal aantal mislukte probings binnen 30 minuten voordat een lange cooldown (15 min) ingaat.",
        },
        hint: { en: "Default 5 · Range 1–10", it: "Default 5 · Range 1–10", nl: "Standaard 5 · Bereik 1–10" } },
    ],
  },
  {
    id: "boost", iconClass: "boost", icon: "⏱",
    name: { en: "Boost Schedule", it: "Programmazione Boost", nl: "Boost-planning" },
    desc: {
      en: "Automatic Boost activation in a daily time window",
      it: "Attivazione automatica del Boost in una finestra oraria giornaliera",
      nl: "Automatische activering van Boost in een dagelijks tijdvenster",
    },
    items: [
      { entityKey: "boostScheduleEnabled", kind: "toggle",
        name: { en: "Schedule Enabled", it: "Programmazione attiva", nl: "Planning ingeschakeld" },
        desc: {
          en: "Activate Boost automatically at the start time and stop it at the end time every day.",
          it: "Attiva il Boost automaticamente all'orario di inizio e lo ferma a quello di fine, ogni giorno.",
          nl: "Activeer Boost automatisch op starttijd en stop op eindtijd, elke dag.",
        },
        hint: { en: "Default off", it: "Default off", nl: "Standaard uit" } },
      { entityKey: "boostScheduleStartTime", kind: "time",
        name: { en: "Schedule Start", it: "Inizio programmato", nl: "Geplande start" },
        desc: {
          en: "Time at which automatic Boost begins.",
          it: "Ora di inizio del Boost automatico.",
          nl: "Tijdstip waarop automatische Boost begint.",
        },
        hint: { en: "—", it: "—", nl: "—" } },
      { entityKey: "boostScheduleEndTime", kind: "time",
        name: { en: "Schedule End", it: "Fine programmata", nl: "Geplande einde" },
        desc: {
          en: "Time at which automatic Boost stops.",
          it: "Ora di fine del Boost automatico.",
          nl: "Tijdstip waarop automatische Boost stopt.",
        },
        hint: { en: "—", it: "—", nl: "—" } },
    ],
  },
  {
    id: "notif", iconClass: "bell", icon: "🔔",
    name: { en: "Notifications", it: "Notifiche", nl: "Notificaties" },
    desc: {
      en: "Mobile alerts with presence-based filtering",
      it: "Avvisi mobile con filtro per presenza del proprietario",
      nl: "Mobiele meldingen met aanwezigheidsfilter",
    },
    items: [
      { entityKey: "notifySmartBlocker", kind: "toggle",
        name: { en: "Smart Blocker Alerts", it: "Avvisi Smart Blocker", nl: "Smart Blocker-meldingen" },
        desc: {
          en: "Send push when Smart Blocker prevents an unexpected charging session.",
          it: "Invia push quando Smart Blocker blocca una sessione di ricarica inattesa.",
          nl: "Stuur push wanneer Smart Blocker een onverwachte laadsessie blokkeert.",
        },
        hint: { en: "Filtered by owner presence", it: "Filtrate per presenza del proprietario", nl: "Gefilterd op aanwezigheid eigenaar" } },
      { entityKey: "notifyPriorityBalancer", kind: "toggle",
        name: { en: "Priority Balancer Alerts", it: "Avvisi Priority Balancer", nl: "Priority Balancer-meldingen" },
        desc: {
          en: "Notify when the priority engine switches between EV / Home / EV-Free.",
          it: "Notifica quando il motore priorita passa tra EV / Home / EV-Free.",
          nl: "Melden wanneer de prioriteit-engine wisselt tussen EV / Home / EV-Free.",
        },
        hint: { en: "Filtered by owner presence", it: "Filtrate per presenza del proprietario", nl: "Gefilterd op aanwezigheid eigenaar" } },
      { entityKey: "notifyNightCharge", kind: "toggle",
        name: { en: "Night Charge Alerts", it: "Avvisi Night Charge", nl: "Night Charge-meldingen" },
        desc: {
          en: "Notify when Night Smart Charge starts a session (BATTERY or GRID).",
          it: "Notifica quando Night Smart Charge avvia una sessione (BATTERY o GRID).",
          nl: "Melden wanneer Night Smart Charge een sessie start (BATTERY of GRID).",
        },
        hint: { en: "Filtered by owner presence", it: "Filtrate per presenza del proprietario", nl: "Gefilterd op aanwezigheid eigenaar" } },
    ],
  },
  {
    id: "log", iconClass: "log", icon: "📊",
    name: { en: "Logging & Diagnostics", it: "Logging e diagnostica", nl: "Logging & diagnose" },
    desc: {
      en: "Date-organized log files for troubleshooting",
      it: "File di log organizzati per data per il troubleshooting",
      nl: "Op datum geordende logbestanden voor probleemoplossing",
    },
    items: [
      { entityKey: "traceLogging", kind: "toggle",
        name: { en: "Trace Logging", it: "Trace logging", nl: "Trace-logging" },
        desc: {
          en: "Verbose diagnostic logging for in-depth debugging.",
          it: "Logging diagnostico verboso per debug approfondito.",
          nl: "Uitgebreide diagnostische logging voor diepgaande foutopsporing.",
        },
        hint: { en: "Default off", it: "Default off", nl: "Standaard uit" } },
      { entityKey: "enableFileLogging", kind: "toggle",
        name: { en: "Enable File Logging", it: "Abilita file di log", nl: "Bestand-logging inschakelen" },
        desc: {
          en: "Write a dedicated log file under /config/.../logs/<year>/<month>/<day>.log. Useful for sharing with the community.",
          it: "Scrive un file di log dedicato in /config/.../logs/<anno>/<mese>/<giorno>.log. Utile per condividere i log con la community.",
          nl: "Schrijft een toegewijd logbestand in /config/.../logs/<jaar>/<maand>/<dag>.log. Handig om logs met de community te delen.",
        },
        hint: { en: "Default off", it: "Default off", nl: "Standaard uit" } },
      { entityKey: "logFilePath", kind: "info",
        name: { en: "Log File Path", it: "Percorso file di log", nl: "Pad logbestand" },
        desc: {
          en: "Current path of today's log file (read-only, exposed as sensor).",
          it: "Percorso corrente del file di log di oggi (sola lettura, esposto come sensore).",
          nl: "Huidig pad van het logbestand van vandaag (alleen-lezen, blootgesteld als sensor).",
        },
        hint: { en: "—", it: "—", nl: "—" } },
    ],
  },
];

const STATIC_LABELS = {
  en: {
    nav_dashboard: "Dashboard", nav_settings: "Settings",
    settings_title: "Settings", settings_intro: "Automation module configuration. Click a category to expand its parameters.",
    weekly_title: "Weekly Planner", weekly_desc: "Daily SOC targets · Car ready toggle per day",
    weekly_ev: "EV target", weekly_home: "Home target", weekly_car: "Car ready",
    weekly_today_badge: "Today",
    weekly_info: "When active, Night Smart Charge falls back to grid if the home battery is insufficient. When inactive, charging is skipped pending solar surplus.",
    night_start: "Start", night_car_ready: "Car Ready", night_enabled: "Enabled", night_card_title: "Night Smart Charge", night_card_sub: "Forecast driven",
    hero_ev: "EV", hero_charging: "CHARGING",
    profile_label: "Charging Profile", profile_hint: "Strategy mode selection",
    override_title: "Override & Boost", override_hint: "Manual intervention — bypass automations",
  },
  it: {
    nav_dashboard: "Dashboard", nav_settings: "Impostazioni",
    settings_title: "Impostazioni", settings_intro: "Configurazione dei moduli di automazione. Clicca su una categoria per espandere i parametri.",
    weekly_title: "Pianificatore settimanale", weekly_desc: "Target SOC giornalieri · Toggle Car Ready per giorno",
    weekly_ev: "Target EV", weekly_home: "Target casa", weekly_car: "Car ready",
    weekly_today_badge: "Oggi",
    weekly_info: "Quando attivo, Night Smart Charge fa fallback su rete se la batteria di casa non basta. Quando inattivo la ricarica viene saltata in attesa del surplus solare.",
    night_start: "Inizio", night_car_ready: "Auto pronta", night_enabled: "Attivo", night_card_title: "Night Smart Charge", night_card_sub: "Guidato dal forecast",
    hero_ev: "EV", hero_charging: "IN CARICA",
    profile_label: "Profilo di ricarica", profile_hint: "Selezione strategia",
    override_title: "Override e Boost", override_hint: "Intervento manuale — bypass automazioni",
  },
  nl: {
    nav_dashboard: "Dashboard", nav_settings: "Instellingen",
    settings_title: "Instellingen", settings_intro: "Configuratie van de automatiseringsmodules. Klik op een categorie om de parameters uit te vouwen.",
    weekly_title: "Weekplanner", weekly_desc: "Dagelijkse SOC-doelen · Car Ready-schakelaar per dag",
    weekly_ev: "EV-doel", weekly_home: "Thuisdoel", weekly_car: "Auto klaar",
    weekly_today_badge: "Vandaag",
    weekly_info: "Indien actief schakelt Night Smart Charge naar het net als de thuisbatterij onvoldoende is. Indien inactief wordt het laden overgeslagen in afwachting van zonneoverschot.",
    night_start: "Start", night_car_ready: "Auto klaar", night_enabled: "Actief", night_card_title: "Slim nachtelijk laden", night_card_sub: "Op verwachting gestuurd",
    hero_ev: "EV", hero_charging: "LADEN",
    profile_label: "Laadprofiel", profile_hint: "Strategiekeuze",
    override_title: "Override & Boost", override_hint: "Handmatige interventie — automatiseringen overslaan",
  },
};

const DEFAULT_LOCALE = "en";
const FRONTEND_LOCALES = {
  "en": {
    "title.default": "EV Smart Charger",
    "common.unavailable": "Unavailable",
    "common.no_options": "No options",
    "boot.waiting_for_hass": "Waiting for Home Assistant state...",
    "hero.eyebrow": "Custom Integration Control Surface",
    "hero.description":
      "Single-column EV charging control with native Home Assistant service calls, stacked modules, and live operational telemetry.",
    "metric.charging_power": "Charging Power",
    "metric.live_power": "Live power",
    "metric.ev_soc": "EV",
    "metric.vehicle_battery": "Vehicle battery",
    "metric.home_battery": "Home Battery",
    "charging_state.fully_charged": "Fully Charged",
    "charging_state.not_charging": "Not Charging",
    "charging_state.waiting": "Waiting",
    "metric.storage_reserve": "Storage reserve",
    "metric.grid_import": "Grid Import",
    "metric.import_threshold": "Import threshold",
    "metric.solar_power": "Solar Power",
    "metric.pv_feed": "PV feed",
    "metric.charge_current": "Charge Current",
    "metric.wallbox_current": "Wallbox current",
    "fallback.live_feed_optional": "Live feed optional",
    "fallback.ev_soc_entity": "Add `ev_soc_entity`",
    "fallback.home_battery_soc_entity": "Add `home_battery_soc_entity`",
    "fallback.solar_power_entity": "Add `solar_power_entity`",
    "fallback.grid_import_entity": "Add `grid_import_entity`",
    "fallback.current_entity": "Add `current_entity`",
    "spotlight.priority_engine": "Priority Engine",
    "spotlight.description": "Dynamic target arbitration between EV demand and home energy reserve.",
    "spotlight.today_ev_target": "Today EV Target",
    "spotlight.today_home_target": "Today Home Target",
    "module.override_layer": "Override Layer",
    "module.main_controls": "Main Controls",
    "control.force_charge": "Force Charge",
    "control.override_all": "Override All",
    "control.charging_profile": "Charging Profile",
    "control.mode_strategy": "Mode Strategy",
    "module.fast_override": "Fast Override",
    "module.boost_charge": "Boost Charge",
    "control.boost_session": "Boost Session",
    "control.high_priority": "High Priority",
    "control.boost_amperage": "Boost Amperage",
    "control.output": "Output",
    "control.boost_target_soc": "Boost Target SOC",
    "control.auto_stop": "Auto Stop",
    "module.forecast_driven": "Forecast Driven",
    "module.night_smart_charge": "Night Smart Charge",
    "control.enable_night_smart_charge": "Enable Night Smart Charge",
    "control.night_window": "Night Window",
    "control.preserve_home_battery": "Preserve Home Battery",
    "control.skip_when_not_required": "Skip overnight charging when the car is not required by morning",
    "control.start_time": "Start Time",
    "control.schedule": "Schedule",
    "control.min_solar_forecast": "Min Solar Forecast",
    "control.tomorrow_threshold": "Tomorrow Threshold",
    "control.night_charge_amperage": "Night Charge Amperage",
    "control.overnight_current": "Overnight Current",
    "module.adaptive_curve": "Adaptive Curve",
    "module.solar_surplus": "Solar Surplus",
    "control.check_interval": "Check Interval",
    "control.polling": "Polling",
    "control.grid_import_threshold": "Grid Import Threshold",
    "control.clamp": "Clamp",
    "control.grid_import_delay": "Grid Import Delay",
    "control.debounce": "Debounce",
    "control.surplus_drop_delay": "Surplus Drop Delay",
    "control.cloud_filter": "Cloud Filter",
    "control.use_home_battery": "Use Home Battery",
    "control.fallback_reserve": "Fallback Reserve",
    "control.home_battery_min_soc": "Home Battery Min SOC",
    "control.reserve_floor": "Reserve Floor",
    "control.battery_support_amperage": "Battery Support Amperage",
    "control.assist_output": "Assist Output",
    "module.safety_nets": "Safety Nets",
    "module.protection_layer": "Protection Layer",
    "control.priority_balancer": "Priority Balancer",
    "control.target_arbitration": "Target Arbitration",
    "control.smart_charger_blocker": "Smart Charger Blocker",
    "control.nighttime_lockout": "Nighttime Lockout",
    "control.trace_logging": "Trace Logging",
    "control.deep_diagnostics": "Deep Diagnostics",
    "control.solar_max_amperage": "Solar Max Amperage",
    "control.wallbox_ceiling": "Wallbox Ceiling",
    "control.battery_support_sunset_buffer": "Sunset Buffer",
    "control.protect_evening_battery": "Protect evening battery",
    "module.boost_schedule": "Boost Schedule",
    "module.daily_window": "Daily Window",
    "control.schedule_boost": "Schedule Boost",
    "control.daily_schedule": "Daily schedule",
    "control.schedule_start": "Schedule Start",
    "control.schedule_end": "Schedule End",
    "module.car_ready": "Car Ready",
    "module.weekly_planner": "Weekly Planner",
    "control.car_ready_time": "Car Ready Time",
    "control.morning_deadline": "Morning deadline",
    "control.car_ready_grid_hint": "Tap a day to toggle whether the car must be ready by deadline",
    "module.daily_targets": "Daily SOC Targets",
    "module.target_planner": "Target Planner",
    "control.ev_targets_label": "EV daily target",
    "control.home_targets_label": "Home battery daily target",
    "module.hybrid_inverter": "Hybrid Inverter Mode",
    "module.curtailment_discovery": "Curtailment Discovery (issue #20)",
    "control.hybrid_enabled": "Enable Hybrid Mode",
    "control.opt_in_probing": "Opt-in PV probing",
    "control.hybrid_battery_full_threshold": "Battery Full Threshold",
    "control.curtailment_trigger": "Curtailment trigger",
    "control.hybrid_probe_duration": "Probe Duration",
    "control.test_window": "Test window",
    "control.hybrid_max_import_duration": "Max Import Duration",
    "control.backoff_window": "Backoff window",
    "control.hybrid_max_failed_probes": "Max Failed Probes",
    "control.sliding_window": "Sliding window (30 min)",
    "module.notifications": "Notifications",
    "module.mobile_alerts": "Mobile Alerts",
    "control.notify_smart_blocker": "Notify Smart Blocker",
    "control.notify_priority_balancer": "Notify Priority Balancer",
    "control.notify_night_charge": "Notify Night Charge",
    "control.alert_channel": "Alert channel",
    "module.logging": "Logging",
    "module.observability": "Observability",
    "control.enable_file_logging": "Enable File Logging",
    "control.daily_log_files": "Daily log files",
    "log.file_path_label": "Today's log file",
    "diagnostic.automation": "Automation Diagnostic",
    "diagnostic.solar_surplus": "Solar Surplus Diagnostic",
    "diagnostic.hybrid_inverter": "Hybrid Inverter Diagnostic",
    "diagnostic.cached_ev_soc": "Cached EV SOC",
    "diagnostic.cached_ev_soc_hint": "Last valid value preserved when source becomes unavailable",
    "diagnostic.active_owner": "Active Owner",
    "diagnostic.last_reason": "Last Reason",
    "diagnostic.external_cause": "External Cause",
    "diagnostic.last_denial": "Last Denial",
    "diagnostic.trace_mode": "Trace Mode",
    "diagnostic.hybrid_state": "State",
    "diagnostic.hybrid_failed_probes": "Failed Probes (30 min)",
    "diagnostic.hybrid_long_cooldowns": "Long Cooldowns Today",
    "profile.manual": "Manual",
    "profile.solar_surplus": "Solar Surplus"
  },
  "it": {
    "title.default": "EV Smart Charger",
    "common.unavailable": "Non disponibile",
    "common.no_options": "Nessuna opzione",
    "boot.waiting_for_hass": "In attesa dello stato di Home Assistant...",
    "hero.eyebrow": "Pannello di controllo integrazione custom",
    "hero.description":
      "Controllo ricarica EV a colonna singola con chiamate servizio native di Home Assistant, moduli sovrapposti e telemetria operativa live.",
    "metric.charging_power": "Potenza di ricarica",
    "metric.live_power": "Potenza live",
    "metric.ev_soc": "EV",
    "charging_state.fully_charged": "Completamente carica",
    "charging_state.not_charging": "Non in carica",
    "charging_state.waiting": "In attesa",
    "metric.vehicle_battery": "Batteria veicolo",
    "metric.home_battery": "Batteria domestica",
    "metric.storage_reserve": "Riserva accumulo",
    "metric.grid_import": "Prelievo rete",
    "metric.import_threshold": "Soglia prelievo",
    "metric.solar_power": "Potenza solare",
    "metric.pv_feed": "Produzione FV",
    "metric.charge_current": "Corrente di ricarica",
    "metric.wallbox_current": "Corrente wallbox",
    "fallback.live_feed_optional": "Feed live opzionale",
    "fallback.ev_soc_entity": "Aggiungi `ev_soc_entity`",
    "fallback.home_battery_soc_entity": "Aggiungi `home_battery_soc_entity`",
    "fallback.solar_power_entity": "Aggiungi `solar_power_entity`",
    "fallback.grid_import_entity": "Aggiungi `grid_import_entity`",
    "fallback.current_entity": "Aggiungi `current_entity`",
    "spotlight.priority_engine": "Motore priorita",
    "spotlight.description": "Arbitraggio dinamico dei target tra domanda EV e riserva energetica domestica.",
    "spotlight.today_ev_target": "Target EV di oggi",
    "spotlight.today_home_target": "Target casa di oggi",
    "module.override_layer": "Livello override",
    "module.main_controls": "Controlli principali",
    "control.force_charge": "Forza ricarica",
    "control.override_all": "Override totale",
    "control.charging_profile": "Profilo di ricarica",
    "control.mode_strategy": "Strategia modalita",
    "module.fast_override": "Override rapido",
    "module.boost_charge": "Boost Charge",
    "control.boost_session": "Sessione boost",
    "control.high_priority": "Alta priorita",
    "control.boost_amperage": "Amperaggio boost",
    "control.output": "Output",
    "control.boost_target_soc": "Target SOC boost",
    "control.auto_stop": "Arresto automatico",
    "module.forecast_driven": "Guidato dalla previsione",
    "module.night_smart_charge": "Night Smart Charge",
    "control.enable_night_smart_charge": "Abilita Night Smart Charge",
    "control.night_window": "Finestra notturna",
    "control.preserve_home_battery": "Preserva batteria di casa",
    "control.skip_when_not_required": "Salta la ricarica notturna quando l'auto non deve essere pronta al mattino",
    "control.start_time": "Ora di avvio",
    "control.schedule": "Programmazione",
    "control.min_solar_forecast": "Previsione solare minima",
    "control.tomorrow_threshold": "Soglia domani",
    "control.night_charge_amperage": "Amperaggio notturno",
    "control.overnight_current": "Corrente notturna",
    "module.adaptive_curve": "Curva adattiva",
    "module.solar_surplus": "Surplus solare",
    "control.check_interval": "Intervallo di controllo",
    "control.polling": "Polling",
    "control.grid_import_threshold": "Soglia prelievo rete",
    "control.clamp": "Limite",
    "control.grid_import_delay": "Ritardo prelievo rete",
    "control.debounce": "Debounce",
    "control.surplus_drop_delay": "Ritardo calo surplus",
    "control.cloud_filter": "Filtro nuvole",
    "control.use_home_battery": "Usa batteria domestica",
    "control.fallback_reserve": "Riserva di fallback",
    "control.home_battery_min_soc": "SOC minimo batteria domestica",
    "control.reserve_floor": "Soglia riserva",
    "control.battery_support_amperage": "Amperaggio supporto batteria",
    "control.assist_output": "Output supporto",
    "module.safety_nets": "Reti di sicurezza",
    "module.protection_layer": "Livello protezione",
    "control.priority_balancer": "Priority Balancer",
    "control.target_arbitration": "Arbitraggio target",
    "control.smart_charger_blocker": "Smart Charger Blocker",
    "control.nighttime_lockout": "Blocco notturno",
    "control.trace_logging": "Trace logging",
    "control.deep_diagnostics": "Diagnostica profonda",
    "control.solar_max_amperage": "Amperaggio max solare",
    "control.wallbox_ceiling": "Limite wallbox",
    "control.battery_support_sunset_buffer": "Buffer tramonto",
    "control.protect_evening_battery": "Protezione batteria serale",
    "module.boost_schedule": "Boost programmato",
    "module.daily_window": "Finestra giornaliera",
    "control.schedule_boost": "Programma boost",
    "control.daily_schedule": "Programmazione giornaliera",
    "control.schedule_start": "Inizio programmazione",
    "control.schedule_end": "Fine programmazione",
    "module.car_ready": "Auto pronta",
    "module.weekly_planner": "Pianificatore settimanale",
    "control.car_ready_time": "Ora auto pronta",
    "control.morning_deadline": "Scadenza mattino",
    "control.car_ready_grid_hint": "Tocca un giorno per attivare/disattivare se l'auto deve essere pronta entro la scadenza",
    "module.daily_targets": "Target SOC giornalieri",
    "module.target_planner": "Pianificatore target",
    "control.ev_targets_label": "Target EV giornaliero",
    "control.home_targets_label": "Target batteria di casa giornaliero",
    "module.hybrid_inverter": "Hybrid Inverter Mode",
    "module.curtailment_discovery": "Scoperta curtailment (issue #20)",
    "control.hybrid_enabled": "Abilita Hybrid Mode",
    "control.opt_in_probing": "Probing PV opt-in",
    "control.hybrid_battery_full_threshold": "Soglia batteria piena",
    "control.curtailment_trigger": "Trigger curtailment",
    "control.hybrid_probe_duration": "Durata probe",
    "control.test_window": "Finestra di test",
    "control.hybrid_max_import_duration": "Durata max import",
    "control.backoff_window": "Finestra di backoff",
    "control.hybrid_max_failed_probes": "Probe falliti max",
    "control.sliding_window": "Finestra mobile (30 min)",
    "module.notifications": "Notifiche",
    "module.mobile_alerts": "Avvisi mobile",
    "control.notify_smart_blocker": "Notifica Smart Blocker",
    "control.notify_priority_balancer": "Notifica Priority Balancer",
    "control.notify_night_charge": "Notifica Night Charge",
    "control.alert_channel": "Canale avvisi",
    "module.logging": "Logging",
    "module.observability": "Osservabilita",
    "control.enable_file_logging": "Abilita logging su file",
    "control.daily_log_files": "Log giornalieri",
    "log.file_path_label": "File di log di oggi",
    "diagnostic.automation": "Diagnostica automazione",
    "diagnostic.solar_surplus": "Diagnostica surplus solare",
    "diagnostic.hybrid_inverter": "Diagnostica Hybrid Inverter",
    "diagnostic.cached_ev_soc": "SOC EV cached",
    "diagnostic.cached_ev_soc_hint": "Ultimo valore valido mantenuto quando la sorgente non e' disponibile",
    "diagnostic.active_owner": "Owner attivo",
    "diagnostic.last_reason": "Ultimo motivo",
    "diagnostic.external_cause": "Causa esterna",
    "diagnostic.last_denial": "Ultimo denial",
    "diagnostic.trace_mode": "Modalita trace",
    "diagnostic.hybrid_state": "Stato",
    "diagnostic.hybrid_failed_probes": "Probe falliti (30 min)",
    "diagnostic.hybrid_long_cooldowns": "Cooldown lunghi oggi",
    "profile.manual": "Manuale",
    "profile.solar_surplus": "Surplus solare"
  },
  "nl": {
    "title.default": "EV Smart Charger",
    "common.unavailable": "Niet beschikbaar",
    "common.no_options": "Geen opties",
    "boot.waiting_for_hass": "Wachten op Home Assistant-status...",
    "hero.eyebrow": "Bedieningspaneel voor custom integratie",
    "hero.description":
      "Enkelkoloms EV-laadbediening met native Home Assistant-serviceaanroepen, gestapelde modules en live operationele telemetrie.",
    "metric.charging_power": "Laadvermogen",
    "metric.live_power": "Live vermogen",
    "metric.ev_soc": "EV",
    "charging_state.fully_charged": "Volledig opgeladen",
    "charging_state.not_charging": "Niet aan het laden",
    "charging_state.waiting": "Wachten",
    "metric.vehicle_battery": "Voertuigbatterij",
    "metric.home_battery": "Thuisbatterij",
    "metric.storage_reserve": "Opslagreserve",
    "metric.grid_import": "Netafname",
    "metric.import_threshold": "Afnamedrempel",
    "metric.solar_power": "Zonnevermogen",
    "metric.pv_feed": "PV-opwek",
    "metric.charge_current": "Laadstroom",
    "metric.wallbox_current": "Wallbox-stroom",
    "fallback.live_feed_optional": "Live feed optioneel",
    "fallback.ev_soc_entity": "Voeg `ev_soc_entity` toe",
    "fallback.home_battery_soc_entity": "Voeg `home_battery_soc_entity` toe",
    "fallback.solar_power_entity": "Voeg `solar_power_entity` toe",
    "fallback.grid_import_entity": "Voeg `grid_import_entity` toe",
    "fallback.current_entity": "Voeg `current_entity` toe",
    "spotlight.priority_engine": "Prioriteitsmotor",
    "spotlight.description": "Dynamische doelarbitrage tussen EV-vraag en energiereserve van de woning.",
    "spotlight.today_ev_target": "EV-doel vandaag",
    "spotlight.today_home_target": "Woningdoel vandaag",
    "module.override_layer": "Override-laag",
    "module.main_controls": "Hoofdregeling",
    "control.force_charge": "Laad forceren",
    "control.override_all": "Alles overrulen",
    "control.charging_profile": "Laadprofiel",
    "control.mode_strategy": "Modusstrategie",
    "module.fast_override": "Snelle override",
    "module.boost_charge": "Boost Charge",
    "control.boost_session": "Boostsessie",
    "control.high_priority": "Hoge prioriteit",
    "control.boost_amperage": "Boostlaadstroom",
    "control.output": "Output",
    "control.boost_target_soc": "Boostdoel-SOC",
    "control.auto_stop": "Automatisch stoppen",
    "module.forecast_driven": "Op verwachting gestuurd",
    "module.night_smart_charge": "Slim nachtelijk laden",
    "control.enable_night_smart_charge": "Slim nachtelijk laden inschakelen",
    "control.night_window": "Nachtvenster",
    "control.preserve_home_battery": "Thuisbatterij sparen",
    "control.skip_when_not_required": "Sla 's nachts laden over wanneer de auto 's ochtends niet klaar hoeft te zijn",
    "control.start_time": "Starttijd",
    "control.schedule": "Planning",
    "control.min_solar_forecast": "Minimale zonneverwachting",
    "control.tomorrow_threshold": "Drempel voor morgen",
    "control.night_charge_amperage": "Nachtlaadstroom",
    "control.overnight_current": "Nachtstroom",
    "module.adaptive_curve": "Adaptieve curve",
    "module.solar_surplus": "Zonne-overschot",
    "control.check_interval": "Controle-interval",
    "control.polling": "Polling",
    "control.grid_import_threshold": "Netafnamedrempel",
    "control.clamp": "Begrenzen",
    "control.grid_import_delay": "Vertraging netafname",
    "control.debounce": "Debounce",
    "control.surplus_drop_delay": "Vertraging surplusdaling",
    "control.cloud_filter": "Wolkfilter",
    "control.use_home_battery": "Thuisbatterij gebruiken",
    "control.fallback_reserve": "Fallbackreserve",
    "control.home_battery_min_soc": "Min. SOC thuisbatterij",
    "control.reserve_floor": "Reservevloer",
    "control.battery_support_amperage": "Ondersteuningsstroom batterij",
    "control.assist_output": "Ondersteuningsoutput",
    "module.safety_nets": "Veiligheidslagen",
    "module.protection_layer": "Beschermingslaag",
    "control.priority_balancer": "Prioriteitsbalans",
    "control.target_arbitration": "Doelarbitrage",
    "control.smart_charger_blocker": "Slimme laadblokkering",
    "control.nighttime_lockout": "Nachtblokkering",
    "control.trace_logging": "Trace-logging",
    "control.deep_diagnostics": "Diepe diagnostiek",
    "control.solar_max_amperage": "Max zonne-stroom",
    "control.wallbox_ceiling": "Wallbox-plafond",
    "control.battery_support_sunset_buffer": "Zonsondergangbuffer",
    "control.protect_evening_battery": "Beschermt avondbatterij",
    "module.boost_schedule": "Boost-planning",
    "module.daily_window": "Dagvenster",
    "control.schedule_boost": "Boost plannen",
    "control.daily_schedule": "Dagelijkse planning",
    "control.schedule_start": "Begintijd",
    "control.schedule_end": "Eindtijd",
    "module.car_ready": "Auto Klaar",
    "module.weekly_planner": "Weekplanner",
    "control.car_ready_time": "Auto klaar om",
    "control.morning_deadline": "Ochtenddeadline",
    "control.car_ready_grid_hint": "Tik op een dag om in te stellen of de auto klaar moet zijn voor de deadline",
    "module.daily_targets": "Dagelijkse SOC-doelen",
    "module.target_planner": "Doelplanner",
    "control.ev_targets_label": "EV-doel per dag",
    "control.home_targets_label": "Thuisbatterijdoel per dag",
    "module.hybrid_inverter": "Hybride omvormermodus",
    "module.curtailment_discovery": "Curtailment-detectie (issue #20)",
    "control.hybrid_enabled": "Hybride modus inschakelen",
    "control.opt_in_probing": "Opt-in PV-probing",
    "control.hybrid_battery_full_threshold": "Drempel volle batterij",
    "control.curtailment_trigger": "Curtailment-trigger",
    "control.hybrid_probe_duration": "Probeduur",
    "control.test_window": "Testvenster",
    "control.hybrid_max_import_duration": "Max importduur",
    "control.backoff_window": "Backoff-venster",
    "control.hybrid_max_failed_probes": "Max mislukte probes",
    "control.sliding_window": "Schuifvenster (30 min)",
    "module.notifications": "Meldingen",
    "module.mobile_alerts": "Mobiele meldingen",
    "control.notify_smart_blocker": "Melding Smart Blocker",
    "control.notify_priority_balancer": "Melding Priority Balancer",
    "control.notify_night_charge": "Melding Night Charge",
    "control.alert_channel": "Meldingskanaal",
    "module.logging": "Logging",
    "module.observability": "Waarneembaarheid",
    "control.enable_file_logging": "Logbestand inschakelen",
    "control.daily_log_files": "Dagelijkse logbestanden",
    "log.file_path_label": "Logbestand van vandaag",
    "diagnostic.automation": "Automatiseringsdiagnose",
    "diagnostic.solar_surplus": "Diagnose zonne-overschot",
    "diagnostic.hybrid_inverter": "Diagnose hybride omvormer",
    "diagnostic.cached_ev_soc": "Cached EV SOC",
    "diagnostic.cached_ev_soc_hint": "Laatste geldige waarde bewaard wanneer de bron onbeschikbaar is",
    "diagnostic.active_owner": "Actieve eigenaar",
    "diagnostic.last_reason": "Laatste reden",
    "diagnostic.external_cause": "Externe oorzaak",
    "diagnostic.last_denial": "Laatste weigering",
    "diagnostic.trace_mode": "Trace-modus",
    "diagnostic.hybrid_state": "Status",
    "diagnostic.hybrid_failed_probes": "Mislukte probes (30 min)",
    "diagnostic.hybrid_long_cooldowns": "Lange cooldowns vandaag",
    "profile.manual": "Handmatig",
    "profile.solar_surplus": "Zonne-overschot"
  }
};

class EvSmartChargerDashboard extends HTMLElement {
  static getStubConfig() {
    return {
      entity_prefix: "ev_smart_charger_<entry_id>",
      title: DEFAULT_TITLE,
    };
  }

  setConfig(config) {
    // v1.9.1: soft accept. We auto-discover the real entity_prefix from
    // hass.states using the `evsc_forza_ricarica` sentinel, so the user no
    // longer has to know (or correctly spell) the prefix in advance.
    this._config = {
      title: config?.title,
      entity_prefix: config?.entity_prefix || "",
      charging_power_entity: config?.charging_power_entity,
      ev_soc_entity: config?.ev_soc_entity,
      home_battery_soc_entity: config?.home_battery_soc_entity,
      solar_power_entity: config?.solar_power_entity,
      grid_import_entity: config?.grid_import_entity,
      current_entity: config?.current_entity,
      charger_status_entity: config?.charger_status_entity,
    };

    // Reset discovery and render caches — the configured prefix may have changed.
    this._resolvedPrefix = null;
    this._discoveryDone = false;
    this._lastRenderHash = "";

    // v1.10.0: view state (Dashboard / Settings) and accordion open set.
    // Preserved across re-renders so HA state ticks do not reset the UI.
    if (!this._view) this._view = "dashboard";
    if (!this._openAccordions) this._openAccordions = new Set(["solar"]);

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    // Run entity-prefix discovery exactly once (or whenever setConfig has
    // reset the flag). The scan is cheap (Object.keys + regex) and runs only
    // until we resolve a valid prefix.
    if (!this._discoveryDone) {
      this._discoverEntityPrefix();
      this._discoveryDone = true;
    }
    if (this.shadowRoot) {
      this.render();
    }
  }

  /**
   * Discover the real entity prefix from hass.states using the
   * `evsc_forza_ricarica` switch as a sentinel (it is created by every
   * EV Smart Charger entry). Case is preserved exactly as found in HA — do
   * NOT lowercase, since installs predating v1.6.23 keep uppercase ULID IDs
   * in their state machine and forcing lowercase would break them.
   */
  _discoverEntityPrefix() {
    const states = this._hass?.states;
    if (!states) return;

    // Fast path: configured prefix already resolves a real entity.
    const configured = this._config?.entity_prefix;
    if (configured && states[`switch.${configured}_evsc_forza_ricarica`]) {
      this._resolvedPrefix = configured;
      return;
    }

    // Scan the state machine.
    const sentinelRe = /^switch\.(.+)_evsc_forza_ricarica$/;
    const matches = [];
    for (const entityId of Object.keys(states)) {
      const m = sentinelRe.exec(entityId);
      if (m) matches.push(m[1]);
    }

    if (matches.length === 0) {
      this._resolvedPrefix = null;
      return;
    }
    if (matches.length === 1) {
      this._resolvedPrefix = matches[0];
      return;
    }

    // Multi-entry install: prefer case-insensitive match against config,
    // otherwise pick the first deterministically and warn.
    if (configured) {
      const lc = configured.toLowerCase();
      const preferred = matches.find((p) => p.toLowerCase() === lc);
      if (preferred) {
        this._resolvedPrefix = preferred;
        return;
      }
    }
    this._resolvedPrefix = matches[0];
    // eslint-disable-next-line no-console
    console.warn(
      "[ev-smart-charger-dashboard] Multiple EV Smart Charger entries detected; " +
        "using prefix:",
      matches[0],
      "Other candidates:",
      matches.slice(1)
    );
  }

  getCardSize() {
    return 12;
  }

  _entityId(key) {
    const [domain, suffix] = DOMAIN_SUFFIXES[key];
    // v1.9.1: use the resolved (real) prefix when available; fall back to
    // whatever the user passed in config. An empty prefix produces
    // `${domain}._${suffix}` which will not resolve and shows "Unavailable"
    // gracefully — no exception, no flicker.
    const prefix = this._resolvedPrefix || this._config?.entity_prefix || "";
    return `${domain}.${prefix}_${suffix}`;
  }

  /**
   * djb2-style cheap string hash. Used by render() to skip innerHTML rewrites
   * when nothing visible changed — eliminates the per-state-tick flicker
   * caused by `set hass()` firing on every HA state change.
   */
  _cheapHash(s) {
    let h = 5381;
    for (let i = 0; i < s.length; i++) {
      h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
    }
    return h;
  }

  _stateObj(entityId) {
    return entityId ? this._hass?.states?.[entityId] : undefined;
  }

  _integrationState(key) {
    return this._stateObj(this._entityId(key));
  }

  _language() {
    const rawLanguage = this._hass?.language || DEFAULT_LOCALE;
    const normalized = rawLanguage.replaceAll("_", "-").toLowerCase().split("-")[0];
    return FRONTEND_LOCALES[normalized] ? normalized : DEFAULT_LOCALE;
  }

  _t(key) {
    const locale = FRONTEND_LOCALES[this._language()] || FRONTEND_LOCALES[DEFAULT_LOCALE];
    return locale[key] || FRONTEND_LOCALES[DEFAULT_LOCALE][key] || key;
  }

  /**
   * v1.10.0: pick a translation from an inline {en, it, nl} object — the
   * pattern used by SETTINGS_CATALOG. Falls back to English when the
   * detected language is unsupported.
   */
  _loc(obj) {
    if (!obj) return "";
    const lang = this._language();
    return obj[lang] || obj.en || Object.values(obj)[0] || "";
  }

  /**
   * v1.10.0: pick a static UI label from STATIC_LABELS for the detected
   * language. Falls back to English.
   */
  _label(key) {
    const lang = this._language();
    return (STATIC_LABELS[lang] || STATIC_LABELS.en)[key] || STATIC_LABELS.en[key] || key;
  }

  _displayValue(entityId, fallback) {
    const resolvedFallback = fallback || this._t("common.unavailable");
    const stateObj = this._stateObj(entityId);
    if (!stateObj) {
      return resolvedFallback;
    }
    const unit = stateObj.attributes?.unit_of_measurement;
    if (!stateObj.state || stateObj.state === "unknown" || stateObj.state === "unavailable") {
      return resolvedFallback;
    }
    return unit ? `${stateObj.state} ${unit}` : stateObj.state;
  }

  _labelFor(entityId, fallback) {
    const stateObj = this._stateObj(entityId);
    return stateObj?.attributes?.friendly_name || fallback;
  }

  _isOn(entityId) {
    const stateObj = this._stateObj(entityId);
    return stateObj?.state === "on";
  }

  async _toggle(entityId) {
    if (!this._hass || !entityId) {
      return;
    }
    // v1.11.3: optimistic UI — flip the visual state immediately so the
    // user gets sub-frame feedback instead of waiting for the HA service
    // round-trip + state event. If the service call errors, the next
    // live-update tick (which reads the real state) will revert it.
    this._optimisticToggleVisual(entityId);
    const [domain] = entityId.split(".");
    try {
      await this._hass.callService(domain, "toggle", { entity_id: entityId });
    } catch (e) {
      // Revert: live-update will snap the visual back on the next render
      // tick, but trigger one immediately to avoid a frame of wrongness.
      this.render();
      throw e;
    }
  }

  /**
   * v1.11.3: Flip the visual state of every DOM node bound to an
   * entity toggle. Used for optimistic UI on click; the next render
   * tick (driven by HA's state_changed event) will confirm via the
   * live-update path.
   */
  _optimisticToggleVisual(entityId) {
    const root = this.shadowRoot;
    if (!root) return;
    const escapedId = (typeof CSS !== "undefined" && CSS.escape)
      ? CSS.escape(entityId)
      : entityId.replace(/"/g, '\\"');
    root.querySelectorAll(`[data-toggle="${escapedId}"]`).forEach((node) => {
      if (
        node.classList.contains("control-toggle")
        || node.classList.contains("day-cell")
        || node.classList.contains("day-soc-cell")
      ) {
        const next = !node.classList.contains("is-on");
        node.classList.toggle("is-on", next);
        const shell = node.querySelector(".switch-shell");
        if (shell) shell.classList.toggle("is-on", next);
      } else {
        const next = !node.classList.contains("on");
        node.classList.toggle("on", next);
      }
    });
  }

  async _setNumber(entityId, value) {
    if (!this._hass || !entityId) {
      return;
    }
    await this._hass.callService("number", "set_value", {
      entity_id: entityId,
      value,
    });
  }

  async _adjustNumber(entityId, direction) {
    const stateObj = this._stateObj(entityId);
    if (!stateObj) {
      return;
    }

    const current = Number(stateObj.state);
    const step = Number(stateObj.attributes?.step ?? 1);
    const min = Number(stateObj.attributes?.min ?? current);
    const max = Number(stateObj.attributes?.max ?? current);
    const next = Math.min(max, Math.max(min, current + step * direction));
    // v1.11.3: optimistic UI — update every span bound to this entity
    // before the HA service call resolves. Live-update will confirm on
    // the next render tick (or revert if the call errored).
    this._optimisticNumberVisual(entityId, next);
    await this._setNumber(entityId, next);
  }

  /**
   * v1.11.3: Update every DOM node bound to a number entity with the
   * pending value. Mirrors _updateLiveValues() number handling so the
   * visual stays consistent between optimistic + confirmed updates.
   */
  _optimisticNumberVisual(entityId, value) {
    const root = this.shadowRoot;
    if (!root) return;
    const escapedId = (typeof CSS !== "undefined" && CSS.escape)
      ? CSS.escape(entityId)
      : entityId.replace(/"/g, '\\"');
    const newText = String(value);
    root.querySelectorAll(`[data-live-number="${escapedId}"]`).forEach((node) => {
      const first = node.firstChild;
      if (first && first.nodeType === 3) {
        if (first.nodeValue !== newText) first.nodeValue = newText;
      } else {
        node.insertBefore(document.createTextNode(newText), node.firstChild);
      }
    });
  }

  async _setSelect(entityId, option) {
    if (!this._hass || !entityId) {
      return;
    }
    await this._hass.callService("select", "select_option", {
      entity_id: entityId,
      option,
    });
  }

  async _adjustTime(entityId, stepMinutes) {
    const stateObj = this._stateObj(entityId);
    if (!stateObj || !stateObj.state || !stateObj.state.includes(":")) {
      return;
    }

    const [rawHours, rawMinutes] = stateObj.state.split(":");
    const hours = Number(rawHours);
    const minutes = Number(rawMinutes);
    const total = ((hours * 60 + minutes + stepMinutes) % 1440 + 1440) % 1440;
    const nextHours = String(Math.floor(total / 60)).padStart(2, "0");
    const nextMinutes = String(total % 60).padStart(2, "0");

    await this._hass.callService("time", "set_value", {
      entity_id: entityId,
      time: `${nextHours}:${nextMinutes}:00`,
    });
  }

  /**
   * Extract a numeric value from an HA entity state. Returns null when the
   * entity is missing or its state is unknown/unavailable.
   */
  _numericState(entityId) {
    const stateObj = this._stateObj(entityId);
    if (!stateObj || !stateObj.state) return null;
    if (stateObj.state === "unknown" || stateObj.state === "unavailable") return null;
    const v = Number(stateObj.state);
    return Number.isFinite(v) ? v : null;
  }

  /**
   * Dual concentric SOC ring (iOS Activity-style):
   *   outer = EV SOC (system green)
   *   inner = Home Battery SOC (system purple) — only drawn when configured
   *
   * The center shows the most useful piece of info we have:
   *   - charging power if a charging_power_entity is configured and >0
   *   - otherwise the EV SOC %
   *   - otherwise "—"
   */
  _renderHeroRing() {
    const evPct = this._numericState(this._config.ev_soc_entity);
    const homePct = this._numericState(this._config.home_battery_soc_entity);
    const chargingPowerObj = this._stateObj(this._config.charging_power_entity);
    const chargerStatus = this._stateObj(this._config.charger_status_entity)?.state;
    const isCharging =
      chargerStatus === "charger_charging" ||
      (chargingPowerObj && Number(chargingPowerObj.state) > 0.05);

    // Geometry — viewBox is 220×220, center (110,110)
    const rOuter = 96;
    const rInner = 76;
    const cOuter = 2 * Math.PI * rOuter;
    const cInner = 2 * Math.PI * rInner;
    const clamp01 = (n) => Math.max(0, Math.min(1, n));
    const evFrac = evPct != null ? clamp01(evPct / 100) : 0;
    const homeFrac = homePct != null ? clamp01(homePct / 100) : 0;

    // v1.10.5: same logic as _collectLiveValues to keep first-render and
    // live-update output identical (avoids a one-frame flash).
    const chargingPowerNum = chargingPowerObj
      ? Number(chargingPowerObj.state)
      : null;
    const isActuallyCharging =
      isCharging
      && chargingPowerObj
      && Number.isFinite(chargingPowerNum)
      && chargingPowerNum > 0.05
      && !(evPct != null && evPct >= 100);
    let headline = "—";
    let sub = this._t("metric.ev_soc");
    if (isActuallyCharging) {
      const unit = chargingPowerObj.attributes?.unit_of_measurement || "";
      headline = `${chargingPowerObj.state}${unit ? " " + unit : ""}`;
      sub = this._t("metric.charging_power");
    } else if (evPct != null) {
      headline = `${Math.round(evPct)}%`;
    }

    // v1.11.0: rings use aurora accents (more saturated, more electric)
    // for the live arcs while keeping the track in the muted system gray.
    const inner = homePct != null
      ? `
        <circle class="ring-track" cx="110" cy="110" r="${rInner}" stroke-width="13"/>
        <circle class="ring-progress" cx="110" cy="110" r="${rInner}" stroke-width="13"
                style="color: var(--evsc-aurora-violet); stroke: var(--evsc-aurora-violet);"
                stroke-dasharray="${cInner}" stroke-dashoffset="${cInner * (1 - homeFrac)}"
                data-live-attr-id="ring.homeOffset"/>`
      : "";

    const legendHomeText = homePct != null
      ? `${this._t("metric.home_battery")} ${Math.round(homePct)}%`
      : "";
    const legendHome = homePct != null
      ? `<div style="color: var(--evsc-aurora-violet);"><span class="ring-dot"></span><span data-live="legend.home">${legendHomeText}</span></div>`
      : "";

    const chargingDot = isCharging
      ? `<span class="charging-pulse" title="${this._t("metric.charging_power")}"></span>`
      : "";

    const legendEvText = `${this._t("metric.ev_soc")}${evPct != null ? " " + Math.round(evPct) + "%" : ""}`;

    return `
      <div class="hero-ring-wrap">
        <div class="hero-ring">
          <svg viewBox="0 0 220 220" aria-hidden="true">
            <circle class="ring-track" cx="110" cy="110" r="${rOuter}" stroke-width="13"/>
            <circle class="ring-progress" cx="110" cy="110" r="${rOuter}" stroke-width="13"
                    style="color: var(--evsc-aurora-green); stroke: var(--evsc-aurora-green);"
                    stroke-dasharray="${cOuter}" stroke-dashoffset="${cOuter * (1 - evFrac)}"
                    data-live-attr-id="ring.evOffset"/>
            ${inner}
          </svg>
          <div class="hero-ring-center">
            <div class="ring-headline">${chargingDot}<span data-live="ring.headline">${headline}</span></div>
            <div class="ring-sub" data-live="ring.sub">${sub}</div>
          </div>
        </div>
        <div class="hero-ring-legend">
          <div style="color: var(--evsc-aurora-green);"><span class="ring-dot"></span><span data-live="legend.ev">${legendEvText}</span></div>
          ${legendHome}
        </div>
      </div>
    `;
  }

  /**
   * Render the priority engine state as a colored pill. EV → green,
   * Home → blue, EV_Free → purple. Unknown / unavailable → neutral chip.
   */
  _renderPriorityPill(stateObj) {
    if (!stateObj?.state) {
      return `<span class="priority-pill">${this._t("common.unavailable")}</span>`;
    }
    const raw = String(stateObj.state).trim();
    const modifier = raw.toLowerCase().replace(/\s+/g, "_");
    const labelMap = {
      ev: "EV",
      home: "Home",
      ev_free: "EV Free",
    };
    const label = labelMap[modifier] || raw;
    return `<span class="priority-pill state-${modifier}">${label}</span>`;
  }

  _bindEvents() {
    const root = this.shadowRoot;
    if (!root) {
      return;
    }

    root.querySelectorAll("[data-toggle]").forEach((node) => {
      node.addEventListener("click", () => this._toggle(node.dataset.toggle));
    });

    root.querySelectorAll("[data-number][data-direction]").forEach((node) => {
      node.addEventListener("click", () => {
        this._adjustNumber(node.dataset.number, Number(node.dataset.direction));
      });
    });

    root.querySelectorAll("[data-time][data-minutes]").forEach((node) => {
      node.addEventListener("click", () => {
        this._adjustTime(node.dataset.time, Number(node.dataset.minutes));
      });
    });

    root.querySelectorAll("[data-select][data-option]").forEach((node) => {
      node.addEventListener("click", () => {
        this._setSelect(node.dataset.select, node.dataset.option);
      });
    });

    // v1.10.0: tab switching (Dashboard / Settings)
    root.querySelectorAll("[data-view]").forEach((node) => {
      node.addEventListener("click", () => {
        const next = node.dataset.view;
        if (this._view === next) return;
        this._view = next;
        this._lastRenderHash = ""; // force re-render past anti-flicker hash check
        this.render();
      });
    });

    // v1.10.0: accordion open/close (Settings categories)
    root.querySelectorAll("[data-accordion]").forEach((node) => {
      node.addEventListener("click", () => {
        const id = node.dataset.accordion;
        if (this._openAccordions.has(id)) {
          this._openAccordions.delete(id);
        } else {
          this._openAccordions.add(id);
        }
        this._lastRenderHash = "";
        this.render();
      });
    });
  }

  _renderToggle(entityId, label, hint, tone = "cyan") {
    const enabled = this._isOn(entityId);
    return `
      <button class="control-card control-toggle ${enabled ? "is-on" : ""} tone-${tone}" data-toggle="${entityId}">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <span class="switch-shell ${enabled ? "is-on" : ""}">
          <span class="switch-thumb"></span>
        </span>
      </button>
    `;
  }

  _renderStepper(entityId, label, hint, tone = "amber") {
    const stateObj = this._stateObj(entityId);
    const unit = stateObj?.attributes?.unit_of_measurement || "";
    const value = stateObj?.state || "0";
    return `
      <div class="control-card tone-${tone}">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <div class="stepper-shell">
          <button class="stepper-button" data-number="${entityId}" data-direction="-1">-</button>
          <span class="stepper-value" data-live-number="${entityId}">${value}<small>${unit}</small></span>
          <button class="stepper-button" data-number="${entityId}" data-direction="1">+</button>
        </div>
      </div>
    `;
  }

  _renderTimeControl(entityId, label, hint) {
    const value = this._stateObj(entityId)?.state || "--:--";
    return `
      <div class="control-card tone-violet">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <div class="time-shell">
          <button class="stepper-button" data-time="${entityId}" data-minutes="-15">-15m</button>
          <span class="time-value" data-live-time="${entityId}">${value.slice(0, 5)}</span>
          <button class="stepper-button" data-time="${entityId}" data-minutes="15">+15m</button>
        </div>
      </div>
    `;
  }

  _renderSelectChips(entityId, label, hint) {
    const stateObj = this._stateObj(entityId);
    const current = stateObj?.state;
    const options = (stateObj?.attributes?.options || []).filter((option) =>
      SUPPORTED_PROFILES.includes(option)
    );
    const chips = options
      .map((option) => {
        const selected = option === current ? "selected" : "";
        return `<button class="profile-chip ${selected}" data-select="${entityId}" data-option="${option}">${this._t(`profile.${option}`)}</button>`;
      })
      .join("");

    return `
      <div class="profile-card">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <div class="profile-row">${chips || `<span class="muted">${this._t("common.no_options")}</span>`}</div>
      </div>
    `;
  }

  _renderMetric(label, value, tone, sublabel, liveKey) {
    // v1.10.4: liveKey marks the dynamic value span for in-place DOM
    // mutation by _updateLiveValues(). When set, this <strong> can be
    // updated without rebuilding the entire DOM tree.
    // v1.10.5: sublabel rendered only when non-empty.
    const liveAttr = liveKey ? ` data-live="${liveKey}"` : "";
    const subHtml = sublabel ? `<span class="metric-sub">${sublabel}</span>` : "";
    return `
      <div class="metric-card tone-${tone}">
        <span class="eyebrow">${label}</span>
        <strong${liveAttr}>${value}</strong>
        ${subHtml}
      </div>
    `;
  }

  _renderInfoCard(label, value, hint, tone = "cyan") {
    return `
      <div class="control-card info-card tone-${tone}">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <div class="info-value">${value}</div>
      </div>
    `;
  }

  _renderDayToggleGrid(label, hint, keyPrefix, tone = "violet") {
    const locale = this._language();
    const initials = DAY_INITIALS_BY_LOCALE[locale] || DAY_INITIALS_BY_LOCALE[DEFAULT_LOCALE];
    const cells = DAYS.map((day, index) => {
      const entityId = this._entityId(`${keyPrefix}_${day}`);
      const enabled = this._isOn(entityId);
      return `
        <button class="day-cell ${enabled ? "is-on" : ""}" data-toggle="${entityId}" title="${day}">
          <span class="day-initial">${initials[index]}</span>
          <span class="day-dot ${enabled ? "is-on" : ""}"></span>
        </button>
      `;
    }).join("");

    return `
      <div class="control-card weekly-grid tone-${tone}">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <div class="day-row">${cells}</div>
      </div>
    `;
  }

  _renderDaySocGrid(label, hint, keyPrefix, tone = "cyan") {
    const locale = this._language();
    const initials = DAY_INITIALS_BY_LOCALE[locale] || DAY_INITIALS_BY_LOCALE[DEFAULT_LOCALE];
    const cells = DAYS.map((day, index) => {
      const entityId = this._entityId(`${keyPrefix}_${day}`);
      const stateObj = this._stateObj(entityId);
      const value = stateObj?.state ?? "--";
      return `
        <div class="day-soc-cell">
          <span class="day-initial-sm">${initials[index]}</span>
          <div class="day-soc-controls">
            <button class="micro-stepper" data-number="${entityId}" data-direction="-1">−</button>
            <span class="day-soc-value" data-live-number="${entityId}">${value}<small>%</small></span>
            <button class="micro-stepper" data-number="${entityId}" data-direction="1">+</button>
          </div>
        </div>
      `;
    }).join("");

    return `
      <div class="control-card daily-soc tone-${tone}">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <div class="day-soc-row">${cells}</div>
      </div>
    `;
  }

  _diagnosticValue(value) {
    return value === undefined || value === null || value === ""
      ? this._t("common.unavailable")
      : value;
  }

  _renderDiagnosticDetail(label, value) {
    return `
      <div class="diag-detail">
        <span class="eyebrow">${label}</span>
        <strong>${this._diagnosticValue(value)}</strong>
      </div>
    `;
  }

  _renderDiagnostics(primary, secondary, hybrid, cachedEvSoc) {
    const primaryAttrs = primary?.attributes || {};
    const secondaryAttrs = secondary?.attributes || {};
    const hybridAttrs = hybrid?.attributes || {};
    const cachedAttrs = cachedEvSoc?.attributes || {};
    const lastDenial = primaryAttrs.last_denial?.denial_reason || primaryAttrs.last_denial?.reason;
    const activeOwner = primaryAttrs.active_owner;
    const lastReason = primaryAttrs.last_reason_detail || primaryAttrs.last_reason_code;
    const externalCause = primaryAttrs.last_external_cause;
    const traceMode = primaryAttrs.trace_enabled ? "ON" : "OFF";
    const solarReason =
      secondaryAttrs.last_reason_detail ||
      secondaryAttrs.reason ||
      secondaryAttrs.night_mode ||
      secondaryAttrs.profile;
    const hybridState = hybrid?.state || this._t("common.unavailable");
    const hybridFailed = hybridAttrs.failed_probes_in_window;
    const hybridLongCooldowns = hybridAttrs.long_cooldowns_today;
    const cachedSocLabel =
      cachedEvSoc && cachedEvSoc.state && cachedEvSoc.state !== "unknown" && cachedEvSoc.state !== "unavailable"
        ? `${cachedEvSoc.state}%`
        : this._t("common.unavailable");
    const cachedFlag = cachedAttrs.is_cached ? "yes" : "no";

    return `
      <section class="diagnostic-panel">
        <div class="diag-card">
          <span class="eyebrow">${this._t("diagnostic.automation")}</span>
          <p>${primary?.state || this._t("common.unavailable")}</p>
          <div class="diag-grid">
            ${this._renderDiagnosticDetail(this._t("diagnostic.active_owner"), activeOwner)}
            ${this._renderDiagnosticDetail(this._t("diagnostic.last_reason"), lastReason)}
            ${this._renderDiagnosticDetail(this._t("diagnostic.external_cause"), externalCause)}
            ${this._renderDiagnosticDetail(this._t("diagnostic.last_denial"), lastDenial)}
            ${this._renderDiagnosticDetail(this._t("diagnostic.trace_mode"), traceMode)}
          </div>
        </div>
        <div class="diag-card">
          <span class="eyebrow">${this._t("diagnostic.solar_surplus")}</span>
          <p>${secondary?.state || this._t("common.unavailable")}</p>
          <div class="diag-grid">
            ${this._renderDiagnosticDetail(this._t("diagnostic.last_reason"), solarReason)}
          </div>
        </div>
        <div class="diag-card">
          <span class="eyebrow">${this._t("diagnostic.hybrid_inverter")}</span>
          <p>${hybridState}</p>
          <div class="diag-grid">
            ${this._renderDiagnosticDetail(this._t("diagnostic.hybrid_failed_probes"), hybridFailed)}
            ${this._renderDiagnosticDetail(this._t("diagnostic.hybrid_long_cooldowns"), hybridLongCooldowns)}
          </div>
        </div>
        <div class="diag-card">
          <span class="eyebrow">${this._t("diagnostic.cached_ev_soc")}</span>
          <p>${cachedSocLabel}</p>
          <div class="diag-grid">
            ${this._renderDiagnosticDetail("is_cached", cachedFlag)}
          </div>
          <span class="metric-sub">${this._t("diagnostic.cached_ev_soc_hint")}</span>
        </div>
      </section>
    `;
  }

  // ============================================================
  // v1.10.0: split-view rendering — Dashboard / Settings
  // ============================================================

  _renderTabs() {
    const isDashboard = this._view !== "settings";
    return `
      <div class="evsc-tabs">
        <button class="evsc-tab ${isDashboard ? "active" : ""}" data-view="dashboard">
          <span class="evsc-tab-dot"></span>${this._label("nav_dashboard")}
        </button>
        <button class="evsc-tab ${!isDashboard ? "active" : ""}" data-view="settings">${this._label("nav_settings")}</button>
      </div>
    `;
  }

  /**
   * Bento-style Night Smart Charge card with crescent illustration,
   * two time pills and the enable toggle. Replaces the verbose
   * 6-row module from the original dashboard.
   */
  _renderNightCardV2() {
    const enabledId = this._entityId("nightEnabled");
    const nightTimeId = this._entityId("nightTime");
    const carReadyTimeId = this._entityId("carReadyTime");
    const enabled = this._isOn(enabledId);
    const startTime = (this._stateObj(nightTimeId)?.state || "01:00").slice(0, 5);
    const carReadyTime = (this._stateObj(carReadyTimeId)?.state || "08:00").slice(0, 5);
    const forecast = this._displayValue(this._config.pv_forecast_entity, "");

    return `
      <section class="evsc-night-card">
        <div class="evsc-night-head">
          <span class="evsc-night-eyebrow">${this._label("night_card_title")}</span>
          <span class="evsc-night-sub">${this._label("night_card_sub")}</span>
        </div>
        <div class="evsc-night-illu" aria-hidden="true">
          <div class="evsc-night-moon"></div>
        </div>
        <div class="evsc-night-times">
          <div class="evsc-night-time">
            <div class="lbl">${this._label("night_start")}</div>
            <div class="vv" data-live-time="${nightTimeId}">${startTime}</div>
          </div>
          <div class="evsc-night-time">
            <div class="lbl">${this._label("night_car_ready")}</div>
            <div class="vv" data-live-time="${carReadyTimeId}">${carReadyTime}</div>
          </div>
        </div>
        <div class="evsc-night-enable">
          <div>
            <div class="t">${this._label("night_enabled")}</div>
            ${forecast ? `<div class="s">${forecast}</div>` : ""}
          </div>
          <button class="evsc-set-toggle violet ${enabled ? "on" : ""}" data-toggle="${enabledId}" aria-label="${this._label("night_enabled")}"></button>
        </div>
      </section>
    `;
  }

  /**
   * Weekly planner — 7 columns × 3 rows (EV target, Home target, Car ready).
   * Inline stepper controls for SOC targets, mini iOS toggle for car-ready.
   * Today's column is highlighted with a blue tint.
   */
  _renderWeeklyPlannerV2() {
    const locale = this._language();
    const initials = DAY_INITIALS_BY_LOCALE[locale] || DAY_INITIALS_BY_LOCALE[DEFAULT_LOCALE];
    const todayIdx = (new Date().getDay() + 6) % 7; // 0 = Mon … 6 = Sun

    const headers = initials
      .map((init, i) => `<div class="evsc-wp-header ${i === todayIdx ? "today" : ""}">${init}</div>`)
      .join("");

    const evRow = DAYS.map((day, i) => {
      const ent = this._entityId(`evMinSoc_${day}`);
      const v = this._stateObj(ent)?.state ?? "—";
      return `
        <div class="evsc-wp-cell ${i === todayIdx ? "today" : ""}">
          <div class="evsc-wp-soc-row">
            <button class="evsc-wp-mini" data-number="${ent}" data-direction="-1">−</button>
            <span class="evsc-wp-soc ev" data-live-number="${ent}">${v}<small>%</small></span>
            <button class="evsc-wp-mini" data-number="${ent}" data-direction="1">+</button>
          </div>
        </div>
      `;
    }).join("");

    const homeRow = DAYS.map((day, i) => {
      const ent = this._entityId(`homeMinSoc_${day}`);
      const v = this._stateObj(ent)?.state ?? "—";
      return `
        <div class="evsc-wp-cell ${i === todayIdx ? "today" : ""}">
          <div class="evsc-wp-soc-row">
            <button class="evsc-wp-mini" data-number="${ent}" data-direction="-1">−</button>
            <span class="evsc-wp-soc home" data-live-number="${ent}">${v}<small>%</small></span>
            <button class="evsc-wp-mini" data-number="${ent}" data-direction="1">+</button>
          </div>
        </div>
      `;
    }).join("");

    const carRow = DAYS.map((day, i) => {
      const ent = this._entityId(`carReady_${day}`);
      const enabled = this._isOn(ent);
      return `
        <div class="evsc-wp-cell ${i === todayIdx ? "today" : ""}">
          <button class="evsc-wp-tog ${enabled ? "on" : ""}" data-toggle="${ent}" aria-label="${this._label("weekly_car")}"></button>
        </div>
      `;
    }).join("");

    // v1.11.0: day-grouped mobile layout — 7 cards, each containing the
    // full editorial day spread (large italic day name, EV row, Home row,
    // Car toggle). Replaces the v1.10.5 21-card flat stack, which was
    // functional but verbose. Today's card gets a TODAY pill + accent
    // border. The desktop grid above is hidden via CSS @ 768 px and
    // this block takes over — single HTML payload, two render paths.
    const dayFullNames = DAY_FULL_NAMES_BY_LOCALE[locale] || DAY_FULL_NAMES_BY_LOCALE[DEFAULT_LOCALE];
    const dayCards = DAYS.map((day, i) => {
      const evEnt = this._entityId(`evMinSoc_${day}`);
      const homeEnt = this._entityId(`homeMinSoc_${day}`);
      const carEnt = this._entityId(`carReady_${day}`);
      const evV = this._stateObj(evEnt)?.state ?? "—";
      const homeV = this._stateObj(homeEnt)?.state ?? "—";
      const carOn = this._isOn(carEnt);
      const isToday = i === todayIdx;
      const todayBadge = isToday
        ? `<span class="evsc-wp-today-badge">${this._label("weekly_today_badge")}</span>`
        : "";
      return `
        <article class="evsc-wp-day-card ${isToday ? "today" : ""}">
          <header class="evsc-wp-day-head">
            <div class="evsc-wp-day-name-block">
              <span class="evsc-wp-day-name">${dayFullNames[i]}</span>
              ${todayBadge}
            </div>
            <button class="evsc-wp-tog ${carOn ? "on" : ""}"
                    data-toggle="${carEnt}"
                    aria-label="${this._label("weekly_car")}"></button>
          </header>
          <div class="evsc-wp-day-body">
            <div class="evsc-wp-day-row">
              <span class="evsc-wp-day-kind evsc-wp-kind-ev">${this._label("weekly_ev")}</span>
              <div class="evsc-wp-soc-row">
                <button class="evsc-wp-mini" data-number="${evEnt}" data-direction="-1">−</button>
                <span class="evsc-wp-soc ev" data-live-number="${evEnt}">${evV}<small>%</small></span>
                <button class="evsc-wp-mini" data-number="${evEnt}" data-direction="1">+</button>
              </div>
            </div>
            <div class="evsc-wp-day-row">
              <span class="evsc-wp-day-kind evsc-wp-kind-home">${this._label("weekly_home")}</span>
              <div class="evsc-wp-soc-row">
                <button class="evsc-wp-mini" data-number="${homeEnt}" data-direction="-1">−</button>
                <span class="evsc-wp-soc home" data-live-number="${homeEnt}">${homeV}<small>%</small></span>
                <button class="evsc-wp-mini" data-number="${homeEnt}" data-direction="1">+</button>
              </div>
            </div>
          </div>
        </article>
      `;
    }).join("");

    return `
      <section class="evsc-weekly">
        <div class="evsc-wp-head">
          <div>
            <span class="evsc-wp-eyebrow">${this._label("weekly_title")}</span>
            <span class="evsc-wp-sub">${this._label("weekly_desc")}</span>
          </div>
        </div>
        <div class="evsc-wp-grid">
          <div></div>${headers}
          <div class="evsc-wp-row-label">${this._label("weekly_ev")}</div>${evRow}
          <div class="evsc-wp-row-label">${this._label("weekly_home")}</div>${homeRow}
          <div class="evsc-wp-row-label">${this._label("weekly_car")}</div>${carRow}
        </div>
        <div class="evsc-wp-mobile">${dayCards}</div>
        <div class="evsc-wp-info">${this._label("weekly_info")}</div>
      </section>
    `;
  }

  /**
   * Render one accordion (category) for the Settings view. Items are
   * rendered from SETTINGS_CATALOG via _renderSettingItemFromCatalog.
   */
  _renderAccordion(cat) {
    const open = this._openAccordions.has(cat.id);
    const itemsHtml = cat.items.map((item) => this._renderSettingItemFromCatalog(item)).join("");
    return `
      <div class="evsc-acc ${open ? "open" : ""}">
        <div class="evsc-acc-head" data-accordion="${cat.id}">
          <div class="evsc-acc-ico ${cat.iconClass}">${cat.icon}</div>
          <div class="evsc-acc-title">
            <h3>${this._loc(cat.name)}</h3>
            <p>${this._loc(cat.desc)}</p>
          </div>
          <div class="evsc-acc-count">${cat.items.length}</div>
          <svg class="evsc-acc-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true">
            <polyline points="9 6 15 12 9 18"/>
          </svg>
        </div>
        <div class="evsc-acc-body">
          <div class="evsc-acc-body-inner">${itemsHtml}</div>
        </div>
      </div>
    `;
  }

  _renderSettingItemFromCatalog(item) {
    const entityId = this._entityId(item.entityKey);
    const suffix = DOMAIN_SUFFIXES[item.entityKey]?.[1] || "";
    let control = "";
    if (item.kind === "toggle") {
      const enabled = this._isOn(entityId);
      control = `<button class="evsc-set-toggle ${enabled ? "on" : ""}" data-toggle="${entityId}" aria-label="${this._loc(item.name)}"></button>`;
    } else if (item.kind === "stepper") {
      const stateObj = this._stateObj(entityId);
      const unit = stateObj?.attributes?.unit_of_measurement || "";
      const value = stateObj?.state ?? "—";
      control = `
        <div class="evsc-set-stepper">
          <button class="evsc-set-step" data-number="${entityId}" data-direction="-1">−</button>
          <span class="evsc-set-val" data-live-number="${entityId}">${value}<small>${unit}</small></span>
          <button class="evsc-set-step" data-number="${entityId}" data-direction="1">+</button>
        </div>
      `;
    } else if (item.kind === "time") {
      const v = (this._stateObj(entityId)?.state || "--:--").slice(0, 5);
      control = `
        <div class="evsc-set-stepper">
          <button class="evsc-set-step" data-time="${entityId}" data-minutes="-15">−</button>
          <span class="evsc-set-val" data-live-time="${entityId}">${v}</span>
          <button class="evsc-set-step" data-time="${entityId}" data-minutes="15">+</button>
        </div>
      `;
    } else {
      const v = this._stateObj(entityId)?.state || this._t("common.unavailable");
      control = `<span class="evsc-set-info">${v}</span>`;
    }
    return `
      <div class="evsc-set-item">
        <div>
          <h4>${this._loc(item.name)}${suffix ? ` <span class="evsc-set-key">${suffix}</span>` : ""}</h4>
          <p>${this._loc(item.desc)}</p>
          ${item.hint ? `<div class="evsc-set-hint">${this._loc(item.hint)}</div>` : ""}
        </div>
        <div class="evsc-set-ctrl">${control}</div>
      </div>
    `;
  }

  _renderSettingsView() {
    return `
      <div class="evsc-settings-hero">
        <h2>${this._label("settings_title")}</h2>
        <p>${this._label("settings_intro")}</p>
      </div>
      <div class="evsc-settings-list">
        ${SETTINGS_CATALOG.map((cat) => this._renderAccordion(cat)).join("")}
      </div>
    `;
  }

  /**
   * Dashboard view — operational only. Hero ring (with charging pill BELOW
   * the ring + "EV" label inside), Override + Boost, Weekly Planner, Night
   * Smart Charge bento card, Charging Profile chips. Configuration knobs
   * live in the Settings view.
   */
  _renderDashboardView(ids, displayValues, priorityState) {
    // v1.10.2: Boost group — toggle + amperage + target SOC are
    // semantically one control, so render them inside a single visual
    // container with internal dividers instead of three sibling cards.
    const boostGroup = `
      <div class="evsc-boost-group">
        ${this._renderToggle(ids.boostEnabledId, this._t("control.boost_session"), this._t("control.high_priority"), "amber")}
        <div class="evsc-boost-subitems">
          ${this._renderStepper(ids.boostAmperageId, this._t("control.boost_amperage"), this._t("control.output"), "amber")}
          ${this._renderStepper(ids.boostTargetSocId, this._t("control.boost_target_soc"), this._t("control.auto_stop"), "lime")}
        </div>
      </div>
    `;

    const overrideStack = `
      ${this._renderToggle(ids.forceChargeId, this._t("control.force_charge"), this._t("control.override_all"), "rose")}
      ${boostGroup}
    `;

    return `
      <div class="evsc-dash-grid">
        <div class="evsc-stack">
          <header class="evsc-hero-v2">
            ${this._renderHeroRing()}
            <div class="evsc-hero-body">
              ${this._renderPriorityPill(priorityState)}
              <h1>${this._config.title || this._t("title.default")}</h1>
              <p class="evsc-hero-sub">${this._t("hero.description")}</p>
              <div class="evsc-metric-row">
                ${this._renderMetric(this._t("metric.solar_power"), displayValues.solarPower, "amber", "", "metric.solarPower")}
                ${this._renderMetric(this._t("metric.grid_import"), displayValues.gridImport, "rose", "", "metric.gridImport")}
                ${this._renderMetric(this._t("metric.charge_current"), displayValues.chargerCurrent, "teal", "", "metric.chargerCurrent")}
                ${this._renderMetric(this._t("metric.charging_power"), displayValues.chargingPower, "cyan", "", "metric.chargingPower")}
              </div>
            </div>
          </header>

          <section class="evsc-card evsc-override-card">
            <div class="evsc-card-head">
              <span class="evsc-card-title">${this._label("override_title")}</span>
              <span class="evsc-card-eyebrow">${this._label("override_hint")}</span>
            </div>
            <div class="evsc-stack-inner">${overrideStack}</div>
          </section>
        </div>

        <div class="evsc-stack">
          ${this._renderWeeklyPlannerV2()}
          ${this._renderNightCardV2()}

          <section class="evsc-card">
            <div class="evsc-card-head">
              <span class="evsc-card-title">${this._label("profile_label")}</span>
              <span class="evsc-card-eyebrow">${this._label("profile_hint")}</span>
            </div>
            ${this._renderSelectChips(ids.chargingProfileId, this._t("control.charging_profile"), this._t("control.mode_strategy"))}
          </section>
        </div>
      </div>
    `;
  }

  render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    if (!this._hass) {
      // Anti-flicker guard for the boot-state placeholder as well.
      if (this._lastRenderHash === "__boot__") {
        return;
      }
      this._lastRenderHash = "__boot__";
      this.shadowRoot.innerHTML = `
        <ha-card>
          <div class="boot-state">${this._t("boot.waiting_for_hass")}</div>
        </ha-card>
      `;
      return;
    }

    const forceChargeId = this._entityId("forceCharge");
    const boostEnabledId = this._entityId("boostEnabled");
    const boostAmperageId = this._entityId("boostAmperage");
    const boostTargetSocId = this._entityId("boostTargetSoc");
    const boostScheduleEnabledId = this._entityId("boostScheduleEnabled");
    const boostScheduleStartId = this._entityId("boostScheduleStartTime");
    const boostScheduleEndId = this._entityId("boostScheduleEndTime");
    const nightEnabledId = this._entityId("nightEnabled");
    const preserveHomeBatteryId = this._entityId("preserveHomeBattery");
    const nightTimeId = this._entityId("nightTime");
    const carReadyTimeId = this._entityId("carReadyTime");
    const minSolarForecastId = this._entityId("minSolarForecast");
    const nightAmperageId = this._entityId("nightAmperage");
    const chargingProfileId = this._entityId("chargingProfile");
    const checkIntervalId = this._entityId("checkInterval");
    const gridImportThresholdId = this._entityId("gridImportThreshold");
    const gridImportDelayId = this._entityId("gridImportDelay");
    const surplusDropDelayId = this._entityId("surplusDropDelay");
    const solarMaxAmperageId = this._entityId("solarMaxAmperage");
    const useHomeBatteryId = this._entityId("useHomeBattery");
    const homeBatteryMinSocId = this._entityId("homeBatteryMinSoc");
    const batterySupportAmperageId = this._entityId("batterySupportAmperage");
    const batterySupportSunsetBufferId = this._entityId("batterySupportSunsetBuffer");
    const hybridModeId = this._entityId("hybridMode");
    const hybridBatteryFullThresholdId = this._entityId("hybridBatteryFullThreshold");
    const hybridProbeDurationId = this._entityId("hybridProbeDuration");
    const hybridMaxImportDurationId = this._entityId("hybridMaxImportDuration");
    const hybridMaxFailedProbesId = this._entityId("hybridMaxFailedProbes");
    const priorityBalancerId = this._entityId("priorityBalancer");
    const smartBlockerId = this._entityId("smartBlocker");
    const notifySmartBlockerId = this._entityId("notifySmartBlocker");
    const notifyPriorityBalancerId = this._entityId("notifyPriorityBalancer");
    const notifyNightChargeId = this._entityId("notifyNightCharge");
    const traceLoggingId = this._entityId("traceLogging");
    const enableFileLoggingId = this._entityId("enableFileLogging");

    const priorityState = this._integrationState("priorityState");
    const todayEvTarget = this._integrationState("todayEvTarget");
    const todayHomeTarget = this._integrationState("todayHomeTarget");
    const diagnostic = this._integrationState("diagnostic");
    const solarDiagnostic = this._integrationState("solarDiagnostic");
    const hybridDiagnostic = this._integrationState("hybridDiagnostic");
    const cachedEvSoc = this._integrationState("cachedEvSoc");
    const logFilePath = this._integrationState("logFilePath");

    // v1.10.5: charging power label gives a meaningful status string
    // instead of "0.0 W" or "Live feed optional" when the car isn't
    // actually drawing power. Priority order:
    //   1. EV at 100% OR charger_end       → "Fully Charged"
    //   2. charger_free / no power / null  → "Not Charging"
    //   3. charger_wait                    → "Waiting"
    //   4. otherwise                       → live kW reading
    const _chargerStatusState = this._stateObj(this._config.charger_status_entity)?.state;
    const _chargingPowerNum = this._numericState(this._config.charging_power_entity);
    const _evSocNum = this._numericState(this._config.ev_soc_entity);
    let chargingPower;
    if (_evSocNum != null && _evSocNum >= 100) {
      chargingPower = this._t("charging_state.fully_charged");
    } else if (_chargerStatusState === "charger_end") {
      chargingPower = this._t("charging_state.fully_charged");
    } else if (
      _chargerStatusState === "charger_free"
      || _chargingPowerNum == null
      || _chargingPowerNum <= 0.05
    ) {
      chargingPower = this._t("charging_state.not_charging");
    } else if (_chargerStatusState === "charger_wait") {
      chargingPower = this._t("charging_state.waiting");
    } else {
      chargingPower = this._displayValue(this._config.charging_power_entity, this._t("charging_state.not_charging"));
    }
    const evSoc = this._displayValue(this._config.ev_soc_entity, this._t("fallback.ev_soc_entity"));
    const homeBatterySoc = this._displayValue(
      this._config.home_battery_soc_entity,
      this._t("fallback.home_battery_soc_entity"),
    );
    const solarPower = this._displayValue(this._config.solar_power_entity, this._t("fallback.solar_power_entity"));
    const gridImport = this._displayValue(this._config.grid_import_entity, this._t("fallback.grid_import_entity"));
    const chargerCurrent = this._displayValue(this._config.current_entity, this._t("fallback.current_entity"));

    // v1.10.0: dispatch into Dashboard or Settings view depending on _view.
    const ids = {
      forceChargeId, boostEnabledId, boostAmperageId, boostTargetSocId,
      chargingProfileId, nightEnabledId, nightTimeId, carReadyTimeId,
    };
    const displayValues = { chargingPower, solarPower, gridImport, chargerCurrent };

    // v1.10.4: collect live values (sensor-driven, change frequently) for
    // in-place DOM mutation when only sensors changed since last render.
    const liveSnapshot = this._collectLiveValues(displayValues, priorityState);

    // v1.10.4: structural key — everything that, when changed, requires a
    // full DOM rebuild. Live sensor values are EXCLUDED so frequent sensor
    // ticks don't trigger a full rewrite (which would cause visible flicker).
    const structuralKey = this._computeStructuralKey();

    // Fast path: structure unchanged AND shadow DOM already populated →
    // mutate live values in place, no innerHTML rewrite, no flicker.
    if (
      structuralKey === this._lastStructuralKey
      && this.shadowRoot.childNodes.length > 0
    ) {
      this._updateLiveValues(liveSnapshot);
      return;
    }

    // Slow path: structure changed (view switch, accordion open/close,
    // profile chip change, charger status transition, priority state
    // change, language switch, prefix resolved) → full innerHTML
    // replacement. v1.11.3 removed toggle / number / time changes from
    // the structural key — those now use the fast path above.
    const viewHtml = this._view === "settings"
      ? this._renderSettingsView()
      : this._renderDashboardView(ids, displayValues, priorityState);

    const diagnosticsHtml = this._view === "settings"
      ? this._renderDiagnostics(diagnostic, solarDiagnostic, hybridDiagnostic, cachedEvSoc)
      : "";

    const html = `
      <ha-card>
        <div class="dashboard-shell">
          <div class="aurora aurora-a"></div>
          <div class="aurora aurora-b"></div>
          <div class="grain"></div>

          ${this._renderTabs()}
          ${viewHtml}
          ${diagnosticsHtml}
        </div>
      </ha-card>
      <style>${this._inlineStyles()}</style>
    `;

    this._lastStructuralKey = structuralKey;
    this.shadowRoot.innerHTML = html;
    this._bindEvents();
  }

  /**
   * v1.10.4 / v1.11.3: structural key includes ONLY truly structural
   * state — view tab, accordion open/close, profile select (which
   * restructures the chip row), prefix, language, home-battery flag,
   * charger status, priority state. Toggles, numbers and times were
   * REMOVED from this key in v1.11.3 because their visual change is
   * just a class flip or text node update — perfectly suited for the
   * fast-path live-update. Keeping them in the structural key caused
   * a full innerHTML rebuild on every toggle / + / − click, which
   * scrolled the page to the top of the dashboard (the bug the user
   * called out as "mi riporta on top della dashboard").
   */
  _computeStructuralKey() {
    const states = this._hass?.states || {};
    let select = "";

    for (const key of Object.keys(DOMAIN_SUFFIXES)) {
      const [domain] = DOMAIN_SUFFIXES[key];
      const entityId = this._entityId(key);
      const state = states[entityId]?.state;
      if (domain === "select" && key === "chargingProfile") {
        select = state || "";
      }
    }

    const chargerStatus = this._stateObj(this._config.charger_status_entity)?.state || "";
    const priorityState = this._integrationState("priorityState")?.state || "";

    return JSON.stringify({
      view: this._view,
      acc: [...(this._openAccordions || [])].sort(),
      sel: select,
      pfx: this._resolvedPrefix || "",
      lang: this._language(),
      hb: !!this._config.home_battery_soc_entity,
      cs: chargerStatus,
      ps: priorityState,
    });
  }

  /**
   * v1.10.4: Collect a snapshot of live sensor values keyed by data-live
   * id. Consumed by _updateLiveValues() which performs targeted text /
   * attribute updates on the existing DOM without rebuilding it.
   */
  _collectLiveValues(displayValues, priorityState) {
    const evPct = this._numericState(this._config.ev_soc_entity);
    const homePct = this._numericState(this._config.home_battery_soc_entity);
    const chargingPowerObj = this._stateObj(this._config.charging_power_entity);
    const chargerStatus = this._stateObj(this._config.charger_status_entity)?.state;
    const isCharging =
      chargerStatus === "charger_charging" ||
      (chargingPowerObj && Number(chargingPowerObj.state) > 0.05);

    // Ring geometry — must match _renderHeroRing() exactly.
    const rOuter = 96;
    const rInner = 76;
    const cOuter = 2 * Math.PI * rOuter;
    const cInner = 2 * Math.PI * rInner;
    const clamp01 = (n) => Math.max(0, Math.min(1, n));
    const evFrac = evPct != null ? clamp01(evPct / 100) : 0;
    const homeFrac = homePct != null ? clamp01(homePct / 100) : 0;

    // v1.10.5: ring headline shows live kW only when actually drawing
    // power. When the car is fully charged or idle, show the EV % so the
    // ring stays informative instead of jumping to "0.0 W".
    const chargingPowerNum = chargingPowerObj
      ? Number(chargingPowerObj.state)
      : null;
    const isActuallyCharging =
      isCharging
      && chargingPowerObj
      && Number.isFinite(chargingPowerNum)
      && chargingPowerNum > 0.05
      && !(evPct != null && evPct >= 100);
    let ringHeadline = "—";
    let ringSub = this._t("metric.ev_soc");
    if (isActuallyCharging) {
      const unit = chargingPowerObj.attributes?.unit_of_measurement || "";
      ringHeadline = `${chargingPowerObj.state}${unit ? " " + unit : ""}`;
      ringSub = this._t("metric.charging_power");
    } else if (evPct != null) {
      ringHeadline = `${Math.round(evPct)}%`;
    }

    const legendEvText = `${this._t("metric.ev_soc")}${evPct != null ? " " + Math.round(evPct) + "%" : ""}`;
    const legendHomeText = homePct != null
      ? `${this._t("metric.home_battery")} ${Math.round(homePct)}%`
      : "";

    // v1.11.3: collect toggle / number / time state for live-update so
    // those interactions no longer trigger a full innerHTML rebuild.
    // Avoids the scroll-to-top + perceived "click did nothing" bugs.
    const toggleStates = {};
    const numberValues = {};
    const timeValues = {};
    for (const key of Object.keys(DOMAIN_SUFFIXES)) {
      const [domain] = DOMAIN_SUFFIXES[key];
      const entityId = this._entityId(key);
      const stateObj = this._stateObj(entityId);
      if (domain === "switch") {
        toggleStates[entityId] = stateObj?.state === "on";
      } else if (domain === "number") {
        numberValues[entityId] = stateObj?.state ?? "0";
      } else if (domain === "time") {
        const v = stateObj?.state || "--:--";
        timeValues[entityId] = v.slice(0, 5);
      }
    }

    return {
      text: {
        "metric.solarPower": displayValues.solarPower,
        "metric.gridImport": displayValues.gridImport,
        "metric.chargerCurrent": displayValues.chargerCurrent,
        "metric.chargingPower": displayValues.chargingPower,
        "ring.headline": ringHeadline,
        "ring.sub": ringSub,
        "legend.ev": legendEvText,
        "legend.home": legendHomeText,
      },
      attrs: {
        "ring.evOffset": {
          attr: "stroke-dashoffset",
          value: String(cOuter * (1 - evFrac)),
        },
        "ring.homeOffset": {
          attr: "stroke-dashoffset",
          value: String(cInner * (1 - homeFrac)),
        },
      },
      toggles: toggleStates,
      numbers: numberValues,
      times: timeValues,
    };
  }

  /**
   * v1.10.4 / v1.11.3: Apply live value updates via targeted DOM
   * mutation. No innerHTML, no reflow on the parent tree — only the
   * matched elements' textContent / attribute / class changes.
   * Eliminates flicker on sensor ticks AND eliminates the scroll-to-top
   * bug when the user clicks a toggle / stepper (those used to trigger
   * a full DOM rebuild via the structural key).
   */
  _updateLiveValues(snapshot) {
    const root = this.shadowRoot;
    if (!root) return;

    // Text content updates (sensor values, ring headline, legends)
    for (const [key, value] of Object.entries(snapshot.text || {})) {
      const el = root.querySelector(`[data-live="${key}"]`);
      if (el && el.textContent !== String(value)) {
        el.textContent = value;
      }
    }

    // Attribute updates (SVG ring stroke-dashoffset)
    for (const [key, { attr, value }] of Object.entries(snapshot.attrs || {})) {
      const el = root.querySelector(`[data-live-attr-id="${key}"]`);
      if (el && el.getAttribute(attr) !== value) {
        el.setAttribute(attr, value);
      }
    }

    // v1.11.3: Toggle class updates — find every [data-toggle="entityId"]
    // and flip the correct "is-on" / "on" class based on the actual state.
    // Different toggle widgets in the codebase use different class names:
    //   .control-toggle / .day-cell / .day-soc-cell → "is-on"
    //   .evsc-set-toggle / .evsc-wp-tog            → "on"
    // The inner .switch-shell (child of .control-toggle) also mirrors the
    // is-on state — toggle that too so the iOS-style switch animates.
    for (const [entityId, enabled] of Object.entries(snapshot.toggles || {})) {
      const escapedId = (typeof CSS !== "undefined" && CSS.escape)
        ? CSS.escape(entityId)
        : entityId.replace(/"/g, '\\"');
      root.querySelectorAll(`[data-toggle="${escapedId}"]`).forEach((node) => {
        if (
          node.classList.contains("control-toggle")
          || node.classList.contains("day-cell")
          || node.classList.contains("day-soc-cell")
        ) {
          node.classList.toggle("is-on", enabled);
          const shell = node.querySelector(".switch-shell");
          if (shell) shell.classList.toggle("is-on", enabled);
        } else {
          // evsc-set-toggle, evsc-wp-tog
          node.classList.toggle("on", enabled);
        }
      });
    }

    // v1.11.3: Number value updates — every stepper-value / wp-soc /
    // day-soc-value span carries data-live-number="entityId". Replace
    // ONLY the leading text node, preserving the trailing <small> unit.
    for (const [entityId, value] of Object.entries(snapshot.numbers || {})) {
      const escapedId = (typeof CSS !== "undefined" && CSS.escape)
        ? CSS.escape(entityId)
        : entityId.replace(/"/g, '\\"');
      root.querySelectorAll(`[data-live-number="${escapedId}"]`).forEach((node) => {
        const newText = String(value);
        const first = node.firstChild;
        if (first && first.nodeType === 3) {
          // Text node — update in place, keeps <small> sibling intact
          if (first.nodeValue !== newText) first.nodeValue = newText;
        } else {
          // No text node yet — prepend one
          node.insertBefore(document.createTextNode(newText), node.firstChild);
        }
      });
    }

    // v1.11.3: Time value updates — every time-value span carries
    // data-live-time="entityId". textContent replacement is safe here
    // because the span has no children (just the "HH:MM" text).
    for (const [entityId, value] of Object.entries(snapshot.times || {})) {
      const escapedId = (typeof CSS !== "undefined" && CSS.escape)
        ? CSS.escape(entityId)
        : entityId.replace(/"/g, '\\"');
      root.querySelectorAll(`[data-live-time="${escapedId}"]`).forEach((node) => {
        if (node.textContent !== value) node.textContent = value;
      });
    }
  }

  _inlineStyles() {
    return `
        /* ============================================================
         * EV Smart Charger — Liquid Aurora design system (v1.11.0+)
         * ------------------------------------------------------------
         * v1.11.2: reverted to native system fonts after user feedback
         * ("non mi piace questo font, preferivo il precedente"). The
         * Bunny Fonts import (Instrument Serif italic + JetBrains Mono)
         * introduced in v1.11.0 has been removed — no external font
         * dependency, no FOUT, dashboard renders fully native. All other
         * Liquid Aurora elements stay: aurora color accents, vertical-
         * stack layout, mobile day cards, responsive clamps, motion.
         *
         * ▸ FULL TOKEN REFERENCE, USAGE RULES, ANTI-PATTERNS:
         *   custom_components/ev_smart_charger/frontend/DESIGN.md
         *   Read it before adding/changing tokens or adding new
         *   components. The doc is the discoverable surface of this
         *   inline stylesheet.
         * ============================================================ */

        :host {
          /* v1.10.4: shadow DOM box model reset — explicit, NOT inherited
             from light DOM. min-width:0 allows the host to shrink inside
             any flex/grid parent without overflowing the viewport. */
          display: block;
          width: 100%;
          max-width: 100%;
          min-width: 0;
          overflow-x: hidden;
          box-sizing: border-box;
          --evsc-font: -apple-system, "SF Pro Display", "SF Pro Text",
            BlinkMacSystemFont, "Inter", "Segoe UI", system-ui, sans-serif;

          --evsc-bg-1: #f2f2f7;
          --evsc-bg-2: #e5e5ea;
          --evsc-surface: rgba(255, 255, 255, 0.62);
          --evsc-surface-strong: rgba(255, 255, 255, 0.78);
          --evsc-stroke: rgba(0, 0, 0, 0.07);
          --evsc-stroke-strong: rgba(0, 0, 0, 0.12);
          --evsc-fg: #1c1c1e;
          --evsc-fg-mid: rgba(60, 60, 67, 0.78);
          --evsc-fg-low: rgba(60, 60, 67, 0.55);

          --evsc-sys-blue: #007aff;
          --evsc-sys-green: #34c759;
          --evsc-sys-mint: #00c7be;
          --evsc-sys-teal: #30b0c7;
          --evsc-sys-indigo: #5856d6;
          --evsc-sys-purple: #af52de;
          --evsc-sys-pink: #ff2d55;
          --evsc-sys-red: #ff3b30;
          --evsc-sys-orange: #ff9500;
          --evsc-sys-yellow: #ffcc00;
          --evsc-sys-cyan: #32ade6;

          /* v1.11.0: Aurora accents — saturated, electric, used sparingly
             for "live" moments (active charging, today, priority change).
             Distinct from the muted Apple System palette which carries
             the rest of the surface. */
          --evsc-aurora-green: #00d35a;
          --evsc-aurora-cyan: #00d4ff;
          --evsc-aurora-violet: #b794ff;
          --evsc-aurora-amber: #ffb84d;

          --evsc-shadow-soft: 0 1px 2px rgba(0, 0, 0, 0.04),
            0 8px 24px rgba(0, 0, 0, 0.06);
          --evsc-shadow-lift: 0 1px 2px rgba(0, 0, 0, 0.06),
            0 12px 36px rgba(0, 0, 0, 0.1);
          --evsc-blur: saturate(180%) blur(40px);
          --evsc-blur-light: saturate(160%) blur(20px);
          --evsc-spring: cubic-bezier(0.32, 0.72, 0, 1);
          --evsc-radius: 22px;
          --evsc-radius-lg: 28px;
          --evsc-radius-pill: 999px;
        }

        @media (prefers-color-scheme: dark) {
          :host {
            --evsc-bg-1: #000000;
            --evsc-bg-2: #1c1c1e;
            --evsc-surface: rgba(28, 28, 30, 0.62);
            --evsc-surface-strong: rgba(44, 44, 46, 0.82);
            --evsc-stroke: rgba(255, 255, 255, 0.08);
            --evsc-stroke-strong: rgba(255, 255, 255, 0.16);
            --evsc-fg: #f2f2f7;
            --evsc-fg-mid: rgba(235, 235, 245, 0.6);
            --evsc-fg-low: rgba(235, 235, 245, 0.4);
            --evsc-shadow-soft: 0 1px 2px rgba(0, 0, 0, 0.4),
              0 12px 32px rgba(0, 0, 0, 0.5);
            --evsc-shadow-lift: 0 1px 2px rgba(0, 0, 0, 0.5),
              0 16px 48px rgba(0, 0, 0, 0.6);
          }
        }

        /* v1.10.4: explicit box-sizing reset for all descendants, including
           pseudo-elements. Shadow DOM does NOT inherit box-sizing from the
           light DOM, so this MUST be re-declared inside the shadow root. */
        *, *::before, *::after {
          box-sizing: border-box;
        }

        ha-card {
          /* v1.10.4: ha-card has implicit min-width (~280-360px) per HA
             community findings — must be overridden explicitly. */
          width: 100%;
          max-width: 100%;
          min-width: 0;
          overflow: hidden;
          border: 0 !important;
          border-radius: 0;
          background:
            radial-gradient(1200px 600px at 8% -10%, color-mix(in srgb, var(--evsc-sys-cyan) 22%, transparent), transparent 60%),
            radial-gradient(1000px 500px at 110% 10%, color-mix(in srgb, var(--evsc-sys-purple) 22%, transparent), transparent 60%),
            radial-gradient(900px 600px at 50% 110%, color-mix(in srgb, var(--evsc-sys-mint) 18%, transparent), transparent 70%),
            linear-gradient(160deg, var(--evsc-bg-1) 0%, var(--evsc-bg-2) 100%);
          box-shadow: none;
          color: var(--evsc-fg);
          font-family: var(--evsc-font);
          font-feature-settings: "tnum" on, "ss01" on, "cv01" on;
          -webkit-font-smoothing: antialiased;
          letter-spacing: -0.011em;
          min-height: 100vh;
        }

        .dashboard-shell {
          /* v1.11.1: bumped max-width for large monitors (27"/32"/4K)
             and made padding/gap scale fluidly with viewport. Stops
             expanding at 1180 px so the eye-line stays readable —
             classic "comfortable reading width" cap, à la Linear /
             Vercel / Stripe dashboards. Centered horizontally on
             everything wider. */
          position: relative;
          padding: clamp(14px, 2.6vw, 36px);
          display: grid;
          gap: clamp(14px, 1.6vw, 22px);
          max-width: 1180px;
          margin: 0 auto;
        }

        /* v1.11.0: aurora blobs — bigger, softer, slower. The radius
           shifts on a long sine + a complementary scale wobble give the
           impression of slow weather rather than a JS-driven loop. */
        .aurora {
          position: absolute;
          inset: auto;
          filter: blur(96px);
          opacity: 0.55;
          pointer-events: none;
          animation: floatGlow 28s ease-in-out infinite;
          will-change: transform, opacity;
        }

        .aurora-a {
          width: 440px;
          height: 440px;
          top: -120px;
          right: -100px;
          background: radial-gradient(circle,
            color-mix(in srgb, var(--evsc-aurora-cyan) 38%, transparent),
            transparent 65%);
        }

        .aurora-b {
          width: 520px;
          height: 520px;
          bottom: -8%;
          left: -160px;
          background: radial-gradient(circle,
            color-mix(in srgb, var(--evsc-aurora-violet) 32%, transparent),
            transparent 70%);
          animation-delay: -11s;
          animation-duration: 36s;
        }

        @keyframes floatGlow {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); opacity: 0.48; }
          50%      { transform: translate3d(28px, -22px, 0) scale(1.12); opacity: 0.72; }
        }

        .grain {
          position: absolute;
          inset: 0;
          pointer-events: none;
          opacity: 0.04;
          mix-blend-mode: overlay;
          background-image:
            radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.6) 0, transparent 14%),
            radial-gradient(circle at 80% 35%, rgba(255, 255, 255, 0.4) 0, transparent 10%),
            radial-gradient(circle at 40% 78%, rgba(255, 255, 255, 0.45) 0, transparent 12%);
        }

        .hero-card,
        .module-panel,
        .spotlight-panel,
        .diagnostic-panel {
          position: relative;
          z-index: 1;
        }

        /* ---------- Hero ---------- */
        .hero-card {
          display: grid;
          gap: 22px;
          grid-template-columns: minmax(220px, 280px) 1fr;
          align-items: center;
          padding: 26px 28px;
          border-radius: var(--evsc-radius-lg);
          background: var(--evsc-surface);
          border: 1px solid var(--evsc-stroke);
          backdrop-filter: var(--evsc-blur);
          -webkit-backdrop-filter: var(--evsc-blur);
          box-shadow: var(--evsc-shadow-lift),
            inset 0 1px 0 color-mix(in srgb, white 30%, transparent);
        }

        .hero-right {
          display: grid;
          gap: 18px;
          min-width: 0;
        }

        .hero-copy h1 {
          margin: 8px 0 6px;
          font-size: clamp(1.7rem, 3.4vw, 2.6rem);
          line-height: 1.02;
          letter-spacing: -0.035em;
          font-weight: 700;
          color: var(--evsc-fg);
        }

        .hero-copy p {
          margin: 0;
          max-width: 52ch;
          color: var(--evsc-fg-mid);
          line-height: 1.5;
          font-size: 0.92rem;
        }

        .hero-grid {
          display: grid;
          gap: 10px;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        }

        /* SOC ring stack — concentric activity-style rings (EV + Home). */
        .hero-ring {
          position: relative;
          width: 220px;
          height: 220px;
          margin: 0 auto;
          display: grid;
          place-items: center;
          isolation: isolate;
        }
        .hero-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); display: block; }
        .hero-ring circle { fill: none; stroke-linecap: round; }
        .hero-ring .ring-track { stroke: var(--evsc-stroke); }
        .hero-ring .ring-progress {
          transition: stroke-dashoffset 800ms var(--evsc-spring);
          filter: drop-shadow(0 0 6px color-mix(in srgb, currentColor 50%, transparent));
        }
        .hero-ring-center {
          position: absolute; inset: 0;
          display: flex; flex-direction: column;
          align-items: center; justify-content: center;
          gap: 2px; text-align: center;
        }
        .hero-ring-center .ring-headline {
          /* v1.11.2: reverted to system sans bold (was Instrument Serif
             italic in v1.11.0-1.11.1). User preferred the native look. */
          font-size: 2.2rem;
          font-weight: 700;
          letter-spacing: -0.04em;
          color: var(--evsc-fg);
        }
        .hero-ring-center .ring-sub {
          font-size: 0.78rem;
          color: var(--evsc-fg-mid);
          letter-spacing: 0.04em;
          text-transform: uppercase;
          font-weight: 600;
        }
        .hero-ring-legend {
          display: flex; gap: 16px; justify-content: center; margin-top: 12px;
        }
        .hero-ring-legend > div {
          display: flex; align-items: center; gap: 6px;
          font-size: 0.78rem;
          color: var(--evsc-fg-mid);
          font-variant-numeric: tabular-nums;
        }
        .ring-dot {
          width: 8px; height: 8px; border-radius: 50%;
          background: currentColor;
          box-shadow: 0 0 8px color-mix(in srgb, currentColor 60%, transparent);
        }

        .eyebrow,
        .kicker {
          /* v1.11.2: reverted to system sans (was JetBrains Mono in
             v1.11.0-1.11.1). */
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 0.7rem;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          color: var(--evsc-fg-low);
          font-weight: 600;
        }

        /* ---------- Generic glass cards ---------- */
        .metric-card,
        .target-chip,
        .diag-card,
        .control-card,
        .profile-card {
          border-radius: var(--evsc-radius);
          border: 1px solid var(--evsc-stroke);
          background: var(--evsc-surface);
          backdrop-filter: var(--evsc-blur-light);
          -webkit-backdrop-filter: var(--evsc-blur-light);
          box-shadow: var(--evsc-shadow-soft),
            inset 0 1px 0 color-mix(in srgb, white 25%, transparent);
          transition: transform 200ms var(--evsc-spring),
            box-shadow 200ms var(--evsc-spring);
        }

        .metric-card:hover,
        .control-card:hover,
        .target-chip:hover {
          transform: translateY(-1px);
          box-shadow: var(--evsc-shadow-lift),
            inset 0 1px 0 color-mix(in srgb, white 30%, transparent);
        }

        /* ---------- Metric cards (hero KPIs) ---------- */
        .metric-card {
          min-height: 92px;
          padding: 14px 16px;
          display: grid;
          gap: 6px;
          align-content: space-between;
          overflow: hidden;
          position: relative;
        }

        .metric-card::before {
          content: "";
          position: absolute;
          inset: 0;
          background: radial-gradient(120% 80% at 100% 0%, var(--evsc-tone, transparent), transparent 60%);
          opacity: 0.18;
          pointer-events: none;
        }

        .metric-card strong,
        .spotlight-main strong,
        .target-chip strong {
          /* v1.11.2: reverted to system sans (was JetBrains Mono in
             v1.11.0-1.11.1). Tabular numerics still on via ha-card. */
          font-size: clamp(1.2rem, 2vw, 1.7rem);
          line-height: 1.05;
          letter-spacing: -0.02em;
          font-weight: 700;
          color: var(--evsc-fg);
        }

        .metric-sub {
          color: var(--evsc-fg-mid);
          font-size: 0.8rem;
          font-weight: 500;
        }

        /* ---------- Spotlight (priority engine) ---------- */
        .spotlight-panel {
          display: grid;
          grid-template-columns: 1.4fr 1fr;
          gap: 16px;
        }

        .spotlight-main {
          padding: 22px 24px;
          border-radius: var(--evsc-radius-lg);
          background: var(--evsc-surface);
          border: 1px solid var(--evsc-stroke);
          backdrop-filter: var(--evsc-blur);
          -webkit-backdrop-filter: var(--evsc-blur);
          box-shadow: var(--evsc-shadow-soft),
            inset 0 1px 0 color-mix(in srgb, white 25%, transparent);
          display: grid;
          gap: 12px;
        }

        .spotlight-main strong {
          font-size: clamp(1.6rem, 3vw, 2.3rem);
          font-weight: 700;
        }

        .spotlight-side {
          display: grid;
          gap: 12px;
        }

        .target-chip,
        .diag-card {
          padding: 16px 18px;
          display: grid;
          gap: 8px;
        }

        .diag-grid {
          display: grid;
          gap: 8px;
          grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        }

        .diag-detail {
          display: grid;
          gap: 4px;
        }

        .diag-detail strong {
          font-size: 0.95rem;
          line-height: 1.35;
          letter-spacing: -0.015em;
          color: var(--evsc-fg);
          word-break: break-word;
          font-weight: 600;
        }

        /* ---------- Module panels (collapsible sections) ---------- */
        .module-grid {
          display: grid;
          gap: 16px;
          grid-template-columns: 1fr;
        }

        .module-panel {
          display: grid;
          gap: 14px;
          padding: 22px 24px;
          border-radius: var(--evsc-radius-lg);
          background: var(--evsc-surface);
          border: 1px solid var(--evsc-stroke);
          backdrop-filter: var(--evsc-blur);
          -webkit-backdrop-filter: var(--evsc-blur);
          box-shadow: var(--evsc-shadow-soft),
            inset 0 1px 0 color-mix(in srgb, white 25%, transparent);
        }

        .module-header {
          display: grid;
          gap: 4px;
          margin-bottom: 4px;
        }

        .module-header h2 {
          margin: 0;
          font-size: 1.35rem;
          line-height: 1.1;
          letter-spacing: -0.025em;
          font-weight: 700;
          color: var(--evsc-fg);
        }

        /* ---------- Control rows (switch / stepper / time / select) ---------- */
        .control-card,
        .profile-card {
          width: 100%;
          padding: 14px 16px;
          display: grid;
          gap: 12px;
          align-items: center;
        }

        .control-toggle {
          cursor: pointer;
          appearance: none;
          color: inherit;
          text-align: left;
          grid-template-columns: 1fr auto;
          background: var(--evsc-surface-strong);
          border: 1px solid var(--evsc-stroke);
        }

        .control-toggle.is-on {
          border-color: color-mix(in srgb, var(--evsc-sys-green) 45%, transparent);
          background: color-mix(in srgb, var(--evsc-sys-green) 8%, var(--evsc-surface-strong));
          box-shadow: 0 0 0 4px color-mix(in srgb, var(--evsc-sys-green) 12%, transparent),
            var(--evsc-shadow-soft);
        }

        .control-copy {
          display: grid;
          gap: 4px;
        }

        .control-label {
          font-size: 0.98rem;
          line-height: 1.2;
          font-weight: 600;
          color: var(--evsc-fg);
        }

        /* iOS-style toggle: 51×31 pill with 27px thumb */
        .switch-shell {
          justify-self: end;
          width: 51px;
          height: 31px;
          border-radius: var(--evsc-radius-pill);
          padding: 2px;
          background: color-mix(in srgb, var(--evsc-fg-low) 24%, transparent);
          transition: background 250ms var(--evsc-spring);
          flex-shrink: 0;
        }

        .switch-shell.is-on {
          background: var(--evsc-sys-green);
        }

        .switch-thumb {
          display: block;
          width: 27px;
          height: 27px;
          border-radius: 50%;
          background: #ffffff;
          transform: translateX(0);
          transition: transform 280ms var(--evsc-spring);
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06),
            0 3px 8px rgba(0, 0, 0, 0.15);
        }

        .switch-shell.is-on .switch-thumb {
          transform: translateX(20px);
        }

        .stepper-shell,
        .time-shell {
          display: grid;
          grid-template-columns: auto 1fr auto;
          gap: 8px;
          align-items: center;
        }

        .stepper-button,
        .profile-chip {
          cursor: pointer;
          appearance: none;
          border: 1px solid var(--evsc-stroke);
          color: var(--evsc-fg);
          border-radius: 14px;
          background: var(--evsc-surface-strong);
          font: inherit;
          font-weight: 600;
          transition: transform 160ms var(--evsc-spring),
            background 160ms ease, border-color 160ms ease;
        }

        .stepper-button {
          padding: 10px 12px;
          min-width: 44px;
          font-size: 1rem;
        }

        .stepper-button:hover,
        .profile-chip:hover {
          background: color-mix(in srgb, var(--evsc-sys-blue) 12%, var(--evsc-surface-strong));
          border-color: color-mix(in srgb, var(--evsc-sys-blue) 30%, var(--evsc-stroke));
        }

        .stepper-button:active,
        .profile-chip:active,
        .day-cell:active,
        .day-soc-cell:active {
          transform: scale(0.96);
        }

        .stepper-value,
        .time-value {
          /* v1.11.2: reverted to system sans (was JetBrains Mono in
             v1.11.0-1.11.1). Tabular nums still active via ha-card.
             align-items: center preserved from v1.10.5 stepper fix. */
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          min-height: 44px;
          padding: 0 14px;
          border-radius: 14px;
          background: var(--evsc-surface-strong);
          border: 1px solid var(--evsc-stroke);
          font-weight: 700;
          font-size: 1.1rem;
          letter-spacing: -0.02em;
          font-variant-numeric: tabular-nums;
          color: var(--evsc-fg);
        }

        .stepper-value small {
          color: var(--evsc-fg-mid);
          font-size: 0.8rem;
          font-weight: 500;
        }

        .profile-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .profile-chip {
          padding: 9px 14px;
          text-transform: capitalize;
          font-size: 0.92rem;
          border-radius: var(--evsc-radius-pill);
        }

        .profile-chip.selected {
          background: var(--evsc-sys-blue);
          color: #ffffff;
          border-color: var(--evsc-sys-blue);
          box-shadow: 0 4px 16px color-mix(in srgb, var(--evsc-sys-blue) 35%, transparent);
        }

        /* ---------- Weekly Day Grid (Car Ready) ---------- */
        .weekly-grid {
          padding: 14px;
          display: grid;
          gap: 12px;
        }

        .day-row {
          display: grid;
          grid-template-columns: repeat(7, minmax(0, 1fr));
          gap: 6px;
        }

        .day-cell {
          padding: 12px 4px;
          border-radius: 16px;
          border: 1px solid var(--evsc-stroke);
          background: var(--evsc-surface-strong);
          color: var(--evsc-fg-mid);
          cursor: pointer;
          display: grid;
          gap: 6px;
          justify-items: center;
          font: inherit;
          transition: all 200ms var(--evsc-spring);
        }

        .day-cell:hover {
          border-color: var(--evsc-stroke-strong);
          color: var(--evsc-fg);
        }

        .day-cell.is-on {
          background: var(--evsc-sys-green);
          border-color: var(--evsc-sys-green);
          color: #ffffff;
          box-shadow: 0 4px 14px color-mix(in srgb, var(--evsc-sys-green) 35%, transparent);
        }

        .day-initial,
        .day-initial-sm {
          font-weight: 600;
          letter-spacing: 0.04em;
        }

        .day-initial { font-size: 0.95rem; }
        .day-initial-sm { font-size: 0.78rem; opacity: 0.78; }

        .day-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: color-mix(in srgb, var(--evsc-fg-low) 60%, transparent);
          transition: background 200ms var(--evsc-spring);
        }

        .day-cell.is-on .day-dot {
          background: rgba(255, 255, 255, 0.95);
          box-shadow: 0 0 8px rgba(255, 255, 255, 0.6);
        }

        /* ---------- Daily SOC stepper grid ---------- */
        .daily-soc {
          padding: 14px;
          display: grid;
          gap: 12px;
        }

        .day-soc-row {
          display: grid;
          grid-template-columns: repeat(7, minmax(0, 1fr));
          gap: 6px;
        }

        .day-soc-cell {
          padding: 10px 4px;
          border-radius: 14px;
          border: 1px solid var(--evsc-stroke);
          background: var(--evsc-surface-strong);
          display: grid;
          gap: 6px;
          justify-items: center;
        }

        .day-soc-controls {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .micro-stepper {
          width: 22px;
          height: 22px;
          padding: 0;
          border-radius: 50%;
          border: 1px solid var(--evsc-stroke);
          background: var(--evsc-surface);
          color: var(--evsc-fg);
          cursor: pointer;
          font-size: 0.8rem;
          font-weight: 700;
          line-height: 1;
          transition: all 150ms var(--evsc-spring);
        }

        .micro-stepper:hover {
          background: var(--evsc-sys-blue);
          color: #ffffff;
          border-color: var(--evsc-sys-blue);
        }

        .day-soc-value {
          min-width: 38px;
          text-align: center;
          font-size: 0.82rem;
          font-variant-numeric: tabular-nums;
          font-weight: 600;
          color: var(--evsc-fg);
        }

        /* ---------- Info card (read-only) ---------- */
        .info-card {
          padding: 16px;
          display: grid;
          gap: 10px;
        }

        .info-value {
          font-family: ui-monospace, "SF Mono", Menlo, monospace;
          font-size: 0.78rem;
          color: var(--evsc-fg);
          word-break: break-all;
          padding: 10px 12px;
          border-radius: 12px;
          background: var(--evsc-surface-strong);
          border: 1px solid var(--evsc-stroke);
        }

        /* ---------- Diagnostics ---------- */
        .diagnostic-panel {
          display: grid;
          gap: 14px;
          grid-template-columns: 1fr;
        }

        .diag-card p {
          margin: 0;
          color: var(--evsc-fg-mid);
          line-height: 1.5;
          white-space: pre-wrap;
        }

        .boot-state,
        .muted {
          padding: 24px;
          color: var(--evsc-fg-mid);
          font-size: 0.95rem;
        }

        /* Tonal accents — pre-assigned to each hero metric via tone-* class */
        .tone-cyan   { --evsc-tone: var(--evsc-sys-cyan);   color: var(--evsc-sys-cyan); }
        .tone-violet { --evsc-tone: var(--evsc-sys-purple); color: var(--evsc-sys-purple); }
        .tone-lime   { --evsc-tone: var(--evsc-sys-green);  color: var(--evsc-sys-green); }
        .tone-rose   { --evsc-tone: var(--evsc-sys-pink);   color: var(--evsc-sys-pink); }
        .tone-amber  { --evsc-tone: var(--evsc-sys-orange); color: var(--evsc-sys-orange); }
        .tone-teal   { --evsc-tone: var(--evsc-sys-teal);   color: var(--evsc-sys-teal); }

        /* Priority state pill — v1.11.2: reverted to system sans (was
           JetBrains Mono uppercase in v1.11.0-1.11.1). Slow pulse halo
           kept. */
        .priority-pill {
          display: inline-flex; align-items: center; gap: 8px;
          padding: 6px 12px;
          border-radius: var(--evsc-radius-pill);
          font-size: 0.85rem;
          font-weight: 600;
          background: var(--evsc-surface-strong);
          border: 1px solid var(--evsc-stroke);
          color: var(--evsc-fg);
        }
        .priority-pill::before {
          content: ""; width: 7px; height: 7px; border-radius: 50%;
          background: currentColor;
          box-shadow: 0 0 10px currentColor;
          animation: evsc-pulse-slow 3.2s ease-in-out infinite;
        }
        @keyframes evsc-pulse-slow {
          0%, 100% { opacity: 1; box-shadow: 0 0 10px currentColor; }
          50%      { opacity: 0.55; box-shadow: 0 0 16px currentColor; }
        }
        .priority-pill.state-ev      { color: var(--evsc-sys-green);  }
        .priority-pill.state-home    { color: var(--evsc-sys-blue);   }
        .priority-pill.state-ev_free { color: var(--evsc-sys-purple); }

        /* Charging indicator with pulse */
        @keyframes evsc-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%      { opacity: 0.55; transform: scale(0.85); }
        }
        .charging-pulse {
          /* v1.11.0: aurora-green for a more vivid "live" feel.
             Slightly larger glow halo than before. */
          display: inline-block;
          width: 9px; height: 9px;
          border-radius: 50%;
          background: var(--evsc-aurora-green);
          box-shadow: 0 0 14px var(--evsc-aurora-green),
                      0 0 6px var(--evsc-aurora-green);
          animation: evsc-pulse 1.4s ease-in-out infinite;
          margin-right: 8px;
          vertical-align: middle;
        }

        /* v1.10.2: entrance animations disabled.
           Reason: the dashboard re-renders on every Home Assistant state
           update (SOC tick, solar reading, status change, …). With
           innerHTML replacement, the DOM is rebuilt and CSS entrance
           animations replay from scratch — causing a visible flicker
           every few seconds. Keeping only the aurora floatGlow on the
           ::before pseudo-element (which survives innerHTML swaps) and
           the live charging-pulse dot. */
        @keyframes evsc-fade-in {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        /* Reduced motion */
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after {
            animation-duration: 0.01ms !important;
            transition-duration: 0.01ms !important;
          }
        }

        /* Responsive */
        @media (max-width: 980px) {
          .hero-card { grid-template-columns: 1fr; }
          .spotlight-panel,
          .module-grid,
          .diagnostic-panel {
            grid-template-columns: 1fr;
          }
          .hero-ring { width: 180px; height: 180px; }
          .dashboard-shell { padding: 16px; }
        }

        @media (max-width: 540px) {
          .hero-card { padding: 18px 18px; }
          .module-panel { padding: 18px 18px; }
          .spotlight-main { padding: 18px 18px; }
          .hero-ring { width: 160px; height: 160px; }
          .hero-ring-center .ring-headline { font-size: 1.8rem; }
        }

        /* ============================================================
         * v1.10.0 — Split-view (Dashboard / Settings) additions
         * ============================================================ */

        /* Top tab bar */
        .evsc-tabs {
          display: inline-flex;
          align-items: center;
          padding: 4px;
          background: var(--evsc-surface);
          backdrop-filter: var(--evsc-blur);
          -webkit-backdrop-filter: var(--evsc-blur);
          border: 1px solid var(--evsc-stroke);
          border-radius: 999px;
          box-shadow: var(--evsc-shadow-soft);
          margin: 0 auto 8px;
          width: max-content;
        }
        .evsc-tab {
          appearance: none;
          border: none;
          background: transparent;
          color: var(--evsc-fg-mid);
          font: inherit;
          font-size: 13px;
          font-weight: 600;
          letter-spacing: -0.005em;
          padding: 9px 18px;
          border-radius: 999px;
          cursor: pointer;
          transition: all 280ms var(--evsc-spring);
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .evsc-tab.active {
          background: var(--evsc-surface-strong);
          color: var(--evsc-fg);
          box-shadow: 0 1px 0 rgba(255, 255, 255, 0.5) inset,
                      0 6px 14px -6px rgba(15, 17, 40, 0.18);
        }
        .evsc-tab-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--evsc-sys-green);
          box-shadow: 0 0 8px var(--evsc-sys-green);
        }

        /* Two-column dashboard grid */
        /* v1.11.1: vertical stack at every viewport. Was previously a
           2-column grid (hero | weekly) which compressed both cards on
           any width below ~1200 px — the hero h1 wrapped letter-by-letter
           and the 4 metric tiles became 4 stacked rows of unreadable
           pseudo-columns. Going full-width-per-card mirrors the way
           Linear / Vercel / Stripe lay out content-dense dashboards:
           each card gets to use its full eye-line, no inter-card
           competition for horizontal space. */
        .evsc-dash-grid {
          display: flex;
          flex-direction: column;
          gap: clamp(14px, 1.6vw, 22px);
        }
        .evsc-dash-grid > * {
          min-width: 0;
        }
        .evsc-dash-grid .evsc-stack {
          /* the two original "columns" now stack as siblings inside the
             single flex column — same render output, no DOM change. */
          width: 100%;
        }
        .evsc-stack {
          display: flex;
          flex-direction: column;
          gap: 18px;
        }
        .evsc-card {
          position: relative;
          background: var(--evsc-surface);
          backdrop-filter: var(--evsc-blur);
          -webkit-backdrop-filter: var(--evsc-blur);
          border: 1px solid var(--evsc-stroke);
          border-radius: var(--evsc-radius-lg);
          box-shadow: var(--evsc-shadow-soft);
          padding: 22px;
          overflow: hidden;
        }
        .evsc-card-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 14px;
        }
        .evsc-card-title {
          font-size: 13px;
          font-weight: 600;
          color: var(--evsc-fg-low);
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }
        .evsc-card-eyebrow {
          font-size: 11px;
          color: var(--evsc-fg-low);
          font-weight: 500;
        }
        .evsc-stack-inner {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        /* Revised hero — status pill BELOW the ring, EV label inside */
        .evsc-hero-v2 {
          background: var(--evsc-surface);
          backdrop-filter: var(--evsc-blur);
          -webkit-backdrop-filter: var(--evsc-blur);
          border: 1px solid var(--evsc-stroke);
          border-radius: var(--evsc-radius-lg);
          box-shadow: var(--evsc-shadow-soft);
          padding: 26px;
          display: grid;
          /* v1.10.4: minmax(0, …) on both tracks prevents the auto track
             from blowing past viewport. */
          grid-template-columns: minmax(0, auto) minmax(0, 1fr);
          gap: 26px;
          align-items: center;
        }
        .evsc-hero-v2 > * {
          min-width: 0;
        }
        @media (max-width: 720px) {
          .evsc-hero-v2 {
            grid-template-columns: minmax(0, 1fr);
            text-align: left;
            gap: 22px;
            padding: 22px;
          }
        }
        .evsc-hero-body h1 {
          /* v1.11.2: reverted to system sans bold (was Instrument Serif
             italic in v1.11.0-1.11.1). Conservative clamp kept from
             v1.11.1 so the title never blows out on wide hero bodies. */
          margin: 8px 0 4px;
          font-size: clamp(20px, 1.8vw, 26px);
          font-weight: 700;
          letter-spacing: -0.02em;
          color: var(--evsc-fg);
        }
        .evsc-hero-sub {
          color: var(--evsc-fg-mid);
          font-size: 13px;
          line-height: 1.55;
          margin: 0 0 20px;
          max-width: 42ch;
        }
        .evsc-metric-row {
          /* v1.11.1: adaptive grid — was hard-coded 2×2 since v1.10.4.
             Now uses auto-fit with a 140 px floor so the row gracefully
             becomes:
               · 4 columns when the hero body is ≥ 620 px wide (large
                 monitors with the new full-width hero)
               · 2 columns when the body is between ~300 and 620 px
                 (typical tablet / desktop)
               · 1 column below ~300 px (very narrow mobile)
             No flash of broken layout regardless of viewport. */
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 10px;
        }
        .evsc-metric-row > * {
          min-width: 0;
        }

        /* v1.10.1: center the metric-card content for visual symmetry.
           v1.10.4: also override legacy min-height: 92px which was making
           the tiles unnecessarily tall on mobile, and prevent text overflow. */
        .evsc-metric-row .metric-card {
          text-align: center;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 6px;
          min-height: 0;
          min-width: 0;
          padding: 12px 14px;
          word-break: break-word;
          overflow-wrap: anywhere;
        }
        .evsc-metric-row .metric-card .eyebrow,
        .evsc-metric-row .metric-card .metric-sub,
        .evsc-metric-row .metric-card strong {
          display: block;
          width: 100%;
        }

        /* v1.10.5: hero ring center is now flex-centered (see base rule).
           Sub label keeps the wide-tracking, lowered-opacity treatment. */
        .evsc-hero-v2 .hero-ring-center .ring-sub {
          margin-top: 2px;
          letter-spacing: 0.16em;
          opacity: 0.65;
        }

        /* v1.10.2: Boost group — merge boost toggle + amperage + target SOC
           into one visual card. Internal items lose their own surface and
           rely on the parent group's background + dividers. */
        .evsc-boost-group {
          background: var(--evsc-surface-strong);
          border: 1px solid var(--evsc-stroke);
          border-radius: var(--evsc-radius);
          box-shadow: var(--evsc-shadow-soft);
          overflow: hidden;
          backdrop-filter: var(--evsc-blur-light);
          -webkit-backdrop-filter: var(--evsc-blur-light);
        }
        .evsc-boost-group > .control-card,
        .evsc-boost-group > .control-toggle {
          background: transparent !important;
          border: none !important;
          border-radius: 0 !important;
          box-shadow: none !important;
          margin: 0 !important;
          backdrop-filter: none !important;
          -webkit-backdrop-filter: none !important;
        }
        .evsc-boost-subitems {
          border-top: 1px solid var(--evsc-stroke);
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
          gap: 0;
        }
        .evsc-boost-subitems > * {
          min-width: 0;
        }
        .evsc-boost-subitems .control-card {
          background: transparent !important;
          border: none !important;
          border-radius: 0 !important;
          box-shadow: none !important;
          margin: 0 !important;
          backdrop-filter: none !important;
          -webkit-backdrop-filter: none !important;
        }
        .evsc-boost-subitems .control-card:first-child {
          border-right: 1px solid var(--evsc-stroke);
        }
        @media (max-width: 600px) {
          .evsc-boost-subitems {
            grid-template-columns: 1fr;
          }
          .evsc-boost-subitems .control-card:first-child {
            border-right: none;
            border-bottom: 1px solid var(--evsc-stroke);
          }
        }

        /* v1.10.4: hero ring container — explicit styling so the SVG
           scales fluidly with the viewport. .hero-ring-wrap was previously
           unstyled (root cause #2 of the mobile overflow). */
        .evsc-hero-v2 .hero-ring-wrap {
          width: 100%;
          max-width: 100%;
          min-width: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
        }
        .evsc-hero-v2 .hero-ring {
          width: min(220px, 60vw);
          aspect-ratio: 1 / 1;
          height: auto;
          max-width: 100%;
          min-width: 0;
          margin: 0;
        }
        .evsc-hero-v2 .hero-ring svg {
          width: 100%;
          height: 100%;
          display: block;
        }

        /* v1.11.1: responsive breakpoint ladder.
             ≤600 px → hero collapses to 1 column (ring on top, body below)
             ≤480 px → compact metric tiles, smaller fonts, padding shrink
           (dash-grid is now always 1-col — see .evsc-dash-grid above.) */
        @media (max-width: 600px) {
          .dashboard-shell {
            padding: 14px !important;
            max-width: 100% !important;
          }
          .evsc-hero-v2 {
            grid-template-columns: minmax(0, 1fr);
            text-align: center;
            gap: 16px;
            padding: 18px;
          }
          .evsc-hero-body {
            text-align: left;
          }
          .evsc-hero-v2 .hero-ring {
            width: min(200px, 55vw);
          }
        }
        @media (max-width: 480px) {
          .dashboard-shell {
            padding: 12px !important;
          }
          .evsc-hero-v2 .hero-ring {
            width: min(180px, 50vw);
          }
          /* Metric tiles stay 2×2 but compact — user explicit request. */
          .evsc-metric-row {
            gap: 8px;
          }
          .evsc-metric-row .metric-card {
            padding: 10px 8px;
            gap: 4px;
          }
          .evsc-metric-row .metric-card .eyebrow {
            font-size: 9px;
          }
          .evsc-metric-row .metric-card strong {
            font-size: 15px;
          }
          .evsc-metric-row .metric-card .metric-sub {
            font-size: 10px;
          }
          .evsc-card,
          .evsc-weekly,
          .evsc-night-card,
          .evsc-settings-hero,
          .evsc-acc {
            padding: 14px;
            border-radius: 18px;
          }
          .evsc-acc-head {
            padding: 14px;
          }
          .evsc-acc-body-inner {
            padding: 4px 14px 14px;
          }
          .evsc-wp-grid {
            grid-template-columns: 42px repeat(7, minmax(0, 1fr));
            gap: 3px;
          }
          .evsc-wp-soc {
            font-size: 11px;
          }
          .evsc-wp-mini {
            width: 14px;
            height: 14px;
            font-size: 11px;
          }
          .evsc-tabs {
            margin: 0 auto 6px;
          }
          .evsc-tab {
            padding: 8px 14px;
            font-size: 12px;
          }
        }

        /* Belt-and-braces overflow guard. The :host already declares
           overflow-x: hidden in the reset block above; .dashboard-shell
           also gets it here so any pathological child (e.g. a long
           friendly_name with no spaces) is clipped, not scrolled. */
        .dashboard-shell {
          overflow-x: hidden;
        }

        /* Weekly Planner card */
        .evsc-weekly {
          background: var(--evsc-surface);
          backdrop-filter: var(--evsc-blur);
          -webkit-backdrop-filter: var(--evsc-blur);
          border: 1px solid var(--evsc-stroke);
          border-radius: var(--evsc-radius-lg);
          box-shadow: var(--evsc-shadow-soft);
          padding: 22px;
        }
        .evsc-wp-head { margin-bottom: 14px; }
        .evsc-wp-eyebrow {
          display: block;
          font-size: 13px;
          font-weight: 600;
          color: var(--evsc-fg-low);
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }
        .evsc-wp-sub {
          display: block;
          font-size: 11px;
          color: var(--evsc-fg-low);
          margin-top: 2px;
        }
        .evsc-wp-grid {
          display: grid;
          grid-template-columns: 70px repeat(7, minmax(0, 1fr));
          gap: 6px;
          align-items: center;
        }
        .evsc-wp-grid > * {
          min-width: 0;
        }
        @media (max-width: 600px) {
          .evsc-wp-grid { grid-template-columns: 54px repeat(7, minmax(0, 1fr)); }
        }
        .evsc-wp-header {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: var(--evsc-fg-low);
          font-weight: 700;
          text-align: center;
          padding: 4px 0;
        }
        .evsc-wp-header.today {
          color: var(--evsc-sys-blue);
        }
        .evsc-wp-row-label {
          font-size: 12px;
          color: var(--evsc-fg-mid);
          font-weight: 600;
          padding-right: 6px;
        }
        .evsc-wp-cell {
          padding: 6px 2px;
          border-radius: 12px;
          background: color-mix(in srgb, var(--evsc-fg) 4%, transparent);
          border: 1px solid var(--evsc-stroke);
          text-align: center;
        }
        .evsc-wp-cell.today {
          background: color-mix(in srgb, var(--evsc-sys-blue) 14%, transparent);
          border-color: color-mix(in srgb, var(--evsc-sys-blue) 35%, transparent);
        }

        /* v1.11.0: mobile day-card stack — hidden on desktop, shown ≤768px.
           Each card is a self-contained editorial spread for one day. */
        .evsc-wp-mobile { display: none; }
        .evsc-wp-day-card {
          padding: 16px 18px;
          border-radius: var(--evsc-radius);
          background: var(--evsc-surface);
          border: 1px solid var(--evsc-stroke);
          backdrop-filter: var(--evsc-blur-light);
          -webkit-backdrop-filter: var(--evsc-blur-light);
          box-shadow: var(--evsc-shadow-soft);
          transition: transform 240ms var(--evsc-spring),
                      box-shadow 240ms var(--evsc-spring);
        }
        .evsc-wp-day-card.today {
          border-color: color-mix(in srgb, var(--evsc-sys-blue) 40%, var(--evsc-stroke));
          box-shadow: var(--evsc-shadow-soft),
                      0 0 0 1px color-mix(in srgb, var(--evsc-sys-blue) 22%, transparent),
                      0 12px 30px color-mix(in srgb, var(--evsc-sys-blue) 14%, transparent);
        }
        .evsc-wp-day-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding-bottom: 12px;
          margin-bottom: 12px;
          border-bottom: 1px solid color-mix(in srgb, var(--evsc-fg) 6%, transparent);
        }
        .evsc-wp-day-name-block {
          display: flex;
          align-items: baseline;
          gap: 10px;
          min-width: 0;
        }
        .evsc-wp-day-name {
          /* v1.11.2: reverted to system sans bold (was Instrument Serif
             italic 22px in v1.11.0-1.11.1). Still the card's anchor —
             just native. */
          font-size: 18px;
          font-weight: 700;
          line-height: 1;
          color: var(--evsc-fg);
          letter-spacing: -0.02em;
        }
        .evsc-wp-day-card.today .evsc-wp-day-name {
          color: var(--evsc-sys-blue);
        }
        .evsc-wp-today-badge {
          /* v1.11.2: reverted to system sans (was JetBrains Mono caps). */
          display: inline-block;
          padding: 3px 9px;
          border-radius: var(--evsc-radius-pill);
          background: var(--evsc-sys-blue);
          color: #fff;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          box-shadow: 0 4px 12px color-mix(in srgb, var(--evsc-sys-blue) 35%, transparent);
        }
        .evsc-wp-day-body {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .evsc-wp-day-row {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          align-items: center;
          gap: 12px;
        }
        .evsc-wp-day-kind {
          /* v1.11.2: reverted to system sans (was JetBrains Mono caps). */
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--evsc-fg-mid);
        }
        .evsc-wp-day-row .evsc-wp-kind-ev   { color: var(--evsc-sys-blue);  }
        .evsc-wp-day-row .evsc-wp-kind-home { color: var(--evsc-sys-green); }
        .evsc-wp-soc-row {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 2px;
        }
        .evsc-wp-soc {
          min-width: 28px;
          font-size: 13px;
          font-weight: 700;
          font-variant-numeric: tabular-nums;
          letter-spacing: -0.01em;
        }
        .evsc-wp-soc.ev { color: var(--evsc-sys-blue); }
        .evsc-wp-soc.home { color: var(--evsc-sys-green); }
        .evsc-wp-soc small {
          font-size: 9px;
          color: var(--evsc-fg-low);
          font-weight: 600;
          margin-left: 1px;
        }
        .evsc-wp-mini {
          appearance: none;
          border: none;
          background: transparent;
          width: 18px;
          height: 18px;
          border-radius: 5px;
          font-size: 13px;
          font-weight: 600;
          color: var(--evsc-fg-mid);
          cursor: pointer;
          line-height: 1;
        }
        .evsc-wp-mini:hover {
          background: color-mix(in srgb, var(--evsc-fg) 8%, transparent);
        }
        .evsc-wp-tog {
          appearance: none;
          width: 38px;
          height: 22px;
          border: none;
          border-radius: 999px;
          background: rgba(120, 120, 128, 0.32);
          position: relative;
          cursor: pointer;
          transition: background 240ms var(--evsc-spring);
          margin: 0 auto;
          padding: 0;
        }
        .evsc-wp-tog::after {
          content: "";
          width: 18px;
          height: 18px;
          background: #fff;
          border-radius: 50%;
          position: absolute;
          top: 2px;
          left: 2px;
          transition: transform 240ms var(--evsc-spring);
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
        }
        .evsc-wp-tog.on { background: var(--evsc-sys-purple); }
        .evsc-wp-tog.on::after { transform: translateX(16px); }
        .evsc-wp-info {
          margin-top: 14px;
          padding: 12px 14px;
          border-radius: 12px;
          background: color-mix(in srgb, var(--evsc-fg) 5%, transparent);
          border: 1px solid var(--evsc-stroke);
          font-size: 12px;
          line-height: 1.5;
          color: var(--evsc-fg-mid);
        }

        /* v1.11.0: at ≤768 px the desktop 8-column grid is swapped out for
           the day-grouped mobile card stack. Two separate DOM payloads
           rendered, only one is visible. Cleaner than reflowing one grid
           into multiple breakpoints. */
        @media (max-width: 768px) {
          .evsc-weekly { padding: 18px; }
          .evsc-wp-grid { display: none; }
          .evsc-wp-mobile {
            display: flex;
            flex-direction: column;
            gap: 10px;
          }
          .evsc-wp-day-card .evsc-wp-soc-row {
            justify-content: flex-end;
            gap: 6px;
          }
          .evsc-wp-day-card .evsc-wp-mini {
            width: 30px;
            height: 30px;
            font-size: 17px;
            background: color-mix(in srgb, var(--evsc-fg) 6%, transparent);
            border-radius: 9px;
            font-weight: 500;
          }
          .evsc-wp-day-card .evsc-wp-mini:hover {
            background: color-mix(in srgb, var(--evsc-sys-blue) 18%, transparent);
            color: var(--evsc-sys-blue);
          }
          .evsc-wp-day-card .evsc-wp-soc {
            /* v1.11.2: reverted to system sans. */
            font-size: 16px;
            font-weight: 700;
            min-width: 42px;
            text-align: center;
            font-variant-numeric: tabular-nums;
          }
          .evsc-wp-day-card .evsc-wp-soc small {
            font-size: 10px;
            margin-left: 2px;
            opacity: 0.7;
          }
          .evsc-wp-day-card .evsc-wp-tog {
            margin: 0;
          }
        }

        /* Night Smart Charge — bento illustration card */
        .evsc-night-card {
          background:
            radial-gradient(80% 60% at 100% 0%, color-mix(in srgb, var(--evsc-sys-indigo) 20%, transparent), transparent 60%),
            var(--evsc-surface);
          backdrop-filter: var(--evsc-blur);
          -webkit-backdrop-filter: var(--evsc-blur);
          border: 1px solid var(--evsc-stroke);
          border-radius: var(--evsc-radius-lg);
          box-shadow: var(--evsc-shadow-soft);
          padding: 22px;
        }
        .evsc-night-head { margin-bottom: 16px; }
        .evsc-night-eyebrow {
          display: block;
          font-size: 13px;
          color: var(--evsc-sys-purple);
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }
        .evsc-night-sub {
          display: block;
          font-size: 11px;
          color: var(--evsc-fg-low);
          margin-top: 2px;
        }
        .evsc-night-illu {
          height: 90px;
          background: radial-gradient(60% 100% at 50% 100%, color-mix(in srgb, var(--evsc-sys-purple) 35%, transparent), transparent 70%);
          border-radius: 14px;
          position: relative;
          margin-bottom: 16px;
          overflow: hidden;
        }
        .evsc-night-moon {
          position: absolute;
          top: 18px;
          left: 50%;
          transform: translateX(-50%);
          width: 44px;
          height: 44px;
          border-radius: 50%;
          background: linear-gradient(140deg, #fff, #d1d5e0);
          box-shadow: 0 8px 24px rgba(175, 82, 222, 0.6);
        }
        .evsc-night-moon::after {
          content: "";
          position: absolute;
          inset: 4px;
          background: radial-gradient(ellipse 60% 60% at 75% 35%, rgba(175, 82, 222, 0.20), transparent 60%);
          border-radius: 50%;
        }
        .evsc-night-illu::before,
        .evsc-night-illu::after {
          content: "";
          position: absolute;
          border-radius: 50%;
          background: var(--evsc-fg);
          opacity: 0.5;
        }
        .evsc-night-illu::before { width: 3px; height: 3px; top: 22px; left: 30%; }
        .evsc-night-illu::after  { width: 2px; height: 2px; top: 38px; right: 25%; }
        .evsc-night-times {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
          gap: 10px;
          margin-bottom: 14px;
        }
        .evsc-night-time {
          background: color-mix(in srgb, var(--evsc-fg) 5%, transparent);
          border: 1px solid var(--evsc-stroke);
          border-radius: 12px;
          padding: 10px 12px;
        }
        .evsc-night-time .lbl {
          /* v1.11.2: reverted to system sans (was JetBrains Mono). */
          font-size: 9px;
          color: var(--evsc-fg-low);
          text-transform: uppercase;
          letter-spacing: 0.08em;
          font-weight: 700;
        }
        .evsc-night-time .vv {
          /* v1.11.2: reverted to system sans bold (was Instrument Serif
             italic 32px in v1.11.0-1.11.1). */
          font-size: 22px;
          font-weight: 800;
          letter-spacing: -0.02em;
          margin-top: 2px;
          font-variant-numeric: tabular-nums;
          color: var(--evsc-fg);
        }
        .evsc-night-enable {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 14px;
          background: color-mix(in srgb, var(--evsc-fg) 5%, transparent);
          border: 1px solid var(--evsc-stroke);
          border-radius: 12px;
        }
        .evsc-night-enable .t {
          font-size: 13px;
          font-weight: 700;
          letter-spacing: -0.01em;
        }
        .evsc-night-enable .s {
          font-size: 11px;
          color: var(--evsc-fg-low);
          margin-top: 2px;
        }

        /* Settings view — hero + accordion list */
        .evsc-settings-hero {
          background: var(--evsc-surface);
          backdrop-filter: var(--evsc-blur);
          -webkit-backdrop-filter: var(--evsc-blur);
          border: 1px solid var(--evsc-stroke);
          border-radius: var(--evsc-radius-lg);
          padding: 26px 28px;
          margin-bottom: 14px;
          box-shadow: var(--evsc-shadow-soft);
        }
        .evsc-settings-hero h2 {
          margin: 0;
          font-size: 26px;
          font-weight: 800;
          letter-spacing: -0.02em;
        }
        .evsc-settings-hero p {
          margin: 6px 0 0;
          color: var(--evsc-fg-mid);
          font-size: 14px;
          line-height: 1.55;
          max-width: 640px;
        }
        .evsc-settings-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .evsc-acc {
          background: var(--evsc-surface);
          backdrop-filter: var(--evsc-blur);
          -webkit-backdrop-filter: var(--evsc-blur);
          border: 1px solid var(--evsc-stroke);
          border-radius: var(--evsc-radius-lg);
          box-shadow: var(--evsc-shadow-soft);
          overflow: hidden;
        }
        .evsc-acc.open {
          box-shadow: var(--evsc-shadow-soft),
                      0 0 0 1px color-mix(in srgb, var(--evsc-sys-blue) 18%, transparent);
        }
        .evsc-acc-head {
          display: grid;
          grid-template-columns: 44px 1fr auto auto;
          gap: 14px;
          align-items: center;
          padding: 18px 22px;
          cursor: pointer;
          transition: background 180ms ease;
        }
        .evsc-acc-head:hover {
          background: color-mix(in srgb, var(--evsc-fg) 4%, transparent);
        }
        @media (max-width: 640px) {
          .evsc-acc-head {
            padding: 16px;
            grid-template-columns: 40px 1fr auto auto;
            gap: 12px;
          }
        }
        .evsc-acc-ico {
          width: 44px;
          height: 44px;
          border-radius: 13px;
          display: grid;
          place-items: center;
          color: #fff;
          font-size: 18px;
          flex-shrink: 0;
        }
        .evsc-acc-ico.sun   { background: linear-gradient(135deg, var(--evsc-sys-orange), var(--evsc-sys-yellow)); }
        .evsc-acc-ico.moon  { background: linear-gradient(135deg, var(--evsc-sys-indigo), var(--evsc-sys-purple)); }
        .evsc-acc-ico.bat   { background: linear-gradient(135deg, var(--evsc-sys-green), var(--evsc-sys-teal)); }
        .evsc-acc-ico.hyb   { background: linear-gradient(135deg, var(--evsc-sys-teal), var(--evsc-sys-blue)); }
        .evsc-acc-ico.boost { background: linear-gradient(135deg, var(--evsc-sys-orange), var(--evsc-sys-pink)); }
        .evsc-acc-ico.bell  { background: linear-gradient(135deg, var(--evsc-sys-pink), var(--evsc-sys-orange)); }
        .evsc-acc-ico.log   { background: linear-gradient(135deg, var(--evsc-fg-mid), var(--evsc-fg-low)); }
        .evsc-acc-title h3 {
          margin: 0;
          font-size: 16px;
          font-weight: 700;
          letter-spacing: -0.015em;
        }
        .evsc-acc-title p {
          margin: 2px 0 0;
          font-size: 12px;
          color: var(--evsc-fg-low);
        }
        .evsc-acc-count {
          font-size: 11px;
          color: var(--evsc-fg-low);
          font-weight: 600;
          font-variant-numeric: tabular-nums;
          background: color-mix(in srgb, var(--evsc-fg) 6%, transparent);
          padding: 4px 9px;
          border-radius: 999px;
        }
        .evsc-acc-chev {
          width: 22px;
          height: 22px;
          color: var(--evsc-fg-low);
          transition: transform 280ms var(--evsc-spring);
        }
        .evsc-acc.open .evsc-acc-chev {
          transform: rotate(90deg);
          color: var(--evsc-sys-blue);
        }
        .evsc-acc-body {
          max-height: 0;
          overflow: hidden;
          transition: max-height 380ms var(--evsc-spring);
        }
        .evsc-acc.open .evsc-acc-body { max-height: 2400px; }
        .evsc-acc-body-inner {
          padding: 4px 28px 22px;
          border-top: 1px solid var(--evsc-stroke);
        }
        @media (max-width: 640px) {
          .evsc-acc-body-inner { padding: 4px 18px 18px; }
        }
        .evsc-set-item {
          padding: 18px 0;
          border-bottom: 1px solid var(--evsc-stroke);
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 18px;
          align-items: start;
        }
        .evsc-set-item:last-child { border-bottom: none; }
        @media (max-width: 520px) {
          .evsc-set-item { grid-template-columns: 1fr; }
        }
        .evsc-set-item h4 {
          margin: 0 0 4px;
          font-size: 15px;
          font-weight: 600;
          letter-spacing: -0.01em;
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
        }
        .evsc-set-key {
          font-family: ui-monospace, "SF Mono", Menlo, monospace;
          font-size: 10px;
          background: color-mix(in srgb, var(--evsc-fg) 6%, transparent);
          color: var(--evsc-fg-low);
          padding: 2px 6px;
          border-radius: 5px;
          font-weight: 500;
        }
        .evsc-set-item p {
          margin: 0;
          font-size: 13px;
          color: var(--evsc-fg-mid);
          line-height: 1.55;
          max-width: 580px;
        }
        .evsc-set-hint {
          margin-top: 8px;
          font-size: 11px;
          color: var(--evsc-fg-low);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .evsc-set-toggle {
          appearance: none;
          width: 51px;
          height: 31px;
          border: none;
          border-radius: 999px;
          background: rgba(120, 120, 128, 0.32);
          position: relative;
          cursor: pointer;
          transition: background 280ms var(--evsc-spring);
          padding: 0;
          flex-shrink: 0;
        }
        .evsc-set-toggle::after {
          content: "";
          width: 27px;
          height: 27px;
          border-radius: 50%;
          background: #fff;
          position: absolute;
          top: 2px;
          left: 2px;
          transition: transform 280ms var(--evsc-spring);
          box-shadow: 0 3px 8px rgba(0, 0, 0, 0.18);
        }
        .evsc-set-toggle.on { background: var(--evsc-sys-green); }
        .evsc-set-toggle.on.violet { background: var(--evsc-sys-purple); }
        .evsc-set-toggle.on::after { transform: translateX(20px); }
        .evsc-set-stepper {
          display: inline-flex;
          align-items: center;
          padding: 2px;
          background: color-mix(in srgb, var(--evsc-fg) 8%, transparent);
          border-radius: 10px;
        }
        .evsc-set-step {
          appearance: none;
          width: 28px;
          height: 28px;
          border: none;
          background: transparent;
          font-size: 15px;
          color: var(--evsc-fg);
          cursor: pointer;
          font-weight: 600;
          border-radius: 8px;
        }
        .evsc-set-step:hover {
          background: color-mix(in srgb, var(--evsc-fg) 6%, transparent);
        }
        .evsc-set-val {
          min-width: 46px;
          text-align: center;
          font-variant-numeric: tabular-nums;
          font-weight: 600;
          font-size: 14px;
        }
        .evsc-set-val small {
          color: var(--evsc-fg-low);
          font-weight: 500;
          font-size: 11px;
          margin-left: 2px;
        }
        .evsc-set-info {
          font-size: 12px;
          color: var(--evsc-fg-low);
          font-family: ui-monospace, "SF Mono", Menlo, monospace;
          max-width: 220px;
          word-break: break-all;
          text-align: right;
        }
    `;
  }
}

customElements.define("ev-smart-charger-dashboard", EvSmartChargerDashboard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ev-smart-charger-dashboard",
  name: "EV Smart Charger Dashboard",
  description: "Animated native control surface for the EV Smart Charger integration.",
});
