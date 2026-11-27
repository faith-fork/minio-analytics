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
    ...Array.from({length:27},(_,i)=>({node_name:"node02",drive_path:"/bulk"+String(i+1).padStart(2,"0"),mountpoint:"/mnt/bulk"+String(i+1).padStart(2,"0"),total_bytes:10*1024**3,used_bytes:1024**3,filesystem_total_bytes:10*1024**3,filesystem_used_bytes:1024**3,filesystem_used_pct:10,filesystem_readonly:0,availability_errors:0,io_errors:0,timeout_errors:0})),
  ],
  pools:[],erasure_sets:[],family_errors:{}
};

window.__requests = [];
window.fetch = async (url) => {
  const key = String(url);
  window.__requests.push(key);
  if (key.includes("/api/analytics/clusters/test-cluster/topology/trends")) return {ok:true,status:200,json:async()=>({sample_count:1,retention_days:3,interval_minutes:5,samples:[{snapshot_ts:"2026-11-25T10:00:00Z",drives_online:3,drives_offline:1,availability_errors:1,io_errors:2,timeout_errors:0,filesystem_used_pct:46,filesystem_weighted_used_pct:46}]})};
  if (key.includes("/api/analytics/clusters/test-cluster/network/performance-series")) return {ok:true,status:200,json:async()=>({
    cluster:{id:"test-cluster",name:"Test Cluster"},start_ts:"2026-11-27T08:00:00Z",end_ts:"2026-11-27T14:00:00Z",hours:6,retention_days:3,interval_minutes:5,selected_node:null,selected_interface:null,
    available_interfaces:[{node_name:"node01",instance:"node01:9100",interface_name:"ens3"},{node_name:"node01",instance:"node01:9100",interface_name:"ens4"},{node_name:"node02",instance:"node02:9100",interface_name:"ens3"}],
    series:[
      {snapshot_ts:"2026-11-27T13:55:00Z",node_name:"node01",instance:"node01:9100",interface_name:"ens3",rx_bytes_per_second:100,tx_bytes_per_second:50,rx_packets_per_second:10,tx_packets_per_second:5,rx_errors_per_second:0,tx_errors_per_second:0,rx_drops_per_second:0,tx_drops_per_second:0},
      {snapshot_ts:"2026-11-27T14:00:00Z",node_name:"node01",instance:"node01:9100",interface_name:"ens3",rx_bytes_per_second:200,tx_bytes_per_second:100,rx_packets_per_second:20,tx_packets_per_second:10,rx_errors_per_second:0,tx_errors_per_second:0,rx_drops_per_second:0,tx_drops_per_second:0},
      {snapshot_ts:"2026-11-27T14:00:00Z",node_name:"node01",instance:"node01:9100",interface_name:"ens4",rx_bytes_per_second:55,tx_bytes_per_second:25,rx_packets_per_second:8,tx_packets_per_second:4,rx_errors_per_second:0,tx_errors_per_second:0,rx_drops_per_second:0,tx_drops_per_second:0},
    ],
    statistics:[{node_name:"node01",instance:"node01:9100",interface_name:"ens3",sample_count:2,metrics:{rx_bytes_per_second:{average:150,minimum:100,maximum:200,latest:200,sample_count:2},tx_bytes_per_second:{average:75,minimum:50,maximum:100,latest:100,sample_count:2},rx_packets_per_second:{average:15,minimum:10,maximum:20,latest:20,sample_count:2},tx_packets_per_second:{average:7.5,minimum:5,maximum:10,latest:10,sample_count:2},rx_errors_per_second:{average:0,minimum:0,maximum:0,latest:0,sample_count:2},tx_errors_per_second:{average:0,minimum:0,maximum:0,latest:0,sample_count:2},rx_drops_per_second:{average:0,minimum:0,maximum:0,latest:0,sample_count:2},tx_drops_per_second:{average:0,minimum:0,maximum:0,latest:0,sample_count:2}}},{node_name:"node01",instance:"node01:9100",interface_name:"ens4",sample_count:1,metrics:{rx_bytes_per_second:{average:55,minimum:55,maximum:55,latest:55,sample_count:1},tx_bytes_per_second:{average:25,minimum:25,maximum:25,latest:25,sample_count:1}}}],
    sample_count:2,truncated:false,supported_metrics:[],aggregation:"per-interface only"
  })};
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
    () => window.document.querySelector('[data-general-config-tab="collection"]'),
    "Master Configuration General tab content",
  );
  assert.equal(
    window.document.querySelector('.nav-link[data-view="master-config"]').classList.contains("active"),
    true,
    "Master Configuration sidebar item should become active",
  );

  // Exercise the nested General Configuration tab and ensure its active state updates.
  window.document.querySelector('[data-general-config-tab="backups"]').click();
  await waitFor(
    () => window.document.querySelector('[data-general-config-tab="backups"][aria-selected="true"]') !== null,
    "Database Backups tab",
  );
  window.document.querySelector('[data-general-config-tab="collection"]').click();
  await waitFor(
    () => window.document.querySelector('[data-general-config-tab="collection"][aria-selected="true"]') !== null,
    "Collection Settings tab",
  );

  // Exercise the actual top-level tab click handler.
  window.document.querySelector('[data-master-config-tab="prometheus"]').click();
  await waitFor(
    () => window.document.querySelector("#pc-list"),
    "Prometheus Configuration renderer",
  );
  assert.equal(
    window.document.querySelector('[data-master-config-tab="prometheus"].active') !== null,
    true,
    "Prometheus tab should be active",
  );

  window.document.querySelector('[data-master-config-tab="backfill"]').click();
  await waitFor(
    () => window.document.querySelector("#bf-list"),
    "Historical Backfill renderer",
  );
  assert.equal(
    window.document.querySelector('[data-master-config-tab="backfill"].active') !== null,
    true,
    "Backfill tab should be active",
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
  assert.match(appSource, /Network/);
  assert.ok(appSource.includes("/network/performance-series"), "Network API route should be present");
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
  assert.match(window.document.querySelector("[data-drive-page-summary]").textContent,/1–25 of 30/);
  window.document.querySelector("[data-drive-page=next]").click();
  assert.match(window.document.querySelector("[data-drive-page-summary]").textContent,/26–30 of 30/);
  window.document.querySelector("[data-drive-page=prev]").click();
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
  await waitFor(()=>window.document.querySelectorAll("[data-drive-row][data-drive-filter-visible='1']").length===30,"reset inventory filters");
  window.document.querySelector('[data-drive-sort="path"]').click();
  assert.match(window.document.querySelector('[data-drive-sort="path"] .sort-indicator').textContent,/▲|▼/,"Selected sort column should show its direction");
  const sortedPaths=[...window.document.querySelectorAll(".drive-inventory-flat tbody tr:not(.hidden)")].map(row=>row.cells[1].textContent);
  assert.equal(sortedPaths[0],"/bulk01","Path sort should put bulk01 first");
  assert.ok(sortedPaths.indexOf("/bulk02")<sortedPaths.indexOf("/bulk10"),"Path sort should use natural numeric ordering");
  assert.match(window.document.querySelector(".drive-inventory-flat tbody tr:not(.hidden) td:nth-child(5)").textContent,/10.0 GiB/,"Capacity should use adaptive GiB units");
  assert.match(window.document.querySelector(".drive-inventory-flat tbody tr:not(.hidden) td:nth-child(6)").textContent,/1.0 GiB/,"Used space should use adaptive GiB units");
  window.document.querySelector('[data-drive-view="graphs"]').click();
  await waitFor(()=>window.document.querySelector('[data-drive-view="graphs"][aria-selected="true"]'),"return to graphs tab");
  assert.ok(window.document.querySelector("#infra-filesystem-trend"),"Graphs tab should remain available after switching");
  // Network workspace is a peer Node Infrastructure section and renders per-interface telemetry.
  await window.showClusterTopology("test-cluster", "network");
  await waitFor(() => window.document.querySelector("[data-network-node-filter]"), "Network workspace");
  assert.ok(window.document.querySelector("[data-network-interface-filter]"), "Network interface selector should render");
  assert.ok(window.document.querySelector("#network-throughput-chart"), "Throughput chart should render");
  assert.ok(window.document.querySelector("#network-packets-chart"), "Packets chart should render");
  assert.ok(window.document.querySelector("#network-errors-chart"), "Errors chart should render");
  assert.ok(window.document.querySelector("#network-drops-chart"), "Drops chart should render");
  assert.match(window.document.querySelector(".table-panel").textContent, /ens3/);


  // D1: the shared selector drives all timestamp-based Node Infrastructure charts.
  await window.showClusterTopology("test-cluster","network");
  assert.ok(window.document.querySelector("[data-historical-picker='network']"),"Network should use the shared time picker");
  assert.ok(window.document.querySelector("[data-historical-range='1h']"),"Shared quick ranges should render");
  assert.equal(window.document.querySelector("[data-network-range]"),null,"Network-local range buttons should not remain");
  assert.match(window.document.querySelector(".historical-time-picker").textContent,/5 min cadence/);
  window.document.querySelector("[data-historical-range='6h']").click();
  await waitFor(()=>window.document.querySelector("[data-historical-range='6h'].active"),"shared 6h range");
  assert.ok(window.__requests.some(url=>url.includes("/network/performance-series")&&url.includes("start_ts=")),"Network requests should use timestamps");

  const iface=window.document.querySelector("[data-network-interface-filter]");
  assert.equal(iface.options[0].value,"all","All interfaces must be the default selection");
  assert.ok([...window.document.querySelectorAll(".table-panel tbody tr")].some(row=>row.textContent.includes("ens4")),"All interfaces view must show ens4 in the summary table");
  iface.value="node01|ens3|node01:9100";
  iface.dispatchEvent(new window.Event("change",{bubbles:true}));
  await waitFor(()=>[...window.document.querySelectorAll(".table-panel tbody tr")].some(row=>row.textContent.includes("ens3")),"single interface summary");
  assert.equal([...window.document.querySelectorAll(".table-panel tbody tr")].filter(row=>row.querySelector("td")&&row.cells[0]?.textContent.includes("ens4")).length,0,"Selecting one interface filters out the others");
  const nodeSelect=window.document.querySelector("[data-network-node-filter]");
  nodeSelect.value="node02";
  nodeSelect.dispatchEvent(new window.Event("change",{bubbles:true}));
  await waitFor(()=>window.document.querySelector("[data-network-interface-filter]")?.value==="all","node change resets interface to All interfaces");

  const customFrom=window.document.querySelector("[data-historical-start]");
  const customTo=window.document.querySelector("[data-historical-end]");
  const customEndUtc=new Date(Date.now()-10*60*1000);
  const customStartUtc=new Date(customEndUtc.getTime()-60*60*1000);
  const utcToIstInput=value=>new Date(value.getTime()+5.5*60*60*1000).toISOString().slice(0,16);
  customFrom.value=utcToIstInput(customStartUtc);
  customTo.value=utcToIstInput(customEndUtc);
  window.document.querySelector("[data-action='apply-historical-range']").click();
  await waitFor(()=>window.__requests.some(url=>url.includes("/network/performance-series")&&url.includes("start_ts=")),"custom absolute range query");
  const expectedStart=new Date(customFrom.value+":00+05:30").toISOString();
  assert.ok(window.__requests.some(url=>new window.URL(url,"http://localhost").searchParams.get("start_ts")===expectedStart),"IST range should be normalized to the expected UTC timestamp");

  await window.showClusterTopology("test-cluster","nodes");
  assert.ok(window.document.querySelector("[data-historical-picker='availability']"),"Availability trends should use shared range");
  assert.equal(window.document.querySelector("[data-action='apply-infra-trends']"),null,"Legacy date controls should be removed");
  window.document.querySelector("[data-node-subtab='performance']").click();
  await waitFor(()=>window.document.querySelector("[data-historical-picker='performance']"),"Node Performance picker");
  assert.equal(window.document.querySelector("[data-dashboard-range]"),null,"Node Performance should not contain a duplicate picker");
  window.document.querySelector("[data-node-subtab='collection']").click();
  await waitFor(()=>window.document.querySelector("[data-node-subtab='collection']"),"Collection Health tab");
  assert.equal(window.document.querySelector("[data-historical-picker]"),null,"Collection Health collection-window controls remain independent");

  await window.showClusterTopology("test-cluster","drives");
  assert.ok(window.document.querySelector("[data-historical-picker='drives']"),"Drive/Filesystem charts should use shared range");
  window.document.querySelector("[data-drive-view='inventory']").click();
  await waitFor(()=>window.document.querySelector("[data-drive-view='inventory'][aria-selected='true']"),"Drive Inventory");
  assert.equal(window.document.querySelector("[data-historical-picker]"),null,"Current inventory is not filtered by chart range");

  await tick();
  await tick();
  console.log("DOM-backed frontend navigation, interface and time-range tests passed.");
  dom.window.close();
}

run().catch((error) => {
  console.error(error);
  dom.window.close();
  process.exitCode = 1;
});
