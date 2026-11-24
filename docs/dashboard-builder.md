# Lovelace dashboard builder

- The config flow defaults to no dashboard. Only a new opt-in stages the link
  in HA Notifications; saved values from versions with a default of on are
  not treated as consent. The explicit build button can stage the same link
  later. It cannot call any EV charging service.
- The hidden native custom panel requires an administrator. The actual create
  and initial save are ordinary Lovelace WebSocket calls from the administrator
  who clicks **Create dashboard**, not a server-side impersonation. The
  integration does not instantiate a separate dashboard collection, open
  Lovelace storage, or replace its live renderer.
- The builder checks that the path is free, uses the native create command's
  duplicate check, and only initializes a freshly returned matching dashboard
  which HA reports as not configured. It will not repair or overwrite an
  existing panel. If the first save fails, a blank dashboard may remain; finish
  or remove it through **Settings → Dashboards**.
- Existing dashboards and their card configuration survive upgrades,
  reconfiguration, reload, and removal. Only the integration's isolated
  builder panel is removed on unload. Storage-mode resource registration is
  separate; YAML users can add the bundled resource and card manually.

## Regression checks

Run `pytest tests/test_dashboard_builder.py` with the repository's test
requirements, and `node --test tests/dashboard-builder.test.mjs`.
The Python test exercises registered Lovelace WebSocket commands through
Home Assistant Core with administrator and read-only accounts. The
JavaScript test asserts that duplicates, permission errors and failed
creation never fall through to the save.

On current HA/Python, charger service timeouts use the Python standard library.
The inherited `async_timeout` dependency is only used by the pinned Python
3.10 test environment and is not required on a stock modern HA install.
