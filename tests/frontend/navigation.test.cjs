"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "app/static/index.html"), "utf8")
  .replace(/<script[^>]*src="https?:\\/\\/[^"]+[^>]*><\\/script>/g, "")
  .replace(/<script[^>]*src="\\/static\\/[^"]+[^>]*><\\/script>/g, "");

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
  const key = new URL(String(url), window.location.href).pathname + new URL(String(url), window.location.href).search;
  const body = payloads[key] ?? { items: [] };
  return { ok: true, status: 200, json: async () => body };
};

function tick() {
  return new Promise((resolve) => window.setTimeout(resolve, 0));
}

async function waitFor(predicate, description) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
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

  // Exercise real delegated sidebar navigation, not only direct function calls.
  const masterConfigNav = window.document.querySelector('.nav-link[data-view="master-config"]');
  assert.ok(masterConfigNav, "Master Configuration navigation control should exist");
  masterConfigNav.click();
  await waitFor(
    () => window.document.querySelector('[data-master-config-tab="general"]') !== null
      && window.document.querySelector(".config-settings-grid") !== null,
    "Master Configuration General tab",
  );
  assert.equal(masterConfigNav.classList.contains("active"), true, "Master Configuration nav should become active");

  // General Configuration's nested tab handler should switch to Database Backups.
  window.document.querySelector('[data-general-config-tab="backups"]').click();
  await waitFor(
    () => window.document.querySelector('[data-general-config-tab="backups"][aria-selected="true"]') !== null,
    "Database Backups tab",
  );

  // Exercise the actual top-level Master Configuration tab delegation.
  window.document.querySelector('[data-master-config-tab="prometheus"]').click();
  await waitFor(
    () => window.document.querySelector("#pc-list") !== null,
    "Prometheus Configuration renderer",
  );
  assert.equal(
    window.document.querySelector('[data-master-config-tab="prometheus"].active') !== null,
    true,
    "Prometheus tab should be active",
  );

  window.document.querySelector('[data-master-config-tab="backfill"]').click();
  await waitFor(
    () => window.document.querySelector("#bf-list") !== null,
    "Historical Backfill renderer",
  );
  assert.equal(
    window.document.querySelector('[data-master-config-tab="backfill"].active') !== null,
    true,
    "Backfill tab should be active",
  );

  // Verify each legacy view alias maps to the correct workspace tab.
  window.setView("master-admin");
  await waitFor(
    () => window.document.querySelector('[data-master-config-tab="general"].active') !== null
      && window.document.querySelector(".config-settings-grid") !== null,
    "legacy Master Admin alias",
  );

  window.setView("prometheus-connections");
  await waitFor(
    () => window.document.querySelector('[data-master-config-tab="prometheus"].active') !== null
      && window.document.querySelector("#pc-list") !== null,
    "legacy Prometheus Connections alias",
  );

  window.setView("backfill-jobs");
  await waitFor(
    () => window.document.querySelector('[data-master-config-tab="backfill"].active') !== null
      && window.document.querySelector("#bf-list") !== null,
    "legacy Backfill Jobs alias",
  );

  console.log("DOM-backed frontend navigation regression tests passed.");
  dom.window.close();
}

run().catch((error) => {
  console.error(error);
  dom.window.close();
  process.exitCode = 1;
});
