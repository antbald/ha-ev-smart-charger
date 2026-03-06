const DEFAULT_TITLE = "EV Smart Charger";
const SUPPORTED_PROFILES = ["manual", "solar_surplus"];
const DOMAIN_SUFFIXES = {
  forceCharge: ["switch", "evsc_forza_ricarica"],
  boostEnabled: ["switch", "evsc_boost_charge_enabled"],
  boostAmperage: ["number", "evsc_boost_charge_amperage"],
  boostTargetSoc: ["number", "evsc_boost_target_soc"],
  nightEnabled: ["switch", "evsc_night_smart_charge_enabled"],
  nightTime: ["time", "evsc_night_charge_time"],
  minSolarForecast: ["number", "evsc_min_solar_forecast_threshold"],
  nightAmperage: ["number", "evsc_night_charge_amperage"],
  chargingProfile: ["select", "evsc_charging_profile"],
  checkInterval: ["number", "evsc_check_interval"],
  gridImportThreshold: ["number", "evsc_grid_import_threshold"],
  gridImportDelay: ["number", "evsc_grid_import_delay"],
  surplusDropDelay: ["number", "evsc_surplus_drop_delay"],
  useHomeBattery: ["switch", "evsc_use_home_battery"],
  homeBatteryMinSoc: ["number", "evsc_home_battery_min_soc"],
  batterySupportAmperage: ["number", "evsc_battery_support_amperage"],
  priorityBalancer: ["switch", "evsc_priority_balancer_enabled"],
  smartBlocker: ["switch", "evsc_smart_charger_blocker_enabled"],
  priorityState: ["sensor", "evsc_priority_daily_state"],
  todayEvTarget: ["sensor", "evsc_today_ev_target"],
  todayHomeTarget: ["sensor", "evsc_today_home_target"],
  diagnostic: ["sensor", "evsc_diagnostic"],
  solarDiagnostic: ["sensor", "evsc_solar_surplus_diagnostic"],
};

class EvSmartChargerDashboard extends HTMLElement {
  static getStubConfig() {
    return {
      entity_prefix: "ev_smart_charger_<entry_id>",
      title: DEFAULT_TITLE,
    };
  }

