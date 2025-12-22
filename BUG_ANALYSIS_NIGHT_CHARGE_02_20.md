# Analisi Bug: Night Charge Bloccato alle 02:20

## Sintomo Riportato

**Data/Ora**: Stanotte alle 02:20
**Azione utente**: Collegata la macchina al caricatore
**Comportamento atteso**: Night Smart Charge dovrebbe attivarsi (siamo dopo l'ora configurata 01:00 e prima dell'alba)
**Comportamento reale**: Il componente ha interrotto la ricarica e inviato notifica "fuori dalla fascia night charge"

## Root Cause Analysis

### Il Bug Principale: Calcolo Errato della Finestra di Blocco

Il problema si trova nello **Smart Blocker** nel metodo `_get_night_charge_datetime()` (automations.py:437-439):

```python
# CODICE BUGATO (automations.py:437-439)
return TimeParsingService.time_string_to_next_occurrence(
    time_state, reference_date
)
```

### Come si Manifesta il Bug

**Scenario**: Utente collega macchina alle 02:20, con `night_charge_time` configurato a `01:00:00`

#### Step 1: Smart Blocker Calcola la Finestra

```python
now = 02:20  # oggi
night_charge_time = time_string_to_next_occurrence("01:00:00", now=02:20)
```

Il metodo `time_string_to_next_occurrence` fa:
1. Crea datetime: `oggi 01:00:00`
2. Controlla: `01:00:00 < 02:20:00` → **TRUE**
3. **Aggiunge un giorno**: `target_time += timedelta(days=1)`
4. Ritorna: **`domani 01:00:00`** ❌

#### Step 2: Calcolo Finestra di Blocco

Lo Smart Blocker chiama `get_blocking_window()`:
- `window_start` = `ieri 18:30` (sunset di ieri, perché siamo prima del sunrise)
- `window_end` = **`domani 01:00`** (calcolato erroneamente!)

#### Step 3: Verifica se Siamo Bloccati

```python
is_blocked = window_start <= reference_time < window_end
is_blocked = ieri_18:30 <= oggi_02:20 < domani_01:00
is_blocked = TRUE ❌ SBAGLIATO!
```

**Risultato**: Lo Smart Blocker pensa che siamo ancora nella finestra di blocco e blocca la ricarica!

### Logica Corretta (Come Dovrebbe Essere)

Alle 02:20, con night_charge_time=01:00:
- La finestra di blocco **era**: `ieri 18:30 → oggi 01:00`
- Alle 02:20 siamo **DOPO** `oggi 01:00`
- Quindi siamo **FUORI** dalla finestra di blocco ✓
- Night Smart Charge dovrebbe essere attivo ✓

### Perché il Bug Non Si Manifesta Sempre

Il bug si manifesta **SOLO** in queste condizioni:
1. Night Smart Charge è **ENABLED**
2. Siamo **dopo mezzanotte** (early morning)
3. Siamo **dopo** il `night_charge_time` configurato (es. 02:20 > 01:00)
4. Siamo **prima** del sunrise (es. 02:20 < 07:00)
5. L'utente **collega la macchina manualmente** (late arrival)

