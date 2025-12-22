# 🚀 DEPLOY v1.4.14 - ISTRUZIONI IMMEDIATE

## ✅ Tutto Pronto - 1 Solo Click Richiesto

**Status**: Codice pushato ✅ | Tag creato ✅ | Documentazione pronta ✅

---

## 🎯 AZIONE RICHIESTA: Crea GitHub Release

### STEP 1: Apri questo URL

```
https://github.com/antbald/ha-ev-smart-charger/releases/new?tag=v1.4.14&target=claude/fix-night-charge-bug-ZVTMt
```

**OPPURE** vai manualmente a:
- https://github.com/antbald/ha-ev-smart-charger/releases/new

### STEP 2: Compila il Form

**Choose a tag** → Scrivi: `v1.4.14` (crea nuovo)
**Target** → Seleziona: `claude/fix-night-charge-bug-ZVTMt`
**Release title** → Copia-incolla:
```
v1.4.14 - Fix Smart Blocker Blocking Window Calculation
```

**Description** → Copia-incolla TUTTO il testo qui sotto:

---

```markdown
## 🔴 CRITICAL FIX: Smart Blocker Blocking Window Calculation

### Problem Fixed

Smart Blocker incorrectly blocked charging when users plugged in their car in the early morning hours (after midnight) but **after** the configured `night_charge_time`.

**Example Scenario**:
- User plugs in at **02:20**
- Configured `night_charge_time=01:00`
- **Bug**: Smart Blocker blocked with notification "fuori dalla fascia night charge"
- **Expected**: Night Smart Charge should activate

### Root Cause

The `_get_night_charge_datetime()` method in Smart Blocker used `time_string_to_next_occurrence()` which always returns the NEXT future occurrence. At 02:20 with configured time 01:00:

1. Creates datetime: `today 01:00:00`
2. Sees that `01:00 < 02:20` (time has passed)
3. **Adds one day**: returns `tomorrow 01:00:00` ❌

This caused an incorrect blocking window:
- **Start**: `yesterday 18:30` (sunset)
- **End**: `tomorrow 01:00` (WRONG!)
- **Check**: `yesterday_18:30 <= 02:20 < tomorrow_01:00` → **BLOCKED** ❌

**Correct logic**: At 02:20, the blocking window should be `yesterday 18:30 → today 01:00`. Since we're at 02:20, we're **OUTSIDE** the window.

### Solution

Modified `_get_night_charge_datetime()` in `automations.py` with **sunrise-based occurrence selection**:

**Before sunrise** (early morning):
- Use `time_string_to_datetime()` → Returns **TODAY's occurrence** (even if passed)
- Example: At 02:20 returns `today 01:00`
- Blocking window: `yesterday_18:30 → today_01:00` ✓
- At 02:20 we're **OUTSIDE** ✓

**After sunrise** (afternoon/evening):
- Use `time_string_to_next_occurrence()` → Returns **TOMORROW's occurrence**
- Example: At 20:00 returns `tomorrow 01:00`
- Blocking window: `today_18:30 → tomorrow_01:00` ✓
- At 20:00 we're **INSIDE** ✓

### When Bug Manifested

Only under these specific conditions:
- ✅ Night Smart Charge is **ENABLED**
- ✅ User plugs in **after midnight** (early morning)
- ✅ User plugs in **after** `night_charge_time` (e.g., 02:20 > 01:00)
- ✅ **Before sunrise** (e.g., 02:20 < 07:00)
- ✅ **Manual late arrival** (not scheduled activation)

### Impact

✅ Smart Blocker now calculates correct blocking window for early morning hours
✅ Night Smart Charge activates correctly for late arrivals after configured time
✅ No more incorrect "outside night charge window" notifications at 02:20
✅ Blocking window logic consistent across all time scenarios

### Files Modified

- **automations.py**: Fixed `_get_night_charge_datetime()` with sunrise-based logic (lines 417-465)
- **const.py**: VERSION = "1.4.14"
- **manifest.json**: version = "1.4.14"
- **CLAUDE.md**: Added v1.4.14 changelog

### Test Scenarios Validated

| Scenario | Time | Night Charge Time | Expected Result | Status |
|----------|------|-------------------|-----------------|--------|
| Late arrival morning | 02:20 | 01:00 | Night Charge ACTIVATES | ✅ |
| Late arrival pre-time | 00:30 | 01:00 | Smart Blocker BLOCKS | ✅ |
| Evening connection | 20:00 | 01:00 | Smart Blocker BLOCKS | ✅ |
| Daytime connection | 14:00 | 01:00 | Allowed (outside window) | ✅ |

### Upgrade Priority

🔴 **CRITICAL** - Fixes complete Night Smart Charge failure for late arrivals in early morning hours

### Related Documentation

See [BUG_ANALYSIS_NIGHT_CHARGE_02_20.md](https://github.com/antbald/ha-ev-smart-charger/blob/claude/fix-night-charge-bug-ZVTMt/BUG_ANALYSIS_NIGHT_CHARGE_02_20.md) for detailed technical analysis.

### Installation

**Via HACS** (automatic):
- HACS will detect the new version and offer update
- Update to v1.4.14
- Restart Home Assistant

**Manual**:
1. Download release files
2. Copy to `custom_components/ev_smart_charger/`
3. Restart Home Assistant

### Commits Included

- `0e337e3` - Add deployment guide and release notes for v1.4.14
- `5618ade` - Release v1.4.14: Fix Blocking Window Calculation in Smart Blocker
- `273fa1a` - Add comprehensive bug analysis for Night Charge 02:20 blocking issue
```

---

### STEP 3: Pubblica

1. **NON selezionare** "Set as a pre-release"
2. **NON selezionare** "Set as the latest release" (lascia default)
3. Click **"Publish release"**

---

## ✅ FATTO!

Dopo la pubblicazione:
- HACS rileverà automaticamente v1.4.14
- Gli utenti potranno aggiornare via HACS
- La release sarà visibile su: https://github.com/antbald/ha-ev-smart-charger/releases/tag/v1.4.14

---

## 📊 Verifica Post-Deploy

1. **Check release**: https://github.com/antbald/ha-ev-smart-charger/releases
2. **Check tag**: https://github.com/antbald/ha-ev-smart-charger/tags
3. **HACS**: Verifica che v1.4.14 sia disponibile per l'update

---

**Branch**: `claude/fix-night-charge-bug-ZVTMt`
**Tag**: `v1.4.14`
**Commits**: 3 (analysis + fix + deployment docs)
**Priority**: 🔴 CRITICAL
