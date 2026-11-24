/* Optional dashboard builder. All dashboard writes use the active admin's
 * authenticated Home Assistant frontend session and native Lovelace commands. */
export async function buildDashboard(hass, settings) {
  if (!hass.user?.is_admin) throw new Error("An administrator must create a dashboard.");
  const path = settings?.dashboardPath;
  if (path !== "ev-smart-charger" || !Array.isArray(settings.layout?.views)) {
    throw new Error("Dashboard setup data is unavailable.");
  }

  const dashboards = await hass.callWS({ type: "lovelace/dashboards/list" });
  if (!Array.isArray(dashboards)) throw new Error("Could not verify existing dashboards.");
  if (dashboards.some(({ url_path }) => url_path === path) || hass.panels?.[path]) {
    return { created: false, path };
  }

  // The native collection rejects a duplicate URL path, including a dashboard
  // registered by another browser after the list check. Never save on failure.
  const created = await hass.callWS({
    type: "lovelace/dashboards/create", url_path: path,
    title: settings.title, icon: settings.icon,
    show_in_sidebar: true, require_admin: false,
  });
  if (created?.url_path !== path || typeof created?.id !== "string" || !created.id) {
    throw new Error("Could not verify the newly created dashboard. Check Settings > Dashboards.");
  }

  // The native registry ID can differ from the URL slug (for example,
  // ev_smart_charger on current HA). Re-list to confirm the live renderer
  // belongs to the exact entry returned by create, never a racing entry.
  const liveDashboards = await hass.callWS({ type: "lovelace/dashboards/list" });
  const matches = Array.isArray(liveDashboards)
    ? liveDashboards.filter(({ url_path }) => url_path === path) : [];
  if (matches.length !== 1 || matches[0].id !== created.id) {
    throw new Error("The new dashboard could not be verified. Check Settings > Dashboards.");
  }

  // Guard against attaching initial content to a dashboard that another admin
  // has already edited. Only native “config_not_found” means it is still empty.
  try {
    await hass.callWS({ type: "lovelace/config", url_path: path, force: true });
    return { created: false, path };
  } catch (error) {
    if (error?.code !== "config_not_found") throw error;
  }
  try {
    await hass.callWS({ type: "lovelace/config/save", url_path: path, config: settings.layout });
  } catch (error) {
    throw new Error("Home Assistant created the dashboard but did not save its initial view. Open Settings > Dashboards to finish setup.");
  }
  return { created: true, path };
}

class EVSCDashboardBuilder extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (this.isConnected && !this._button) this._render();
  }

  connectedCallback() { this._render(); }

  _render() {
    if (this._button) return;
    const root = this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = "main{max-width:38rem;margin:2rem auto;padding:1.25rem;color:var(--primary-text-color)} button{font:inherit;padding:.6rem 1rem} a{color:var(--primary-color)}";
    const main = document.createElement("main");
    const title = document.createElement("h1");
    title.textContent = "EV Smart Charger dashboard";
    const copy = document.createElement("p");
    copy.textContent = "Create the optional sidebar dashboard with the EV Smart Charger card and sensors mapped to this device. Existing dashboards are not changed.";
    const status = document.createElement("p");
    status.setAttribute("role", "status");
    this._button = document.createElement("button");
    this._button.textContent = "Create dashboard";
    this._button.addEventListener("click", async () => {
      this._button.disabled = true;
      status.textContent = "Checking Home Assistant dashboards…";
      try {
        const result = await buildDashboard(this._hass, this.panel?.config);
        status.textContent = result.created ? "Dashboard created. " : "Dashboard already exists and was left unchanged. ";
        const link = document.createElement("a");
        link.href = "/" + result.path;
        link.textContent = "Open dashboard";
        status.append(link);
      } catch (error) {
        status.textContent = error?.message || "Dashboard creation could not be verified. Open Settings > Dashboards.";
        this._button.disabled = false;
      }
    });
    main.append(title, copy, this._button, status);
    root.append(style, main);
  }
}

if (!customElements.get("evsc-dashboard-builder")) {
  customElements.define("evsc-dashboard-builder", EVSCDashboardBuilder);
}
