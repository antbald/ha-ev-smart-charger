// EV Smart Charger Dashboard — Lovelace custom card
// Updated for integration v1.8.0 (Hybrid Inverter Mode + missing entities from
// v1.3.13 through v1.7.0). Exposes all 64 helper entities (51 in PV-only mode).
const DEFAULT_TITLE = "EV Smart Charger";
const SUPPORTED_PROFILES = ["manual", "solar_surplus"];
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const DAY_INITIALS_BY_LOCALE = {
  en: ["M", "T", "W", "T", "F", "S", "S"],
  it: ["L", "M", "M", "G", "V", "S", "D"],
  nl: ["M", "D", "W", "D", "V", "Z", "Z"],
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
    "metric.ev_soc": "EV State Of Charge",
    "metric.vehicle_battery": "Vehicle battery",
    "metric.home_battery": "Home Battery",
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
    "metric.ev_soc": "Stato di carica EV",
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
    "metric.ev_soc": "EV-laadstatus",
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
    const [domain] = entityId.split(".");
    await this._hass.callService(domain, "toggle", { entity_id: entityId });
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
    await this._setNumber(entityId, next);
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

    let headline = "—";
    let sub = this._t("metric.ev_soc");
    if (isCharging && chargingPowerObj) {
      const unit = chargingPowerObj.attributes?.unit_of_measurement || "";
      headline = `${chargingPowerObj.state}${unit ? " " + unit : ""}`;
      sub = this._t("metric.charging_power");
    } else if (evPct != null) {
      headline = `${Math.round(evPct)}%`;
    }

    const inner = homePct != null
      ? `
        <circle class="ring-track" cx="110" cy="110" r="${rInner}" stroke-width="13"/>
        <circle class="ring-progress" cx="110" cy="110" r="${rInner}" stroke-width="13"
                style="color: var(--evsc-sys-purple); stroke: var(--evsc-sys-purple);"
                stroke-dasharray="${cInner}" stroke-dashoffset="${cInner * (1 - homeFrac)}"/>`
      : "";

    const legendHome = homePct != null
      ? `<div style="color: var(--evsc-sys-purple);"><span class="ring-dot"></span><span>${this._t("metric.home_battery")} ${Math.round(homePct)}%</span></div>`
      : "";

    const chargingDot = isCharging
      ? `<span class="charging-pulse" title="${this._t("metric.charging_power")}"></span>`
      : "";

    return `
      <div class="hero-ring-wrap">
        <div class="hero-ring">
          <svg viewBox="0 0 220 220" aria-hidden="true">
            <circle class="ring-track" cx="110" cy="110" r="${rOuter}" stroke-width="13"/>
            <circle class="ring-progress" cx="110" cy="110" r="${rOuter}" stroke-width="13"
                    style="color: var(--evsc-sys-green); stroke: var(--evsc-sys-green);"
                    stroke-dasharray="${cOuter}" stroke-dashoffset="${cOuter * (1 - evFrac)}"/>
            ${inner}
          </svg>
          <div class="hero-ring-center">
            <div class="ring-headline">${chargingDot}${headline}</div>
            <div class="ring-sub">${sub}</div>
          </div>
        </div>
        <div class="hero-ring-legend">
          <div style="color: var(--evsc-sys-green);"><span class="ring-dot"></span><span>${this._t("metric.ev_soc")}${evPct != null ? " " + Math.round(evPct) + "%" : ""}</span></div>
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
          <span class="stepper-value">${value}<small>${unit}</small></span>
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
          <span class="time-value">${value.slice(0, 5)}</span>
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

  _renderMetric(label, value, tone, sublabel) {
    return `
      <div class="metric-card tone-${tone}">
        <span class="eyebrow">${label}</span>
        <strong>${value}</strong>
        <span class="metric-sub">${sublabel}</span>
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
            <span class="day-soc-value">${value}%</span>
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

    const chargingPower = this._displayValue(this._config.charging_power_entity, this._t("fallback.live_feed_optional"));
    const evSoc = this._displayValue(this._config.ev_soc_entity, this._t("fallback.ev_soc_entity"));
    const homeBatterySoc = this._displayValue(
      this._config.home_battery_soc_entity,
      this._t("fallback.home_battery_soc_entity"),
    );
    const solarPower = this._displayValue(this._config.solar_power_entity, this._t("fallback.solar_power_entity"));
    const gridImport = this._displayValue(this._config.grid_import_entity, this._t("fallback.grid_import_entity"));
    const chargerCurrent = this._displayValue(this._config.current_entity, this._t("fallback.current_entity"));

    const html = `
      <ha-card>
        <div class="dashboard-shell">
          <div class="aurora aurora-a"></div>
          <div class="aurora aurora-b"></div>
          <div class="grain"></div>

          <header class="hero-card">
            ${this._renderHeroRing()}
            <div class="hero-right">
              <div class="hero-copy">
                <span class="eyebrow">${this._t("hero.eyebrow")}</span>
                <h1>${this._config.title || this._t("title.default")}</h1>
                <p>${this._t("hero.description")}</p>
              </div>
              <div class="hero-grid">
                ${this._renderMetric(this._t("metric.solar_power"), solarPower, "amber", this._labelFor(this._config.solar_power_entity, this._t("metric.pv_feed")))}
                ${this._renderMetric(this._t("metric.grid_import"), gridImport, "rose", this._labelFor(this._config.grid_import_entity, this._t("metric.import_threshold")))}
                ${this._renderMetric(this._t("metric.charge_current"), chargerCurrent, "teal", this._labelFor(this._config.current_entity, this._t("metric.wallbox_current")))}
                ${this._renderMetric(this._t("metric.charging_power"), chargingPower, "cyan", this._labelFor(this._config.charging_power_entity, this._t("metric.live_power")))}
              </div>
            </div>
          </header>

          <section class="spotlight-panel">
            <div class="spotlight-main">
              <span class="eyebrow">${this._t("spotlight.priority_engine")}</span>
              ${this._renderPriorityPill(priorityState)}
              <span class="metric-sub">${this._t("spotlight.description")}</span>
            </div>
            <div class="spotlight-side">
              <div class="target-chip">
                <span class="eyebrow">${this._t("spotlight.today_ev_target")}</span>
                <strong>${todayEvTarget?.state || "--"}</strong>
              </div>
              <div class="target-chip">
                <span class="eyebrow">${this._t("spotlight.today_home_target")}</span>
                <strong>${todayHomeTarget?.state || "--"}</strong>
              </div>
            </div>
          </section>

          <section class="module-grid">
            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.override_layer")}</span>
                <h2>${this._t("module.main_controls")}</h2>
              </div>
              ${this._renderToggle(forceChargeId, this._t("control.force_charge"), this._t("control.override_all"), "rose")}
              ${this._renderSelectChips(chargingProfileId, this._t("control.charging_profile"), this._t("control.mode_strategy"))}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.fast_override")}</span>
                <h2>${this._t("module.boost_charge")}</h2>
              </div>
              ${this._renderToggle(boostEnabledId, this._t("control.boost_session"), this._t("control.high_priority"), "amber")}
              ${this._renderStepper(boostAmperageId, this._t("control.boost_amperage"), this._t("control.output"), "amber")}
              ${this._renderStepper(boostTargetSocId, this._t("control.boost_target_soc"), this._t("control.auto_stop"), "lime")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.daily_window")}</span>
                <h2>${this._t("module.boost_schedule")}</h2>
              </div>
              ${this._renderToggle(boostScheduleEnabledId, this._t("control.schedule_boost"), this._t("control.daily_schedule"), "amber")}
              ${this._renderTimeControl(boostScheduleStartId, this._t("control.schedule_start"), this._t("control.schedule"))}
              ${this._renderTimeControl(boostScheduleEndId, this._t("control.schedule_end"), this._t("control.schedule"))}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.forecast_driven")}</span>
                <h2>${this._t("module.night_smart_charge")}</h2>
              </div>
              ${this._renderToggle(nightEnabledId, this._t("control.enable_night_smart_charge"), this._t("control.night_window"), "violet")}
              ${this._renderToggle(preserveHomeBatteryId, this._t("control.preserve_home_battery"), this._t("control.skip_when_not_required"), "lime")}
              ${this._renderTimeControl(nightTimeId, this._t("control.start_time"), this._t("control.schedule"))}
              ${this._renderTimeControl(carReadyTimeId, this._t("control.car_ready_time"), this._t("control.morning_deadline"))}
              ${this._renderStepper(minSolarForecastId, this._t("control.min_solar_forecast"), this._t("control.tomorrow_threshold"), "cyan")}
              ${this._renderStepper(nightAmperageId, this._t("control.night_charge_amperage"), this._t("control.overnight_current"), "teal")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.weekly_planner")}</span>
                <h2>${this._t("module.car_ready")}</h2>
              </div>
              ${this._renderDayToggleGrid(this._t("module.car_ready"), this._t("control.car_ready_grid_hint"), "carReady", "violet")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.target_planner")}</span>
                <h2>${this._t("module.daily_targets")}</h2>
              </div>
              ${this._renderDaySocGrid(this._t("control.ev_targets_label"), this._t("spotlight.today_ev_target"), "evMinSoc", "cyan")}
              ${this._renderDaySocGrid(this._t("control.home_targets_label"), this._t("spotlight.today_home_target"), "homeMinSoc", "lime")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.adaptive_curve")}</span>
                <h2>${this._t("module.solar_surplus")}</h2>
              </div>
              ${this._renderStepper(checkIntervalId, this._t("control.check_interval"), this._t("control.polling"), "cyan")}
              ${this._renderStepper(gridImportThresholdId, this._t("control.grid_import_threshold"), this._t("control.clamp"), "rose")}
              ${this._renderStepper(gridImportDelayId, this._t("control.grid_import_delay"), this._t("control.debounce"), "violet")}
              ${this._renderStepper(surplusDropDelayId, this._t("control.surplus_drop_delay"), this._t("control.cloud_filter"), "amber")}
              ${this._renderStepper(solarMaxAmperageId, this._t("control.solar_max_amperage"), this._t("control.wallbox_ceiling"), "teal")}
              ${this._renderToggle(useHomeBatteryId, this._t("control.use_home_battery"), this._t("control.fallback_reserve"), "lime")}
              ${this._renderStepper(homeBatteryMinSocId, this._t("control.home_battery_min_soc"), this._t("control.reserve_floor"), "lime")}
              ${this._renderStepper(batterySupportAmperageId, this._t("control.battery_support_amperage"), this._t("control.assist_output"), "teal")}
              ${this._renderStepper(batterySupportSunsetBufferId, this._t("control.battery_support_sunset_buffer"), this._t("control.protect_evening_battery"), "rose")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.curtailment_discovery")}</span>
                <h2>${this._t("module.hybrid_inverter")}</h2>
              </div>
              ${this._renderToggle(hybridModeId, this._t("control.hybrid_enabled"), this._t("control.opt_in_probing"), "teal")}
              ${this._renderStepper(hybridBatteryFullThresholdId, this._t("control.hybrid_battery_full_threshold"), this._t("control.curtailment_trigger"), "lime")}
              ${this._renderStepper(hybridProbeDurationId, this._t("control.hybrid_probe_duration"), this._t("control.test_window"), "cyan")}
              ${this._renderStepper(hybridMaxImportDurationId, this._t("control.hybrid_max_import_duration"), this._t("control.backoff_window"), "amber")}
              ${this._renderStepper(hybridMaxFailedProbesId, this._t("control.hybrid_max_failed_probes"), this._t("control.sliding_window"), "rose")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.safety_nets")}</span>
                <h2>${this._t("module.protection_layer")}</h2>
              </div>
              ${this._renderToggle(priorityBalancerId, this._t("control.priority_balancer"), this._t("control.target_arbitration"), "cyan")}
              ${this._renderToggle(smartBlockerId, this._t("control.smart_charger_blocker"), this._t("control.nighttime_lockout"), "rose")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.mobile_alerts")}</span>
                <h2>${this._t("module.notifications")}</h2>
              </div>
              ${this._renderToggle(notifySmartBlockerId, this._t("control.notify_smart_blocker"), this._t("control.alert_channel"), "rose")}
              ${this._renderToggle(notifyPriorityBalancerId, this._t("control.notify_priority_balancer"), this._t("control.alert_channel"), "cyan")}
              ${this._renderToggle(notifyNightChargeId, this._t("control.notify_night_charge"), this._t("control.alert_channel"), "violet")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">${this._t("module.observability")}</span>
                <h2>${this._t("module.logging")}</h2>
              </div>
              ${this._renderToggle(traceLoggingId, this._t("control.trace_logging"), this._t("control.deep_diagnostics"), "amber")}
              ${this._renderToggle(enableFileLoggingId, this._t("control.enable_file_logging"), this._t("control.daily_log_files"), "teal")}
              ${this._renderInfoCard(this._t("log.file_path_label"), logFilePath?.state || this._t("common.unavailable"), this._t("control.daily_log_files"), "teal")}
            </section>
          </section>

          ${this._renderDiagnostics(diagnostic, solarDiagnostic, hybridDiagnostic, cachedEvSoc)}
        </div>
      </ha-card>
      <style>
        /* ============================================================
         * EV Smart Charger — Liquid Glass iOS 18
         * Palette: Apple System colors. Adaptive light/dark via
         * prefers-color-scheme + HA --primary-background-color hooks.
         * ============================================================ */
        :host {
          display: block;
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

        * {
          box-sizing: border-box;
        }

        ha-card {
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
          position: relative;
          padding: clamp(16px, 3vw, 40px);
          display: grid;
          gap: 18px;
          max-width: 1080px;
          margin: 0 auto;
        }

        /* Soft accent blobs floating in the background. Subtle and slow. */
        .aurora {
          position: absolute;
          inset: auto;
          filter: blur(80px);
          opacity: 0.55;
          pointer-events: none;
          animation: floatGlow 18s ease-in-out infinite;
        }

        .aurora-a {
          width: 360px;
          height: 360px;
          top: -90px;
          right: -80px;
          background: radial-gradient(circle, color-mix(in srgb, var(--evsc-sys-cyan) 35%, transparent), transparent 65%);
        }

        .aurora-b {
          width: 420px;
          height: 420px;
          bottom: 4%;
          left: -120px;
          background: radial-gradient(circle, color-mix(in srgb, var(--evsc-sys-purple) 30%, transparent), transparent 70%);
          animation-delay: -7s;
        }

        @keyframes floatGlow {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); opacity: 0.5; }
          50%      { transform: translate3d(20px, -16px, 0) scale(1.08); opacity: 0.7; }
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
          position: absolute; inset: 0; display: grid; place-items: center; gap: 2px;
          text-align: center;
        }
        .hero-ring-center .ring-headline {
          font-size: 2.2rem; font-weight: 700; letter-spacing: -0.04em;
          color: var(--evsc-fg);
        }
        .hero-ring-center .ring-sub {
          font-size: 0.78rem; color: var(--evsc-fg-mid);
          letter-spacing: 0.04em; text-transform: uppercase; font-weight: 600;
        }
        .hero-ring-legend {
          display: flex; gap: 16px; justify-content: center; margin-top: 12px;
        }
        .hero-ring-legend > div {
          display: flex; align-items: center; gap: 6px;
          font-size: 0.78rem; color: var(--evsc-fg-mid);
        }
        .ring-dot {
          width: 8px; height: 8px; border-radius: 50%;
          background: currentColor;
          box-shadow: 0 0 8px color-mix(in srgb, currentColor 60%, transparent);
        }

        .eyebrow,
        .kicker {
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
          display: flex;
          align-items: baseline;
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

        /* Priority state pill */
        .priority-pill {
          display: inline-flex; align-items: center; gap: 8px;
          padding: 6px 12px;
          border-radius: var(--evsc-radius-pill);
          font-size: 0.85rem; font-weight: 600;
          background: var(--evsc-surface-strong);
          border: 1px solid var(--evsc-stroke);
          color: var(--evsc-fg);
        }
        .priority-pill::before {
          content: ""; width: 8px; height: 8px; border-radius: 50%;
          background: currentColor;
          box-shadow: 0 0 8px currentColor;
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
          display: inline-block; width: 8px; height: 8px; border-radius: 50%;
          background: var(--evsc-sys-green);
          box-shadow: 0 0 12px var(--evsc-sys-green);
          animation: evsc-pulse 1.4s ease-in-out infinite;
          margin-right: 6px;
          vertical-align: middle;
        }

        /* Section entrance animation */
        @keyframes evsc-fade-in {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .hero-card,
        .spotlight-panel,
        .module-panel,
        .diagnostic-panel > * {
          animation: evsc-fade-in 500ms var(--evsc-spring) backwards;
        }
        .hero-card { animation-delay: 40ms; }
        .spotlight-panel { animation-delay: 100ms; }
        .module-grid .module-panel:nth-child(1) { animation-delay: 160ms; }
        .module-grid .module-panel:nth-child(2) { animation-delay: 200ms; }
        .module-grid .module-panel:nth-child(3) { animation-delay: 240ms; }
        .module-grid .module-panel:nth-child(4) { animation-delay: 280ms; }
        .module-grid .module-panel:nth-child(5) { animation-delay: 320ms; }
        .module-grid .module-panel:nth-child(n+6) { animation-delay: 360ms; }
        .diagnostic-panel > *:nth-child(2) { animation-delay: 80ms; }
        .diagnostic-panel > *:nth-child(3) { animation-delay: 120ms; }

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
      </style>
    `;

    // Anti-flicker guard: HA calls `set hass(hass)` on every state change in
    // the entire system, which triggers render(). Without this guard, we
    // rewrite the entire shadow DOM each time → visible flicker. With it,
    // we only repaint when the HTML output actually changed.
    const newHash = this._cheapHash(html);
    if (newHash === this._lastRenderHash) {
      return;
    }
    this._lastRenderHash = newHash;
    this.shadowRoot.innerHTML = html;

    this._bindEvents();
  }
}

customElements.define("ev-smart-charger-dashboard", EvSmartChargerDashboard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ev-smart-charger-dashboard",
  name: "EV Smart Charger Dashboard",
  description: "Animated native control surface for the EV Smart Charger integration.",
});
