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

window.fetch = async (url) => {
  const key = String(url);
  const body = payloads[key] ?? { items: [] };
  return {
    ok: true,
    status: 200,
    json: async () => body,
  };
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

  await tick();
  await tick();
  console.log("DOM-backed frontend navigation tests passed.");
  dom.window.close();
}

run().catch((error) => {
  console.error(error);
  dom.window.close();
  process.exitCode = 1;
});
