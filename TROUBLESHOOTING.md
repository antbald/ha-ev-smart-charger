# Troubleshooting EV Smart Charger

## Integration Won't Start

### 1. Check the Logs

**Via Home Assistant UI:**
1. Go to **Settings → System → Logs**
2. Search for "ev_smart_charger" or "evsc"
3. Look for ERROR or WARNING messages

**Enable Debug Logging:**

Add this to your `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.ev_smart_charger: debug
```

Then restart Home Assistant and check logs again.

### 2. Common Issues

#### Helper Creation Fails

**Symptoms:**
- Integration fails to start
- Logs show "Failed to create helpers"

**Solution:**
Create the helpers manually via Home Assistant UI:

1. Go to **Settings → Devices & Services → Helpers**
2. Click **"+ CREATE HELPER"**
3. Create these three helpers:

**Helper 1: EVSC Forza Ricarica**
- Type: **Toggle**
- Name: `EVSC Forza Ricarica`
- Icon: `mdi:power`
- Entity ID: `input_boolean.evsc_forza_ricarica`

**Helper 2: EVSC Smart Charger Blocker**
- Type: **Toggle**
- Name: `EVSC Smart Charger Blocker`
- Icon: `mdi:solar-power`
- Entity ID: `input_boolean.evsc_smart_charger_blocker_enabled`

**Helper 3: EVSC Solar Production Threshold**
- Type: **Number**
- Name: `EVSC Solar Production Threshold`
- Icon: `mdi:solar-power-variant`
- Entity ID: `input_number.evsc_solar_production_threshold`
- Minimum: `0`
- Maximum: `1000`
- Step: `10`
- Unit: `W`

#### Automation Setup Fails

**Symptoms:**
- Integration loads but automations don't work
- Logs show "Failed to set up automations"

**Check:**
1. Verify all configured entities exist
2. Check entity IDs are correct
3. Ensure charger status sensor reports states: `charger_charging`, `charger_free`, `charger_end`

#### Entity Not Found Errors

**Symptoms:**
- Logs show "Entity not found: sensor.xxx"

**Solution:**
1. Go to **Settings → Devices & Services → EV Smart Charger**
2. Click **CONFIGURE**
3. Verify all entity selections are correct
4. Make sure the entities actually exist in your system

### 3. Verification Steps

After fixing issues, verify everything works:

1. **Check Helpers Exist:**
   - Go to Settings → Devices & Services → Helpers
   - Search for "evsc"
   - You should see 3 helpers

2. **Test Smart Charger Blocker:**
   - Enable `EVSC Smart Charger Blocker` helper
   - Disable `EVSC Forza Ricarica` (kill switch must be OFF)
   - Plug in your car at night
   - Charger should be blocked automatically

3. **Check Logs:**
   ```
   Settings → System → Logs
   ```
   Look for:
   - "✅ EV Smart Charger setup completed successfully"
   - "Smart Charger Blocker automation set up successfully"

### 4. Get More Help

If issues persist:

1. **Collect Full Logs:**
   - Enable debug logging (see above)
   - Restart Home Assistant
   - Copy relevant log entries

2. **Report Issue:**
   - Go to: https://github.com/antbald/ha-ev-smart-charger/issues
   - Include:
     - Home Assistant version
     - Integration version
     - Full error logs
     - Steps to reproduce

## FAQ

**Q: Can I use the integration without helpers?**
A: No, the helpers are required for the automations to work.

**Q: Will I lose helper settings if I update?**
A: No, helpers persist across updates. They're separate entities in Home Assistant.

**Q: Can I change helper entity IDs?**
A: No, the integration expects specific entity IDs. Use the exact IDs listed above.

**Q: Integration loads but nothing happens when I plug in the car?**
A: Check that:
1. Smart Charger Blocker helper is enabled
2. Forza Ricarica helper is disabled
3. It's actually nighttime or solar production is below threshold
4. Charger status sensor reports "charger_charging" state
