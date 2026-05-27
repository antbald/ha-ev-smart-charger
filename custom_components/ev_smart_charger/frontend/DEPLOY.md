# Dashboard cache-busting & deploy guide

Reference for maintainers and power users. Covers how the bundled Lovelace card's cache busting works, what to update on every release, and how to diagnose stale assets.

For the visual design system (typography, colors, motion, anti-patterns) read [DESIGN.md](DESIGN.md) instead.

## Why this file exists

Home Assistant integrations bundle their custom Lovelace cards as a single JavaScript module served from a static path. Without cache busting, browsers happily reuse the previous bundle for up to a year (the platform's default `Cache-Control: max-age=31536000`), and users see no UI change after upgrading the integration.

This integration solves it deterministically with two layered cache busters on the resource URL — no service worker, no bundler, no manual cache clear.

## How it works

The Lovelace resource is registered as:

```
/api/ev_smart_charger/frontend/ev-smart-charger-dashboard.js?v=<VERSION>&h=<HASH>
```

| Param | Source | Changes when |
|---|---|---|
| `v` | `const.py:VERSION` (manual SemVer bump) | Maintainer bumps it on every release. Visible in logs / issues / GitHub releases. |
| `h` | First 8 hex chars of SHA-256 of the bundled JS file | Any byte of the JS file changes — even a comment edit. Computed in Python on every `async_ensure_resource()` call (no module-level cache, no `@lru_cache`). |

Both must be unchanged for a browser to serve the cached copy. In practice:

- **Normal release** (VERSION bumped + JS edited) → both `v` and `h` change → guaranteed re-fetch.
- **Hotfix that forgets to bump VERSION** → `v` stays, but `h` still flips → re-fetch still happens. This is the safety net.
- **No-op rebuild** (same file content, same VERSION) → both stay → browser serves the cached copy. Zero wasted bandwidth.

The update path inside `dashboard_manager.py`:

```
async_ensure_resource()
  └─ _build_resource_url(hass)
       └─ hass.async_add_executor_job(_compute_bundle_hash)   ← I/O off the event loop
  └─ if existing.url != new_url → resources.async_update_item(...)
  └─ logs "🔄 Updated Lovelace resource"
```

The Lovelace `lovelace_updated` websocket event notifies the frontend that the resource list changed — but it does **not** re-fetch the already-loaded `<script type="module">`. Users must **reload the dashboard page** (F5 / Cmd+R) to pick up the new bundle. The new `?v=…&h=…` URL ensures that reload hits the network instead of the disk cache.

## Where VERSION lives

Single source of truth: `const.py:VERSION`. It propagates to:

1. **`manifest.json:version`** — HACS / HA marketplace metadata. Must match `const.py` manually.
2. **The resource URL** `?v=` — built from `const.py:VERSION` in `dashboard_manager.py:_build_resource_url`.
3. **The card config payload** — `dashboard_manager.py:_build_card_config` passes `_build_version: VERSION`, the JS reads `this.config._build_version` and logs it to the console.

No `BUILD_VERSION` constant duplicated inside `ev-smart-charger-dashboard.js` — runtime injection avoids the triple-bump trap.

## Pre-release checklist

- [ ] `const.py:VERSION` bumped
- [ ] `manifest.json:version` bumped (must match)
- [ ] `CLAUDE.md` changelog entry added at top of Version History
- [ ] (Local test) Reload the dashboard page → DevTools Console shows `[EVSC Dashboard] build version: X.Y.Z` exactly once
- [ ] (Local test) DevTools Network shows `ev-smart-charger-dashboard.js?v=X.Y.Z&h=<8 hex>` with status 200
- [ ] No `RESOURCE_URL` module-level constant reintroduced — must remain a per-call function
- [ ] No `@lru_cache` on `_compute_bundle_hash` — must recompute on every call

## Verify in DevTools

1. Open the EV Smart Charger dashboard in Chrome/Firefox.
2. Open DevTools → Network tab → reload the page (F5).
3. Filter by `ev-smart-charger`. The bundle should appear as:
   ```
   ev-smart-charger-dashboard.js?v=1.11.4&h=a1b2c3d4    200 OK
   ```
4. Reload again without any code change. Same URL should appear with status `304 Not Modified` (or no network call at all — depends on HA's `Cache-Control` header behavior in your setup).
5. Switch to Console tab. Search for `[EVSC Dashboard]`. Exactly one line should appear:
   ```
   [EVSC Dashboard] build version: 1.11.4
   ```

If the version logged differs from `manifest.json:version`, the user is loading an old bundle from cache. Force a hard refresh (Ctrl+Shift+R) once, confirm the log matches, and investigate why the auto-update didn't fire (next section).

## Troubleshooting

### "I upgraded but the UI is unchanged"

1. **Check the registered resource URL.** Settings → Dashboards → Resources → look for the entry pointing at `ev-smart-charger-dashboard.js`. The URL **must** include `?v=` and `&h=` with the new values.
   - If it shows the previous version → restart Home Assistant once. `async_ensure_resource()` runs on every entry setup and will fire `async_update_item` with the new URL.
   - If it still shows the previous version after restart → check HA logs for `Failed to register Lovelace resource` warnings.

2. **The URL is correct but the browser loads old JS.** Hard refresh (Ctrl+Shift+R / Cmd+Shift+R) once. If it then works, the previous fetch was held in the browser's memory cache (not the disk cache the version query bypasses). This is a one-time symptom across HA restarts; subsequent reloads work normally.

3. **The console log shows an old version even after hard refresh.** The card config wasn't regenerated. Reload the integration (Settings → Devices & Services → ⋮ next to "EV Smart Charger" → Reload). The auto-dashboard rewrites the storage file with the new `_build_version`.

### "I disabled the auto-dashboard and the manual snippet shows the old UI"

The manual YAML snippet must be updated by the user on every release — it's a static string in their config. Either:

- Re-enable Step 7 (auto-dashboard) so the integration manages the resource URL for you, or
- Update your `lovelace.resources` entry to bump the `?v=` query string yourself on every upgrade.

The bundled card's `console.info` log will still show `[EVSC Dashboard] build version: unknown` for manual setups that omit `_build_version` from the card YAML — that's expected and harmless (the version is informational only at the JS layer).

## ⚠️ Known limitation — CDN / reverse proxy with "Ignore Query String"

A small minority of HA setups front their instance with a CDN configured to ignore query strings when computing cache keys (notably Cloudflare with the "Cache Everything" rule + "Ignore Query String" enabled). In that configuration, the CDN treats `?v=1.11.3&h=…` and `?v=1.11.4&h=…` as the same cache entry, and our cache busting is silently defeated.

If you administer such a setup and your users report stale dashboards after every release:

1. **Preferred**: add a Page Rule that excludes `/api/ev_smart_charger/*` from the CDN cache entirely. The bundle is ~200 KB and downloaded once per release — not worth caching at the edge for most installations.
2. **Alternative**: disable "Ignore Query String" specifically for `/api/ev_smart_charger/frontend/*`.
3. **Last resort**: purge the CDN cache manually after every upgrade. Tedious but works.

We don't ship filename-based hashing (`ev-smart-charger-dashboard-<hash>.js`) because it would force renaming the served file on every release and break manual installation snippets. The query-string approach is the canonical Home Assistant pattern (see HA community forum thread *"How can I reset a referenced resource in Lovelace"*) and works for the overwhelming majority of users — including all direct Home Assistant access, all default Ingress / Nabu Casa setups, and any reverse proxy that respects query strings.

## Final checklist (post-release)

- [ ] All assets in the bundle have either `?v=` or are inert (no external loads)
- [ ] Lovelace resource entry updated and pointing at the new `?v=&h=`
- [ ] Manual install snippets in `frontend/README.md` and root `README.md` updated to the current `VERSION`
- [ ] No service worker introduced (we don't ship one — verify nobody added one)
- [ ] No iframe wrapper introduced (the card is a pure custom element — keep it that way)
- [ ] DevTools shows new URL + new console log version on a clean browser profile
