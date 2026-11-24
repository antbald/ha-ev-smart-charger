import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

globalThis.HTMLElement = class {};
globalThis.customElements = {get() {}, define() {}};
const code = await readFile(new URL("../custom_components/ev_smart_charger/frontend/evsc-dashboard-builder.js", import.meta.url));
const {buildDashboard} = await import("data:text/javascript;base64," + code.toString("base64"));
const settings = {dashboardPath:"ev-smart-charger",title:"EV Smart Charger", icon:"mdi:ev-station",layout:{views:[]}};
const path = settings.dashboardPath;

function client(responses, is_admin = true, panels = {}) {
  const sent = [];
  return {sent,hass:{user:{is_admin},panels,async callWS(msg) {
    sent.push(msg);
    const response = responses.shift();
    if (response instanceof Error) throw response;
    assert.notEqual(response, undefined);
    return response;
  }}};
}

const names = sent => sent.map(({type}) => type);
const fail = (code) => Object.assign(new Error(code),{code});

test("native two-step create checks blank dashboard first, then saves exact layout", async () => {
  const {hass,sent} = client([[],{url_path:path,id:path},fail("config_not_found"),null]);
  assert.deepEqual(await buildDashboard(hass,settings),{created:true,path});
  assert.deepEqual(names(sent),["lovelace/dashboards/list","lovelace/dashboards/create","lovelace/config","lovelace/config/save"]);
  assert.equal(sent[3].config,settings.layout);
});

test("non-admin and invalid settings never send commands",async () => {
  const a=client([],false), b=client([]);
  await assert.rejects(buildDashboard(a.hass,settings),/administrator/);
  await assert.rejects(buildDashboard(b.hass,undefined),/unavailable/);
  assert.deepEqual(a.sent,[]);
  assert.deepEqual(b.sent,[]);
});

test("an existing dashboard, a path race or a recently edited view are never saved over",async () => {
  const a=client([[{url_path:path,id:path}]]), b=client([[],fail("invalid_format")]), c=client([[],{url_path:path,id:path},{views:[{}]}]);
  assert.deepEqual(await buildDashboard(a.hass,settings),{created:false,path});
  await assert.rejects(buildDashboard(b.hass,settings),/invalid_format/);
  assert.deepEqual(await buildDashboard(c.hass,settings),{created:false,path});
  for(const x of [a,b,c]) assert.equal(names(x.sent).includes("lovelace/config/save"),false);
});

test("unexpected snapshot or save failure never retries or pretends creation completed",async () => {
  const a=client([[],{url_path:path,id:path},fail("unknown_error")]), b=client([[],{url_path:path,id:path},fail("config_not_found"),fail("unknown_error")]);
  await assert.rejects(buildDashboard(a.hass,settings),/unknown_error/);
  await assert.rejects(buildDashboard(b.hass,settings),/did not save/);
  assert.equal(names(a.sent).includes("lovelace/config/save"),false);
  assert.equal(names(b.sent).filter(x=>x==="lovelace/config/save").length,1);
});
