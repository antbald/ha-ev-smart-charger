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
    if (!config?.entity_prefix) {
      throw new Error("`entity_prefix` is required");
    }

    this._config = {
      title: config.title,
      entity_prefix: config.entity_prefix,
      charging_power_entity: config.charging_power_entity,
      ev_soc_entity: config.ev_soc_entity,
      home_battery_soc_entity: config.home_battery_soc_entity,
      solar_power_entity: config.solar_power_entity,
      grid_import_entity: config.grid_import_entity,
      current_entity: config.current_entity,
    };

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this.shadowRoot) {
      this.render();
    }
  }

  getCardSize() {
    return 12;
  }

  _entityId(key) {
    const [domain, suffix] = DOMAIN_SUFFIXES[key];
    return `${domain}.${this._config.entity_prefix}_${suffix}`;
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

    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="dashboard-shell">
          <div class="aurora aurora-a"></div>
          <div class="aurora aurora-b"></div>
          <div class="grain"></div>

          <header class="hero-card">
            <div class="hero-copy">
              <span class="eyebrow">${this._t("hero.eyebrow")}</span>
              <h1>${this._config.title || this._t("title.default")}</h1>
              <p>${this._t("hero.description")}</p>
            </div>
            <div class="hero-grid">
              ${this._renderMetric(this._t("metric.charging_power"), chargingPower, "cyan", this._labelFor(this._config.charging_power_entity, this._t("metric.live_power")))}
              ${this._renderMetric(this._t("metric.ev_soc"), evSoc, "violet", this._labelFor(this._config.ev_soc_entity, this._t("metric.vehicle_battery")))}
              ${this._renderMetric(this._t("metric.home_battery"), homeBatterySoc, "lime", this._labelFor(this._config.home_battery_soc_entity, this._t("metric.storage_reserve")))}
              ${this._renderMetric(this._t("metric.grid_import"), gridImport, "rose", this._labelFor(this._config.grid_import_entity, this._t("metric.import_threshold")))}
              ${this._renderMetric(this._t("metric.solar_power"), solarPower, "amber", this._labelFor(this._config.solar_power_entity, this._t("metric.pv_feed")))}
              ${this._renderMetric(this._t("metric.charge_current"), chargerCurrent, "teal", this._labelFor(this._config.current_entity, this._t("metric.wallbox_current")))}
            </div>
          </header>

          <section class="spotlight-panel">
            <div class="spotlight-main">
              <span class="eyebrow">${this._t("spotlight.priority_engine")}</span>
              <strong>${priorityState?.state || this._t("common.unavailable")}</strong>
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
        :host {
          display: block;
        }

        * {
          box-sizing: border-box;
        }

        ha-card {
          overflow: hidden;
          border: 0;
          border-radius: 32px;
          background:
            radial-gradient(circle at top right, rgba(49, 216, 255, 0.18), transparent 36%),
            radial-gradient(circle at left center, rgba(122, 58, 255, 0.22), transparent 30%),
            linear-gradient(145deg, #060816 0%, #0b1022 42%, #111323 100%);
          box-shadow:
            0 32px 80px rgba(0, 0, 0, 0.42),
            inset 0 1px 0 rgba(255, 255, 255, 0.05);
          color: #f5f7ff;
        }

        .dashboard-shell {
          position: relative;
          padding: 28px;
          display: grid;
          gap: 22px;
          min-height: 400px;
        }

        .aurora {
          position: absolute;
          inset: auto;
          filter: blur(36px);
          opacity: 0.9;
          pointer-events: none;
          animation: floatGlow 9s ease-in-out infinite;
        }

        .aurora-a {
          width: 180px;
          height: 180px;
          top: -40px;
          right: -30px;
          background: radial-gradient(circle, rgba(26, 229, 255, 0.28), transparent 65%);
        }

        .aurora-b {
          width: 220px;
          height: 220px;
          bottom: 10%;
          left: -40px;
          background: radial-gradient(circle, rgba(169, 88, 255, 0.22), transparent 70%);
          animation-delay: -3s;
        }

        .grain {
          position: absolute;
          inset: 0;
          pointer-events: none;
          opacity: 0.08;
          background-image:
            radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.35) 0, transparent 18%),
            radial-gradient(circle at 80% 35%, rgba(255, 255, 255, 0.28) 0, transparent 12%),
            radial-gradient(circle at 40% 75%, rgba(255, 255, 255, 0.22) 0, transparent 14%);
          mix-blend-mode: screen;
        }

        .hero-card,
        .module-panel,
        .spotlight-panel,
        .diagnostic-panel {
          position: relative;
          z-index: 1;
        }

        .hero-card {
          display: grid;
          gap: 18px;
          grid-template-columns: 1fr;
          padding: 24px;
          border-radius: 28px;
          background: linear-gradient(135deg, rgba(14, 18, 41, 0.84), rgba(16, 29, 58, 0.72));
          border: 1px solid rgba(139, 162, 255, 0.16);
          backdrop-filter: blur(14px);
        }

        .hero-copy h1 {
          margin: 6px 0 10px;
          font-size: clamp(2rem, 4vw, 3.4rem);
          line-height: 0.95;
          letter-spacing: -0.04em;
        }

        .hero-copy p {
          margin: 0;
          max-width: 44ch;
          color: rgba(223, 229, 255, 0.8);
          line-height: 1.55;
        }

        .hero-grid {
          display: grid;
          gap: 12px;
          grid-template-columns: 1fr;
        }

        .eyebrow,
        .kicker {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 0.73rem;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: rgba(196, 207, 255, 0.66);
        }

        .metric-card,
        .target-chip,
        .diag-card,
        .control-card,
        .profile-card {
          border-radius: 22px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          background: linear-gradient(180deg, rgba(17, 24, 44, 0.92), rgba(10, 14, 28, 0.94));
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
        }

        .metric-card {
          min-height: 108px;
          padding: 16px;
          display: grid;
          gap: 10px;
          align-content: space-between;
          overflow: hidden;
          position: relative;
        }

        .metric-card::after {
          content: "";
          position: absolute;
          inset: auto -18% -40% auto;
          width: 90px;
          height: 90px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(255, 255, 255, 0.12), transparent 65%);
          opacity: 0.8;
        }

        .metric-card strong,
        .spotlight-main strong,
        .target-chip strong {
          font-size: clamp(1.15rem, 2vw, 1.8rem);
          line-height: 1;
          letter-spacing: -0.03em;
        }

        .metric-sub {
          color: rgba(214, 221, 255, 0.76);
          font-size: 0.82rem;
        }

        .spotlight-panel {
          display: grid;
          grid-template-columns: 1fr;
          gap: 16px;
        }

        .spotlight-main {
          padding: 22px;
          border-radius: 26px;
          background:
            linear-gradient(135deg, rgba(0, 197, 255, 0.14), rgba(134, 77, 255, 0.08)),
            rgba(7, 13, 29, 0.9);
          border: 1px solid rgba(76, 214, 255, 0.18);
          display: grid;
          gap: 12px;
        }

        .spotlight-side {
          display: grid;
          gap: 16px;
        }

        .target-chip,
        .diag-card {
          padding: 18px;
          display: grid;
          gap: 10px;
        }

        .diag-grid {
          display: grid;
          gap: 10px;
          grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        }

        .diag-detail {
          display: grid;
          gap: 4px;
        }

        .diag-detail strong {
          font-size: 0.92rem;
          line-height: 1.35;
          letter-spacing: -0.02em;
          color: rgba(245, 247, 255, 0.92);
          word-break: break-word;
        }

        .module-grid {
          display: grid;
          gap: 18px;
          grid-template-columns: 1fr;
        }

        .module-panel {
          display: grid;
          gap: 14px;
          padding: 20px;
          border-radius: 28px;
          background:
            linear-gradient(180deg, rgba(12, 17, 35, 0.92), rgba(8, 12, 24, 0.96)),
            rgba(8, 12, 24, 0.9);
          border: 1px solid rgba(255, 255, 255, 0.06);
        }

        .module-header {
          display: grid;
          gap: 6px;
          margin-bottom: 2px;
        }

        .module-header h2 {
          margin: 0;
          font-size: 1.45rem;
          line-height: 1;
          letter-spacing: -0.03em;
        }

        .control-card,
        .profile-card {
          width: 100%;
          padding: 14px 16px;
          display: grid;
          gap: 14px;
        }

        .control-toggle {
          cursor: pointer;
          appearance: none;
          color: inherit;
          text-align: left;
          background:
            linear-gradient(180deg, rgba(17, 24, 44, 0.94), rgba(10, 14, 28, 0.98));
        }

        .control-toggle.is-on {
          border-color: rgba(80, 228, 255, 0.26);
          box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.04),
            0 0 0 1px rgba(80, 228, 255, 0.05),
            0 12px 24px rgba(0, 0, 0, 0.18);
        }

        .control-copy {
          display: grid;
          gap: 6px;
        }

        .control-label {
          font-size: 1rem;
          line-height: 1.2;
          font-weight: 700;
          color: #f6f8ff;
        }

        .switch-shell {
          justify-self: end;
          width: 66px;
          height: 36px;
          border-radius: 999px;
          padding: 4px;
          background: rgba(255, 255, 255, 0.12);
          transition: background 180ms ease;
        }

        .switch-shell.is-on {
          background: rgba(30, 201, 255, 0.36);
        }

        .switch-thumb {
          display: block;
          width: 28px;
          height: 28px;
          border-radius: 50%;
          background: white;
          transform: translateX(0);
          transition: transform 180ms ease;
          box-shadow: 0 6px 16px rgba(0, 0, 0, 0.24);
        }

        .switch-shell.is-on .switch-thumb {
          transform: translateX(30px);
        }

        .stepper-shell,
        .time-shell {
          display: grid;
          grid-template-columns: auto 1fr auto;
          gap: 10px;
          align-items: center;
        }

        .stepper-button,
        .profile-chip {
          cursor: pointer;
          appearance: none;
          border: 0;
          color: inherit;
          border-radius: 16px;
          background: rgba(255, 255, 255, 0.08);
          font: inherit;
          transition: transform 160ms ease, background 160ms ease, box-shadow 160ms ease;
        }

        .stepper-button {
          padding: 12px 14px;
          font-weight: 700;
          min-width: 56px;
        }

        .stepper-button:hover,
        .profile-chip:hover {
          transform: translateY(-1px);
          background: rgba(255, 255, 255, 0.13);
        }

        .stepper-value,
        .time-value {
          display: flex;
          align-items: baseline;
          justify-content: center;
          gap: 6px;
          min-height: 48px;
          padding: 0 14px;
          border-radius: 16px;
          background: rgba(255, 255, 255, 0.05);
          font-weight: 800;
          font-size: 1.15rem;
          letter-spacing: -0.02em;
        }

        .stepper-value small {
          color: rgba(214, 221, 255, 0.68);
          font-size: 0.8rem;
          font-weight: 600;
        }

        .profile-row {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
        }

        .profile-chip {
          padding: 10px 14px;
          text-transform: capitalize;
        }

        .profile-chip.selected {
          background: linear-gradient(135deg, rgba(18, 203, 255, 0.35), rgba(130, 92, 255, 0.3));
          box-shadow: 0 10px 24px rgba(34, 132, 255, 0.18);
        }

        /* Weekly grid (Car Ready) */
        .weekly-grid {
          padding: 16px;
          display: grid;
          gap: 12px;
        }

        .day-row {
          display: grid;
          grid-template-columns: repeat(7, minmax(0, 1fr));
          gap: 6px;
        }

        .day-cell {
          padding: 10px 4px;
          border-radius: 12px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          background: rgba(8, 12, 24, 0.7);
          color: rgba(225, 232, 255, 0.84);
          cursor: pointer;
          display: grid;
          gap: 6px;
          justify-items: center;
          font: inherit;
          transition: all 0.15s ease;
        }

        .day-cell:hover {
          background: rgba(16, 22, 40, 0.95);
          border-color: rgba(170, 200, 255, 0.32);
        }

        .day-cell.is-on {
          background: linear-gradient(135deg, rgba(157, 92, 255, 0.34), rgba(122, 58, 255, 0.18));
          border-color: rgba(157, 92, 255, 0.55);
          color: #fff;
        }

        .day-initial,
        .day-initial-sm {
          font-weight: 600;
          letter-spacing: 0.05em;
        }

        .day-initial { font-size: 0.95rem; }
        .day-initial-sm { font-size: 0.78rem; opacity: 0.78; }

        .day-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: rgba(120, 130, 150, 0.4);
          transition: background 0.15s ease;
        }

        .day-dot.is-on {
          background: #56ec86;
          box-shadow: 0 0 10px rgba(86, 236, 134, 0.6);
        }

        /* Daily SOC grid */
        .daily-soc {
          padding: 16px;
          display: grid;
          gap: 12px;
        }

        .day-soc-row {
          display: grid;
          grid-template-columns: repeat(7, minmax(0, 1fr));
          gap: 6px;
        }

        .day-soc-cell {
          padding: 8px 4px;
          border-radius: 10px;
          border: 1px solid rgba(255, 255, 255, 0.06);
          background: rgba(8, 12, 24, 0.55);
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
          border: 1px solid rgba(170, 200, 255, 0.18);
          background: rgba(16, 22, 40, 0.85);
          color: #fff;
          cursor: pointer;
          font-size: 0.8rem;
          line-height: 1;
        }

        .micro-stepper:hover {
          background: rgba(34, 132, 255, 0.18);
          border-color: rgba(34, 132, 255, 0.42);
        }

        .day-soc-value {
          min-width: 38px;
          text-align: center;
          font-size: 0.78rem;
          font-variant-numeric: tabular-nums;
          color: rgba(245, 247, 255, 0.92);
        }

        /* Info card (read-only display, e.g. log file path) */
        .info-card {
          padding: 16px;
          display: grid;
          gap: 10px;
        }

        .info-value {
          font-family: ui-monospace, "SF Mono", Menlo, monospace;
          font-size: 0.78rem;
          color: rgba(225, 232, 255, 0.88);
          word-break: break-all;
          padding: 8px 10px;
          border-radius: 10px;
          background: rgba(8, 12, 24, 0.65);
          border: 1px solid rgba(255, 255, 255, 0.04);
        }

        .diagnostic-panel {
          display: grid;
          gap: 16px;
          grid-template-columns: 1fr;
        }

        .diag-card p {
          margin: 0;
          color: rgba(225, 232, 255, 0.84);
          line-height: 1.55;
          white-space: pre-wrap;
        }

        .boot-state,
        .muted {
          padding: 24px;
          color: rgba(225, 232, 255, 0.72);
        }

        .tone-cyan { box-shadow: inset 0 0 0 1px rgba(0, 224, 255, 0.05); }
        .tone-violet { box-shadow: inset 0 0 0 1px rgba(157, 92, 255, 0.05); }
        .tone-lime { box-shadow: inset 0 0 0 1px rgba(86, 236, 134, 0.05); }
        .tone-rose { box-shadow: inset 0 0 0 1px rgba(255, 88, 133, 0.05); }
        .tone-amber { box-shadow: inset 0 0 0 1px rgba(255, 188, 40, 0.05); }
        .tone-teal { box-shadow: inset 0 0 0 1px rgba(22, 228, 194, 0.05); }

        @keyframes floatGlow {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
          50% { transform: translate3d(0, -10px, 0) scale(1.04); }
        }

        @media (max-width: 980px) {
          .hero-card,
          .spotlight-panel,
          .module-grid,
          .diagnostic-panel {
            grid-template-columns: 1fr;
          }

          .dashboard-shell {
            padding: 18px;
          }

          .hero-grid {
            grid-template-columns: 1fr;
          }
        }
      </style>
    `;

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