Nelle altre situazioni:
- Se Night Charge è già attivo → Smart Blocker non interviene (check #3 in `_should_block_charging`)
- Se colleghiamo prima dell'01:00 → Night Charge si attiva normalmente
- Se colleghiamo dopo sunrise → Non siamo più in window check

## Timeline dell'Errore

```
18:30 (ieri) - Sunset
01:00 (oggi) - Configurato night_charge_time
02:20 (oggi) - UTENTE COLLEGA MACCHINA
              │
              ├─ Late Arrival Detection trigge
              ├─ Night Charge: _is_in_active_window() → TRUE ✓
              ├─ Night Charge: Avvia ricarica (BATTERY/GRID)
              ├─ Charger: Cambia stato → "charging"
              │
              └─ Smart Blocker: Triggered da stato "charging"
                 ├─ Check if Night Charge active: might be FALSE (race condition)
                 ├─ Calcola blocking window:
                 │  • window_start = ieri 18:30
                 │  • window_end = domani 01:00 ❌ (ERRORE!)
                 │
                 ├─ Verifica: ieri_18:30 <= oggi_02:20 < domani_01:00 → TRUE
                 ├─ BLOCCA RICARICA ❌
                 └─ Invia notifica "fuori dalla fascia night charge"
```

## Bug Secondario: Race Condition

C'è anche una potenziale **race condition** tra Night Charge e Smart Blocker:

1. Night Charge avvia il caricatore
2. Il cambio di stato del charger trigge **immediatamente** lo Smart Blocker
3. Se `_night_charge_active` non è ancora settato a TRUE, Smart Blocker non vede che Night Charge è attivo
4. Smart Blocker procede con la verifica della finestra di blocco (che è bugata)

## Soluzioni Proposte

### Soluzione 1: Fix del Calcolo della Finestra (PRINCIPALE)

Modificare `_get_night_charge_datetime()` in `automations.py` per usare l'occorrenza corretta:

```python
async def _get_night_charge_datetime(self, reference_date: datetime) -> datetime | None:
    """Get the night charge time as a datetime object for blocking window."""
    if not self._night_charge_time_entity:
        return None

    time_state = get_state(self.hass, self._night_charge_time_entity)
    if not time_state or time_state in ["unknown", "unavailable"]:
        return None

    try:
        # FIX: Use correct occurrence based on sunrise position
        sunrise_today = self._astral_service.get_sunrise(reference_date)

        if sunrise_today and reference_date < sunrise_today:
            # Early morning (before sunrise): use TODAY's occurrence
            # (even if it's in the past, like 01:00 when it's 02:20)
            return TimeParsingService.time_string_to_datetime(
                time_state, reference_date
            )
        else:
            # After sunrise: use NEXT occurrence (tomorrow)
            return TimeParsingService.time_string_to_next_occurrence(
                time_state, reference_date
            )
    except (ValueError, AttributeError) as e:
        self.logger.warning(
            f"Error parsing night_charge_time '{time_state}': {e}"
        )
        return None
```

**Logica della Fix**:
- **Prima del sunrise** (early morning, es. 02:20): Usa l'01:00 di OGGI (anche se passato)
  → Finestra: `ieri_18:30 → oggi_01:00` → Alle 02:20 siamo FUORI ✓
- **Dopo il sunrise** (pomeriggio/sera, es. 20:00): Usa l'01:00 di DOMANI (next occurrence)
  → Finestra: `oggi_18:30 → domani_01:00` → Alle 20:00 siamo DENTRO ✓

### Soluzione 2: Fix della Race Condition (SECONDARIA)

Assicurarsi che `_night_charge_active` sia settato **PRIMA** di avviare il charger:

In `night_smart_charge.py`, nei metodi `_start_battery_charge()` e `_start_grid_charge()`:

```python
# Set flag BEFORE starting charger (not after)
self._night_charge_active = True
self._active_mode = NIGHT_CHARGE_MODE_BATTERY  # or GRID

# Then start charger
await self.charger_controller.start_charger(amperage, reason)
```

Questo garantisce che quando lo Smart Blocker viene triggerato dal cambio di stato, veda già Night Charge come attivo.

## Test Case per Validazione

Dopo la fix, testare questi scenari:

### Test 1: Late Arrival dopo night_charge_time (BUG CASE)
- Config: night_charge_time = 01:00, Night Charge ENABLED
- Ora: 02:20 (dopo mezzanotte, dopo 01:00, prima sunrise)
- Azione: Collegare macchina
- **Atteso**: Night Charge si attiva, Smart Blocker NON blocca ✓

### Test 2: Late Arrival prima di night_charge_time
- Config: night_charge_time = 01:00
- Ora: 00:30 (dopo mezzanotte, prima 01:00)
- Azione: Collegare macchina
- **Atteso**: Smart Blocker blocca (siamo nella finestra ieri_18:30 → oggi_01:00) ✓

### Test 3: Collegamento serale
- Config: night_charge_time = 01:00
- Ora: 20:00 (dopo sunset, prima mezzanotte)
- Azione: Collegare macchina
- **Atteso**: Smart Blocker blocca (siamo nella finestra oggi_18:30 → domani_01:00) ✓

### Test 4: Collegamento durante giorno
- Config: night_charge_time = 01:00
- Ora: 14:00 (dopo sunrise, prima sunset)
- Azione: Collegare macchina
- **Atteso**: Smart Blocker NON blocca (fuori finestra) ✓

## Priority

🔴 **CRITICAL** - Il bug impedisce completamente l'uso del Night Smart Charge in uno scenario comune (late arrival dopo l'ora configurata).

## Files da Modificare

1. **custom_components/ev_smart_charger/automations.py**
   - Metodo: `_get_night_charge_datetime()` (linee 417-444)
   - Fix: Logica di selezione dell'occorrenza basata su sunrise

2. **custom_components/ev_smart_charger/night_smart_charge.py**
   - Metodi: `_start_battery_charge()`, `_start_grid_charge()`
   - Fix: Settare flag `_night_charge_active` PRIMA di avviare charger

3. **custom_components/ev_smart_charger/const.py**
   - Bump version

4. **custom_components/ev_smart_charger/manifest.json**
   - Bump version
