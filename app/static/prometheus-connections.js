(() => {
  "use strict";

  const root = () => document.getElementById("content");
  const nav = () => document.querySelector('[data-view="prometheus-connections"]');
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
  const api = async (path, options = {}) => {
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || ("Request failed: " + response.status));
    return body;
  };
  const toast = (message, type = "success") => {
    const host = document.getElementById("toast-root");
    if (!host) return;
    const item = document.createElement("div");
    item.className = "toast " + type;
    item.textContent = message;
    host.appendChild(item);
    window.setTimeout(() => item.remove(), 3500);
  };
  const setActiveNav = () => {
    document.querySelectorAll(".nav-link").forEach((item) => item.classList.remove("active"));
    nav()?.classList.add("active");
    const crumb = document.getElementById("page-breadcrumb");
    if (crumb) crumb.textContent = "PROMETHEUS CONNECTIONS";
  };
  const slug = (value) => String(value).toLowerCase().trim()
    .replace(/[^a-z0-9._-]+/g, "-").replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, "").slice(0, 110);

  async function render() {
    setActiveNav();
    const host = root();
    if (!host) return;
    host.innerHTML = '<div class="page-heading"><div><h1>Prometheus connections</h1><p>Manage customer-network endpoints and their MinIO cluster bindings.</p></div><button class="secondary-button" id="pc-reload">↻ Refresh</button></div><section class="panel"><div class="panel-header"><div><h2>Configured endpoints</h2><p>Endpoint secrets are not stored or displayed by this screen.</p></div><button class="primary-button" id="pc-new">Add connection</button></div><div id="pc-list" class="table-scroll"><div class="loading-state">Loading connections…</div></div></section><section class="panel hidden" id="pc-editor"><div class="panel-header"><div><h2 id="pc-editor-title">Add Prometheus connection</h2><p>Test the endpoint and discover MinIO identity labels before saving.</p></div></div><form id="pc-form" class="settings-form"><div class="form-grid"><label>Location ID<input name="location_id" required maxlength="128" pattern="[A-Za-z0-9][A-Za-z0-9._-]*" placeholder="site1"></label><label>Location name<input name="location_name" required maxlength="255" placeholder="Primary DC"></label><label>Connection ID<input name="connection_id" required maxlength="128" pattern="[A-Za-z0-9][A-Za-z0-9._-]*" placeholder="prometheus-site1"></label><label>Protocol<select name="protocol"><option value="http">HTTP</option><option value="https">HTTPS</option></select></label><label>Prometheus host / IP<input name="hostname" required maxlength="253" placeholder="prometheus.example.net or 100.64.1.10"></label><label>Port<input name="port" type="number" min="1" max="65535" value="9090" required></label></div><label class="checkbox-row"><input name="verify_tls" type="checkbox" checked> Verify TLS certificate (HTTPS)</label><div class="form-actions"><button type="button" class="secondary-button" id="pc-test">Test & discover clusters</button><button type="button" class="secondary-button" id="pc-cancel">Cancel</button></div><div id="pc-test-result" class="form-hint" aria-live="polite"></div><div id="pc-discovered"></div><div class="form-actions"><button type="submit" class="primary-button" id="pc-save" disabled>Save connection</button></div></form></section>';
    document.getElementById("pc-reload").addEventListener("click", loadList);
    document.getElementById("pc-new").addEventListener("click", () => openEditor());
    document.getElementById("pc-cancel").addEventListener("click", () => document.getElementById("pc-editor").classList.add("hidden"));
    document.getElementById("pc-test").addEventListener("click", testEndpoint);
    document.getElementById("pc-form").addEventListener("submit", save);
    await loadList();
  }

  async function loadList() {
    const target = document.getElementById("pc-list");
    if (!target) return;
    target.innerHTML = '<div class="loading-state">Loading connections…</div>';
    try {
      const data = await api("/api/master-admin/prometheus-connections");
      if (!data.items.length) {
        target.innerHTML = '<div class="empty-state"><strong>No Prometheus connections configured</strong><p>Add an endpoint, test it, discover clusters and bind the clusters you want to collect.</p></div>';
        return;
      }
      target.innerHTML = '<table><thead><tr><th>LOCATION</th><th>ENDPOINT</th><th>CLUSTERS</th><th>STATUS</th><th>ACTION</th></tr></thead><tbody>' +
        data.items.map((item) => '<tr><td><strong>' + esc(item.location_name) + '</strong><small>' + esc(item.location_id) + '</small></td><td>' + esc(item.protocol) + '://' + esc(item.hostname) + ':' + esc(item.port) + '</td><td>' + item.clusters.map((cluster) => esc(cluster.cluster_name) + ' <small>(' + esc(cluster.cluster_id) + ')</small>').join("<br>") + '</td><td><span class="status-pill ' + (item.enabled ? "success" : "muted") + '">' + (item.enabled ? "Enabled" : "Disabled") + '</span></td><td><button class="secondary-button pc-toggle" data-id="' + esc(item.connection_id) + '" data-enabled="' + (!item.enabled) + '">' + (item.enabled ? "Disable" : "Enable") + '</button></td></tr>').join("") +
        '</tbody></table>';
      target.querySelectorAll(".pc-toggle").forEach((button) => button.addEventListener("click", async () => {
        try {
          await api("/api/master-admin/prometheus-connections/" + encodeURIComponent(button.dataset.id) + "/enabled?enabled=" + button.dataset.enabled, { method: "PATCH" });
          toast("Connection status updated");
          await loadList();
        } catch (error) { toast(error.message, "error"); }
      }));
    } catch (error) {
      target.innerHTML = '<div class="empty-state"><strong>Unable to load connections</strong><p>' + esc(error.message) + '</p></div>';
    }
  }

  function openEditor(existing) {
    const editor = document.getElementById("pc-editor");
    const form = document.getElementById("pc-form");
    form.reset();
    document.getElementById("pc-test-result").textContent = "";
    document.getElementById("pc-discovered").innerHTML = "";
    document.getElementById("pc-save").disabled = true;
    editor.classList.remove("hidden");
    if (existing) {
      Object.entries(existing).forEach(([key, value]) => {
        const field = form.elements.namedItem(key);
        if (field) field.type === "checkbox" ? field.checked = !!value : field.value = value;
      });
    }
    editor.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function endpointPayload() {
    const form = document.getElementById("pc-form");
    return {
      protocol: form.elements.protocol.value,
      hostname: form.elements.hostname.value.trim(),
      port: Number(form.elements.port.value),
      verify_tls: form.elements.verify_tls.checked
    };
  }

  async function testEndpoint() {
    const button = document.getElementById("pc-test");
    const result = document.getElementById("pc-test-result");
    const discovered = document.getElementById("pc-discovered");
    button.disabled = true;
    result.textContent = "Testing endpoint and discovering MinIO clusters…";
    discovered.innerHTML = "";
    document.getElementById("pc-save").disabled = true;
    try {
      const data = await api("/api/master-admin/prometheus-connections/test", {
        method: "POST", body: JSON.stringify(endpointPayload())
      });
      result.textContent = "Connection successful. Found " + data.cluster_count + " MinIO cluster identity value(s). Select the clusters to bind.";
      discovered.innerHTML = '<div class="discovery-list"><h3>Discovered MinIO clusters</h3>' +
        data.clusters.map((cluster, index) => '<label class="checkbox-row"><input type="checkbox" class="pc-cluster" data-index="' + index + '" checked><span><strong>' + esc(cluster.label_value) + '</strong><small>Identity label: ' + esc(cluster.label_name) + ' · Metrics: ' + esc(cluster.metrics_found.join(", ")) + '</small></span></label>').join("") +
        '</div>';
      discovered.dataset.clusters = JSON.stringify(data.clusters);
      document.getElementById("pc-save").disabled = data.cluster_count === 0;
    } catch (error) {
      result.textContent = "Test failed: " + error.message;
      result.className = "form-error";
    } finally { button.disabled = false; }
  }

  async function save(event) {
    event.preventDefault();
    const form = document.getElementById("pc-form");
    const clusters = JSON.parse(document.getElementById("pc-discovered").dataset.clusters || "[]");
    const selected = [...document.querySelectorAll(".pc-cluster:checked")].map((checkbox) => {
      const item = clusters[Number(checkbox.dataset.index)];
      return {
        cluster_id: "cluster-" + slug(form.elements.location_id.value).slice(0, 35) + "-" + slug(item.label_value).slice(0, 80),
        cluster_name: item.label_value,
        identity_label_name: item.label_name,
        identity_label_value: item.label_value
      };
    });
    if (!selected.length) { toast("Select at least one discovered cluster", "error"); return; }
    const payload = {
      connection_id: form.elements.connection_id.value.trim(),
      location_id: form.elements.location_id.value.trim(),
      location_name: form.elements.location_name.value.trim(),
      ...endpointPayload(),
      clusters: selected,
      enabled: true
    };
    const button = document.getElementById("pc-save");
    button.disabled = true;
    button.textContent = "Saving…";
    try {
      await api("/api/master-admin/prometheus-connections", { method: "POST", body: JSON.stringify(payload) });
      toast("Prometheus connection saved");
      document.getElementById("pc-editor").classList.add("hidden");
      await loadList();
    } catch (error) { toast(error.message, "error"); }
    finally { button.disabled = false; button.textContent = "Save connection"; }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest('[data-view="prometheus-connections"]');
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    render().catch((error) => toast(error.message, "error"));
  }, true);
})();