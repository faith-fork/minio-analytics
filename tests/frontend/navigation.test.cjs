"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "app/static/index.html"), "utf8")
  .replace(/<script[^>]*src="https?:\/\/[^"]+"[^>]*><\/script>/g, "")
  .replace(/<script[^>]*src="\/static\/[^"]+"[^>]*><\/script>/g, "");

const dom = new JSDOM(html, {
  url: "https://minio-analytics.test/",
  runScripts: "outside-only",
  pretendToBeVisual: true,
});
const { window } = dom;
window.URL.createObjectURL = () => "blob:drive-inventory-test";
window.URL.revokeObjectURL = () => {};
window.HTMLAnchorElement.prototype.click = function () { window.__lastDownload = this.download; window.__lastDownloadHref = this.href; };

const payloads = {
  "/api/auth/me": { user: { username: "test-admin", role: "admin", is_master_admin: true } },
  "/api/analytics/overview": {
    capacity_bytes: { raw_total_bytes: 0, raw_free_bytes: 0, usable_total_bytes: 0 },
    nodes: { online: 0, offline: 0 },
    cluster_items: [],
    clusters: { available: 0, total: 0, unavailable: 0 },
    inventory: { active_buckets: 0, unassigned_buckets: 0, active_tenants: 0 },
  },
  "/api/analytics/clusters": { items: [] },
  "/api/master-admin/settings": {
    settings: { node_interval_minutes: 5, telemetry_retention_days: 3, daily_collection_time: "00:15" },
    telemetry_usage: {},
  },
  "/api/master-admin/backups?limit=10&offset=0": { items: [], total_count: 0 },
  "/api/master-admin/prometheus-connections": { items: [] },
  "/api/master-admin/backfill-jobs": { items: [] },
};

const topologyPayload = {
  cluster:{id:"test-cluster",name:"Test Cluster"},
  nodes:[
    {node_name:"node01",drives_online:2,drives_offline:0},
    {node_name:"node02",drives_online:1,drives_offline:1},
  ],
  drives:[
    {node_name:"node01",drive_path:"/data1",mountpoint:"/mnt/data1",total_bytes:1000,used_bytes:500,filesystem_total_bytes:1000,filesystem_used_bytes:450,filesystem_used_pct:45,filesystem_readonly:0,availability_errors:0,io_errors:0,timeout_errors:0},
    {node_name:"node01",drive_path:"/data2",mountpoint:"/mnt/data2",total_bytes:1000,used_bytes:600,filesystem_total_bytes:1000,filesystem_used_bytes:600,filesystem_used_pct:60,filesystem_readonly:1,availability_errors:1,io_errors:0,timeout_errors:0},
    {node_name:"node02",drive_path:"/data3",mountpoint:"/mnt/data3",total_bytes:1000,used_bytes:400,filesystem_total_bytes:1000,filesystem_used_bytes:350,filesystem_used_pct:35,filesystem_readonly:null,availability_errors:0,io_errors:2,timeout_errors:0},
  ],
  pools:[],erasure_sets:[],family_errors:{}
};

window.fetch = async (url) => {
  const key = String(url);
  if (key.includes("/api/analytics/clusters/test-cluster/topology/trends")) return {ok:true,status:200,json:async()=>({sample_count:1,samples:[{snapshot_ts:"2026-11-25T10:00:00Z",drives_online:3,drives_offline:1,availability_errors:1,io_errors:2,timeout_errors:0,filesystem_used_pct:46,filesystem_weighted_used_pct:46}]})};
  if (key.includes("/api/analytics/clusters/test-cluster/topology")) return {ok:true,status:200,json:async()=>topologyPayload};
  const body = payloads[key] ?? { items: [] };
  return {ok:true,status:200,json:async()=>body};
};

function tick() {
  return new Promise((resolve) => window.setTimeout(resolve, 0));
}

async function waitFor(predicate, description) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (predicate()) return;
    await tick();
  }
  assert.fail("Timed out waiting for " + description);
}

