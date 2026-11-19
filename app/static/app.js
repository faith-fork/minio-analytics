const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const state = { user:null, view:"overview", overview:null, clusters:[], tenants:[], buckets:[], selectedBuckets:[], health:null, charts:[] };
const fmt = (n, digits=2) => n == null ? "—" : new Intl.NumberFormat("en-IN",{maximumFractionDigits:digits}).format(n);
const bytes = n => n == null ? "—" : (n/1024**4).toFixed(2)+" TiB";
const pct = (used,total) => used == null || !total ? null : Math.max(0,Math.min(100,used/total*100));
const esc = s => String(s ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const dateLabel = s => s ? new Date(s+"T00:00:00").toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"}) : "—";
async function api(path, options={}) {
  const response = await fetch(path,{credentials:"same-origin",headers:{"Content-Type":"application/json",...(options.headers||{})},...options});
  if(response.status===401){showLogin();throw new Error("Your session has expired. Please sign in again.");}
  const data = response.status===204 ? null : await response.json().catch(()=>({detail:"Unexpected server response"}));
  if(!response.ok) throw new Error(data?.detail || "Request failed ("+response.status+")");
  return data;
}
function toast(message,error=false){const el=document.createElement("div");el.className="toast"+(error?" error":"");el.textContent=message;$("#toast-root").append(el);setTimeout(()=>el.remove(),3600);}
function showLogin(){state.user=null;$("#app-shell").classList.add("hidden");$("#login-screen").classList.remove("hidden");}
function showApp(user){state.user=user;$("#login-screen").classList.add("hidden");$("#app-shell").classList.remove("hidden");$("#user-name").textContent=user.username;$("#user-role").textContent=user.role.toUpperCase();$("#user-avatar").textContent=user.username.slice(0,1).toUpperCase();$$(".admin-only").forEach(el=>el.classList.toggle("hidden",user.role!=="admin"));}
function pageHead(title,subtitle,actions=""){return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="heading-actions">${actions}</div></div>`;}
function metric(label,value,foot,icon="◈",good=false){return `<div class="metric-card"><div class="metric-top"><span>${label}</span><span class="metric-icon">${icon}</span></div><div class="metric-value">${value}</div><div class="metric-foot ${good?"good":""}">${foot}</div></div>`;}
function pill(status){const cls=status==="success"||status===true?"":status==="partial"?"warn":status==="failed"||status===false?"bad":"neutral";const label=status===true?"Available":status===false?"Unavailable":String(status??"Unknown");return `<span class="status-pill ${cls}"><i></i>${esc(label)}</span>`;}
function panel(title,subtitle,body,tag=""){return `<section class="panel"><div class="panel-header"><div><h3>${title}</h3><p>${subtitle||""}</p></div>${tag?`<span class="panel-tag">${tag}</span>`:""}</div>${body}</section>`;}
function table(title,subtitle,headers,rows,empty="No records found."){return `<section class="table-panel"><div class="table-heading"><div><h3>${title}</h3><p>${subtitle||""}</p></div></div><div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.length?rows.join(""):`<tr><td colspan="${headers.length}" class="empty-state">${empty}</td></tr>`}</tbody></table></div></section>`;}
function chart(id,labels,sets,type="line"){if(!window.Chart)return;const canvas=$("#"+id);if(!canvas)return;const instance=new Chart(canvas,{type,data:{labels,datasets:sets.map(s=>({label:s.label,data:s.data,borderColor:s.color,backgroundColor:s.fill||s.color+"18",borderWidth:2,pointRadius:3,tension:.32,fill:!!s.fill}))},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},plugins:{legend:{position:"bottom",labels:{usePointStyle:true,boxWidth:7,font:{size:10}}}},scales:{x:{grid:{display:false},ticks:{font:{size:9},color:"#94a0af"}},y:{grid:{color:"#edf1f5"},ticks:{font:{size:9},color:"#94a0af"}}}}});state.charts.push(instance);}
function clearCharts(){state.charts.forEach(c=>c.destroy());state.charts=[];}
function setView(view){state.view=view;$$(".nav-link").forEach(b=>b.classList.toggle("active",b.dataset.view===view));$("#page-breadcrumb").textContent=view.replace("-"," ").toUpperCase();render().catch(e=>toast(e.message,true));}
async function loadOverview(){state.overview=await api("/api/analytics/overview");state.clusters=(await api("/api/analytics/clusters")).items;}
async function render(){
  clearCharts();$("#content").innerHTML='<div class="loading-state">Loading dashboard data…</div>';
  if(state.view==="overview") await renderOverview();
  else if(state.view==="clusters") await renderClusters();
  else if(state.view==="tenants") await renderTenants();
  else if(state.view==="buckets") await renderBuckets();
  else if(state.view==="health") await renderHealth();
  else if(state.view==="users" && state.user.role==="admin") await renderUsers();
}
async function renderOverview(){
  await loadOverview();const o=state.overview,c=o.capacity_bytes,n=o.nodes;
  const cap=pct(c.raw_total_bytes-c.raw_free_bytes,c.raw_total_bytes);
  const clusterRows=o.cluster_items.map(x=>`<tr><td><span class="cell-strong">${esc(x.cluster_name)}</span><br><span class="cell-muted">${esc(x.location_name)}</span></td><td>${pill(!!x.metrics_available)}</td><td>${bytes(x.raw_total_bytes)}</td><td>${bytes(x.raw_total_bytes-x.raw_free_bytes)}</td><td>${x.nodes_online??"—"} / ${x.nodes_offline??"—"}</td><td>${x.days_to_full==null?"—":fmt(x.days_to_full,0)+" days"}</td><td><button class="table-link" data-cluster="${esc(x.cluster_id)}">Details →</button></td></tr>`);
  $("#content").innerHTML=pageHead("Fleet overview","A consolidated view of your MinIO storage estate.",'<button class="subtle-button" data-action="refresh">↻ Refresh</button>')+
    `<div class="metric-grid">${metric("RAW CAPACITY",bytes(c.raw_total_bytes),o.latest_cluster_snapshot_date?"Snapshot "+dateLabel(o.latest_cluster_snapshot_date):"No snapshot","▤")}${metric("RAW USED",bytes(c.raw_total_bytes-c.raw_free_bytes),cap==null?"Utilization unavailable":fmt(cap,1)+"% of raw capacity","◒")}${metric("USABLE CAPACITY",bytes(c.usable_total_bytes),"After storage protection","▦")}${metric("ONLINE NODES",n.online==null?"—":fmt(n.online,0),n.offline==null?"Node state unavailable":n.offline+" offline", "⌁",n.offline===0)}${metric("CLUSTERS",o.clusters.available+" / "+o.clusters.total,"Available clusters","◫",o.clusters.unavailable===0)}${metric("BUCKETS",fmt(o.inventory.active_buckets,0),o.inventory.unassigned_buckets+" unassigned","▤")}${metric("ACTIVE TENANTS",fmt(o.inventory.active_tenants,0),"Configured tenants","◇")}${metric("COLLECTION STATUS",o.latest_bucket_snapshot_date?dateLabel(o.latest_bucket_snapshot_date):"—","Latest bucket snapshot","◷")}</div>`+
    `<div class="panel-grid">${panel("Cluster capacity","Raw capacity utilization by cluster",'<div class="chart-wrap"><canvas id="capacity-chart"></canvas></div>',"LATEST SNAPSHOT")}${panel("Capacity breakdown","Fleet-wide capacity totals",`<div class="capacity-list"><div class="capacity-row"><span>Raw total</span><strong>${bytes(c.raw_total_bytes)}</strong><div class="progress"><span style="width:100%"></span></div></div><div class="capacity-row"><span>Raw used</span><strong>${bytes(c.raw_total_bytes-c.raw_free_bytes)}</strong><div class="progress amber"><span style="width:${cap??0}%"></span></div></div><div class="capacity-row"><span>Raw free</span><strong>${bytes(c.raw_free_bytes)}</strong><div class="progress blue"><span style="width:${pct(c.raw_free_bytes,c.raw_total_bytes)??0}%"></span></div></div><div class="capacity-row"><span>Usable total</span><strong>${bytes(c.usable_total_bytes)}</strong><div class="progress"><span style="width:100%"></span></div></div></div>`,"BYTES → TiB")}</div>`+
    table("Cluster status","Latest persisted cluster snapshots",["CLUSTER / LOCATION","STATUS","RAW TOTAL","RAW USED","NODES UP / DOWN","DAYS TO FULL",""],clusterRows);
  const labels=o.cluster_items.map(x=>x.cluster_name);chart("capacity-chart",labels,[{label:"Used TiB",data:o.cluster_items.map(x=>x.raw_total_bytes==null||x.raw_free_bytes==null?null:(x.raw_total_bytes-x.raw_free_bytes)/1024**4),color:"#13a58b",fill:true},{label:"Free TiB",data:o.cluster_items.map(x=>x.raw_free_bytes==null?null:x.raw_free_bytes/1024**4),color:"#4779d8"}],"bar");
}
async function renderClusters(){
  state.clusters=(await api("/api/analytics/clusters")).items;
  const rows=state.clusters.map(x=>`<tr><td><span class="cell-strong">${esc(x.cluster_name)}</span><br><span class="cell-muted">${esc(x.cluster_id)}</span></td><td>${esc(x.location_name)}</td><td>${pill(!!x.metrics_available)}</td><td>${bytes(x.raw_total_bytes)}</td><td>${bytes(x.raw_total_bytes-x.raw_free_bytes)}</td><td>${x.nodes_online??"—"} / ${x.nodes_offline??"—"}</td><td>${x.growth_bytes_per_day==null?"—":fmt(x.growth_bytes_per_day/1024**3)+" GiB"}</td><td><button class="table-link" data-cluster="${esc(x.cluster_id)}">View details →</button></td></tr>`);
  $("#content").innerHTML=pageHead("Clusters","Capacity, node health and daily growth across registered clusters.")+table("Registered clusters",state.clusters.length+" cluster(s)",["CLUSTER","LOCATION","STATUS","RAW CAPACITY","RAW USED","NODES UP / DOWN","GROWTH / DAY",""],rows);
}
async function showCluster(id){
  const d=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"?days=90"),x=d.latest||{},series=d.series||[];
  clearCharts();$("#content").innerHTML=pageHead(esc(d.cluster.name),"Cluster · "+esc(d.cluster.location_name)+" · "+esc(id),'<button class="subtle-button" data-view="clusters">← All clusters</button>')+
    `<div class="detail-grid"><div class="detail-card"><small>RAW CAPACITY</small><strong>${bytes(x.raw_total_bytes)}</strong></div><div class="detail-card"><small>RAW FREE</small><strong>${bytes(x.raw_free_bytes)}</strong></div><div class="detail-card"><small>PROJECTED DAYS TO FULL</small><strong>${x.days_to_full==null?"—":fmt(x.days_to_full,0)+" days"}</strong></div></div>`+
    `<div class="panel-grid">${panel("Capacity trend","Daily raw used and free capacity",'<div class="chart-wrap"><canvas id="cluster-chart"></canvas></div>',"90 DAYS")}${panel("Cluster health","Latest node availability",`<div class="capacity-list"><div class="capacity-row"><span>Online nodes</span><strong>${x.nodes_online??"—"}</strong></div><div class="capacity-row"><span>Offline nodes</span><strong>${x.nodes_offline??"—"}</strong></div><div class="capacity-row"><span>Growth per day</span><strong>${x.growth_bytes_per_day==null?"—":fmt(x.growth_bytes_per_day/1024**3)+" GiB"}</strong></div><div class="capacity-row"><span>Snapshot date</span><strong>${dateLabel(x.snapshot_date)}</strong></div><div class="capacity-row"><span>Metrics</span><strong>${pill(!!x.metrics_available)}</strong></div></div>`,"LATEST SNAPSHOT")}</div>`+
    table("Daily snapshots","Stored cluster metrics",["DATE","RAW TOTAL","RAW FREE","USABLE TOTAL","ONLINE","OFFLINE","STATUS"],series.map(r=>`<tr><td>${dateLabel(r.snapshot_date)}</td><td>${bytes(r.raw_total_bytes)}</td><td>${bytes(r.raw_free_bytes)}</td><td>${bytes(r.usable_total_bytes)}</td><td>${r.nodes_online??"—"}</td><td>${r.nodes_offline??"—"}</td><td>${pill(!!r.metrics_available)}</td></tr>`));
  chart("cluster-chart",series.map(r=>dateLabel(r.snapshot_date)),[{label:"Used TiB",data:series.map(r=>r.raw_total_bytes==null||r.raw_free_bytes==null?null:(r.raw_total_bytes-r.raw_free_bytes)/1024**4),color:"#13a58b",fill:true},{label:"Free TiB",data:series.map(r=>r.raw_free_bytes==null?null:r.raw_free_bytes/1024**4),color:"#4779d8"}]);
}
async function renderUsers(){
  const data=await api("/api/auth/users");
  const rows=data.items.map(u=>`<tr><td><span class="cell-strong">${esc(u.username)}</span></td><td><select class="form-control user-role" data-user-role="${u.id}"><option value="viewer" ${u.role==="viewer"?"selected":""}>Viewer</option><option value="admin" ${u.role==="admin"?"selected":""}>Admin</option></select></td><td>${pill(u.is_active?"Active":"Inactive")}</td><td>${dateLabel((u.created_at||"").slice(0,10))}</td><td><button class="table-link" data-reset-user="${u.id}">Reset password</button> · <button class="table-link" data-toggle-user="${u.id}" data-active="${u.is_active?0:1}">${u.is_active?"Deactivate":"Activate"}</button></td></tr>`);
  $("#content").innerHTML=pageHead("User administration","Manage local dashboard accounts and access roles. OIDC integration can be added later.",'<button class="primary-small" data-action="new-user">＋ Add user</button>')+
    table("Dashboard users",data.count+" account(s)",["USERNAME","ROLE","STATUS","CREATED","ACTIONS"],rows);
}
async function renderTenants(){
  const [summary,tenants]=await Promise.all([api("/api/analytics/tenants"),api("/api/tenants?include_inactive=true")]);state.tenants=tenants.items;
  const rows=summary.items.map(x=>`<tr><td><span class="cell-strong">${esc(x.tenant_name||"Unassigned")}</span></td><td>${x.bucket_count}</td><td>${x.buckets_with_metrics}</td><td>${bytes(x.used_bytes)}</td><td>${fmt(x.object_count,0)}</td><td>${dateLabel(x.latest_snapshot_date)}</td><td>${x.tenant_id?'<button class="table-link" data-tenant="'+x.tenant_id+'">History →</button>':"—"}</td></tr>`);
  $("#content").innerHTML=pageHead("Tenants","Tenant usage follows current bucket ownership; usage values come from the latest stored snapshots.",state.user.role==="admin"?'<button class="primary-small" data-action="new-tenant">＋ Create tenant</button>':"")+
    table("Tenant usage","Current bucket ownership · latest available metrics snapshot",["TENANT","BUCKETS","WITH METRICS","USED","OBJECTS","SNAPSHOT",""],rows)+
    table("Tenant directory","Current tenant configuration",["TENANT","DESCRIPTION","CURRENT BUCKETS","STATUS"],state.tenants.map(t=>`<tr><td class="cell-strong">${esc(t.name)}</td><td>${esc(t.description||"—")}</td><td>${t.bucket_count}</td><td>${pill(t.is_active?"Active":"Inactive")}</td></tr>`));
}
async function showTenant(id,attribution="current"){
  const d=await api("/api/analytics/tenants/"+id+"?days=90&attribution="+encodeURIComponent(attribution));clearCharts();
  const current=attribution==="current";
  const subtitle=current
    ?"Historical bucket usage attributed using current tenant ownership."
    :"Historical usage attributed to this tenant at snapshot time.";
  const actions=`<div class="heading-actions"><button class="subtle-button" data-tenant-mode="current" data-tenant-id="${id}" ${current?'disabled':''}>Current ownership</button><button class="subtle-button" data-tenant-mode="historical" data-tenant-id="${id}" ${!current?'disabled':''}>Historical ownership</button><button class="subtle-button" data-view="tenants">← All tenants</button></div>`;
  const emptyMessage=current
    ?"No stored bucket snapshots found for buckets currently assigned to this tenant."
    :"No snapshots were recorded under this tenant's ownership during this period.";
  $("#content").innerHTML=pageHead(esc(d.tenant.name),subtitle,actions)+
    `<div class="detail-grid"><div class="detail-card"><small>DESCRIPTION</small><strong style="font-size:14px">${esc(d.tenant.description||"—")}</strong></div><div class="detail-card"><small>STATUS</small><strong style="font-size:14px">${d.tenant.is_active?"Active":"Inactive"}</strong></div><div class="detail-card"><small>HISTORY WINDOW</small><strong>90 days</strong></div></div>`+
    panel("Tenant usage trend",current?"Daily usage of buckets currently assigned to this tenant":"Daily usage based on historical snapshot attribution",'<div class="chart-wrap"><canvas id="tenant-chart"></canvas></div>')+
    table("Daily tenant snapshots",current?"Current ownership is applied retrospectively; totals require metrics for every currently assigned bucket.":"Missing metrics remain unavailable, not zero.",["DATE","BUCKETS","USED","OBJECTS","UNAVAILABLE BUCKETS"],d.series.map(r=>`<tr><td>${dateLabel(r.snapshot_date)}</td><td>${r.bucket_count}</td><td>${bytes(r.used_bytes)}</td><td>${fmt(r.object_count,0)}</td><td>${r.unavailable_bucket_metrics}</td></tr>`),emptyMessage);
  chart("tenant-chart",d.series.map(r=>dateLabel(r.snapshot_date)),[{label:"Used TiB",data:d.series.map(r=>r.used_bytes==null?null:r.used_bytes/1024**4),color:"#13a58b",fill:true}]);
}
async function renderBuckets(){
  const [buckets,tenants]=await Promise.all([api("/api/buckets"),api("/api/tenants")]);state.buckets=buckets.items;state.tenants=tenants.items;
  state.selectedBuckets=state.selectedBuckets.filter(id=>state.buckets.some(b=>b.id===id));
  const admin=state.user.role==="admin";
  const rows=state.buckets.map(b=>`<tr>${admin?`<td><input type="checkbox" class="bucket-select" data-select-bucket="${b.id}" aria-label="Select ${esc(b.bucket_name)}" ${state.selectedBuckets.includes(b.id)?"checked":""}></td>`:""}<td><span class="cell-strong">${esc(b.bucket_name)}</span><br><span class="cell-muted">${esc(b.cluster_name)}</span></td><td>${esc(b.location_name)}</td><td>${esc(b.tenant_name||"Unassigned")}</td><td>${pill(b.is_active?"Active":"Inactive")}</td><td><button class="table-link" data-bucket="${b.id}">Details →</button></td>${admin?`<td><button class="table-link" data-assign="${b.id}">Assign</button></td>`:""}</tr>`);
  const headers=admin?["<input type=\"checkbox\" id=\"select-all-buckets\" aria-label=\"Select all buckets\">","BUCKET / CLUSTER","LOCATION","CURRENT TENANT","STATUS","","MANAGE"]:["BUCKET / CLUSTER","LOCATION","CURRENT TENANT","STATUS",""];
  $("#content").innerHTML=pageHead("Buckets","Inventory and current tenant ownership across your MinIO clusters.")+
    `<div class="toolbar" style="margin-bottom:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap"><input id="bucket-filter" class="form-control" placeholder="Filter buckets by name or cluster"><span id="bucket-selection-count" class="cell-muted">${state.selectedBuckets.length} selected</span>${admin?'<button class="primary-small" data-action="bulk-assign" '+(state.selectedBuckets.length?'':'disabled')+'>Assign selected buckets</button>':""}</div>`+
    table("Bucket inventory",buckets.count+" active bucket(s)",headers,rows);
  const selectAll=$("#select-all-buckets");if(selectAll)selectAll.checked=state.buckets.length>0&&state.selectedBuckets.length===state.buckets.length;
}
async function showBucket(id){
  const [d,h]=await Promise.all([api("/api/analytics/buckets/"+id+"?days=90"),api("/api/buckets/"+id+"/history")]);const series=d.series||[],latest=series.at(-1)||{};clearCharts();
  $("#content").innerHTML=pageHead(esc(d.bucket.bucket_name),"Cluster · "+esc(d.bucket.cluster_name)+" · Current tenant: "+esc(d.bucket.current_tenant_name||"Unassigned"),'<button class="subtle-button" data-view="buckets">← All buckets</button>')+
    `<div class="detail-grid"><div class="detail-card"><small>USED</small><strong>${bytes(latest.used_bytes)}</strong></div><div class="detail-card"><small>QUOTA</small><strong>${bytes(latest.quota_bytes)}</strong></div><div class="detail-card"><small>OBJECTS</small><strong>${fmt(latest.object_count,0)}</strong></div></div>`+
    panel("Bucket usage trend","Daily usage in TiB",'<div class="chart-wrap"><canvas id="bucket-chart"></canvas></div>')+
    table("Daily snapshots","Historical tenant attribution is retained per snapshot.",["DATE","TENANT AT SNAPSHOT","USED","QUOTA","OBJECTS","VERSIONS","DELETE MARKERS"],series.map(r=>`<tr><td>${dateLabel(r.snapshot_date)}</td><td>${esc(r.tenant_name_at_snapshot||"Unassigned")}</td><td>${bytes(r.used_bytes)}</td><td>${bytes(r.quota_bytes)}</td><td>${fmt(r.object_count,0)}</td><td>${r.version_count??"—"}</td><td>${r.delete_marker_count??"—"}</td></tr>`))+
    table("Assignment history","Administrative ownership changes",["CHANGED AT","TENANT","CHANGED BY","NOTE"],h.items.map(r=>`<tr><td>${esc(r.changed_at)}</td><td>${esc(r.tenant_name||"Unassigned")}</td><td>${esc(r.changed_by)}</td><td>${esc(r.note||"—")}</td></tr>`));
  chart("bucket-chart",series.map(r=>dateLabel(r.snapshot_date)),[{label:"Used TiB",data:series.map(r=>r.used_bytes==null?null:r.used_bytes/1024**4),color:"#13a58b",fill:true},{label:"Quota TiB",data:series.map(r=>r.quota_bytes==null?null:r.quota_bytes/1024**4),color:"#d9922e"}]);
}
async function renderHealth(){
  state.health=await api("/api/analytics/collection-health?limit=50");const counts=state.health.status_counts;
  const rows=state.health.recent_runs.map(r=>`<tr><td>${esc(r.started_at)}</td><td>${esc(r.location_name||"—")}</td><td>${esc(r.cluster_name||"—")}</td><td>${dateLabel(r.snapshot_date)}</td><td>${pill(r.status)}</td><td>${r.attempt}</td><td>${r.metrics_collected}</td><td>${esc(r.error_text||"—")}</td></tr>`);
  $("#content").innerHTML=pageHead("Collection health","Monitor scheduled snapshot runs, retries and metric availability.")+
    `<div class="metric-grid">${metric("SUCCESSFUL RUNS",fmt(counts.success||0,0),"Recorded successful runs","✓",true)}${metric("PARTIAL RUNS",fmt(counts.partial||0,0),"At least one metric family unavailable","◒")}${metric("FAILED RUNS",fmt(counts.failed||0,0),"Unsuccessful after retry","!")}${metric("RECENT EXECUTIONS",fmt(state.health.count,0),"Latest 50 collection records","◷")}</div>`+
    table("Recent collection runs","Latest collector execution records",["STARTED AT","LOCATION","CLUSTER","SNAPSHOT DATE","STATUS","ATTEMPT","METRICS","ERROR"],rows);
}
function openModal(title,description,fields,onSubmit){
  const root=$("#modal-root");root.innerHTML=`<div class="modal-backdrop"><section class="modal"><h3>${title}</h3><p>${description}</p><form id="modal-form">${fields}<div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-small" type="submit">Save</button></div></form></section></div>`;
  $("#modal-form").addEventListener("submit",async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.currentTarget));try{await onSubmit(data);root.innerHTML="";}catch(err){toast(err.message,true);}});
}
function createUserModal(){
  openModal("Add dashboard user","Create a local account. Passwords must contain at least 12 characters.",'<label>Username</label><input name="username" required minlength="3" maxlength="64" pattern="[A-Za-z0-9._-]+" autocomplete="off"><label>Temporary password</label><input name="password" type="password" required minlength="12" maxlength="1024" autocomplete="new-password"><label>Role</label><select name="role"><option value="viewer" selected>Viewer — read-only</option><option value="admin">Administrator — manage users and tenants</option></select>',async d=>{await api("/api/auth/users",{method:"POST",body:JSON.stringify(d)});toast("User created");await renderUsers();});
}
function resetUserPasswordModal(id){
  openModal("Reset user password","Set a new password of at least 12 characters.",'<label>New password</label><input name="password" type="password" required minlength="12" maxlength="1024" autocomplete="new-password">',async d=>{await api("/api/auth/users/"+id+"/reset-password",{method:"POST",body:JSON.stringify(d)});toast("Password reset successfully");});
}
function createTenantModal(){openModal("Create tenant","Add a tenant to organize bucket ownership.",'<label>Tenant name</label><input name="name" required maxlength="128"><label>Description</label><textarea name="description" maxlength="1000"></textarea>',async d=>{await api("/api/tenants",{method:"POST",body:JSON.stringify(d)});toast("Tenant created");await renderTenants();});}
async function assignBucketModal(id){
  const b=state.buckets.find(x=>x.id===id);const options=state.tenants.filter(t=>t.is_active).map(t=>`<option value="${t.id}" ${t.id===b?.tenant_id?"selected":""}>${esc(t.name)}</option>`).join("");
  openModal("Assign bucket","Change current ownership. Historical snapshots will not be rewritten.",`<label>Bucket</label><input value="${esc(b?.bucket_name||"")}" disabled><label>Tenant</label><select name="tenant_id"><option value="">Unassigned</option>${options}</select><label>Change note (optional)</label><textarea name="note" maxlength="1000"></textarea>`,async d=>{await api("/api/buckets/"+id+"/tenant",{method:"PUT",body:JSON.stringify({tenant_id:d.tenant_id?Number(d.tenant_id):null,note:d.note||null})});toast("Bucket assignment updated");await renderBuckets();});
}
function bulkAssignBucketsModal(){
  const ids=[...state.selectedBuckets];
  if(!ids.length)return;
  const options=state.tenants.filter(t=>t.is_active).map(t=>`<option value="${t.id}">${esc(t.name)}</option>`).join("");
  openModal("Bulk assign buckets",`Assign ${ids.length} selected bucket(s) to one tenant. Existing snapshot attribution will not be changed.`,`<label>Target tenant</label><select name="tenant_id"><option value="">Unassigned</option>${options}</select><label>Change note (optional)</label><textarea name="note" maxlength="1000" placeholder="Reason for this bulk change"></textarea>`,async d=>{
    const result=await api("/api/buckets/bulk-tenant",{method:"PUT",body:JSON.stringify({bucket_ids:ids,tenant_id:d.tenant_id?Number(d.tenant_id):null,note:d.note||null})});
    state.selectedBuckets=[];
    toast(`Bulk assignment complete: ${result.changed_count} changed, ${result.unchanged_count} unchanged`);
    await renderBuckets();
  });
}

