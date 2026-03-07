# EV Smart Charger handleiding (Nederlands)

Deze gids is de Nederlandstalige instappagina voor installatie, configuratie en dagelijks gebruik van EV Smart Charger.

## Installatie

### HACS

1. Open **HACS** in Home Assistant.
2. Ga naar **Integrations**.
3. Voeg `https://github.com/antbald/ha-ev-smart-charger` toe als custom repository.
4. Kies categorie **Integration**.
5. Zoek naar **EV Smart Charger** en installeer de integratie.
6. Herstart Home Assistant.

### Handmatige installatie

1. Download de laatste release van GitHub.
2. Pak de map `custom_components/ev_smart_charger` uit.
3. Kopieer die naar `/config/custom_components/ev_smart_charger/`.
4. Herstart Home Assistant.

## Configuratie

De configuratiewizard bestaat uit 6 stappen:

1. Geef de integratie een herkenbare naam.
2. Koppel de entiteiten van de lader: schakelaar, stroomregeling en statussensor.
3. Koppel de energiesensoren: EV-SOC, thuisbatterij-SOC, zonneproductie, woningverbruik en netafname.
4. Voeg optioneel een sensor voor de zonneverwachting toe voor Night Smart Charge.
5. Kies optioneel mobiele notify-services en de persoonsentiteit van de auto-eigenaar.
6. Stel optioneel EV-batterijcapaciteit en een helper voor het energieverwachtingsdoel in.

Na de installatie maakt de integratie automatisch helper-entiteiten aan voor schakelaars, getallen, tijden, selecties en diagnostische sensoren.

## Belangrijkste entiteiten

- `switch.evsc_forza_ricarica`: handmatige override om laden direct toe te staan.
- `switch.evsc_boost_charge_enabled`: start een boostsessie met vaste stroom en automatisch stopdoel.
- `switch.evsc_night_smart_charge_enabled`: schakelt nachtelijk slim laden in.
- `select.evsc_charging_profile`: kies tussen `manual` en `solar_surplus`.
- `number.evsc_grid_import_threshold`: drempel voor netafname in Solar Surplus.
- `number.evsc_home_battery_min_soc`: minimale SOC van de thuisbatterij.
- `time.evsc_night_charge_time`: starttijd van Night Smart Charge.
- `sensor.evsc_priority_daily_state`: huidige prioriteit tussen EV en woning.

## Dashboardgebruik

De meegeleverde Lovelace-card bundelt de belangrijkste bediening:

- hoofdschakelaars voor Force Charge, Boost Charge en Night Smart Charge
- directe aanpassing van laadstroom, drempels en vertragingen
- live metrics voor EV, thuisbatterij, netafname en zonnevermogen
- diagnostische tegels voor automatiseringen en Solar Surplus

Gebruik `entity_prefix` om de card aan de juiste config entry te koppelen. Extra live metrics zoals laadvermogen of EV-SOC kunnen optioneel via aparte entity-id's worden gekoppeld.

## Laadmodi en automatiseringen

### Manual

Geen automatisering. Je regelt laden volledig zelf.

### Solar Surplus

Laadt alleen met overtollige zonne-energie en verlaagt of stopt laden wanneer netafname optreedt.

### Night Smart Charge

Controleert op het ingestelde tijdstip de zonneverwachting voor de volgende dag en kiest dan:

- **Home Battery** als de verwachting hoog genoeg is
- **Grid** als de verwachting te laag is

Car Ready-flags per weekdag bepalen of de auto de volgende ochtend echt klaar moet zijn.

### Boost Charge

Start een handmatige laadsessie met vaste stroom en stopt automatisch zodra het ingestelde EV-SOC is bereikt.

### Smart Charger Blocker

Blokkeert nachtelijk laden buiten het toegestane venster en kan meldingen sturen wanneer laden automatisch wordt gestopt.

## Eenvoudige probleemoplossing

- Controleer of de gekoppelde lader-entiteiten handmatig werken in Home Assistant.
- Controleer of de statussensor exact `charger_charging`, `charger_free`, `charger_end` of `charger_wait` rapporteert.
- Controleer of netafname en zonneproductie de juiste eenheden gebruiken.
- Controleer of mobiele `notify.mobile_app_*`-services beschikbaar zijn als meldingen niet aankomen.
- Gebruik de diagnostische sensoren en logpad-sensor om runtimegedrag te controleren.

## Verdere documentatie

- Voor Engelstalige installatie- en productdocumentatie: [README](../README.md)
- Voor interne architectuur en onderhoud: [Documentation index](README.md)
