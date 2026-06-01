**EV Smart Charger — MVP**  
Sensore di stato + select per la modalità. Base per strategie di ricarica.

**v2.2.0** — La **potenza di ricarica misurata** (W) diventa la fonte di verità per "l'auto sta caricando?", con il sensore di stato come fallback (ora **opzionale**). Risolve il banner verde "EV in ricarica" della dashboard (prima falliva su wallbox che non riportano esattamente `charger_charging`) e i casi di wallbox bloccato su "charging" a 0 W. Mappa il sensore di potenza (1 in monofase, 3 in trifase) da Riconfigura. Senza sensore di potenza il comportamento è identico a v2.1.x.

**v2.0.0** — Supporto opt-in **trifase** (tre sensori per produzione/consumo/prelievo, velocità bilanciata sulle tre fasi) e selettore **modello wallbox** Tuya / generica (generica = scatti da 1 A + riduzione corrente al volo). I default mantengono monofase + Tuya invariati.