  setConfig(config) {
    if (!config?.entity_prefix) {
      throw new Error("`entity_prefix` is required");
    }

    this._config = {
      title: config.title || DEFAULT_TITLE,
      entity_prefix: config.entity_prefix,
      charging_power_entity: config.charging_power_entity,
      ev_soc_entity: config.ev_soc_entity,
      home_battery_soc_entity: config.home_battery_soc_entity,
      solar_power_entity: config.solar_power_entity,
      grid_import_entity: config.grid_import_entity,
      current_entity: config.current_entity,
    };

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this.shadowRoot) {
      this.render();
    }
  }

  getCardSize() {
    return 12;
  }

  _entityId(key) {
    const [domain, suffix] = DOMAIN_SUFFIXES[key];
    return `${domain}.${this._config.entity_prefix}_${suffix}`;
  }

  _stateObj(entityId) {
    return entityId ? this._hass?.states?.[entityId] : undefined;
  }

  _integrationState(key) {
    return this._stateObj(this._entityId(key));
  }

  _displayValue(entityId, fallback = "Unavailable") {
    const stateObj = this._stateObj(entityId);
    if (!stateObj) {
      return fallback;
    }
    const unit = stateObj.attributes?.unit_of_measurement;
    if (!stateObj.state || stateObj.state === "unknown" || stateObj.state === "unavailable") {
      return fallback;
    }
    return unit ? `${stateObj.state} ${unit}` : stateObj.state;
  }

  _labelFor(entityId, fallback) {
    const stateObj = this._stateObj(entityId);
    return stateObj?.attributes?.friendly_name || fallback;
  }

  _isOn(entityId) {
    const stateObj = this._stateObj(entityId);
    return stateObj?.state === "on";
  }

  async _toggle(entityId) {
    if (!this._hass || !entityId) {
      return;
    }
    const [domain] = entityId.split(".");
    await this._hass.callService(domain, "toggle", { entity_id: entityId });
  }

  async _setNumber(entityId, value) {
    if (!this._hass || !entityId) {
      return;
    }
    await this._hass.callService("number", "set_value", {
      entity_id: entityId,
      value,
    });
  }

  async _adjustNumber(entityId, direction) {
    const stateObj = this._stateObj(entityId);
    if (!stateObj) {
      return;
    }

    const current = Number(stateObj.state);
    const step = Number(stateObj.attributes?.step ?? 1);
    const min = Number(stateObj.attributes?.min ?? current);
    const max = Number(stateObj.attributes?.max ?? current);
    const next = Math.min(max, Math.max(min, current + step * direction));
    await this._setNumber(entityId, next);
  }

  async _setSelect(entityId, option) {
    if (!this._hass || !entityId) {
      return;
    }
    await this._hass.callService("select", "select_option", {
      entity_id: entityId,
      option,
    });
  }

  async _adjustTime(entityId, stepMinutes) {
    const stateObj = this._stateObj(entityId);
    if (!stateObj || !stateObj.state || !stateObj.state.includes(":")) {
      return;
    }

    const [rawHours, rawMinutes] = stateObj.state.split(":");
    const hours = Number(rawHours);
    const minutes = Number(rawMinutes);
    const total = ((hours * 60 + minutes + stepMinutes) % 1440 + 1440) % 1440;
    const nextHours = String(Math.floor(total / 60)).padStart(2, "0");
    const nextMinutes = String(total % 60).padStart(2, "0");

    await this._hass.callService("time", "set_value", {
      entity_id: entityId,
      time: `${nextHours}:${nextMinutes}:00`,
    });
  }

  _bindEvents() {
    const root = this.shadowRoot;
    if (!root) {
      return;
    }

    root.querySelectorAll("[data-toggle]").forEach((node) => {
      node.addEventListener("click", () => this._toggle(node.dataset.toggle));
    });

    root.querySelectorAll("[data-number][data-direction]").forEach((node) => {
      node.addEventListener("click", () => {
        this._adjustNumber(node.dataset.number, Number(node.dataset.direction));
      });
    });

    root.querySelectorAll("[data-time][data-minutes]").forEach((node) => {
      node.addEventListener("click", () => {
        this._adjustTime(node.dataset.time, Number(node.dataset.minutes));
      });
    });

    root.querySelectorAll("[data-select][data-option]").forEach((node) => {
      node.addEventListener("click", () => {
        this._setSelect(node.dataset.select, node.dataset.option);
      });
    });
  }

  _renderToggle(entityId, label, hint, tone = "cyan") {
    const enabled = this._isOn(entityId);
    return `
      <button class="control-card control-toggle ${enabled ? "is-on" : ""} tone-${tone}" data-toggle="${entityId}">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <span class="switch-shell ${enabled ? "is-on" : ""}">
          <span class="switch-thumb"></span>
        </span>
      </button>
    `;
  }

  _renderStepper(entityId, label, hint, tone = "amber") {
    const stateObj = this._stateObj(entityId);
    const unit = stateObj?.attributes?.unit_of_measurement || "";
    const value = stateObj?.state || "0";
    return `
      <div class="control-card tone-${tone}">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <div class="stepper-shell">
          <button class="stepper-button" data-number="${entityId}" data-direction="-1">-</button>
          <span class="stepper-value">${value}<small>${unit}</small></span>
          <button class="stepper-button" data-number="${entityId}" data-direction="1">+</button>
        </div>
      </div>
    `;
  }

  _renderTimeControl(entityId, label, hint) {
    const value = this._stateObj(entityId)?.state || "--:--";
    return `
      <div class="control-card tone-violet">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <div class="time-shell">
          <button class="stepper-button" data-time="${entityId}" data-minutes="-15">-15m</button>
          <span class="time-value">${value.slice(0, 5)}</span>
          <button class="stepper-button" data-time="${entityId}" data-minutes="15">+15m</button>
        </div>
      </div>
    `;
  }

  _renderSelectChips(entityId, label, hint) {
    const stateObj = this._stateObj(entityId);
    const current = stateObj?.state;
    const options = (stateObj?.attributes?.options || []).filter((option) =>
      SUPPORTED_PROFILES.includes(option)
    );
    const chips = options
      .map((option) => {
        const selected = option === current ? "selected" : "";
        return `<button class="profile-chip ${selected}" data-select="${entityId}" data-option="${option}">${option.replaceAll("_", " ")}</button>`;
      })
      .join("");

    return `
      <div class="profile-card">
        <div class="control-copy">
          <span class="eyebrow">${hint}</span>
          <span class="control-label">${label}</span>
        </div>
        <div class="profile-row">${chips || '<span class="muted">No options</span>'}</div>
      </div>
    `;
  }

  _renderMetric(label, value, tone, sublabel) {
    return `
      <div class="metric-card tone-${tone}">
        <span class="eyebrow">${label}</span>
        <strong>${value}</strong>
        <span class="metric-sub">${sublabel}</span>
      </div>
    `;
  }

  _renderDiagnostics(primary, secondary) {
    return `
      <section class="diagnostic-panel">
        <div class="diag-card">
          <span class="eyebrow">Automation Diagnostic</span>
          <p>${primary?.state || "Unavailable"}</p>
        </div>
        <div class="diag-card">
          <span class="eyebrow">Solar Surplus Diagnostic</span>
          <p>${secondary?.state || "Unavailable"}</p>
        </div>
      </section>
    `;
  }

  render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    if (!this._hass) {
      this.shadowRoot.innerHTML = `
        <ha-card>
          <div class="boot-state">Waiting for Home Assistant state...</div>
        </ha-card>
      `;
      return;
    }

    const forceChargeId = this._entityId("forceCharge");
    const boostEnabledId = this._entityId("boostEnabled");
    const boostAmperageId = this._entityId("boostAmperage");
    const boostTargetSocId = this._entityId("boostTargetSoc");
    const nightEnabledId = this._entityId("nightEnabled");
    const nightTimeId = this._entityId("nightTime");
    const minSolarForecastId = this._entityId("minSolarForecast");
    const nightAmperageId = this._entityId("nightAmperage");
    const chargingProfileId = this._entityId("chargingProfile");
    const checkIntervalId = this._entityId("checkInterval");
    const gridImportThresholdId = this._entityId("gridImportThreshold");
    const gridImportDelayId = this._entityId("gridImportDelay");
    const surplusDropDelayId = this._entityId("surplusDropDelay");
    const useHomeBatteryId = this._entityId("useHomeBattery");
    const homeBatteryMinSocId = this._entityId("homeBatteryMinSoc");
    const batterySupportAmperageId = this._entityId("batterySupportAmperage");
    const priorityBalancerId = this._entityId("priorityBalancer");
    const smartBlockerId = this._entityId("smartBlocker");

    const priorityState = this._integrationState("priorityState");
    const todayEvTarget = this._integrationState("todayEvTarget");
    const todayHomeTarget = this._integrationState("todayHomeTarget");
    const diagnostic = this._integrationState("diagnostic");
    const solarDiagnostic = this._integrationState("solarDiagnostic");

    const chargingPower = this._displayValue(this._config.charging_power_entity, "Live feed optional");
    const evSoc = this._displayValue(this._config.ev_soc_entity, "Add `ev_soc_entity`");
    const homeBatterySoc = this._displayValue(
      this._config.home_battery_soc_entity,
      "Add `home_battery_soc_entity`",
    );
    const solarPower = this._displayValue(this._config.solar_power_entity, "Add `solar_power_entity`");
    const gridImport = this._displayValue(this._config.grid_import_entity, "Add `grid_import_entity`");
    const chargerCurrent = this._displayValue(this._config.current_entity, "Add `current_entity`");

    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="dashboard-shell">
          <div class="aurora aurora-a"></div>
          <div class="aurora aurora-b"></div>
          <div class="grain"></div>

          <header class="hero-card">
            <div class="hero-copy">
              <span class="eyebrow">Custom Integration Control Surface</span>
              <h1>${this._config.title}</h1>
              <p>Single-column EV charging control with native Home Assistant service calls, stacked modules, and live operational telemetry.</p>
            </div>
            <div class="hero-grid">
              ${this._renderMetric("Charging Power", chargingPower, "cyan", this._labelFor(this._config.charging_power_entity, "Live power"))}
              ${this._renderMetric("EV State Of Charge", evSoc, "violet", this._labelFor(this._config.ev_soc_entity, "Vehicle battery"))}
              ${this._renderMetric("Home Battery", homeBatterySoc, "lime", this._labelFor(this._config.home_battery_soc_entity, "Storage reserve"))}
              ${this._renderMetric("Grid Import", gridImport, "rose", this._labelFor(this._config.grid_import_entity, "Import threshold"))}
              ${this._renderMetric("Solar Power", solarPower, "amber", this._labelFor(this._config.solar_power_entity, "PV feed"))}
              ${this._renderMetric("Charge Current", chargerCurrent, "teal", this._labelFor(this._config.current_entity, "Wallbox current"))}
            </div>
          </header>

          <section class="spotlight-panel">
            <div class="spotlight-main">
              <span class="eyebrow">Priority Engine</span>
              <strong>${priorityState?.state || "Unavailable"}</strong>
              <span class="metric-sub">Dynamic target arbitration between EV demand and home energy reserve.</span>
            </div>
            <div class="spotlight-side">
              <div class="target-chip">
                <span class="eyebrow">Today EV Target</span>
                <strong>${todayEvTarget?.state || "--"}</strong>
              </div>
              <div class="target-chip">
                <span class="eyebrow">Today Home Target</span>
                <strong>${todayHomeTarget?.state || "--"}</strong>
              </div>
            </div>
          </section>

          <section class="module-grid">
            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">Override Layer</span>
                <h2>Main Controls</h2>
              </div>
              ${this._renderToggle(forceChargeId, "Force Charge", "Override All", "rose")}
              ${this._renderSelectChips(chargingProfileId, "Charging Profile", "Mode Strategy")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">Fast Override</span>
                <h2>Boost Charge</h2>
              </div>
              ${this._renderToggle(boostEnabledId, "Boost Session", "High Priority", "amber")}
              ${this._renderStepper(boostAmperageId, "Boost Amperage", "Output", "amber")}
              ${this._renderStepper(boostTargetSocId, "Boost Target SOC", "Auto Stop", "lime")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">Forecast Driven</span>
                <h2>Night Smart Charge</h2>
              </div>
              ${this._renderToggle(nightEnabledId, "Enable Night Smart Charge", "Night Window", "violet")}
              ${this._renderTimeControl(nightTimeId, "Start Time", "Schedule")}
              ${this._renderStepper(minSolarForecastId, "Min Solar Forecast", "Tomorrow Threshold", "cyan")}
              ${this._renderStepper(nightAmperageId, "Night Charge Amperage", "Overnight Current", "teal")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">Adaptive Curve</span>
                <h2>Solar Surplus</h2>
              </div>
              ${this._renderStepper(checkIntervalId, "Check Interval", "Polling", "cyan")}
              ${this._renderStepper(gridImportThresholdId, "Grid Import Threshold", "Clamp", "rose")}
              ${this._renderStepper(gridImportDelayId, "Grid Import Delay", "Debounce", "violet")}
              ${this._renderStepper(surplusDropDelayId, "Surplus Drop Delay", "Cloud Filter", "amber")}
              ${this._renderToggle(useHomeBatteryId, "Use Home Battery", "Fallback Reserve", "lime")}
              ${this._renderStepper(homeBatteryMinSocId, "Home Battery Min SOC", "Reserve Floor", "lime")}
              ${this._renderStepper(batterySupportAmperageId, "Battery Support Amperage", "Assist Output", "teal")}
            </section>

            <section class="module-panel">
              <div class="module-header">
                <span class="kicker">Safety Nets</span>
                <h2>Protection Layer</h2>
              </div>
              ${this._renderToggle(priorityBalancerId, "Priority Balancer", "Target Arbitration", "cyan")}
              ${this._renderToggle(smartBlockerId, "Smart Charger Blocker", "Nighttime Lockout", "rose")}
            </section>
          </section>

          ${this._renderDiagnostics(diagnostic, solarDiagnostic)}
        </div>
      </ha-card>
      <style>
        :host {
          display: block;
        }

        * {
          box-sizing: border-box;
        }

        ha-card {
          overflow: hidden;
          border: 0;
          border-radius: 32px;
          background:
            radial-gradient(circle at top right, rgba(49, 216, 255, 0.18), transparent 36%),
            radial-gradient(circle at left center, rgba(122, 58, 255, 0.22), transparent 30%),
            linear-gradient(145deg, #060816 0%, #0b1022 42%, #111323 100%);
          box-shadow:
            0 32px 80px rgba(0, 0, 0, 0.42),
            inset 0 1px 0 rgba(255, 255, 255, 0.05);
          color: #f5f7ff;
        }

        .dashboard-shell {
          position: relative;
          padding: 28px;
          display: grid;
          gap: 22px;
          min-height: 400px;
        }

        .aurora {
          position: absolute;
          inset: auto;
          filter: blur(36px);
          opacity: 0.9;
          pointer-events: none;
          animation: floatGlow 9s ease-in-out infinite;
        }

        .aurora-a {
          width: 180px;
          height: 180px;
          top: -40px;
          right: -30px;
          background: radial-gradient(circle, rgba(26, 229, 255, 0.28), transparent 65%);
        }

        .aurora-b {
          width: 220px;
          height: 220px;
          bottom: 10%;
          left: -40px;
          background: radial-gradient(circle, rgba(169, 88, 255, 0.22), transparent 70%);
          animation-delay: -3s;
        }

        .grain {
          position: absolute;
          inset: 0;
          pointer-events: none;
          opacity: 0.08;
          background-image:
            radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.35) 0, transparent 18%),
            radial-gradient(circle at 80% 35%, rgba(255, 255, 255, 0.28) 0, transparent 12%),
            radial-gradient(circle at 40% 75%, rgba(255, 255, 255, 0.22) 0, transparent 14%);
          mix-blend-mode: screen;
        }

        .hero-card,
        .module-panel,
        .spotlight-panel,
        .diagnostic-panel {
          position: relative;
          z-index: 1;
        }

        .hero-card {
          display: grid;
          gap: 18px;
          grid-template-columns: 1fr;
          padding: 24px;
          border-radius: 28px;
          background: linear-gradient(135deg, rgba(14, 18, 41, 0.84), rgba(16, 29, 58, 0.72));
          border: 1px solid rgba(139, 162, 255, 0.16);
          backdrop-filter: blur(14px);
        }

        .hero-copy h1 {
          margin: 6px 0 10px;
          font-size: clamp(2rem, 4vw, 3.4rem);
          line-height: 0.95;
          letter-spacing: -0.04em;
        }

        .hero-copy p {
          margin: 0;
          max-width: 44ch;
          color: rgba(223, 229, 255, 0.8);
          line-height: 1.55;
        }

        .hero-grid {
          display: grid;
          gap: 12px;
          grid-template-columns: 1fr;
        }

        .eyebrow,
        .kicker {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 0.73rem;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: rgba(196, 207, 255, 0.66);
        }

        .metric-card,
        .target-chip,
        .diag-card,
        .control-card,
        .profile-card {
          border-radius: 22px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          background: linear-gradient(180deg, rgba(17, 24, 44, 0.92), rgba(10, 14, 28, 0.94));
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
        }

        .metric-card {
          min-height: 108px;
          padding: 16px;
          display: grid;
          gap: 10px;
          align-content: space-between;
          overflow: hidden;
          position: relative;
        }

        .metric-card::after {
          content: "";
          position: absolute;
          inset: auto -18% -40% auto;
          width: 90px;
          height: 90px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(255, 255, 255, 0.12), transparent 65%);
          opacity: 0.8;
        }

        .metric-card strong,
        .spotlight-main strong,
        .target-chip strong {
          font-size: clamp(1.15rem, 2vw, 1.8rem);
          line-height: 1;
          letter-spacing: -0.03em;
        }

        .metric-sub {
          color: rgba(214, 221, 255, 0.76);
          font-size: 0.82rem;
        }

        .spotlight-panel {
          display: grid;
          grid-template-columns: 1fr;
          gap: 16px;
        }

        .spotlight-main {
          padding: 22px;
          border-radius: 26px;
          background:
            linear-gradient(135deg, rgba(0, 197, 255, 0.14), rgba(134, 77, 255, 0.08)),
            rgba(7, 13, 29, 0.9);
          border: 1px solid rgba(76, 214, 255, 0.18);
          display: grid;
          gap: 12px;
        }

        .spotlight-side {
          display: grid;
          gap: 16px;
        }

        .target-chip,
        .diag-card {
          padding: 18px;
          display: grid;
          gap: 10px;
        }

        .module-grid {
          display: grid;
          gap: 18px;
          grid-template-columns: 1fr;
        }

        .module-panel {
          display: grid;
          gap: 14px;
          padding: 20px;
          border-radius: 28px;
          background:
            linear-gradient(180deg, rgba(12, 17, 35, 0.92), rgba(8, 12, 24, 0.96)),
            rgba(8, 12, 24, 0.9);
          border: 1px solid rgba(255, 255, 255, 0.06);
        }

        .module-header {
          display: grid;
          gap: 6px;
          margin-bottom: 2px;
        }

        .module-header h2 {
          margin: 0;
          font-size: 1.45rem;
          line-height: 1;
          letter-spacing: -0.03em;
        }

        .control-card,
        .profile-card {
          width: 100%;
          padding: 14px 16px;
          display: grid;
          gap: 14px;
        }

        .control-toggle {
          cursor: pointer;
          appearance: none;
          color: inherit;
          text-align: left;
          background:
            linear-gradient(180deg, rgba(17, 24, 44, 0.94), rgba(10, 14, 28, 0.98));
        }

        .control-toggle.is-on {
          border-color: rgba(80, 228, 255, 0.26);
          box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.04),
            0 0 0 1px rgba(80, 228, 255, 0.05),
            0 12px 24px rgba(0, 0, 0, 0.18);
        }

        .control-copy {
          display: grid;
          gap: 6px;
        }

        .control-label {
          font-size: 1rem;
          line-height: 1.2;
          font-weight: 700;
          color: #f6f8ff;
        }

        .switch-shell {
          justify-self: end;
          width: 66px;
          height: 36px;
          border-radius: 999px;
          padding: 4px;
          background: rgba(255, 255, 255, 0.12);
          transition: background 180ms ease;
        }

        .switch-shell.is-on {
          background: rgba(30, 201, 255, 0.36);
        }

        .switch-thumb {
          display: block;
          width: 28px;
          height: 28px;
          border-radius: 50%;
          background: white;
          transform: translateX(0);
          transition: transform 180ms ease;
          box-shadow: 0 6px 16px rgba(0, 0, 0, 0.24);
        }

        .switch-shell.is-on .switch-thumb {
          transform: translateX(30px);
        }

        .stepper-shell,
        .time-shell {
          display: grid;
          grid-template-columns: auto 1fr auto;
          gap: 10px;
          align-items: center;
        }

        .stepper-button,
        .profile-chip {
          cursor: pointer;
          appearance: none;
          border: 0;
          color: inherit;
          border-radius: 16px;
          background: rgba(255, 255, 255, 0.08);
          font: inherit;
          transition: transform 160ms ease, background 160ms ease, box-shadow 160ms ease;
        }

        .stepper-button {
          padding: 12px 14px;
          font-weight: 700;
          min-width: 56px;
        }

        .stepper-button:hover,
        .profile-chip:hover {
          transform: translateY(-1px);
          background: rgba(255, 255, 255, 0.13);
        }

        .stepper-value,
        .time-value {
          display: flex;
          align-items: baseline;
          justify-content: center;
          gap: 6px;
          min-height: 48px;
          padding: 0 14px;
          border-radius: 16px;
          background: rgba(255, 255, 255, 0.05);
          font-weight: 800;
          font-size: 1.15rem;
          letter-spacing: -0.02em;
        }

        .stepper-value small {
          color: rgba(214, 221, 255, 0.68);
          font-size: 0.8rem;
          font-weight: 600;
        }

        .profile-row {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
        }

        .profile-chip {
          padding: 10px 14px;
          text-transform: capitalize;
        }

        .profile-chip.selected {
          background: linear-gradient(135deg, rgba(18, 203, 255, 0.35), rgba(130, 92, 255, 0.3));
          box-shadow: 0 10px 24px rgba(34, 132, 255, 0.18);
        }

        .diagnostic-panel {
          display: grid;
          gap: 16px;
          grid-template-columns: 1fr;
        }

        .diag-card p {
          margin: 0;
          color: rgba(225, 232, 255, 0.84);
          line-height: 1.55;
          white-space: pre-wrap;
        }

        .boot-state,
        .muted {
          padding: 24px;
          color: rgba(225, 232, 255, 0.72);
        }

        .tone-cyan { box-shadow: inset 0 0 0 1px rgba(0, 224, 255, 0.05); }
        .tone-violet { box-shadow: inset 0 0 0 1px rgba(157, 92, 255, 0.05); }
        .tone-lime { box-shadow: inset 0 0 0 1px rgba(86, 236, 134, 0.05); }
        .tone-rose { box-shadow: inset 0 0 0 1px rgba(255, 88, 133, 0.05); }
        .tone-amber { box-shadow: inset 0 0 0 1px rgba(255, 188, 40, 0.05); }
        .tone-teal { box-shadow: inset 0 0 0 1px rgba(22, 228, 194, 0.05); }

        @keyframes floatGlow {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
          50% { transform: translate3d(0, -10px, 0) scale(1.04); }
        }

        @media (max-width: 980px) {
          .hero-card,
          .spotlight-panel,
          .module-grid,
          .diagnostic-panel {
            grid-template-columns: 1fr;
          }

          .dashboard-shell {
            padding: 18px;
          }

          .hero-grid {
            grid-template-columns: 1fr;
          }
        }
      </style>
    `;

    this._bindEvents();
  }
}

customElements.define("ev-smart-charger-dashboard", EvSmartChargerDashboard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ev-smart-charger-dashboard",
  name: "EV Smart Charger Dashboard",
  description: "Animated native control surface for the EV Smart Charger integration.",
});
