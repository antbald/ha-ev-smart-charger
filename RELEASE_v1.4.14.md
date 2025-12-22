# Release v1.4.14 - Deployment Guide

## ✅ Status: READY FOR DEPLOYMENT

All code changes have been committed and pushed to branch `claude/fix-night-charge-bug-ZVTMt`.

## 🚀 Deployment Steps

### Option 1: GitHub Release (RECOMMENDED)

1. **Create GitHub Release**:
   - Go to: https://github.com/antbald/ha-ev-smart-charger/releases/new
   - **Choose a tag**: `v1.4.14` (create new tag)
   - **Target**: `claude/fix-night-charge-bug-ZVTMt` (or master after merge)
   - **Release title**: `v1.4.14 - Fix Smart Blocker Blocking Window Calculation`
   - **Description**: Copy from "GitHub Release Notes" section below
   - Click **"Publish release"**

### Option 2: Merge Pull Request + Release

1. **Create Pull Request**:
   - Go to: https://github.com/antbald/ha-ev-smart-charger/pull/new/claude/fix-night-charge-bug-ZVTMt
   - **Base**: `master`
   - **Compare**: `claude/fix-night-charge-bug-ZVTMt`
   - **Title**: `Release v1.4.14: Fix Smart Blocker Blocking Window Calculation`
   - **Description**: Copy from "Pull Request Description" section below

2. **Merge the PR**:
   - Review and approve
   - Merge to master

3. **Create GitHub Release**:
   - Follow Option 1 steps above (after merge)

---

## 📋 GitHub Release Notes

Copy this for the GitHub Release description:

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

- `5618ade` - Release v1.4.14: Fix Blocking Window Calculation in Smart Blocker
- `273fa1a` - Add comprehensive bug analysis for Night Charge 02:20 blocking issue
```

---

## 📋 Pull Request Description

Copy this for the Pull Request description:

```markdown
## Release v1.4.14: Fix Smart Blocker Blocking Window Calculation

### Summary

This PR fixes a critical bug in Smart Blocker where the blocking window was incorrectly calculated for late arrivals in early morning hours, causing Night Smart Charge to fail when users plugged in after the configured `night_charge_time`.

### Problem

Users plugging in at 02:20 with `night_charge_time=01:00` received incorrect blocking notifications ("fuori dalla fascia night charge"), even though Night Smart Charge should have been active.

### Root Cause

`_get_night_charge_datetime()` used `time_string_to_next_occurrence()` which returns tomorrow's occurrence when the time has passed today, creating an incorrect 24+ hour blocking window.

### Solution

Implemented sunrise-based occurrence selection:
- Before sunrise: Use TODAY's occurrence
- After sunrise: Use NEXT occurrence (tomorrow)

### Impact

✅ Smart Blocker calculates correct blocking window
✅ Night Smart Charge activates for late arrivals
✅ No more incorrect blocking notifications
✅ Consistent logic across all time scenarios

### Testing

Validated 4 test scenarios:
- ✅ Late arrival at 02:20 → Night Charge activates
- ✅ Late arrival at 00:30 → Smart Blocker blocks
- ✅ Evening at 20:00 → Smart Blocker blocks
- ✅ Daytime at 14:00 → Allowed (outside window)

### Files Changed

- `automations.py` (31 lines)
- `const.py` (1 line)
- `manifest.json` (1 line)
- `CLAUDE.md` (64 lines)
- `BUG_ANALYSIS_NIGHT_CHARGE_02_20.md` (217 lines, new)

### Priority

🔴 **CRITICAL** - Fixes Night Smart Charge failure for late arrivals

### Related

See [BUG_ANALYSIS_NIGHT_CHARGE_02_20.md](BUG_ANALYSIS_NIGHT_CHARGE_02_20.md) for detailed technical analysis.
```

---

## 📊 Deployment Checklist

- [x] Code committed
- [x] Code pushed to `claude/fix-night-charge-bug-ZVTMt`
- [x] Bug analysis document created
- [x] Changelog updated in CLAUDE.md
- [x] Version bumped (1.4.13 → 1.4.14)
- [x] manifest.json updated
- [ ] **GitHub Release created** ← MANUAL STEP REQUIRED
- [ ] **Tag v1.4.14 created on GitHub** ← AUTOMATIC with release creation

---

## 🔍 Verification After Deployment

After release is published:

1. **HACS Update Check**:
   - HACS should show v1.4.14 as available
   - Users can update via HACS UI

2. **GitHub Release Check**:
   - Tag v1.4.14 should be visible at: https://github.com/antbald/ha-ev-smart-charger/tags
   - Release should be at: https://github.com/antbald/ha-ev-smart-charger/releases/tag/v1.4.14

3. **Test Scenario**:
   - Wait for late arrival scenario (02:20 with night_charge_time=01:00)
   - Verify Night Smart Charge activates
   - Verify no blocking notification from Smart Blocker

---

## 📞 Support

If issues arise after deployment:
- Check logs for "Smart Blocker" and "Night Smart Charge" entries
- Look for "Blocking window" calculations in logs
- Verify `_get_night_charge_datetime()` is using correct occurrence logic
- Reference BUG_ANALYSIS_NIGHT_CHARGE_02_20.md for debugging

---

**Prepared by**: Claude Code AI Assistant
**Date**: 2025-12-22
**Branch**: `claude/fix-night-charge-bug-ZVTMt`
**Commits**: `273fa1a`, `5618ade`