async function run() {
  window.eval(fs.readFileSync(path.join(root, "app/static/app.js"), "utf8"));
  window.eval(fs.readFileSync(path.join(root, "app/static/prometheus-connections.js"), "utf8"));
  window.eval(fs.readFileSync(path.join(root, "app/static/backfill-jobs.js"), "utf8"));

  await waitFor(
    () => window.document.querySelector("#content .metric-grid") !== null,
    "initial authenticated dashboard render",
  );

  // Exercise the real delegated sidebar click and the multi-element nav selector.
  window.document.querySelector('.nav-link[data-view="master-config"]').click();
  await waitFor(
    () => window.document.querySelector('[data-master-config-tab="general"]'),
    "Master Configuration General tab",
  );
  assert.equal(
    window.document.querySelector('.nav-link[data-view="master-config"]').classList.contains("active"),
    true,
    "Master Configuration sidebar item should become active",
  );

  // Exercise the actual top-level tab click handler.
  window.document.querySelector('[data-master-config-tab="prometheus"]').click();
  await waitFor(
    () => window.document.querySelector("#pc-list"),
    "Prometheus Configuration renderer",
  );

  window.document.querySelector('[data-master-config-tab="backfill"]').click();
  await waitFor(
    () => window.document.querySelector("#bf-list"),
    "Historical Backfill renderer",
  );

  // Legacy view aliases must route to their corresponding workspace tabs.
  window.setView("master-admin");
  await waitFor(
    () => window.document.querySelector('[data-master-config-tab="general"].active') && window.document.querySelector(".config-settings-grid"),
    "legacy Master Admin alias",
  );

  window.setView("prometheus-connections");
  await waitFor(
    () => window.document.querySelector('[data-master-config-tab="prometheus"].active') && window.document.querySelector("#pc-list .empty-state"),
    "legacy Prometheus Connections alias",
  );

  window.setView("backfill-jobs");
  await waitFor(
    () => window.document.querySelector('[data-master-config-tab="backfill"].active') && window.document.querySelector("#bf-list .bf-empty-state"),
    "legacy Backfill Jobs alias",
  );

  // Infrastructure workspace labels and overview trend panels are kept separate
  // from collection reliability so CPU/memory telemetry stays in Node Infrastructure.
  const appSource = fs.readFileSync(path.join(root, "app/static/app.js"), "utf8");
  assert.match(appSource, /Node Health & Performance/);
  assert.match(appSource, /Drives & Filesystems/);
  assert.match(appSource, /CPU & Memory Trends/);
  assert.match(appSource, /infra-overview-cpu/);
  assert.match(appSource, /infra-overview-memory/);
  assert.match(appSource, /performanceTrendPanel/);
  assert.match(appSource, /section==="nodes"\|\|section==="infra-overview"/);

  // Drives & Filesystems retains Graphs and presents the inventory as a sortable flat table.
  await window.showClusterTopology("test-cluster", "drives");
  await waitFor(() => window.document.querySelector('[data-drive-view="graphs"]'), "Drives graphs workspace");
  assert.equal(window.document.querySelector('[data-drive-view="graphs"]').getAttribute("aria-selected"), "true");
  assert.ok(window.document.querySelector("#infra-drive-availability"), "Graphs tab should retain drive availability panel");
  window.document.querySelector('[data-drive-view="inventory"]').click();
  await waitFor(() => window.document.querySelector('[data-drive-node-filter]'), "Drive Inventory tab");
  assert.ok(window.document.querySelector(".drive-inventory-flat"), "Inventory should use a unified flat table");
  assert.equal(window.document.querySelectorAll("[data-drive-row]").length, 30, "All drives should be rows");
  assert.ok(window.document.querySelector("[data-drive-export]"), "Inventory should provide CSV export");
  assert.ok(window.document.querySelector("[data-drive-page-size]"), "Inventory should provide page-size selection");
  assert.ok(window.document.querySelector("[data-drive-sort=capacity]"), "Capacity should be sortable");
  assert.match(window.document.querySelector(".drive-inventory-summary").textContent, /30/);
  assert.match(window.document.querySelector("[data-drive-page-summary]").textContent,/1–25 of 30/);\n  window.document.querySelector("[data-drive-page=next]").click();\n  assert.match(window.document.querySelector("[data-drive-page-summary]").textContent,/26–30 of 30/);\n  window.document.querySelector("[data-drive-page=prev]").click();
  assert.ok(window.document.querySelector('[data-drive-row][data-drive-status="readonly"]'));
  assert.ok(window.document.querySelector('[data-drive-row][data-drive-error="1"]'));

  const nodeFilter=window.document.querySelector("[data-drive-node-filter]");
  nodeFilter.value="node01";nodeFilter.dispatchEvent(new window.Event("change",{bubbles:true}));
  await waitFor(()=>window.document.querySelectorAll("[data-drive-row][data-drive-filter-visible='1']").length===2,"node selector filtering");
  assert.match(window.document.querySelector("[data-drive-page-summary]").textContent,/2 drives/);
  const search=window.document.querySelector("[data-drive-search]");
  search.value="/data2";search.dispatchEvent(new window.Event("input",{bubbles:true}));
  assert.equal(window.document.querySelectorAll("[data-drive-row][data-drive-filter-visible='1']").length,1,"Search should filter drive rows");
  assert.ok(window.document.querySelector("[data-drive-row][data-drive-filter-visible='1']").textContent.includes("/data2"));
  const stateFilter=window.document.querySelector("[data-drive-state-filter]");
  stateFilter.value="readonly";stateFilter.dispatchEvent(new window.Event("change",{bubbles:true}));
  await waitFor(()=>window.document.querySelectorAll("[data-drive-row][data-drive-filter-visible='1']").length===1,"filesystem state filter");
  assert.match(window.document.querySelector("[data-drive-row][data-drive-filter-visible='1']").textContent,/Read-only/);
  window.document.querySelector("[data-drive-export]").click();
  assert.equal(window.__lastDownload,"drive-inventory-"+new Date().toISOString().slice(0,10)+".csv","Export should download filtered inventory");
  stateFilter.value="errors";stateFilter.dispatchEvent(new window.Event("change",{bubbles:true}));
  await waitFor(()=>window.document.querySelectorAll("[data-drive-row][data-drive-filter-visible='1']").length===1,"drive error filter");
  assert.ok(/1 \/ 0 \/ 0|0 \/ 2 \/ 0/.test(window.document.querySelector("[data-drive-row][data-drive-filter-visible='1']").textContent),"Error filter should include a drive with reported errors");
  search.value="";search.dispatchEvent(new window.Event("input",{bubbles:true}));
  stateFilter.value="all";stateFilter.dispatchEvent(new window.Event("change",{bubbles:true}));
  const nodeFilterReset=window.document.querySelector("[data-drive-node-filter]");nodeFilterReset.value="all";nodeFilterReset.dispatchEvent(new window.Event("change",{bubbles:true}));
  await waitFor(()=>window.document.querySelectorAll("[data-drive-row][data-drive-filter-visible='1']").length===3,"reset inventory filters");
  window.document.querySelector('[data-drive-sort="path"]').click();
  assert.match(window.document.querySelector('[data-drive-sort="path"] .sort-indicator').textContent,/▲|▼/,"Selected sort column should show its direction");
  assert.match(window.document.querySelector(".drive-inventory-flat tbody tr:not(.hidden) td:nth-child(2)").textContent,/\/data1/,"Sorting by path should reorder visible rows");
  window.document.querySelector('[data-drive-view="graphs"]').click();
  await waitFor(()=>window.document.querySelector('[data-drive-view="graphs"][aria-selected="true"]'),"return to graphs tab");
  assert.ok(window.document.querySelector("#infra-filesystem-trend"),"Graphs tab should remain available after switching");
  await tick();
  await tick();
  console.log("DOM-backed frontend navigation and drive inventory tests passed.");
  dom.window.close();
}

run().catch((error) => {
  console.error(error);
  dom.window.close();
  process.exitCode = 1;
});
