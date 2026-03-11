"""Runtime localization helpers for EV Smart Charger."""
from __future__ import annotations

from homeassistant.core import HomeAssistant

DEFAULT_RUNTIME_LANGUAGE = "en"

RUNTIME_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "common.error_label": "Error",
        "common.not_available_short": "N/A",
        "common.reason_label": "Reason",
        "common.time_label": "Time",
        "mode.battery": "Home Battery",
        "mode.grid": "Grid",
        "priority.EV": "EV",
        "priority.EV_Free": "EV Free",
        "priority.Home": "Home",
        "mobile.smart_blocker.message": (
            "EV charging stopped because it is outside the configured charging window\n\n"
            "Reason: {reason}\n"
            "Time: {time}"
        ),
        "mobile.priority_change.message": (
            "Priority changed: {priority_label}\n\n"
            "EV: {ev_soc:.1f}% (target: {ev_target}%)\n"
            "Home: {home_soc:.1f}% (target: {home_target}%)\n\n"
            "Reason: {reason}"
        ),
        "mobile.night_charge.message_with_forecast": (
            "EV charging started via {mode_label}\n\n"
            "Tomorrow solar forecast: {forecast:.1f} kWh\n"
            "{reason}\n"
            "Amperage: {amperage}A\n"
            "Time: {time}"
        ),
        "mobile.night_charge.message_without_forecast": (
            "EV charging started via {mode_label}\n\n"
            "{reason}\n"
            "Amperage: {amperage}A\n"
            "Time: {time}"
        ),
        "mobile.night_charge_skipped.message": (
            "Night Smart Charge skipped\n\n"
            "{reason}\n"
            "Time: {time}"
        ),
        "night_charge.reason.preserve_home_battery": (
            "Preserve Home Battery is enabled and the car is not required by morning. "
            "Overnight charging is skipped to avoid unnecessary home battery cycles."
        ),
        "mobile.boost_started.message": (
            "EV boost charge started\n\n"
            "EV: {start_soc:.1f}%\n"
            "Boost target: {target_soc}%\n"
            "Amperage: {amperage}A\n"
            "Time: {time}"
        ),
        "mobile.boost_completed.message": (
            "EV boost charge completed\n\n"
            "Final EV: {end_soc_label}\n"
            "Boost target: {target_soc_label}\n"
            "Reason: {reason}\n"
            "Returning to automatic mode."
        ),
        "boost.reason.manual_stop": "Boost manually disabled",
        "boost.reason.missing_configuration": "Unable to start Boost Charge: incomplete configuration.",
        "boost.reason.missing_soc": "Unable to start Boost Charge: EV SOC unavailable.",
        "boost.reason.not_started_target_reached": (
            "The configured SOC target has already been reached.\n\n"
            "Current SOC: {current_soc:.1f}%\n"
            "Boost target: {target_soc}%"
        ),
        "boost.reason.coordinator_denied": "Unable to start Boost Charge: {reason}",
        "boost.reason.start_failed": "Unable to start boost charging.",
        "boost.reason.command_rejected": (
            "Unable to start Boost Charge: the charger did not accept the command."
        ),
        "boost.reason.session_config_missing": (
            "Boost configuration became unavailable during the session."
        ),
        "boost.reason.session_soc_missing": "EV SOC unavailable for 60 seconds.",
        "boost.reason.target_reached": "SOC target reached ({current_soc:.1f}% >= {target_soc}%)",
        "boost.title.not_started": "Boost Charge not started",
        "boost.title.completed": "Boost Charge completed",
        "boost.title.stopped": "Boost Charge stopped",
        "boost.message.completed": (
            "The Boost session completed successfully.\n\n"
            "Reason: {reason}\n"
            "Returning to automatic mode."
        ),
        "boost.message.stopped": (
            "The Boost session was interrupted.\n\n"
            "Reason: {reason}\n"
            "Returning to automatic mode."
        ),
        "smart_blocker.title.blocked": "Charging Blocked",
        "smart_blocker.message.blocked": (
            "Charging has been automatically blocked.\n\n"
            "To override this behavior, enable 'Force Charge' or disable 'Smart Charger Blocker'.\n\n"
            "**Continuous monitoring:** Any external attempt to re-enable charging will be immediately blocked."
        ),
        "smart_blocker.title.blocking_failed": "Blocking Failed",
        "smart_blocker.message.blocking_failed": (
            "Failed to block charging.\n\n"
            "Please check:\n"
            "- Charger switch entity is functioning\n"
            "- No conflicting automations\n"
            "- Charger hardware status"
        ),
        "smart_blocker.additional.reason": "Reason",
        "smart_blocker.additional.timestamp": "Timestamp",
    },
    "it": {
        "common.error_label": "Errore",
        "common.not_available_short": "N/D",
        "common.reason_label": "Motivo",
        "common.time_label": "Ora",
        "mode.battery": "Batteria domestica",
        "mode.grid": "Rete elettrica",
        "priority.EV": "EV",
        "priority.EV_Free": "EV Free",
        "priority.Home": "Casa",
        "mobile.smart_blocker.message": (
            "Ricarica EV interrotta perche' fuori dalla finestra di ricarica configurata\n\n"
            "Motivo: {reason}\n"
            "Ora: {time}"
        ),
        "mobile.priority_change.message": (
            "Priorita' cambiata: {priority_label}\n\n"
            "EV: {ev_soc:.1f}% (target: {ev_target}%)\n"
            "Casa: {home_soc:.1f}% (target: {home_target}%)\n\n"
            "Motivo: {reason}"
        ),
        "mobile.night_charge.message_with_forecast": (
            "Ricarica EV avviata tramite {mode_label}\n\n"
            "Previsione solare di domani: {forecast:.1f} kWh\n"
            "{reason}\n"
            "Amperaggio: {amperage}A\n"
            "Ora: {time}"
        ),
        "mobile.night_charge.message_without_forecast": (
            "Ricarica EV avviata tramite {mode_label}\n\n"
            "{reason}\n"
            "Amperaggio: {amperage}A\n"
            "Ora: {time}"
        ),
        "mobile.night_charge_skipped.message": (
            "Night Smart Charge saltato\n\n"
            "{reason}\n"
            "Ora: {time}"
        ),
        "night_charge.reason.preserve_home_battery": (
            "Preserva batteria di casa e' attivo e l'auto non deve essere pronta al mattino. "
            "La ricarica notturna viene saltata per evitare cicli inutili della batteria domestica."
        ),
        "mobile.boost_started.message": (
            "Boost EV avviato\n\n"
            "EV: {start_soc:.1f}%\n"
            "Target Boost: {target_soc}%\n"
            "Amperaggio: {amperage}A\n"
            "Ora: {time}"
        ),
        "mobile.boost_completed.message": (
            "Boost EV completato\n\n"
            "EV finale: {end_soc_label}\n"
            "Target Boost: {target_soc_label}\n"
            "Motivo: {reason}\n"
            "Ritorno alla modalita' automatica in corso."
        ),
        "boost.reason.manual_stop": "Boost disattivato manualmente",
        "boost.reason.missing_configuration": (
            "Impossibile avviare Boost Charge: configurazione incompleta."
        ),
        "boost.reason.missing_soc": "Impossibile avviare Boost Charge: SOC EV non disponibile.",
        "boost.reason.not_started_target_reached": (
            "Il target SOC configurato e' gia' stato raggiunto.\n\n"
            "SOC attuale: {current_soc:.1f}%\n"
            "Target Boost: {target_soc}%"
        ),
        "boost.reason.coordinator_denied": "Impossibile avviare Boost Charge: {reason}",
        "boost.reason.start_failed": "Impossibile avviare la ricarica Boost.",
        "boost.reason.command_rejected": (
            "Impossibile avviare Boost Charge: il charger non ha accettato il comando."
        ),
        "boost.reason.session_config_missing": (
            "Configurazione Boost non disponibile durante la sessione."
        ),
        "boost.reason.session_soc_missing": "SOC EV non disponibile per 60 secondi.",
        "boost.reason.target_reached": "Target SOC raggiunto ({current_soc:.1f}% >= {target_soc}%)",
        "boost.title.not_started": "Boost Charge non avviato",
        "boost.title.completed": "Boost Charge completato",
        "boost.title.stopped": "Boost Charge terminato",
        "boost.message.completed": (
            "La sessione Boost si e' conclusa correttamente.\n\n"
            "Motivo: {reason}\n"
            "Ritorno alla modalita' automatica in corso."
        ),
        "boost.message.stopped": (
            "La sessione Boost e' stata interrotta.\n\n"
            "Motivo: {reason}\n"
            "Ritorno alla modalita' automatica in corso."
        ),
        "smart_blocker.title.blocked": "Ricarica bloccata",
        "smart_blocker.message.blocked": (
            "La ricarica e' stata bloccata automaticamente.\n\n"
            "Per forzare questo comportamento, abilita 'Forza Ricarica' oppure disabilita 'Smart Charger Blocker'.\n\n"
            "**Monitoraggio continuo:** qualsiasi tentativo esterno di riattivare la ricarica verra' bloccato immediatamente."
        ),
        "smart_blocker.title.blocking_failed": "Blocco non riuscito",
        "smart_blocker.message.blocking_failed": (
            "Impossibile bloccare la ricarica.\n\n"
            "Controlla:\n"
            "- Il corretto funzionamento dello switch del charger\n"
            "- L'assenza di automazioni in conflitto\n"
            "- Lo stato hardware del charger"
        ),
        "smart_blocker.additional.reason": "Motivo",
        "smart_blocker.additional.timestamp": "Timestamp",
    },
    "nl": {
        "common.error_label": "Fout",
        "common.not_available_short": "n.v.t.",
        "common.reason_label": "Reden",
        "common.time_label": "Tijd",
        "mode.battery": "Thuisbatterij",
        "mode.grid": "Net",
        "priority.EV": "EV",
        "priority.EV_Free": "EV Free",
        "priority.Home": "Woning",
        "mobile.smart_blocker.message": (
            "EV-laden is gestopt omdat het buiten het ingestelde laadvenster valt\n\n"
            "Reden: {reason}\n"
            "Tijd: {time}"
        ),
        "mobile.priority_change.message": (
            "Prioriteit gewijzigd: {priority_label}\n\n"
            "EV: {ev_soc:.1f}% (doel: {ev_target}%)\n"
            "Woning: {home_soc:.1f}% (doel: {home_target}%)\n\n"
            "Reden: {reason}"
        ),
        "mobile.night_charge.message_with_forecast": (
            "EV-laden gestart via {mode_label}\n\n"
            "Zonneverwachting voor morgen: {forecast:.1f} kWh\n"
            "{reason}\n"
            "Stroomsterkte: {amperage}A\n"
            "Tijd: {time}"
        ),
        "mobile.night_charge.message_without_forecast": (
            "EV-laden gestart via {mode_label}\n\n"
            "{reason}\n"
            "Stroomsterkte: {amperage}A\n"
            "Tijd: {time}"
        ),
        "mobile.night_charge_skipped.message": (
            "Slim nachtelijk laden overgeslagen\n\n"
            "{reason}\n"
            "Tijd: {time}"
        ),
        "night_charge.reason.preserve_home_battery": (
            "Thuisbatterij sparen is ingeschakeld en de auto hoeft 's ochtends niet klaar te zijn. "
            "Nachtelijk laden wordt overgeslagen om onnodige cycli van de thuisbatterij te voorkomen."
        ),
        "mobile.boost_started.message": (
            "EV-boostladen gestart\n\n"
            "EV: {start_soc:.1f}%\n"
            "Boostdoel: {target_soc}%\n"
            "Stroomsterkte: {amperage}A\n"
            "Tijd: {time}"
        ),
        "mobile.boost_completed.message": (
            "EV-boostladen voltooid\n\n"
            "Eind-EV: {end_soc_label}\n"
            "Boostdoel: {target_soc_label}\n"
            "Reden: {reason}\n"
            "Terugkeer naar automatische modus."
        ),
        "boost.reason.manual_stop": "Boost handmatig uitgeschakeld",
        "boost.reason.missing_configuration": (
            "Boost Charge kan niet worden gestart: onvolledige configuratie."
        ),
        "boost.reason.missing_soc": "Boost Charge kan niet worden gestart: EV-SOC niet beschikbaar.",
        "boost.reason.not_started_target_reached": (
            "Het ingestelde SOC-doel is al bereikt.\n\n"
            "Huidige SOC: {current_soc:.1f}%\n"
            "Boostdoel: {target_soc}%"
        ),
        "boost.reason.coordinator_denied": "Boost Charge kan niet worden gestart: {reason}",
        "boost.reason.start_failed": "Boostladen kan niet worden gestart.",
        "boost.reason.command_rejected": (
            "Boost Charge kan niet worden gestart: de lader accepteerde de opdracht niet."
        ),
        "boost.reason.session_config_missing": (
            "De boostconfiguratie werd tijdens de sessie onbeschikbaar."
        ),
        "boost.reason.session_soc_missing": "EV-SOC 60 seconden niet beschikbaar.",
        "boost.reason.target_reached": "SOC-doel bereikt ({current_soc:.1f}% >= {target_soc}%)",
        "boost.title.not_started": "Boost Charge niet gestart",
        "boost.title.completed": "Boost Charge voltooid",
        "boost.title.stopped": "Boost Charge gestopt",
        "boost.message.completed": (
            "De boostsessie is succesvol afgerond.\n\n"
            "Reden: {reason}\n"
            "Terugkeer naar automatische modus."
        ),
        "boost.message.stopped": (
            "De boostsessie is onderbroken.\n\n"
            "Reden: {reason}\n"
            "Terugkeer naar automatische modus."
        ),
        "smart_blocker.title.blocked": "Laden geblokkeerd",
        "smart_blocker.message.blocked": (
            "Laden is automatisch geblokkeerd.\n\n"
            "Om dit gedrag te overrulen, schakel 'Force Charge' in of schakel 'Smart Charger Blocker' uit.\n\n"
            "**Continue bewaking:** elke externe poging om laden opnieuw in te schakelen wordt onmiddellijk geblokkeerd."
        ),
        "smart_blocker.title.blocking_failed": "Blokkeren mislukt",
        "smart_blocker.message.blocking_failed": (
            "Het laden kon niet worden geblokkeerd.\n\n"
            "Controleer:\n"
            "- Of de schakelaar van de lader werkt\n"
            "- Of er geen conflicterende automatiseringen zijn\n"
            "- De hardwarestatus van de lader"
        ),
        "smart_blocker.additional.reason": "Reden",
        "smart_blocker.additional.timestamp": "Tijdstip",
    },
}


def get_runtime_language(hass: HomeAssistant) -> str:
    """Return the normalized Home Assistant language for runtime text."""
    raw_language = getattr(getattr(hass, "config", None), "language", None) or DEFAULT_RUNTIME_LANGUAGE
    normalized = raw_language.replace("_", "-").split("-", 1)[0].lower()
    if normalized in RUNTIME_TRANSLATIONS:
        return normalized
    return DEFAULT_RUNTIME_LANGUAGE


def translate_runtime(hass: HomeAssistant, key: str, **placeholders) -> str:
    """Translate runtime copy using Home Assistant language with English fallback."""
    language = get_runtime_language(hass)
    template = RUNTIME_TRANSLATIONS.get(language, {}).get(key)
    if template is None:
        template = RUNTIME_TRANSLATIONS[DEFAULT_RUNTIME_LANGUAGE].get(key)
    if template is None:
        return key
    return template.format(**placeholders)