document.addEventListener("click",async e=>{
  const view=e.target.closest("[data-view]");if(view){e.preventDefault();setView(view.dataset.view);return;}
  const cluster=e.target.closest("[data-cluster]");if(cluster){try{await showCluster(cluster.dataset.cluster);}catch(err){toast(err.message,true);}return;}
  const tenant=e.target.closest("[data-tenant]");if(tenant){try{await showTenant(tenant.dataset.tenant);}catch(err){toast(err.message,true);}return;}
  const tenantMode=e.target.closest("[data-tenant-mode]");if(tenantMode){try{await showTenant(Number(tenantMode.dataset.tenantId),tenantMode.dataset.tenantMode);}catch(err){toast(err.message,true);}return;}
  const bucket=e.target.closest("[data-bucket]");if(bucket){try{await showBucket(bucket.dataset.bucket);}catch(err){toast(err.message,true);}return;}
  const assign=e.target.closest("[data-assign]");if(assign){assignBucketModal(Number(assign.dataset.assign));return;}
  const action=e.target.closest("[data-action]")?.dataset.action;
  if(action==="refresh"){render().catch(err=>toast(err.message,true));}
  if(action==="new-tenant")createTenantModal();
  if(action==="new-user")createUserModal();
  if(action==="bulk-assign")bulkAssignBucketsModal();
  const reset=e.target.closest("[data-reset-user]");if(reset){resetUserPasswordModal(Number(reset.dataset.resetUser));return;}
  const toggle=e.target.closest("[data-toggle-user]");if(toggle){try{await api("/api/auth/users/"+toggle.dataset.toggleUser+"/active",{method:"POST",body:JSON.stringify({is_active:toggle.dataset.active==="1"})});toast("User status updated");await renderUsers();}catch(err){toast(err.message,true);}return;}
  if(action==="close-modal")$("#modal-root").innerHTML="";
});
$("#login-form").addEventListener("submit",async e=>{e.preventDefault();$("#login-error").textContent="";const form=new FormData(e.currentTarget);try{const d=await api("/api/auth/login",{method:"POST",body:JSON.stringify({username:form.get("username"),password:form.get("password")})});showApp(d.user);setView("overview");}catch(err){$("#login-error").textContent=err.message;}});
$("#logout-button").addEventListener("click",async()=>{try{await api("/api/auth/logout",{method:"POST"});}catch{}showLogin();});
$("#refresh-button").addEventListener("click",()=>render().catch(e=>toast(e.message,true)));
$("#content").addEventListener("change",e=>{
  if(e.target.matches("[data-user-role]")){
    const id=Number(e.target.dataset.userRole),role=e.target.value;
    api("/api/auth/users/"+id,{method:"PATCH",body:JSON.stringify({role})}).then(()=>toast("User role updated")).catch(err=>{toast(err.message,true);renderUsers();});
  }

  if(e.target.matches("[data-select-bucket]")){
    const id=Number(e.target.dataset.selectBucket);
    state.selectedBuckets=e.target.checked?[...new Set([...state.selectedBuckets,id])]:state.selectedBuckets.filter(x=>x!==id);
    const count=$("#bucket-selection-count");if(count)count.textContent=state.selectedBuckets.length+" selected";
    const button=$("[data-action='bulk-assign']");if(button)button.disabled=!state.selectedBuckets.length;
    const all=$("#select-all-buckets");if(all)all.checked=state.buckets.length>0&&state.selectedBuckets.length===state.buckets.length;
  }
  if(e.target.id==="select-all-buckets"){
    state.selectedBuckets=e.target.checked?state.buckets.map(b=>b.id):[];
    $(".bucket-select",$("#content")).forEach(el=>el.checked=e.target.checked);
    const count=$("#bucket-selection-count");if(count)count.textContent=state.selectedBuckets.length+" selected";
    const button=$("[data-action='bulk-assign']");if(button)button.disabled=!state.selectedBuckets.length;
  }
});
$("#content").addEventListener("input",e=>{if(e.target.id==="bucket-filter"){const q=e.target.value.toLowerCase();$("tbody tr",$("#content")).forEach(row=>row.classList.toggle("hidden",!row.textContent.toLowerCase().includes(q)));}});
(async()=>{try{const d=await api("/api/auth/me");showApp(d.user);await setView("overview");}catch{showLogin();}})();
