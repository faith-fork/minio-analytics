const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const state = { user:null, view:"overview", overview:null, clusters:[], tenants:[], buckets:[], selectedBuckets:[], reportColumns:{used_usable:true,used_bkt:true}, reportColumnVisibility:{}, bucketUsageFilters:{cluster:[],location:[],tenant:[]}, bucketUsageFilterDraft:{cluster:[],location:[],tenant:[]}, health:null, healthFilters:{startDate:"",endDate:"",status:"",page:1,pageSize:20}, charts:[], snapshotClusterId:null, snapshotRange:{days:90,startDate:null,endDate:null}, snapshotContext:{type:null,id:null,attribution:"current",days:90,startDate:null,endDate:null},nodeSubsection:"health",nodePerformanceHours:6 };
const fmt = (n, digits=2) => n == null ? "—" : new Intl.NumberFormat("en-IN",{maximumFractionDigits:digits}).format(n);
const bytes = n => n == null ? "—" : (n/1024**4).toFixed(2)+" TiB";
const tibValue = n => n == null ? "—" : (n/1024**4).toFixed(2);
const pct = (used,total) => used == null || !total ? null : Math.max(0,Math.min(100,used/total*100));
const esc = s => String(s ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const dateLabel = s => s ? new Date(s+"T00:00:00").toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"}) : "—";
const timestampLabel = s => s ? new Intl.DateTimeFormat("en-IN",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:true,timeZone:"Asia/Kolkata"}).format(new Date(s))+" IST" : "Not collected";
async function api(path, options={}) {
  const response = await fetch(path,{credentials:"same-origin",headers:{"Content-Type":"application/json",...(options.headers||{})},...options});
  if(response.status===401){showLogin();throw new Error("Your session has expired. Please sign in again.");}
  const data = response.status===204 ? null : await response.json().catch(()=>({detail:"Unexpected server response"}));
  if(!response.ok) throw new Error(data?.detail || "Request failed ("+response.status+")");
  return data;
}
function toast(message,error=false){const el=document.createElement("div");el.className="toast"+(error?" error":"");el.textContent=message;$("#toast-root").append(el);setTimeout(()=>el.remove(),3600);}
function showLogin(){state.user=null;$("#app-shell").classList.add("hidden");$("#login-screen").classList.remove("hidden");}
function showApp(user){state.user=user;$("#login-screen").classList.add("hidden");$("#app-shell").classList.remove("hidden");$("#user-name").textContent=user.username;$("#user-role").textContent=user.role.toUpperCase();$("#user-avatar").textContent=user.username.slice(0,1).toUpperCase();$$(".admin-only").forEach(el=>el.classList.toggle("hidden",user.role!=="admin"));$$(".master-admin-only").forEach(el=>el.classList.toggle("hidden",!user.is_master_admin));}
function pageHead(title,subtitle,actions=""){return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="heading-actions">${actions}</div></div>`;}
function reportTabs(active){const tabs=[["capacity-report","Consolidated Provisioned"],["bucket-usage-report","Consolidated Bucket Usage"],["raw-capacity-report","Consolidated RAW Capacity"]];return '<div class="report-tabs" role="tablist" aria-label="Consolidated reports">'+tabs.map(([view,label])=>'<button type="button" role="tab" aria-selected="'+(active===view)+'" class="'+(active===view?"active":"")+'" data-report-view="'+view+'">'+label+'</button>').join("")+'</div>';}
function metric(label,value,foot,icon="◈",good=false){return `<div class="metric-card"><div class="metric-top"><span>${label}</span><span class="metric-icon">${icon}</span></div><div class="metric-value">${value}</div><div class="metric-foot ${good?"good":""}">${foot}</div></div>`;}
function pill(status){const cls=status==="success"||status===true?"":status==="partial"?"warn":status==="failed"||status===false?"bad":"neutral";const label=status===true?"Available":status===false?"Unavailable":String(status??"Unknown");return `<span class="status-pill ${cls}"><i></i>${esc(label)}</span>`;}
function panel(title,subtitle,body,tag=""){const chartId=body.match(/<canvas id="([^"]+)"/)?.[1];return `<section class="panel ${chartId?"chart-panel":""}"><div class="panel-header"><div><h3>${title}</h3><p>${subtitle||""}</p></div><div class="panel-header-actions">${tag?`<span class="panel-tag">${tag}</span>`:""}${chartId?`<button type="button" class="chart-expand-button" data-expand-chart="${chartId}" aria-label="Expand ${esc(title)} chart" title="Expand chart">⛶</button>`:""}</div></div>${body}</section>`;}

function loadReportColumnVisibility(reportId,columns,defaults={}) {
  let saved={};try{saved=JSON.parse(localStorage.getItem("minio-analytics-report-columns:"+reportId)||"{}")||{};}catch{}
  const visibility={};columns.forEach(column=>{visibility[column.key]=typeof saved[column.key]==="boolean"?saved[column.key]:typeof defaults[column.key]==="boolean"?defaults[column.key]:true;});
  state.reportColumnVisibility[reportId]=visibility;return visibility;
}
function saveReportColumnVisibility(reportId,visibility) {state.reportColumnVisibility[reportId]={...visibility};localStorage.setItem("minio-analytics-report-columns:"+reportId,JSON.stringify(visibility));}
function reportRowCells(row,columns,visibility) {
  let index=0;
  return row.replace(/<td(?=[\s>])/g,()=>{
    const column=columns[index++];
    return column?'<td data-report-column-key="'+esc(column.key)+'"'+(visibility[column.key]===false?' hidden':''):'<td';
  });
}
function applyReportColumnVisibility(panel,visibility) {
  panel?.querySelectorAll("th[data-report-column-key],td[data-report-column-key]").forEach(cell=>{cell.hidden=visibility[cell.dataset.reportColumnKey]===false;});
}
function table(title,subtitle,headers,rows,empty="No records found.",reportConfig=null) {
  const columns=reportConfig?.columns||null,visibility=reportConfig?.visibility||{};
  const menu=columns?'<details class="report-column-menu"><summary>Columns <span>▾</span></summary><div class="report-column-options">'+columns.map(column=>'<label><input type="checkbox" data-report-column-toggle data-report-id="'+esc(reportConfig.id)+'" data-report-column-key="'+esc(column.key)+'" '+(visibility[column.key]!==false?"checked":"")+'><span>'+esc(column.label)+'</span></label>').join("")+'</div></details>':"";
  const actions='<div class="table-heading-actions">'+menu+'<button type="button" class="subtle-button table-export-button" data-export-table>↓ Export CSV</button></div>';
  const th=headers.map((header,index)=>'<th'+(columns?' data-report-column-key="'+esc(columns[index].key)+'"'+(visibility[columns[index].key]===false?' hidden':''):"")+'>'+header+'</th>').join("");
  const body=rows.length?rows.map(row=>columns?reportRowCells(row,columns,visibility):row).join(""):'<tr><td colspan="'+headers.length+'" class="empty-state">'+empty+'</td></tr>';
  return '<section class="table-panel'+(columns?' report-table-panel':'')+'"><div class="table-heading"><div><h3>'+title+'</h3><p>'+(subtitle||"")+'</p></div>'+actions+'</div><div class="table-scroll"><table><thead><tr>'+th+'</tr></thead><tbody>'+body+'</tbody></table></div></section>';
}
function exportTableCsv(button){
  const panel=button.closest(".table-panel"),tableEl=panel?.querySelector("table");
  if(!tableEl)return;
  const csvCell=value=>'"'+String(value??"").replace(/"/g,'""')+'"';
  const headers=[...tableEl.querySelectorAll("thead tr:first-child th[data-report-column-key]")];
  const visibleKeys=headers.filter(cell=>!cell.hidden&&getComputedStyle(cell).display!=="none").map(cell=>cell.dataset.reportColumnKey);
  const rows=[...tableEl.querySelectorAll("tbody tr")].filter(row=>!row.querySelector(".empty-state")).map(row=>{
    const cells=new Map([...row.querySelectorAll("td[data-report-column-key]")].map(cell=>[cell.dataset.reportColumnKey,cell]));
    return visibleKeys.map(key=>{
      const cell=cells.get(key);
      return cell&&!cell.hidden&&getComputedStyle(cell).display!=="none"?cell.innerText.replace(/\s+/g," ").trim():"";
    });
  });
  if(!visibleKeys.length||!rows.length){toast("There is no visible table data to export.",true);return;}
  const csv="\uFEFF"+[headers.filter(cell=>visibleKeys.includes(cell.dataset.reportColumnKey)).map(cell=>cell.innerText.replace(/\s+/g," ").trim()),...rows].map(row=>row.map(csvCell).join(",")).join("\r\n");
  const blob=new Blob([csv],{type:"text/csv;charset=utf-8;"}),url=URL.createObjectURL(blob),link=document.createElement("a");
  const title=panel.querySelector(".table-heading h3")?.textContent||"minio-report";
  const filename=title.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")||"minio-report";
  link.href=url;link.download=filename+"-"+new Date().toISOString().slice(0,10)+".csv";document.body.append(link);link.click();link.remove();URL.revokeObjectURL(url);
}
function chart(id,labels,sets,type="line",yMin=null,ySuffix=""){if(!window.Chart)return;const canvas=$("#"+id);if(!canvas)return;const instance=new Chart(canvas,{type,data:{labels,datasets:sets.map(s=>({label:s.label,data:s.data,borderColor:s.color,backgroundColor:s.color+"18",borderWidth:2,borderDash:s.dash?[7,5]:[],pointRadius:labels.length>45?1.5:3,pointHoverRadius:5,tension:.25,fill:false}))},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},plugins:{legend:{position:"bottom",labels:{usePointStyle:true,boxWidth:7,font:{size:10}}},tooltip:{callbacks:{label:ctx=>ctx.dataset.label+": "+(ctx.parsed.y==null?"—":new Intl.NumberFormat("en-IN",{maximumFractionDigits:3}).format(ctx.parsed.y)+ySuffix)}}},scales:{x:{grid:{display:false},ticks:{autoSkip:true,maxTicksLimit:11,maxRotation:45,minRotation:0,font:{size:9},color:"#94a0af"}},y:{...(yMin===null?{}:{min:yMin}),grid:{color:"#edf1f5"},ticks:{font:{size:9},color:"#94a0af",callback:value=>new Intl.NumberFormat("en-IN",{maximumFractionDigits:3}).format(value)+ySuffix}}}}});state.charts.push(instance);}
function clearCharts(){state.charts.forEach(c=>c.destroy());state.charts=[];}
function openExpandedChart(chartId,button){
  const instance=state.charts.find(item=>item.canvas?.id===chartId);
  const canvas=$("#"+CSS.escape(chartId));
  if(!instance||!canvas)return;
  closeExpandedChart();
  const placeholder=document.createComment("chart-placeholder");
  const originalParent=canvas.parentNode;
  const originalNext=canvas.nextSibling;
  originalParent.replaceChild(placeholder,canvas);
  const overlay=document.createElement("div");
  overlay.className="chart-expand-backdrop";
  overlay.innerHTML='<section class="chart-expand-dialog" role="dialog" aria-modal="true" aria-label="Expanded chart"><header><div><strong></strong><span>Expanded interactive chart</span></div><button type="button" class="chart-expand-close" aria-label="Close expanded chart" title="Close">×</button></header><div class="chart-expand-content"></div></section>';
  const panelEl=button.closest(".panel");
  overlay.querySelector("header strong").textContent=panelEl?.querySelector(".panel-header h3")?.textContent||"Chart";
  overlay.querySelector(".chart-expand-content").append(canvas);
  document.body.append(overlay);
  state.expandedChart={overlay,canvas,placeholder,originalParent,originalNext,instance};
  requestAnimationFrame(()=>instance.resize());
  overlay.querySelector(".chart-expand-close").focus();
  overlay.addEventListener("click",event=>{if(event.target===overlay)closeExpandedChart();});
}
function closeExpandedChart(){
  const current=state.expandedChart;
  if(!current)return;
  if(current.placeholder.parentNode)current.placeholder.parentNode.replaceChild(current.canvas,current.placeholder);
  else current.originalParent.insertBefore(current.canvas,current.originalNext?.parentNode===current.originalParent?current.originalNext:null);
  current.overlay.remove();
  state.expandedChart=null;
  requestAnimationFrame(()=>current.instance.resize());
}

function histogramRangeLabel(value){
  return String(value||"").replace(/_/g," ").replace(/LESS THAN/gi,"< ").replace(/GREATER THAN/gi,"> ").replace(/BETWEEN/gi,"").replace(/AND/gi,"–").replace(/\s+/g," ").trim();
}
function objectSizeHistogram(data,title){
  if(!data||data.status==="unavailable"||!data.distribution?.length)
    return panel(title,"Object-size distribution from the latest stored snapshot",'<div class="empty-state"><strong>Object-size distribution unavailable</strong><p>The MinIO size-distribution metric is missing for this snapshot.</p></div>');
  const partial=data.status==="partial";
  const note=partial?'<div class="chart-note"><strong>Partial histogram:</strong> '+data.buckets_available+' of '+data.buckets_expected+' buckets reported a distribution. Totals and percentages are withheld to avoid under-reporting.</div>':"";
  const rows=data.distribution;
  const tableRows=rows.map(x=>'<tr><td>'+esc(histogramRangeLabel(x.range))+'</td><td class="histogram-number">'+fmt(x.object_count,0)+'</td><td class="histogram-number">'+(x.percentage==null?'—':fmt(x.percentage,2)+'%')+'</td></tr>').join("");
  const controls='<div class="histogram-toolbar"><span>Display</span><div class="tenant-chart-controls"><button type="button" class="active" data-histogram-mode="graph" aria-pressed="true">Graph</button><button type="button" data-histogram-mode="table" aria-pressed="false">Table</button></div></div>';
  const graph='<div class="histogram-view" data-histogram-view="graph"><div class="chart-wrap histogram-chart-wrap"><canvas id="object-size-histogram"></canvas></div></div>';
  const tabular='<div class="histogram-view hidden" data-histogram-view="table"><div class="table-scroll"><table class="histogram-table"><thead><tr><th>OBJECT SIZE RANGE</th><th class="histogram-number">OBJECT COUNT</th><th class="histogram-number">PERCENTAGE</th></tr></thead><tbody>'+tableRows+'</tbody></table></div></div>';
  return panel(title,"Latest snapshot · "+dateLabel(data.snapshot_date)+" · Object count by object-size range",controls+graph+tabular+'<div class="histogram-summary"><strong>'+(data.total_objects==null?"—":fmt(data.total_objects,0))+'</strong><span>objects represented in histogram</span><span>'+data.buckets_available+'/'+data.buckets_expected+' buckets with distribution data</span></div>'+note);
}
function drawObjectSizeHistogram(data){
  if(!data||!["available","partial"].includes(data.status)||!data.distribution?.length)return;
  const canvas=$("#object-size-histogram");if(!canvas||!window.Chart)return;
  const rows=[...data.distribution].sort((a,b)=>a.object_count-b.object_count);
  const instance=new Chart(canvas,{type:"bar",data:{labels:rows.map(x=>histogramRangeLabel(x.range)),datasets:[{label:"Objects",data:rows.map(x=>x.object_count),backgroundColor:"#13a58b",borderRadius:4,barThickness:"flex",maxBarThickness:24}]},options:{indexAxis:"y",responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},plugins:{legend:{display:false},tooltip:{callbacks:{afterLabel:ctx=>{const x=rows[ctx.dataIndex];return x.percentage==null?"":x.percentage.toFixed(2)+"% of objects";}}}},scales:{x:{beginAtZero:true,grid:{color:"#edf1f5"},ticks:{font:{size:10},callback:v=>new Intl.NumberFormat("en-IN",{notation:"compact"}).format(v)}},y:{grid:{display:false},ticks:{font:{size:10},color:"#64748b"}}}}});
  state.charts.push(instance);
}
function setView(view){state.view=view;$$(".nav-link").forEach(b=>b.classList.toggle("active",b.dataset.view===(["bucket-usage-report","raw-capacity-report"].includes(view)?"capacity-report":view)));$("#page-breadcrumb").textContent=(["capacity-report","bucket-usage-report","raw-capacity-report"].includes(view)?"REPORTS":view.replaceAll("-"," ")).toUpperCase();render().catch(e=>toast(e.message,true));}
async function loadOverview(){state.overview=await api("/api/analytics/overview");state.clusters=(await api("/api/analytics/clusters")).items;}
async function render(){
  clearCharts();$("#content").innerHTML='<div class="loading-state">Loading dashboard data…</div>';
  if(state.view==="overview") await renderOverview();
  else if(state.view==="clusters") await renderClusters();
  else if(state.view==="capacity-report") await renderCapacityReport();
  else if(state.view==="bucket-usage-report") await renderBucketUsageReport();
  else if(state.view==="raw-capacity-report") await renderRawCapacityReport();
  else if(state.view==="tenants") await renderTenants();
  else if(state.view==="buckets") await renderBuckets();
  else if(state.view==="health") await renderHealth();
  else if(state.view==="users" && state.user.role==="admin") await renderUsers();
  else if(state.view==="master-admin" && state.user.is_master_admin) await renderMasterAdmin();
}
async function renderOverview(){
  await loadOverview();const o=state.overview,c=o.capacity_bytes,n=o.nodes;
  const cap=pct(c.raw_total_bytes-c.raw_free_bytes,c.raw_total_bytes);
  const clusterRows=o.cluster_items.map(x=>`<tr><td><span class="cell-strong">${esc(x.cluster_name)}</span><br><span class="cell-muted">${esc(x.location_name)}</span></td><td>${pill(!!x.metrics_available)}</td><td>${bytes(x.raw_total_bytes)}</td><td>${bytes(x.raw_total_bytes-x.raw_free_bytes)}</td><td>${x.nodes_online??"—"} / ${x.nodes_offline??"—"}</td><td>${x.days_to_full==null?"—":fmt(x.days_to_full,0)+" days"}</td><td><button class="table-link" data-cluster="${esc(x.cluster_id)}">Details →</button></td></tr>`);
  $("#content").innerHTML=pageHead("Fleet overview","A consolidated view of your MinIO storage estate.",'<button class="subtle-button" data-action="refresh">↻ Refresh</button>')+
    `<div class="metric-grid">${metric("RAW CAPACITY",bytes(c.raw_total_bytes),o.latest_cluster_snapshot_date?"Snapshot "+dateLabel(o.latest_cluster_snapshot_date):"No snapshot","▤")}${metric("RAW USED",bytes(c.raw_total_bytes-c.raw_free_bytes),cap==null?"Utilization unavailable":fmt(cap,1)+"% of raw capacity","◒")}${metric("USABLE CAPACITY",bytes(c.usable_total_bytes),"After storage protection","▦")}${metric("ONLINE NODES",n.online==null?"—":fmt(n.online,0),n.offline==null?"Node state unavailable":n.offline+" offline", "⌁",n.offline===0)}${metric("CLUSTERS",o.clusters.available+" / "+o.clusters.total,"Available clusters","◫",o.clusters.unavailable===0)}${metric("BUCKETS",fmt(o.inventory.active_buckets,0),o.inventory.unassigned_buckets+" unassigned","▤")}${metric("ACTIVE TENANTS",fmt(o.inventory.active_tenants,0),"Configured tenants","◇")}${metric("COLLECTION STATUS",o.latest_bucket_snapshot_date?dateLabel(o.latest_bucket_snapshot_date):"—","Latest bucket snapshot","◷")}</div>`+
    `<div class="panel-grid">${panel("Cluster capacity","Raw capacity utilization by cluster",'<div class="chart-wrap"><canvas id="capacity-chart"></canvas></div>',"LATEST SNAPSHOT")}${panel("Capacity breakdown","Fleet-wide capacity totals",`<div class="capacity-list"><div class="capacity-row"><span>Raw total</span><strong>${bytes(c.raw_total_bytes)}</strong><div class="progress"><span style="width:100%"></span></div></div><div class="capacity-row"><span>Raw used</span><strong>${bytes(c.raw_total_bytes-c.raw_free_bytes)}</strong><div class="progress amber"><span style="width:${cap??0}%"></span></div></div><div class="capacity-row"><span>Raw free</span><strong>${bytes(c.raw_free_bytes)}</strong><div class="progress blue"><span style="width:${pct(c.raw_free_bytes,c.raw_total_bytes)??0}%"></span></div></div><div class="capacity-row"><span>Usable total</span><strong>${bytes(c.usable_total_bytes)}</strong><div class="progress"><span style="width:100%"></span></div></div></div>`,"BYTES → TiB")}</div>`+
    table("Cluster status","Latest persisted cluster snapshots",["CLUSTER / LOCATION","STATUS","RAW TOTAL","RAW USED","NODES UP / DOWN","DAYS TO FULL",""],clusterRows);
  const labels=o.cluster_items.map(x=>x.cluster_name);chart("capacity-chart",labels,[{label:"Used TiB",data:o.cluster_items.map(x=>x.raw_total_bytes==null||x.raw_free_bytes==null?null:(x.raw_total_bytes-x.raw_free_bytes)/1024**4),color:"#13a58b"},{label:"Free TiB",data:o.cluster_items.map(x=>x.raw_free_bytes==null?null:x.raw_free_bytes/1024**4),color:"#4779d8"}],"bar");
}

async function renderCapacityReport(){
  const [d,columnPreferences]=await Promise.all([api("/api/analytics/capacity-report"),api("/api/analytics/report-column-preferences")]);
  const provisionedColumns=[{key:"cluster",label:"CLUSTER"},{key:"location",label:"LOCATION"},{key:"installed",label:"INSTALLED (TiB)"},{key:"provisioned",label:"PROVISIONED (TiB)"},{key:"used_usable",label:"USED CAP (TiB)"},{key:"used_bkt",label:"USED BKT (TiB)"},{key:"usable_free",label:"USABLE FREE (TiB)"},{key:"usage_pct",label:"USAGE %"},{key:"prov_pct",label:"PROV %"},{key:"bucket_coverage",label:"BUCKET COVERAGE"}];
  state.reportColumns=loadReportColumnVisibility("provisioned",provisionedColumns,columnPreferences.columns||{used_usable:true,used_bkt:true});
  const t=d.totals_bytes||{},f=d.capacity_factors||{dp:1.33,rf:0.85,eff:0.99};
  const cards=[
    metric("INSTALLED CAPACITY",bytes(t.installed_capacity_bytes),"Sum of installed capacity","▤"),
    metric("PROVISIONED",bytes(t.provisioned_bytes),"Sum of active bucket quotas","◫"),
    metric("USED CAP",bytes(t.used_cap_bytes),"Usable capacity minus usable free","◒"),
    metric("USED BKT",bytes(t.used_bucket_bytes),"Sum of active bucket usage","▤"),
    metric("USABLE FREE",bytes(t.free_capacity_bytes),"Usable free capacity","◇"),
    metric("AVG USED %",d.avg_used_pct==null?"—":fmt(d.avg_used_pct,1)+"%","Average of cluster Usage %","◔")
  ].join("");
  const rows=(d.items||[]).map(x=>{
    const coverage=x.active_bucket_count===0?"No active buckets":fmt(x.buckets_with_metrics,0)+" / "+fmt(x.active_bucket_count,0)+" buckets";
    return '<tr><td><span class="cell-strong">'+esc(x.cluster_name)+'</span></td><td><span class="cell-muted">'+esc(x.location_name)+'</span></td>'+
      '<td>'+tibValue(x.installed_capacity_bytes)+'</td>'+
      '<td>'+tibValue(x.provisioned_bytes)+'</td>'+
      '<td>'+tibValue(x.used_cap_bytes)+'</td><td>'+tibValue(x.used_bucket_bytes)+'</td>'+
      '<td>'+tibValue(x.free_capacity_bytes)+'</td>'+
      '<td>'+(x.usage_pct==null?"—":'<span class="status-pill '+(x.usage_pct>=80?"bad":x.usage_pct>=70?"warn":"")+'">'+fmt(x.usage_pct,1)+"%"+'</span>')+'</td>'+
      '<td>'+(x.provisioned_pct==null?"—":fmt(x.provisioned_pct,1)+"%")+'</td>'+
      '<td>'+esc(coverage)+'</td></tr>';
  });
  const formulas='<div class="report-footnotes"><strong>Calculation formulas</strong><ul>'+
    '<li>Installed Capacity = RAW total capacity from the latest cluster snapshot × Eff × (RF ÷ DP). Current factors: Eff '+fmt(f.eff,2)+', RF '+fmt(f.rf,2)+', DP '+fmt(f.dp,2)+'.</li>'+

    '<li>Provisioned = sum of quota bytes across all active buckets; shown only when every active bucket has quota data.</li>'+
    '<li>Used Cap = MinIO usable total capacity − usable free capacity.</li>'+
    '<li>Used BKT = sum of used bytes across all active buckets; shown only when every active bucket has usage data.</li>'+
    '<li>Usable Free = usable free bytes from the latest cluster snapshot.</li>'+
    '<li>Usage % = Used Cap ÷ Installed Capacity × 100. Prov % = Provisioned ÷ Installed Capacity × 100.</li>'+
    '<li>Avg Used % = arithmetic average of the available per-cluster Usage % values; unavailable values are excluded.</li>'+
    '</ul><p>Usage % colour: green below 70%; amber from 70% to below 80%; red at 80% and above.</p><p>Capacity units are shown in the column headers. N/A (—) indicates a missing snapshot or incomplete metric coverage; it is never treated as zero. Cluster capacity uses the latest cluster snapshot, while bucket totals use the latest bucket snapshot for that cluster.</p></div>';
  const generatedAt=new Date().toLocaleString("en-IN",{timeZone:"Asia/Kolkata",day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false});
  const dataAsOf=d.data_as_of?new Date(d.data_as_of).toLocaleString("en-IN",{timeZone:"Asia/Kolkata",day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false}):"Unavailable — snapshot missing for one or more clusters";
  const reportFactors='<span class="report-factor-meta" title="Data Protection · Risk Factor · Effective">DP = '+fmt(f.dp,2)+'&nbsp;&nbsp; RF = '+fmt(f.rf,2)+'&nbsp;&nbsp; Eff = '+fmt(f.eff,2)+'</span>';
  const factorControls=state.user?.role==="admin"?'<div class="capacity-factor-toolbar"><div class="capacity-factor-heading"><strong>Capacity planning factors</strong><small>Choose the data protection, risk factor and efficiency values used for capacity calculations.</small></div><form id="capacity-factors-form" class="capacity-factor-controls"><label>DP<input name="dp" type="number" min="0.01" max="100" step="0.01" value="'+Number(f.dp).toFixed(2)+'" required></label><label>RF<input name="rf" type="number" min="0.01" max="100" step="0.01" value="'+Number(f.rf).toFixed(2)+'" required></label><label>Eff<input name="eff" type="number" min="0.01" max="1" step="0.01" value="'+Number(f.eff).toFixed(2)+'" required></label><button class="primary-small" type="submit">Save & recalculate</button></form></div>':'';

  const headers=provisionedColumns.map(column=>column.label);
  $("#content").innerHTML=pageHead("Consolidated Provisioned Report","Fleet-wide raw capacity, used and free storage from the latest stored cluster snapshots. Data as of "+esc(dataAsOf)+" IST.",reportFactors+'<button class="subtle-button" data-action="refresh">↻ Refresh</button>')+
    reportTabs("capacity-report")+
    factorControls+
    '<div class="metric-grid capacity-report-grid">'+cards+'</div>'+
    table("Capacity by cluster",fmt(d.cluster_count,0)+" enabled cluster(s) · latest available cluster and bucket snapshots",headers,rows,"No enabled clusters are registered.",{id:"provisioned",columns:provisionedColumns,visibility:state.reportColumns})+
    formulas;
}
async function renderRawCapacityReport(){
  const d=await api("/api/analytics/raw-capacity-report");
  const t=d.totals_bytes||{};
  const generatedAt=new Date().toLocaleString("en-IN",{timeZone:"Asia/Kolkata",day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false});
  const dataAsOf=d.data_as_of?new Date(d.data_as_of).toLocaleString("en-IN",{timeZone:"Asia/Kolkata",day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false}):"Unavailable — snapshot missing for one or more clusters";
  const cards=[
    metric("RAW CAPACITY",bytes(t.raw_total_bytes),"Sum of latest raw capacity snapshots","▤"),
    metric("RAW USED",bytes(t.raw_used_bytes),"Raw capacity minus raw free","◒"),
    metric("RAW FREE",bytes(t.raw_free_bytes),"Sum of latest raw free capacity","◇"),
    metric("RAW USED %",d.raw_used_pct==null?"—":fmt(d.raw_used_pct,1)+"%","Fleet raw used ÷ raw capacity","◔"),
    metric("CLUSTER COVERAGE",fmt(d.available_cluster_count,0)+" / "+fmt(d.cluster_count,0),"Clusters with complete raw metrics","◫")
  ].join("");
  const rows=(d.items||[]).map(x=>{
    const usedPct=x.raw_used_pct==null?"—":'<span class="status-pill '+(x.raw_used_pct>=80?"bad":x.raw_used_pct>=70?"warn":"")+'">'+fmt(x.raw_used_pct,1)+"%"+'</span>';
    const nodes=x.nodes_online==null||x.nodes_offline==null?"—":fmt(x.nodes_online,0)+" online / "+fmt(x.nodes_offline,0)+" offline";
    const status=x.metrics_available?'<span class="status-pill">Available</span>':'<span class="status-pill bad">Unavailable</span>';
    const signedTiB=n=>n==null?"—":(n>=0?"+":"−")+tibValue(Math.abs(n));
    const growth=signedTiB(x.trend_growth_bytes_per_day);
    const change=signedTiB(x.change_vs_yesterday_bytes);
    const projection=x.projected_days_to_full==null?"N/A":fmt(x.projected_days_to_full,0);
    return '<tr><td><span class="cell-strong">'+esc(x.cluster_name)+'</span></td><td><span class="cell-muted">'+esc(x.location_name)+'</span></td>'+
      '<td>'+tibValue(x.raw_total_bytes)+'</td><td>'+tibValue(x.raw_used_bytes)+'</td><td>'+tibValue(x.raw_free_bytes)+'</td>'+
      '<td>'+usedPct+'</td><td>'+change+'</td><td>'+growth+(x.trend_sample_count!=null?' <span class="cell-muted">('+fmt(x.trend_sample_count,0)+' samples)</span>':'')+'</td><td>'+projection+'</td>'+
      '<td>'+nodes+'</td><td>'+status+'</td></tr>';
  });
  const notes='<div class="report-footnotes"><strong>Calculation and coverage notes</strong><ul>'+
    '<li>Raw capacity and raw free values are taken from each enabled cluster’s latest stored cluster snapshot.</li>'+
    '<li>Raw Used = Raw Capacity − Raw Free. The collector already applies the 0.993 raw-efficiency adjustment to stored raw capacity; it is not applied a second time in this report.</li>'+
    '<li>Change vs Yesterday = latest 00:00 IST Used − previous day 00:00 IST Used. It is unavailable if either daily snapshot is missing.</li>'+
    '<li>Trend Growth/Day = linear-regression slope of daily Used values over the latest 30 calendar days, using actual day offsets and available 00:00 IST snapshots. Negative growth is retained; fewer than two samples is unavailable.</li>'+
    '<li>Projected Days to Full = current RAW Free ÷ positive Trend Growth/Day, rounded down to whole days. It is N/A for zero or negative growth, or insufficient history.</li>'+
    '<li>Fleet totals and Raw Used % are shown only when every enabled cluster has both raw capacity and raw free metrics. Missing values are never treated as zero.</li>'+
    '<li>Fleet Raw Used % = total Raw Used ÷ total Raw Capacity × 100; this is a capacity-weighted fleet percentage.</li>'+
    '<li>Cluster node counts are displayed as reported by the same cluster snapshot and are not used to calculate raw capacity.</li>'+
    '</ul><p>Capacity and growth units are shown in the column headers. A dash indicates missing data. Historical calculations use the scheduled SQLite snapshots aligned to 00:00 IST.</p></div>';
  const rawCapacityColumns=[{key:"cluster",label:"CLUSTER"},{key:"location",label:"LOCATION"},{key:"raw_capacity",label:"RAW CAPACITY (TiB)"},{key:"raw_used",label:"RAW USED (TiB)"},{key:"raw_free",label:"RAW FREE (TiB)"},{key:"raw_used_pct",label:"RAW USED %"},{key:"change_yesterday",label:"CHANGE VS YESTERDAY (TiB)"},{key:"trend_growth",label:"TREND GROWTH (TiB/day)"},{key:"projected_days",label:"PROJECTED DAYS TO FULL"},{key:"nodes",label:"NODES"},{key:"status",label:"STATUS"}];
  const rawCapacityVisibility=loadReportColumnVisibility("raw-capacity",rawCapacityColumns);
  $("#content").innerHTML=pageHead("Consolidated RAW Capacity Report","Fleet-wide raw capacity, used and free storage from the latest stored cluster snapshots. Data as of "+esc(dataAsOf)+" IST.",'<button class="subtle-button" data-action="refresh">↻ Refresh</button>')+
    reportTabs("raw-capacity-report")+'<div class="metric-grid raw-capacity-grid">'+cards+'</div>'+
    table("Raw capacity by cluster",fmt(d.cluster_count,0)+" enabled cluster(s) · "+fmt(d.available_cluster_count,0)+" with complete raw metrics",rawCapacityColumns.map(column=>column.label),rows,"No enabled clusters are registered.",{id:"raw-capacity",columns:rawCapacityColumns,visibility:rawCapacityVisibility})+notes;
}
function bucketUsageFilterControl(key,title,items,valueKey,labelKey){
  const unique=[...new Map(items.map(x=>[String(x[valueKey]??"unassigned"),{value:String(x[valueKey]??"unassigned"),label:x[labelKey]||"Unassigned"}])).values()].sort((a,b)=>a.label.localeCompare(b.label));
  const selected=state.bucketUsageFilterDraft[key]||[];
  const summary=selected.length?selected.length+" selected":"All "+({Cluster:"clusters",Location:"locations",Tenant:"tenants"}[title]||title.toLowerCase());
  return '<div class="bucket-usage-filter-field"><label>'+title+'</label><details class="bucket-usage-multiselect" data-bucket-filter-group="'+key+'"><summary><span data-bucket-filter-summary>'+esc(summary)+'</span><span aria-hidden="true">▾</span></summary><div class="bucket-usage-multiselect-menu"><input type="search" class="bucket-usage-filter-search" placeholder="Search '+title.toLowerCase()+'…" data-bucket-filter-search="'+key+'"><div class="bucket-usage-filter-options">'+unique.map(x=>'<label class="bucket-usage-filter-option"><input type="checkbox" data-bucket-filter-option="'+key+'" value="'+esc(x.value)+'" '+(selected.includes(x.value)?"checked":"")+'><span>'+esc(x.label)+'</span></label>').join("")+'</div><div class="bucket-usage-multiselect-actions"><button type="button" class="subtle-button" data-bucket-filter-action="select-all" data-filter-key="'+key+'">Select all</button><button type="button" class="subtle-button" data-bucket-filter-action="clear" data-filter-key="'+key+'">Clear</button><button type="button" class="primary-small" data-bucket-filter-action="apply" data-filter-key="'+key+'">Apply</button></div></div></details></div>';
}
function closeBucketUsageFilterGroup(group){
  const key=group.dataset.bucketFilterGroup;
  group.open=false;
  state.bucketUsageFilterDraft[key]=[...(state.bucketUsageFilters[key]||[])];
  group.querySelectorAll("[data-bucket-filter-option]").forEach(input=>{input.checked=state.bucketUsageFilterDraft[key].includes(input.value);});
  updateBucketFilterGroup(group);
}
function updateBucketFilterGroup(group){
  const key=group.dataset.bucketFilterGroup,selected=state.bucketUsageFilterDraft[key]||[];
  const summary=group.querySelector("[data-bucket-filter-summary]");
  if(summary)summary.textContent=selected.length?selected.length+" selected":"All "+({cluster:"clusters",location:"locations",tenant:"tenants"}[key]||key);
}
async function renderBucketUsageReport(){
  const d=await api("/api/analytics/bucket-usage-report"),allItems=d.items||[],filters=state.bucketUsageFilters;
  state.bucketUsageFilterDraft={cluster:[...filters.cluster],location:[...filters.location],tenant:[...filters.tenant]};
  const filterPanel='<section class="panel bucket-usage-filters">'+bucketUsageFilterControl("cluster","Cluster",allItems,"cluster_id","cluster_name")+bucketUsageFilterControl("location","Location",allItems,"location_id","location_name")+bucketUsageFilterControl("tenant","Tenant",allItems,"tenant_id_at_snapshot","tenant_name_at_snapshot")+'<button type="button" class="subtle-button" data-action="reset-bucket-usage-filters">Clear filters</button></section>';
  const items=allItems.filter(x=>(!filters.cluster.length||filters.cluster.includes(String(x.cluster_id??"unassigned")))&&(!filters.location.length||filters.location.includes(String(x.location_id??"unassigned")))&&(!filters.tenant.length||filters.tenant.includes(String(x.tenant_id_at_snapshot??"unassigned"))));
  const fields=["used_bytes","quota_bytes","object_count","version_count","delete_marker_count"],totals={};
  for(const field of fields)totals[field]=!items.length?0:items.every(x=>x.metrics_available===1&&x[field]!=null)?items.reduce((sum,x)=>sum+x[field],0):null;
  const clusterIds=[...new Set(items.map(x=>x.cluster_id))],withMetrics=items.filter(x=>x.metrics_available===1).length,coverage=items.length?withMetrics/items.length*100:null;
  const snapshotMap=new Map();items.forEach(x=>snapshotMap.set(x.cluster_id,{date:x.bucket_snapshot_date,ts:x.cluster_bucket_snapshot_ts}));
  const dataAsOf=snapshotMap.size&&[...snapshotMap.values()].every(x=>x.date&&x.ts)?[...snapshotMap.values()].map(x=>x.ts).sort()[0]:null;
  const cards=[metric("USED STORAGE",bytes(totals.used_bytes),"Sum across filtered buckets","◒"),metric("ALLOCATED QUOTA",bytes(totals.quota_bytes),"Sum of filtered bucket quotas","▤"),metric("OBJECTS",totals.object_count==null?"—":fmt(totals.object_count,0),"Across filtered buckets","◫"),metric("VERSIONS",totals.version_count==null?"—":fmt(totals.version_count,0),"Stored object versions","▦"),metric("DELETE MARKERS",totals.delete_marker_count==null?"—":fmt(totals.delete_marker_count,0),"Across filtered buckets","◇"),metric("METRIC COVERAGE",items.length?fmt(withMetrics,0)+" / "+fmt(items.length,0):"0","Filtered buckets with metrics · "+(coverage==null?"—":fmt(coverage,1)+"%"),"◔")].join("");
  const rows=items.map(x=>{const status=x.status==="Available"?'<span class="status-pill">Available</span>':x.status==="Unavailable"?'<span class="status-pill bad">Unavailable</span>':'<span class="status-pill warn">No snapshot</span>';const tenant=x.metric_bucket_id?(x.tenant_name_at_snapshot||"Unassigned"):"—";return '<tr><td><span class="cell-strong">'+esc(x.bucket_name)+'</span></td><td>'+esc(x.cluster_name)+'</td><td>'+esc(x.location_name)+'</td><td>'+esc(tenant)+'</td><td>'+tibValue(x.quota_bytes)+'</td><td>'+tibValue(x.used_bytes)+'</td><td>'+(x.usage_pct==null?"—":fmt(x.usage_pct,1)+"%")+'</td><td>'+(x.object_count==null?"—":fmt(x.object_count,0))+'</td><td>'+(x.version_count==null?"—":fmt(x.version_count,0))+'</td><td>'+(x.delete_marker_count==null?"—":fmt(x.delete_marker_count,0))+'</td><td>'+status+'</td></tr>';});
  const asOf=dataAsOf?timestampLabel(dataAsOf):"Unavailable — one or more filtered clusters have no bucket snapshot",summary=filters.cluster.length||filters.location.length||filters.tenant.length?"Filtered view · ":"";
  const bucketUsageColumns=[{key:"bucket",label:"BUCKET"},{key:"cluster",label:"CLUSTER"},{key:"location",label:"LOCATION"},{key:"tenant",label:"TENANT"},{key:"quota",label:"QUOTA (TiB)"},{key:"used",label:"USED (TiB)"},{key:"usage_pct",label:"USAGE %"},{key:"objects",label:"OBJECTS"},{key:"versions",label:"VERSIONS"},{key:"delete_markers",label:"DELETE MARKERS"},{key:"status",label:"STATUS"}];
  const bucketUsageVisibility=loadReportColumnVisibility("bucket-usage",bucketUsageColumns);
  $("#content").innerHTML=pageHead("Consolidated Bucket Usage Report","Latest stored bucket usage for active buckets across enabled clusters. Data as of "+esc(asOf)+".",'<button class="subtle-button" data-action="refresh">↻ Refresh</button>')+reportTabs("bucket-usage-report")+filterPanel+'<div class="metric-grid bucket-usage-grid">'+cards+'</div>'+table("Bucket usage by tenant and cluster",summary+fmt(items.length,0)+" of "+fmt(allItems.length,0)+" active bucket(s) · "+fmt(clusterIds.length,0)+" cluster(s) · latest bucket snapshot per cluster",bucketUsageColumns.map(column=>column.label),rows,"No buckets match the selected filters.",{id:"bucket-usage",columns:bucketUsageColumns,visibility:bucketUsageVisibility})+'<div class="report-footnotes"><strong>Calculation and coverage notes</strong><ul><li>Each cluster uses its latest stored bucket snapshot date; all active buckets in that cluster are represented.</li><li>Totals are shown only when every filtered bucket has an available, non-null value for that metric. Missing values are never treated as zero.</li><li>Tenant attribution is taken from the bucket snapshot, not the current bucket assignment.</li><li>Usage % = Used bytes ÷ Quota bytes × 100; it is unavailable when quota is zero or missing.</li></ul><p>Capacity units are shown in the column headers. A dash indicates missing snapshot data or incomplete metric coverage.</p></div>';
}

async function renderClusters(){
  state.clusters=(await api("/api/analytics/clusters")).items;
  const rows=state.clusters.map(x=>`<tr><td><span class="cell-strong">${esc(x.cluster_name)}</span><br><span class="cell-muted">${esc(x.cluster_id)}</span></td><td>${esc(x.location_name)}</td><td>${pill(!!x.metrics_available)}</td><td>${bytes(x.raw_total_bytes)}</td><td>${bytes(x.raw_total_bytes-x.raw_free_bytes)}</td><td>${x.nodes_online??"—"} / ${x.nodes_offline??"—"}</td><td>${x.growth_bytes_per_day==null?"—":fmt(x.growth_bytes_per_day/1024**3)+" GiB"}</td><td><button class="table-link" data-cluster="${esc(x.cluster_id)}">View details →</button></td></tr>`);
  $("#content").innerHTML=pageHead("Clusters","Capacity, node health and daily growth across registered clusters.")+table("Registered clusters",state.clusters.length+" cluster(s)",["CLUSTER","LOCATION","STATUS","RAW CAPACITY","RAW USED","NODES UP / DOWN","GROWTH / DAY",""],rows);
}

async function renderMasterAdmin(){
  const [d, backups] = await Promise.all([
    api("/api/master-admin/settings"),
    api("/api/master-admin/backups")
  ]);
  const s=d.settings;
  const backupRows=backups.items.map(b=>`<tr><td><span class="cell-strong">${esc(b.filename)}</span></td><td>${timestampLabel(b.created_at)}</td><td>${fmt(b.size_bytes/1024/1024,2)} MiB</td><td>${pill("success")} Verified</td><td><a class="table-link" href="${esc(b.download_url)}">Download ↓</a></td></tr>`);
  $("#content").innerHTML=pageHead("Master Admin","Configure collector cadence and manage verified database backups.")+
    `<section class="panel" style="max-width:760px;margin-bottom:16px"><div class="panel-header"><div><h3>Collector schedule</h3><p>All times use Asia/Kolkata (IST).</p></div><span class="panel-tag">LIVE SETTINGS</span></div>
    <form id="master-settings-form" class="form-grid" style="display:grid;gap:14px;max-width:520px">
      <label>Node, drive health and filesystem interval (minutes)<input class="form-control" type="number" name="node_interval_minutes" min="1" max="60" step="1" value="${s.node_interval_minutes}" required></label>
      <p class="cell-muted">Default: every 5 minutes. Valid range: 1–60 minutes. Daily capacity, bucket and storage-topology collection remains separate.</p>
      <label>Detailed infrastructure telemetry retention (days)<input class="form-control" type="number" name="telemetry_retention_days" min="1" max="90" step="1" value="${s.telemetry_retention_days}" required></label>
      <p class="cell-muted">Default: 3 days. Applies to high-frequency node and drive samples across all configured clusters. Expired samples are removed automatically once per day.</p>
      <label>Daily capacity, bucket and pool collection time (IST)<input class="form-control" type="time" name="daily_collection_time" value="${esc(s.daily_collection_time)}" required></label>
      <label>Confirm your Master Admin password<input class="form-control" type="password" name="current_password" autocomplete="current-password" required></label>
      <div><button class="primary-button" type="submit">Save collector settings</button></div>
    </form><p class="cell-muted" style="margin-top:14px">The scheduler checks settings every 60 seconds. Retention cleanup runs daily. Daily reports and storage-topology history are not affected. Scheduled database backups continue at their configured time.</p></section>`+
    `<section class="panel" style="max-width:100%"><div class="panel-header"><div><h3>Database backups</h3><p>Creates a consistent SQLite online backup and verifies it with PRAGMA integrity_check. The dashboard remains available.</p></div><button class="primary-small" data-action="create-backup">Create backup now</button></div><p class="cell-muted" style="margin:0 0 14px">Manual backups use the same backup directory as scheduled backups. Scheduled retention remains 14 days.</p></section>`+
    table("Backup history",backups.count+" backup file(s)",["FILE","CREATED AT","SIZE","INTEGRITY",""],backupRows,"No database backups found.");
}

function rangeControl(days,kind,id,attribution="current") {
  const options=[[7,"Last 7 days"],[30,"Last 30 days"],[60,"Last 60 days"],[90,"Last 90 days"],[180,"Last 6 months"],[365,"Last 12 months"]];
  return '<div class="toolbar trend-controls"><label for="trend-range" class="cell-muted">Trend period</label><select id="trend-range" class="form-control" data-trend-kind="'+kind+'" data-trend-id="'+esc(id)+'" data-trend-attribution="'+attribution+'">'+options.map(([value,label])=>'<option value="'+value+'" '+(Number(days)===value?'selected':'')+'>'+label+'</option>').join('')+'<option value="custom">Custom range</option></select><label class="trend-date-label" for="trend-start">From</label><input type="date" id="trend-start" class="form-control" aria-label="Start date"><label class="trend-date-label" for="trend-end">To</label><input type="date" id="trend-end" class="form-control" aria-label="End date"><button class="secondary-button" data-action="apply-trend-dates" data-trend-kind="'+kind+'" data-trend-id="'+esc(id)+'" data-trend-attribution="'+attribution+'">Apply</button></div>';
}
function trendQuery(days,startDate,endDate,extra="") {
  const params=new URLSearchParams();
  if(startDate&&endDate){params.set("start_date",startDate);params.set("end_date",endDate);}
  else params.set("days",String(days));
  if(extra) for(const [k,v] of new URLSearchParams(extra)) params.set(k,v);
  return params.toString();
}
function quotaPanelBody(series){
  const withMetrics=series.filter(r=>(r.quota_bucket_count||0)>0);
  if(!withMetrics.length)return '<div class="chart-empty-state"><strong>No bucket quota metrics reported</strong><p>No quota values were reported for the selected snapshots. This may mean no bucket quotas are configured, or that Prometheus is not exposing the quota metric. Verify the MinIO quota metric before concluding.</p></div>';
  const incomplete=series.some(r=>r.bucket_quota_bytes==null);
  return (incomplete?'<div class="chart-note"><strong>Incomplete quota coverage:</strong> Some snapshots do not have quota metrics for every active bucket. Gaps are left blank rather than treating missing values as zero.</div>':"")+'<div class="chart-wrap"><canvas id="cluster-quota-chart"></canvas></div>';
}
async function showCluster(id,days=90,startDate=null,endDate=null){
  state.snapshotClusterId=id;state.snapshotRange={days,startDate,endDate};
  const [d,hist]=await Promise.all([api("/api/analytics/clusters/"+encodeURIComponent(id)+"?"+trendQuery(days,startDate,endDate)),api("/api/analytics/object-size-distribution/cluster/"+encodeURIComponent(id))]),x=d.latest||{},series=d.series||[];
  clearCharts();
  const section=(title,subtitle,content,tag="")=>'<section class="analytics-section"><div class="analytics-section-heading"><div><h2>'+title+'</h2><p>'+subtitle+'</p></div>'+(tag?'<span class="panel-tag">'+tag+'</span>':'')+'</div>'+content+'</section>';
  const healthBody='<div class="capacity-list"><div class="capacity-row"><span>Online nodes</span><strong>'+(x.nodes_online??"—")+'</strong></div><div class="capacity-row"><span>Offline nodes</span><strong>'+(x.nodes_offline??"—")+'</strong></div><div class="capacity-row"><span>30-day estimated growth</span><strong>'+(x.growth_bytes_per_day==null?"—":fmt(x.growth_bytes_per_day/1024**3)+" GiB/day")+'</strong></div><div class="capacity-row"><span>Snapshot date</span><strong>'+dateLabel(x.snapshot_date)+'</strong></div><div class="capacity-row"><span>Metrics</span><strong>'+pill(!!x.metrics_available)+'</strong></div></div>';
  const topologyBody='<div class="cluster-experience-links"><article class="cluster-experience-card"><div class="cluster-action-icon">⌁</div><div><strong>Node Infrastructure</strong><p>Monitor node availability, CPU, memory, drive health and filesystem utilisation over time.</p><button class="primary-small" data-action="open-node-infrastructure">Explore infrastructure →</button></div></article><article class="cluster-experience-card"><div class="cluster-action-icon">▦</div><div><strong>Storage Topology</strong><p>Inspect storage pools, erasure sets, drive distribution and read/write quorum.</p><button class="primary-small" data-action="open-storage-topology">Explore topology →</button></div></article></div>';
  $("#content").innerHTML=pageHead(esc(d.cluster.name),"Cluster · "+esc(d.cluster.location_name)+" · "+esc(id),'<button class="subtle-button" data-view="clusters">← All clusters</button>')+
    `<div class="detail-grid"><div class="detail-card"><small>RAW CAPACITY</small><strong>${bytes(x.raw_total_bytes)}</strong></div><div class="detail-card"><small>RAW FREE</small><strong>${bytes(x.raw_free_bytes)}</strong></div><div class="detail-card"><small>PROJECTED DAYS TO FULL</small><strong>${x.days_to_full==null||x.days_to_full<=0?"N/A":fmt(x.days_to_full,0)+" days"}</strong></div></div>`+
    section("Infrastructure status","See cluster availability first, then drill into nodes, drives, pools and erasure sets.",'<div class="panel-grid cluster-health-grid">'+
      panel("Cluster health","Latest infrastructure snapshot",healthBody,"LATEST SNAPSHOT")+
      '<section class="panel cluster-action-panel">'+topologyBody+'</section></div>')+
    section("Capacity & forecast","Understand raw capacity, bucket quota, growth velocity and projected exhaustion.",rangeControl(days,"cluster",id)+'<div class="panel-grid cluster-chart-grid">'+
      panel("Capacity trend","Daily raw used, free and total capacity",'<div class="chart-wrap"><canvas id="cluster-chart"></canvas></div>',days+" DAYS")+
      panel("Bucket quota trend","Sum of bucket quotas across active buckets",quotaPanelBody(series))+
      panel("Growth trend","30-day estimated growth rate · GiB/day",'<div class="chart-wrap"><canvas id="cluster-growth-chart"></canvas></div>')+
      panel("Days to full trend","30-day net consumption forecast · only projections up to 1,825 days (5 years) are shown",series.some(r=>r.days_to_full!=null&&r.days_to_full>0)?'<div class="chart-wrap"><canvas id="cluster-days-full-chart"></canvas></div>':'<div class="chart-empty-state"><strong>No reliable planning forecast</strong><p>A forecast requires at least 14 daily observations, declining free capacity and an estimated time to full within 5 years. Longer projections are hidden to avoid false confidence.</p></div>')+'</div>')+
    section("Object & bucket analytics","Track object growth and understand the distribution of object sizes.",'<div class="panel-grid cluster-chart-grid">'+
      panel("Object trend","Total objects across active buckets when metrics are complete",'<div class="chart-wrap"><canvas id="cluster-object-chart"></canvas></div>')+
      objectSizeHistogram(hist,"Cluster object size distribution")+'</div>')+
    '<div class="snapshot-link-panel"><div><strong>Daily snapshots</strong><p>Browse the complete daily history and collection status for this cluster.</p></div><button class="primary-small" data-action="open-cluster-snapshots">View daily snapshots →</button></div>';
  const trendLabels=series.map(r=>dateLabel(r.snapshot_date));
  chart("cluster-chart",trendLabels,[{label:"Used TiB",data:series.map(r=>r.raw_total_bytes==null||r.raw_free_bytes==null?null:(r.raw_total_bytes-r.raw_free_bytes)/1024**4),color:"#13a58b"},{label:"Free TiB",data:series.map(r=>r.raw_free_bytes==null?null:r.raw_free_bytes/1024**4),color:"#4779d8"},{label:"Total TiB",data:series.map(r=>r.raw_total_bytes==null?null:r.raw_total_bytes/1024**4),color:"#d9922e",dash:true}],"line",null," TiB");
  chart("cluster-growth-chart",trendLabels,[{label:"Estimated growth GiB/day",data:series.map(r=>r.growth_bytes_per_day==null?null:r.growth_bytes_per_day/1024**3),color:"#d9922e"}]);
  if(series.some(r=>r.days_to_full!=null&&r.days_to_full>0))chart("cluster-days-full-chart",trendLabels,[{label:"Projected days to full",data:series.map(r=>r.days_to_full==null||r.days_to_full<=0?null:r.days_to_full),color:"#4779d8"}],"line",0," days");
  chart("cluster-quota-chart",series.map(r=>dateLabel(r.snapshot_date)),[{label:"Bucket quota TiB",data:series.map(r=>r.bucket_quota_bytes==null?null:r.bucket_quota_bytes/1024**4),color:"#d9922e"}]);
  chart("cluster-object-chart",series.map(r=>dateLabel(r.snapshot_date)),[{label:"Objects",data:series.map(r=>r.bucket_object_count),color:"#4779d8"}]);drawObjectSizeHistogram(hist);
}

async function showClusterTopology(id, section="infra-overview"){
  const d=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"/topology");
  state.topologyClusterId=id;state.topologySection=section;
  const storageView=section==="storage-overview"||section==="pools"||section==="sets";
  const tabs=storageView?[["storage-overview","Overview"],["pools","Pools"],["sets","Erasure Sets"]]:[["infra-overview","Overview"],["nodes","Nodes"],["drives","Drives"]];
  const tabHtml='<div class="tabs">'+tabs.map(([key,label])=>'<button class="tab '+(section===key?'active':'')+'" data-topology-tab="'+key+'">'+label+'</button>').join("")+'</div>';
  const nodeSubsection=state.nodeSubsection||"health";
  const nodeSubTabsHtml='<div class="tabs node-subtabs">'+[["health","Health & Availability"],["performance","Performance"],["reports","Reports"]].map(([key,label])=>'<button class="tab '+(nodeSubsection===key?'active':'')+'" data-node-subtab="'+key+'">'+label+'</button>').join("")+'</div>';
  const nodes=d.nodes||[],drives=d.drives||[],pools=d.pools||[],sets=d.erasure_sets||[];
  const driveCountsComplete=nodes.length>0&&nodes.every(n=>n.drives_online!=null&&n.drives_offline!=null);
  const drivesOnline=driveCountsComplete?nodes.reduce((sum,n)=>sum+n.drives_online,0):null;
  const drivesOffline=driveCountsComplete?nodes.reduce((sum,n)=>sum+n.drives_offline,0):null;
  const nodeRows=nodes.map(n=>{
    const ne=n.node_exporter_up===1,ms=n.minio_scrape_up===1;
    const mem=n.memory_total_bytes&&n.memory_used_bytes!=null?n.memory_used_bytes/n.memory_total_bytes*100:null;
    return '<tr><td><span class="cell-strong">'+esc(n.node_name)+'</span></td><td>'+pill(ne?'Online':n.node_exporter_up===0?'Offline':'Unknown')+'</td><td>'+pill(ms?'Reachable':n.minio_scrape_up===0?'Unreachable':'Unknown')+'</td><td>'+(n.cpu_utilization_pct==null?'—':fmt(n.cpu_utilization_pct,1)+'%')+'</td><td>'+(mem==null?'—':fmt(mem,1)+'%')+'</td><td>'+(n.load1==null?'—':fmt(n.load1,2))+'</td><td>'+(n.drives_online??'—')+'</td><td>'+(n.drives_offline??'—')+'</td></tr>';
  });
  const driveRows=drives.map(v=>{
    const minioPct=v.total_bytes&&v.used_bytes!=null?v.used_bytes/v.total_bytes*100:null;
    const fsPct=v.filesystem_used_pct;
    const readonly=v.filesystem_readonly===1;
    return '<tr><td><span class="cell-strong">'+esc(v.node_name)+'</span></td><td>'+esc(v.drive_path)+'</td><td>'+bytes(v.total_bytes)+'</td><td>'+bytes(v.used_bytes)+'</td><td>'+(minioPct==null?'—':fmt(minioPct,1)+'%')+'</td><td>'+(fsPct==null?'—':fmt(fsPct,1)+'%')+'</td><td>'+pill(readonly?'Read-only':v.filesystem_readonly===0?'Writable':'Unknown')+'</td><td>'+(v.availability_errors??'—')+' / '+(v.io_errors??'—')+' / '+(v.timeout_errors??'—')+'</td></tr>';
  });
  const poolRows=pools.map(p=>'<tr><td>'+esc(p.pool_id)+'</td><td>'+p.erasure_set_count+'</td><td>'+(p.online_drives??'—')+'</td><td>'+(p.healing_drives??'—')+'</td></tr>');
  const setRows=sets.map(s=>'<tr><td>'+esc(s.pool_id)+'</td><td>'+esc(s.set_id)+'</td><td>'+(s.status_value??'—')+'</td><td>'+(s.online_drives??'—')+'</td><td>'+(s.healing_drives??'—')+'</td><td>'+(s.read_quorum??'—')+'</td><td>'+(s.write_quorum??'—')+'</td></tr>');

  let trendData=null,performanceData=null;
  const trendFilter=state.topologyTrendFilters?.[id]||{startDate:"",endDate:""};
  if(section==="drives"){
    const trendParams=new URLSearchParams();
    if(trendFilter.startDate)trendParams.set("start_date",trendFilter.startDate);
    if(trendFilter.endDate)trendParams.set("end_date",trendFilter.endDate);
    trendData=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"/topology/trends?"+trendParams.toString());
  }
  if(section==="nodes"){
    performanceData=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"/nodes/performance?hours="+state.nodePerformanceHours);
  }
  const trendControls=trendData?'<section class="panel health-trends-panel"><div class="panel-header"><div><h3>Historical infrastructure trends</h3><p>Four-hour telemetry samples · '+fmt(trendData.sample_count||0,0)+' samples</p></div></div><div class="health-trend-filters"><label>FROM DATE<input id="infra-trend-start" type="date" value="'+esc(trendFilter.startDate)+'"></label><label>TO DATE<input id="infra-trend-end" type="date" value="'+esc(trendFilter.endDate)+'"></label><button class="primary-small" data-action="apply-infra-trends">Apply</button><button class="subtle-button" data-action="reset-infra-trends">Last 30 days</button></div></section>':'';
  const trendSamples=trendData?.samples||[];
  const trendLabels=trendSamples.map(x=>timestampLabel(x.snapshot_ts));
  const trendPanel=(title,description,canvasId)=>'<section class="panel"><div class="panel-header"><div><h3>'+title+'</h3><p>'+description+'</p></div></div>'+(trendSamples.length?'<div class="chart-wrap health-trend-chart"><canvas id="'+canvasId+'"></canvas></div>':'<div class="chart-empty-state"><strong>No historical samples available</strong><p>No telemetry was stored in the selected date range.</p></div>')+'</section>';
  const infraOverview='<div class="metric-grid">'+
    metric("NODES",nodes.length,nodes.filter(n=>n.node_exporter_up===1).length+" Node Exporter targets reachable","⌁")+
    metric("DRIVES",drives.length,drivesOnline==null?"Online/offline counts unavailable":drivesOnline+" online · "+drivesOffline+" offline","▤")+
    metric("NODE EXPORTER",nodes.filter(n=>n.node_exporter_up===1).length+" / "+nodes.length,"Reachable nodes","◉")+
    metric("MINIO SCRAPES",nodes.filter(n=>n.minio_scrape_up===1).length+" / "+nodes.length,"Reachable MinIO targets","◈")+'</div>';
  const storageOverview='<div class="metric-grid">'+
    metric("STORAGE POOLS",pools.length,"Pools discovered","▦")+
    metric("ERASURE SETS",sets.length,"Sets discovered","◫")+
    metric("DRIVES",drives.length,"Drives reported by MinIO","▤")+
    metric("ONLINE DRIVES",pools.every(p=>p.online_drives!=null)?pools.reduce((sum,p)=>sum+p.online_drives,0):"—","Reported online drive count","◇")+'</div>'+
    table("Storage pools","Pool counts and drive state derived from discovered erasure-set metrics.",["POOL","ERASURE SETS","ONLINE DRIVES","HEALING DRIVES"],poolRows);
  let body="";
  if(section==="infra-overview") body=infraOverview;
  const perfNodes=performanceData?.nodes||[],perfSamples=performanceData?.samples||[];
  const perfRows=perfNodes.map(n=>'<tr><td><span class="cell-strong">'+esc(n.node_name)+'</span></td><td>'+(n.avg_cpu_pct==null?'—':fmt(n.avg_cpu_pct,1)+'%')+'</td><td>'+(n.avg_memory_used_pct==null?'—':fmt(n.avg_memory_used_pct,1)+'%')+'</td><td>'+(n.avg_load1==null?'—':fmt(n.avg_load1,2))+'</td><td>'+fmt(n.sample_count,0)+'</td><td>'+(n.node_exporter_availability_pct==null?'—':fmt(n.node_exporter_availability_pct,1)+'%')+'</td></tr>');
  const perfToolbar='<div class="toolbar node-performance-range"><span class="cell-muted">AVERAGING WINDOW</span>'+[2,6,12,24].map(h=>'<button class="secondary-button '+(state.nodePerformanceHours===h?'active':'')+'" data-node-hours="'+h+'">'+h+'h</button>').join("")+'</div>';
  const perfCoverage=performanceData?'<p class="cell-muted">Samples: '+fmt(performanceData.sample_count,0)+' / '+fmt(performanceData.expected_samples,0)+' expected · '+fmt(performanceData.coverage_pct,1)+'% coverage · collected every '+performanceData.interval_minutes+' minutes</p>':'';
  const avgCpu=perfNodes.length?perfNodes.reduce((s,n)=>s+(n.avg_cpu_pct||0),0)/perfNodes.length:null;
  const avgMem=perfNodes.length?perfNodes.reduce((s,n)=>s+(n.avg_memory_used_pct||0),0)/perfNodes.length:null;
  const avgLoad=perfNodes.length?perfNodes.reduce((s,n)=>s+(n.avg_load1||0),0)/perfNodes.length:null;
  const nodeHealthBody=table("Node availability","Node Exporter and MinIO scrape status are shown independently.",["NODE","NODE EXPORTER","MINIO TARGET","CPU (LATEST)","MEMORY (LATEST)","LOAD 1M","DRIVES UP","DRIVES DOWN"],nodeRows);
  const nodePerformanceBody=perfToolbar+perfCoverage+'<div class="metric-grid">'+metric("AVG CPU",avgCpu==null?"—":fmt(avgCpu,1)+"%","Across nodes · selected window","◒")+metric("AVG MEMORY",avgMem==null?"—":fmt(avgMem,1)+"%","Across nodes · selected window","▤")+metric("AVG LOAD",avgLoad==null?"—":fmt(avgLoad,2),"1-minute load · selected window","⌁")+'</div><div class="health-infra-trend-grid">'+trendPanel("Average CPU utilization","Average across nodes at each five-minute sample","infra-cpu-trend")+trendPanel("Average memory utilization","Weighted memory utilization across nodes","infra-memory-trend")+trendPanel("Average load","Average 1-minute load across nodes","infra-load-trend")+'</div>'+table("Node performance","Per-node averages for the selected time window.",["NODE","AVG CPU","AVG MEMORY","AVG LOAD 1M","SAMPLES","NODE EXPORTER AVAILABILITY"],perfRows);
  const nodeReportsBody=perfToolbar+perfCoverage+table("Node performance report","Average, minimum and peak values for each node over the selected window.",["NODE","CPU AVG / MIN / PEAK","MEMORY AVG / MIN / PEAK","LOAD AVG / PEAK","SAMPLES","EXPORTER AVAILABILITY"],perfNodes.map(n=>'<tr><td><span class="cell-strong">'+esc(n.node_name)+'</span></td><td>'+fmt(n.avg_cpu_pct,1)+'% / '+fmt(n.min_cpu_pct,1)+'% / '+fmt(n.max_cpu_pct,1)+'%</td><td>'+fmt(n.avg_memory_used_pct,1)+'% / '+fmt(n.min_memory_used_pct,1)+'% / '+fmt(n.max_memory_used_pct,1)+'%</td><td>'+fmt(n.avg_load1,2)+' / '+fmt(n.max_load1,2)+'</td><td>'+fmt(n.sample_count,0)+'</td><td>'+fmt(n.node_exporter_availability_pct,1)+'%</td></tr>'));
  if(section==="nodes") body=nodeSubTabsHtml+(nodeSubsection==="health"?nodeHealthBody:nodeSubsection==="performance"?nodePerformanceBody:nodeReportsBody);
  if(section==="drives") body=trendControls+'<div class="health-infra-trend-grid">'+
    trendPanel("Drive availability","Online and offline drive counts across the cluster","infra-drive-availability")+
    trendPanel("Drive error counters","Cumulative availability, I/O and timeout errors reported by drives","infra-drive-errors")+
    trendPanel("Filesystem utilization","Weighted utilization across monitored MinIO data filesystems","infra-filesystem-trend")+
    '</div>'+table("Drive health","MinIO drive metrics and matching Linux filesystem mount metrics. Error columns: availability / I/O / timeout.",["NODE","MINIO DRIVE","MINIO TOTAL","MINIO USED","MINIO USED %","FILESYSTEM USED %","FILESYSTEM","ERRORS A / I / T"],driveRows);
  if(section==="storage-overview") body=storageOverview;
  if(section==="pools") body=table("Storage pools","Pool capacity is not inferred where no pool-level capacity metric was discovered.",["POOL","ERASURE SETS","ONLINE DRIVES","HEALING DRIVES"],poolRows);
  if(section==="sets") body=table("Erasure sets","Status is shown as the raw MinIO metric value; quorum values are not interpreted as a health enum.",["POOL","SET","STATUS VALUE","ONLINE DRIVES","HEALING DRIVES","READ QUORUM","WRITE QUORUM"],setRows);
  const errors=Object.keys(d.family_errors||{}).length?'<div class="detail-card" style="margin-bottom:14px"><strong>Some topology metric families are unavailable</strong><p class="muted">'+esc(JSON.stringify(d.family_errors))+'</p></div>':'';
  clearCharts();
  const pageTitle=storageView?"Storage Topology":"Node Infrastructure";
  const pageSubtitle=storageView?"MinIO storage pools, erasure sets and quorum topology":"Node availability, compute resources, drive health and filesystem telemetry";
  const pageSnapshot='<span class="page-heading-snapshot">Snapshot '+esc(timestampLabel(storageView?d.topology_snapshot_ts:d.node_snapshot_ts))+'</span>';
  $("#content").innerHTML=pageHead(esc(d.cluster.name)+" — "+pageTitle,pageSubtitle+pageSnapshot,'<button class="subtle-button" data-action="back-to-cluster-overview">← Back to cluster</button>')+errors+tabHtml+body;
  if(perfSamples.length&&section==="nodes"&&nodeSubsection==="performance"){
    const perfLabels=perfSamples.map(x=>timestampLabel(x.snapshot_ts));
    chart("infra-cpu-trend",perfLabels,[{label:"Average CPU",data:perfSamples.map(x=>x.avg_cpu_pct),color:"#4776c7"}],"line",0,"%");
    chart("infra-memory-trend",perfLabels,[{label:"Average memory",data:perfSamples.map(x=>x.avg_memory_used_pct),color:"#16a085"}],"line",0,"%");
    chart("infra-load-trend",perfLabels,[{label:"Average load 1m",data:perfSamples.map(x=>x.avg_load1),color:"#d99a35"}],"line",0,"");
  }
  if(trendSamples.length&&section==="drives"){
    chart("infra-drive-availability",trendLabels,[{label:"Drives online",data:trendSamples.map(x=>x.drives_online),color:"#16a085"},{label:"Drives offline",data:trendSamples.map(x=>x.drives_offline),color:"#d9534f"}],"line",0,"");
    chart("infra-drive-errors",trendLabels,[{label:"Availability errors",data:trendSamples.map(x=>x.availability_errors),color:"#d99a35"},{label:"I/O errors",data:trendSamples.map(x=>x.io_errors),color:"#8b6ccf"},{label:"Timeout errors",data:trendSamples.map(x=>x.timeout_errors),color:"#64748b"}],"line",0,"");
    chart("infra-filesystem-trend",trendLabels,[{label:"Filesystem used",data:trendSamples.map(x=>x.filesystem_weighted_used_pct??x.filesystem_used_pct),color:"#d99a35"}],"line",0,"%");
  }
}

async function showClusterSnapshots(id,days=90,startDate=null,endDate=null){
  state.snapshotClusterId=id;state.snapshotRange={days,startDate,endDate};
  const d=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"?"+trendQuery(days,startDate,endDate));
  const rows=(d.series||[]).map(r=>`<tr><td>${dateLabel(r.snapshot_date)}</td><td>${bytes(r.raw_total_bytes)}</td><td>${bytes(r.raw_free_bytes)}</td><td>${bytes(r.usable_total_bytes)}</td><td>${bytes(r.usable_free_bytes)}</td><td>${r.nodes_online??"—"}</td><td>${r.nodes_offline??"—"}</td><td>${r.growth_bytes_per_day==null?"—":fmt(r.growth_bytes_per_day/1024**3)+" GiB"}</td><td>${r.days_to_full==null?"—":fmt(r.days_to_full,0)+" days"}</td><td>${pill(!!r.metrics_available)}</td></tr>`);
  clearCharts();
  $("#content").innerHTML=pageHead(esc(d.cluster.name)+" — Daily snapshots","Historical daily cluster metrics · "+esc(d.cluster.location_name),'<button class="subtle-button" data-action="back-to-cluster">← Back to cluster</button>')+
    rangeControl(days,"cluster-snapshots",id)+
    table("Daily snapshots",rows.length+" snapshot(s) · "+(startDate&&endDate?dateLabel(startDate)+" – "+dateLabel(endDate):"Last "+days+" days"),["DATE","RAW TOTAL","RAW FREE","USABLE TOTAL","USABLE FREE","ONLINE","OFFLINE","GROWTH / DAY","DAYS TO FULL","STATUS"],rows,"No daily snapshots are available for this date range.");
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
async function showTenant(id,attribution="current",days=90,startDate=null,endDate=null){
  state.snapshotContext={type:"tenant",id,attribution,days,startDate,endDate};
  state.tenantCapacityScale=state.tenantCapacityScale||"zero";
  const [d,hist]=await Promise.all([api("/api/analytics/tenants/"+id+"?"+trendQuery(days,startDate,endDate,"attribution="+encodeURIComponent(attribution))),api("/api/analytics/object-size-distribution/tenant/"+id+"?attribution="+encodeURIComponent(attribution))]);clearCharts();
  const current=attribution==="current";
  const subtitle=current
    ?"Historical bucket usage attributed using current tenant ownership."
    :"Historical usage attributed to this tenant at snapshot time.";
  const actions=`<div class="heading-actions"><button class="subtle-button ${current?'active':''}" data-tenant-mode="current" data-tenant-id="${id}" aria-pressed="${current}">Current ownership</button><button class="subtle-button ${!current?'active':''}" data-tenant-mode="historical" data-tenant-id="${id}" aria-pressed="${!current}">Historical ownership</button><button class="subtle-button" data-view="tenants">← All tenants</button></div>`;
  const hasHistoricalSnapshots=Array.isArray(d.series)&&d.series.length>0;
  const noHistoricalAttribution=!current&&!hasHistoricalSnapshots;
  const hasQuota=(d.series||[]).some(r=>r.quota_bytes!=null);
  const capacityControls='<div class="tenant-chart-controls"><span>Y-axis scale</span><button type="button" data-tenant-scale="zero" class="'+(state.tenantCapacityScale==="zero"?"active":"")+'">Zero-based</button><button type="button" data-tenant-scale="zoom" class="'+(state.tenantCapacityScale==="zoom"?"active":"")+'">Zoomed</button></div>';
  const charts=noHistoricalAttribution
    ? panel("No historical attribution available","No bucket snapshots were attributed to this tenant during the selected period.",'<div class="empty-state"><strong>No historical ownership records found</strong><p>Bucket ownership was assigned after the relevant daily snapshots. Historical reporting will populate as new daily snapshots are collected under this tenant\'s ownership.</p><p>To view the historical usage of buckets assigned to this tenant today, switch to <strong>Current ownership</strong>.</p></div>')
    : panel("Tenant capacity and quota trend",current?"Daily usage and summed bucket quotas for currently assigned buckets · GiB":"Daily usage and quotas based on historical snapshot attribution · GiB",capacityControls+'<div class="chart-wrap"><canvas id="tenant-chart"></canvas></div>'+(hasQuota?'':'<div class="chart-note"><span class="chart-note-icon">ⓘ</span><strong>Quota not configured for the buckets attributed to this tenant.</strong></div>'))+
      panel("Tenant object trend","Daily object count across attributed buckets",'<div class="chart-wrap"><canvas id="tenant-object-chart"></canvas></div>')+objectSizeHistogram(hist,"Tenant object size distribution");
  $("#content").innerHTML=pageHead(esc(d.tenant.name),subtitle,actions)+
    `${rangeControl(days,"tenant",id,attribution)}<div class="detail-grid"><div class="detail-card"><small>DESCRIPTION</small><strong style="font-size:14px">${esc(d.tenant.description||"—")}</strong></div><div class="detail-card"><small>STATUS</small><strong style="font-size:14px">${d.tenant.is_active?"Active":"Inactive"}</strong></div><div class="detail-card"><small>HISTORY WINDOW</small><strong>${days} days</strong></div></div>`+
    charts+
    `<div class="snapshot-link-panel"><div><strong>Daily snapshots</strong><p>Browse daily tenant usage, quota, object counts and metric availability.</p></div><button class="primary-small" data-action="open-tenant-snapshots">View daily snapshots →</button></div>`;
  if(!noHistoricalAttribution){
    chart("tenant-chart",d.series.map(r=>dateLabel(r.snapshot_date)),[{label:"Used GiB",data:d.series.map(r=>r.used_bytes==null?null:r.used_bytes/1024**3),color:"#13a58b",fill:true},...(hasQuota?[{label:"Quota GiB",data:d.series.map(r=>r.quota_bytes==null?null:r.quota_bytes/1024**3),color:"#d9922e"}]:[])],"line",state.tenantCapacityScale==="zero"?0:undefined);
    chart("tenant-object-chart",d.series.map(r=>dateLabel(r.snapshot_date)),[{label:"Objects",data:d.series.map(r=>r.object_count),color:"#4779d8",fill:true}]);drawObjectSizeHistogram(hist);
  }
}
async function showTenantSnapshots(id,attribution="current",days=90,startDate=null,endDate=null){
  state.snapshotContext={type:"tenant",id,attribution,days,startDate,endDate};
  const d=await api("/api/analytics/tenants/"+id+"?"+trendQuery(days,startDate,endDate,"attribution="+encodeURIComponent(attribution)));
  const current=attribution==="current";
  const rows=(d.series||[]).map(r=>`<tr><td>${dateLabel(r.snapshot_date)}</td><td>${r.bucket_count}</td><td>${bytes(r.used_bytes)}</td><td>${bytes(r.quota_bytes)}</td><td>${fmt(r.object_count,0)}</td><td>${r.unavailable_bucket_metrics??"—"}</td></tr>`);
  clearCharts();
  $("#content").innerHTML=pageHead(esc(d.tenant.name)+" — Daily snapshots",current?"Daily metrics using current bucket ownership.":"Daily metrics using tenant ownership recorded at snapshot time.",'<button class="subtle-button" data-action="back-to-entity">← Back to tenant</button>')+
    rangeControl(days,"tenant-snapshots",id,attribution)+
    table("Daily tenant snapshots",rows.length+" snapshot(s) · "+(current?"Current ownership":"Historical ownership"),["DATE","BUCKETS","USED","QUOTA","OBJECTS","UNAVAILABLE BUCKETS"],rows,current?"No stored bucket snapshots found for buckets currently assigned to this tenant.":"No snapshots were recorded under this tenant's ownership during this period.");
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
async function showBucket(id,days=90,startDate=null,endDate=null){
  state.snapshotContext={type:"bucket",id,attribution:"current",days,startDate,endDate};
  const [d,h,hist]=await Promise.all([api("/api/analytics/buckets/"+id+"?"+trendQuery(days,startDate,endDate)),api("/api/buckets/"+id+"/history"),api("/api/analytics/object-size-distribution/bucket/"+id)]);const series=d.series||[],latest=series.at(-1)||{};clearCharts();
  $("#content").innerHTML=pageHead(esc(d.bucket.bucket_name),"Cluster · "+esc(d.bucket.cluster_name)+" · Current tenant: "+esc(d.bucket.current_tenant_name||"Unassigned"),'<button class="subtle-button" data-view="buckets">← All buckets</button>')+
    `<div class="detail-grid"><div class="detail-card"><small>USED</small><strong>${bytes(latest.used_bytes)}</strong></div><div class="detail-card"><small>QUOTA</small><strong>${bytes(latest.quota_bytes)}</strong></div><div class="detail-card"><small>OBJECTS</small><strong>${fmt(latest.object_count,0)}</strong></div></div>`+
    panel("Bucket usage and quota trend","Daily usage and quota in TiB",rangeControl(days,"bucket",id)+'<div class="chart-wrap"><canvas id="bucket-chart"></canvas></div>')+
    panel("Bucket object trend","Daily object count",'<div class="chart-wrap"><canvas id="bucket-object-chart"></canvas></div>')+objectSizeHistogram(hist,"Bucket object size distribution")+
    `<div class="snapshot-link-panel"><div><strong>Daily snapshots</strong><p>Browse daily usage, quota, object counts and snapshot-time tenant attribution.</p></div><button class="primary-small" data-action="open-bucket-snapshots">View daily snapshots →</button></div>`+
    table("Assignment history","Administrative ownership changes",["CHANGED AT","TENANT","CHANGED BY","NOTE"],h.items.map(r=>`<tr><td>${esc(r.changed_at)}</td><td>${esc(r.tenant_name||"Unassigned")}</td><td>${esc(r.changed_by)}</td><td>${esc(r.note||"—")}</td></tr>`));
  chart("bucket-chart",series.map(r=>dateLabel(r.snapshot_date)),[{label:"Used TiB",data:series.map(r=>r.used_bytes==null?null:r.used_bytes/1024**4),color:"#13a58b",fill:true},{label:"Quota TiB",data:series.map(r=>r.quota_bytes==null?null:r.quota_bytes/1024**4),color:"#d9922e"}]);
  chart("bucket-object-chart",series.map(r=>dateLabel(r.snapshot_date)),[{label:"Objects",data:series.map(r=>r.object_count),color:"#4779d8",fill:true}]);drawObjectSizeHistogram(hist);
}
async function showBucketSnapshots(id,days=90,startDate=null,endDate=null){
  state.snapshotContext={type:"bucket",id,attribution:"current",days,startDate,endDate};
  const d=await api("/api/analytics/buckets/"+id+"?"+trendQuery(days,startDate,endDate));
  const rows=(d.series||[]).map(r=>`<tr><td>${dateLabel(r.snapshot_date)}</td><td>${esc(r.tenant_name_at_snapshot||"Unassigned")}</td><td>${bytes(r.used_bytes)}</td><td>${bytes(r.quota_bytes)}</td><td>${fmt(r.object_count,0)}</td><td>${r.version_count??"—"}</td><td>${r.delete_marker_count??"—"}</td><td>${pill(!!r.metrics_available)}</td></tr>`);
  clearCharts();
  $("#content").innerHTML=pageHead(esc(d.bucket.bucket_name)+" — Daily snapshots","Historical bucket metrics · Cluster "+esc(d.bucket.cluster_name),'<button class="subtle-button" data-action="back-to-entity">← Back to bucket</button>')+
    rangeControl(days,"bucket-snapshots",id)+
    table("Daily snapshots",rows.length+" snapshot(s)",["DATE","TENANT AT SNAPSHOT","USED","QUOTA","OBJECTS","VERSIONS","DELETE MARKERS","STATUS"],rows,"No bucket snapshots are available for this date range.");
}
async function renderHealth(){
  const f=state.healthFilters;
  const params=new URLSearchParams({page:String(f.page),page_size:String(f.pageSize)});
  if(f.startDate)params.set("start_date",f.startDate);
  if(f.endDate)params.set("end_date",f.endDate);
  if(f.status)params.set("status",f.status);
  state.health=await api("/api/analytics/collection-health?"+params.toString());
  const h=state.health,s=h.schedule||{},jobs=s.jobs||{};
  const node=jobs.node_health||{},daily=jobs.daily_collection||{};
  const counts=h.status_counts||{},pg=h.pagination||{};
  const jobCard=(title,job,nextLabel,subtitle)=>`<section class="panel scheduler-job"><div class="panel-header"><div><h3>${title}</h3><p>${subtitle}</p></div>${pill(job.last_status||"Not run")}</div><div class="scheduler-job-grid"><div><small>LAST STARTED</small><strong>${timestampLabel(job.last_started_at)}</strong></div><div><small>LAST COMPLETED</small><strong>${timestampLabel(job.last_completed_at)}</strong></div><div><small>${nextLabel}</small><strong>${timestampLabel(job.next_expected_at)}</strong></div></div>${job.last_error?`<p class="health-error-text">${esc(job.last_error)}</p>`:""}</section>`;
  const dailyRows=(h.cluster_daily_status||[]).map(c=>{
    const r=c.latest_run;
    let details={};try{details=typeof r?.details_json==="string"?JSON.parse(r.details_json):(r?.details||{});}catch{}
    const errors=details.errors||[],topologyErrors=details.topology_errors||{};
    const errorSummary=[...errors,...Object.entries(topologyErrors).map(([k,v])=>k+": "+v)].join("; ");
    return `<tr><td><span class="cell-strong">${esc(c.cluster_name)}</span><br><span class="cell-muted">${esc(c.location_name)}</span></td><td>${r?pill(r.status):pill("Not run")}</td><td>${r?timestampLabel(r.started_at):"—"}</td><td>${r?timestampLabel(r.finished_at):"—"}</td><td>${r?fmt(r.attempt,0):"—"}</td><td>${r?fmt(r.metrics_collected,0):"—"}</td><td>${esc(errorSummary||r?.error_text||"—")}</td></tr>`;
  });
  const nodeRows=(h.node_health||[]).map(n=>{
    const c=n.counts||{},errors=n.family_errors||{};
    const down=(c.node_exporter_down||0)+(c.minio_scrape_down||0);
    const status=Object.keys(errors).length||down>0||!c.node_count||!c.drive_count?"partial":"success";
    const errorText=Object.entries(errors).map(([k,v])=>k+": "+v).join("; ");
    return `<tr><td><span class="cell-strong">${esc(n.cluster_name)}</span><br><span class="cell-muted">${esc(n.location_name)}</span></td><td>${timestampLabel(n.snapshot_ts)}</td><td>${pill(status)}</td><td>${fmt(c.node_exporter_up,0)} / ${fmt(c.node_count,0)}</td><td>${fmt(c.minio_scrape_up,0)} / ${fmt(c.node_count,0)}</td><td>${fmt(c.drive_count,0)}</td><td>${fmt(c.availability_error_drives,0)} / ${fmt(c.io_error_drives,0)} / ${fmt(c.timeout_error_drives,0)}</td><td>${esc(errorText||"—")}</td></tr>`;
  });
  const runRows=(h.recent_runs||[]).map(r=>{
    const detail=r.details||{},detailErrors=detail.errors||[],topologyErrors=detail.topology_errors||{};
    const hasIssue=r.status==="failed"||r.status==="partial";
    const issueParts=[r.error_text,...detailErrors,...Object.entries(topologyErrors).map(([k,v])=>k+": "+v)].filter(Boolean);
    const issueMarkup=hasIssue?(issueParts.length?`<details class="health-error-details"><summary>View details (${issueParts.length})</summary><ul>${issueParts.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></details>`:"<span class=\"cell-muted\">No error details recorded</span>"):"—";
    return `<tr><td>${timestampLabel(r.started_at)}</td><td>${esc(r.location_name||"—")}</td><td>${esc(r.cluster_name||"—")}</td><td>${dateLabel(r.snapshot_date)}</td><td>${pill(r.status)}</td><td>${r.attempt}</td><td>${r.metrics_collected}</td><td>${issueMarkup}</td></tr>`;
  });
  const filterMarkup=`<section class="table-panel health-history-panel"><div class="table-heading"><div><h3>Recent daily executions</h3><p>${fmt(pg.total_items||0,0)} matching cluster-level runs · Filter by snapshot date and status</p></div></div><div class="health-history-filters"><label>FROM DATE<input id="health-start-date" type="date" value="${esc(f.startDate)}"></label><label>TO DATE<input id="health-end-date" type="date" value="${esc(f.endDate)}"></label><label>STATUS<select id="health-status"><option value="">All statuses</option><option value="success" ${f.status==="success"?"selected":""}>Success</option><option value="partial" ${f.status==="partial"?"selected":""}>Partial</option><option value="failed" ${f.status==="failed"?"selected":""}>Failed</option></select></label><label>ROWS PER PAGE<select id="health-page-size"><option value="10" ${f.pageSize===10?"selected":""}>10</option><option value="20" ${f.pageSize===20?"selected":""}>20</option><option value="50" ${f.pageSize===50?"selected":""}>50</option><option value="100" ${f.pageSize===100?"selected":""}>100</option></select></label><div class="health-filter-actions"><button class="primary-small" data-action="apply-health-filters">Apply filters</button><button class="subtle-button" data-action="reset-health-filters">Reset</button></div></div><div class="table-scroll"><table><thead><tr>${["STARTED AT","LOCATION","CLUSTER","SNAPSHOT DATE","STATUS","ATTEMPT","METRICS","ERROR DETAILS"].map(x=>`<th>${x}</th>`).join("")}</tr></thead><tbody>${runRows.length?runRows.join(""):`<tr><td colspan="8" class="empty-state">No collection runs match these filters.</td></tr>`}</tbody></table></div><div class="health-pagination"><span>Page ${pg.page||1} of ${pg.total_pages||1} · Showing ${runRows.length} of ${fmt(pg.total_items||0,0)}</span><div><button class="subtle-button" data-health-page="${Math.max(1,(pg.page||1)-1)}" ${!pg.has_previous?"disabled":""}>← Previous</button><button class="subtle-button" data-health-page="${(pg.page||1)+1}" ${!pg.has_next?"disabled":""}>Next →</button></div></div></section>`;
  $("#content").innerHTML=pageHead("Collection health","Scheduler cadence, collection freshness and infrastructure telemetry status.",'<button class="subtle-button" data-action="refresh">↻ Refresh</button>')+
    `<div class="metric-grid">${metric("SUCCESSFUL DAILY RUNS",fmt(counts.success||0,0),"Persisted successful cluster runs","✓",true)}${metric("PARTIAL RUNS",fmt(counts.partial||0,0),"One or more metric families unavailable","◒")}${metric("FAILED RUNS",fmt(counts.failed||0,0),"Collector runs that failed","!")}${metric("RECENT EXECUTIONS",fmt(pg.total_items||0,0),"Matching runs in current filter","◷")}</div>`+
    '<div class="health-section-heading"><h2>Scheduler</h2><p>Settings are read from SQLite. The scheduler checks for due work every minute.</p></div>'+
    `<div class="panel-grid scheduler-grid">${jobCard("Node & drive health",node,"NEXT EXPECTED RUN","Every "+fmt(s.node_interval_minutes,0)+" minutes · node exporter, MinIO scrape and drive telemetry")}${jobCard("Daily capacity & bucket collection",daily,"NEXT EXPECTED RUN","Daily at "+esc(s.daily_collection_time||"—")+" "+esc(s.timezone||"IST")+" · cluster, bucket and pool snapshots")}</div>`+
    '<div class="health-section-heading"><h2>Daily collection by cluster</h2><p>Latest persisted daily collector result for each configured cluster.</p></div>'+
    table("Cluster collection status",(h.cluster_daily_status||[]).length+" cluster(s)",["CLUSTER / LOCATION","STATUS","STARTED","FINISHED","ATTEMPT","METRICS","ERRORS / DETAILS"],dailyRows,"No daily collection runs recorded.")+
    '<div class="health-section-heading"><h2>Node & drive telemetry</h2><p>Latest high-frequency sample per cluster. Drive error columns show affected drive counts: availability / I/O / timeout.</p></div>'+
    table("Infrastructure telemetry","Latest node-health snapshots",["CLUSTER / LOCATION","SNAPSHOT","STATUS","NODE EXPORTER UP","MINIO SCRAPE UP","DRIVES","AVAIL / I/O / TIMEOUT","FAMILY ERRORS"],nodeRows,"No node-health samples recorded.")+
    filterMarkup;

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

document.addEventListener("keydown",e=>{
  if(e.key!=="Escape")return;
  const openGroups=$$("[data-bucket-filter-group][open]",$("#content"));
  if(!openGroups.length)return;
  openGroups.forEach(closeBucketUsageFilterGroup);
  openGroups[0]?.querySelector("summary")?.focus();
  e.preventDefault();
});
document.addEventListener("click",e=>{
  if(!(e.target instanceof Element))return;
  const clickedColumnMenu=e.target.closest(".report-column-menu");
  const openColumnMenus=$$(".report-column-menu[open]",$("#content"));
  if(!clickedColumnMenu)openColumnMenus.forEach(menu=>menu.removeAttribute("open"));
  else if(e.target.closest(".report-column-menu summary"))openColumnMenus.filter(menu=>menu!==clickedColumnMenu).forEach(menu=>menu.removeAttribute("open"));
});

document.addEventListener("click",async e=>{
  const clickedFilterGroup=e.target.closest("[data-bucket-filter-group]");
  const openFilterGroups=$$("[data-bucket-filter-group][open]",$("#content"));
  if(clickedFilterGroup){
    openFilterGroups.filter(group=>group!==clickedFilterGroup).forEach(closeBucketUsageFilterGroup);
    if(clickedFilterGroup.open&&e.target.closest("summary")){
      closeBucketUsageFilterGroup(clickedFilterGroup);
      e.preventDefault();
    }
  }else if(!e.target.closest("[data-bucket-filter-action]")&&!e.target.closest("[data-action='reset-bucket-usage-filters']")){
    openFilterGroups.forEach(closeBucketUsageFilterGroup);
  }
  const exportButton=e.target.closest("[data-export-table]");if(exportButton){exportTableCsv(exportButton);return;}
  const bucketFilterAction=e.target.closest("[data-bucket-filter-action]");
  if(bucketFilterAction){
    const key=bucketFilterAction.dataset.filterKey,group=bucketFilterAction.closest("[data-bucket-filter-group]");
    if(!group)return;
    if(bucketFilterAction.dataset.bucketFilterAction==="select-all"){
      const selected=new Set(state.bucketUsageFilterDraft[key]||[]);
      group.querySelectorAll("[data-bucket-filter-option]:not(:disabled)").forEach(input=>{if(!input.closest(".bucket-usage-filter-option").classList.contains("hidden")){selected.add(input.value);input.checked=true;}});
      state.bucketUsageFilterDraft[key]=[...selected];updateBucketFilterGroup(group);
    }else if(bucketFilterAction.dataset.bucketFilterAction==="clear"){
      state.bucketUsageFilterDraft[key]=[];group.querySelectorAll("[data-bucket-filter-option]").forEach(input=>input.checked=false);updateBucketFilterGroup(group);
    }else if(bucketFilterAction.dataset.bucketFilterAction==="apply"){
      state.bucketUsageFilters={...state.bucketUsageFilters,[key]:[...(state.bucketUsageFilterDraft[key]||[])]};
      group.open=false;
      renderBucketUsageReport().catch(err=>toast(err.message,true));
    }
    return;
  }
  const expand=e.target.closest("[data-expand-chart]");if(expand){openExpandedChart(expand.dataset.expandChart,expand);return;}
  if(e.target.closest(".chart-expand-close")){closeExpandedChart();return;}
  const histogramMode=e.target.closest("[data-histogram-mode]");
  if(histogramMode){
    const panelEl=histogramMode.closest(".panel");
    if(!panelEl)return;
    const mode=histogramMode.dataset.histogramMode;
    panelEl.querySelectorAll("[data-histogram-mode]").forEach(button=>{const active=button.dataset.histogramMode===mode;button.classList.toggle("active",active);button.setAttribute("aria-pressed",String(active));});
    panelEl.querySelectorAll("[data-histogram-view]").forEach(view=>view.classList.toggle("hidden",view.dataset.histogramView!==mode));
    if(mode==="graph"){const instance=state.charts.find(item=>item.canvas?.id==="object-size-histogram");if(instance)instance.resize();}
    return;
  }
  const reportView=e.target.closest("[data-report-view]");if(reportView){setView(reportView.dataset.reportView);return;}
  const view=e.target.closest("[data-view]");if(view){e.preventDefault();setView(view.dataset.view);return;}
  const cluster=e.target.closest("[data-cluster]");if(cluster){try{await showCluster(cluster.dataset.cluster);}catch(err){toast(err.message,true);}return;}
  const tenant=e.target.closest("[data-tenant]");if(tenant){try{await showTenant(tenant.dataset.tenant);}catch(err){toast(err.message,true);}return;}
  const tenantMode=e.target.closest("[data-tenant-mode]");if(tenantMode){try{await showTenant(Number(tenantMode.dataset.tenantId),tenantMode.dataset.tenantMode);}catch(err){toast(err.message,true);}return;}
  const tenantScale=e.target.closest("[data-tenant-scale]");if(tenantScale){state.tenantCapacityScale=tenantScale.dataset.tenantScale;const c=state.snapshotContext;if(c?.type==="tenant")showTenant(c.id,c.attribution,c.days,c.startDate,c.endDate).catch(err=>toast(err.message,true));return;}
  const bucket=e.target.closest("[data-bucket]");if(bucket){try{await showBucket(bucket.dataset.bucket);}catch(err){toast(err.message,true);}return;}
  const assign=e.target.closest("[data-assign]");if(assign){assignBucketModal(Number(assign.dataset.assign));return;}
  const topologyTab=e.target.closest("[data-topology-tab]");if(topologyTab){showClusterTopology(state.topologyClusterId,topologyTab.dataset.topologyTab).catch(err=>toast(err.message,true));return;}
  const nodeSubTab=e.target.closest("[data-node-subtab]");if(nodeSubTab){state.nodeSubsection=nodeSubTab.dataset.nodeSubtab;showClusterTopology(state.topologyClusterId,"nodes").catch(err=>toast(err.message,true));return;}
  const nodeHours=e.target.closest("[data-node-hours]");if(nodeHours){state.nodePerformanceHours=Number(nodeHours.dataset.nodeHours);showClusterTopology(state.topologyClusterId,"nodes").catch(err=>toast(err.message,true));return;}
  const action=e.target.closest("[data-action]")?.dataset.action;
  if(action==="open-tenant-snapshots"){const c=state.snapshotContext;showTenantSnapshots(c.id,c.attribution,c.days,c.startDate,c.endDate).catch(err=>toast(err.message,true));return;}
  if(action==="open-bucket-snapshots"){const c=state.snapshotContext;showBucketSnapshots(c.id,c.days,c.startDate,c.endDate).catch(err=>toast(err.message,true));return;}
  if(action==="back-to-entity"){const c=state.snapshotContext;if(c.type==="tenant")showTenant(c.id,c.attribution,c.days,c.startDate,c.endDate).catch(err=>toast(err.message,true));else if(c.type==="bucket")showBucket(c.id,c.days,c.startDate,c.endDate).catch(err=>toast(err.message,true));return;}
  if(action==="open-node-infrastructure"){showClusterTopology(state.snapshotClusterId,"infra-overview").catch(err=>toast(err.message,true));return;}
  if(action==="open-storage-topology"){showClusterTopology(state.snapshotClusterId,"storage-overview").catch(err=>toast(err.message,true));return;}
  if(action==="back-to-cluster-overview"){showCluster(state.snapshotClusterId,state.snapshotRange.days,state.snapshotRange.startDate,state.snapshotRange.endDate).catch(err=>toast(err.message,true));return;}
  if(action==="open-cluster-snapshots"){showClusterSnapshots(state.snapshotClusterId,state.snapshotRange.days,state.snapshotRange.startDate,state.snapshotRange.endDate).catch(err=>toast(err.message,true));return;}
  if(action==="back-to-cluster"){showCluster(state.snapshotClusterId,state.snapshotRange.days,state.snapshotRange.startDate,state.snapshotRange.endDate).catch(err=>toast(err.message,true));return;}
  const healthPage=e.target.closest("[data-health-page]");
  if(healthPage){
    state.healthFilters.page=Number(healthPage.dataset.healthPage)||1;
    renderHealth().catch(err=>toast(err.message,true));
    return;
  }
  if(action==="apply-infra-trends"){
    const start=$("#infra-trend-start")?.value||"",end=$("#infra-trend-end")?.value||"";
    if(start&&end&&start>end){toast("Trend start date must be on or before end date.",true);return;}
    state.topologyTrendFilters=state.topologyTrendFilters||{};
    state.topologyTrendFilters[state.topologyClusterId]={startDate:start,endDate:end};
    showClusterTopology(state.topologyClusterId,state.topologySection).catch(err=>toast(err.message,true));
    return;
  }
  if(action==="reset-infra-trends"){
    state.topologyTrendFilters=state.topologyTrendFilters||{};
    state.topologyTrendFilters[state.topologyClusterId]={startDate:"",endDate:""};
    showClusterTopology(state.topologyClusterId,state.topologySection).catch(err=>toast(err.message,true));
    return;
  }
  if(action==="apply-health-filters"){
    const start=$("#health-start-date")?.value||"",end=$("#health-end-date")?.value||"";
    if(start&&end&&start>end){toast("From date must be on or before To date.",true);return;}
    state.healthFilters={...state.healthFilters,startDate:start,endDate:end,status:$("#health-status")?.value||"",pageSize:Number($("#health-page-size")?.value||20),page:1};
    renderHealth().catch(err=>toast(err.message,true));
    return;
  }
  if(action==="reset-health-filters"){
    state.healthFilters={startDate:"",endDate:"",status:"",page:1,pageSize:20};
    renderHealth().catch(err=>toast(err.message,true));
    return;
  }
  if(action==="reset-bucket-usage-filters"){state.bucketUsageFilters={cluster:[],location:[],tenant:[]};state.bucketUsageFilterDraft={cluster:[],location:[],tenant:[]};renderBucketUsageReport().catch(err=>toast(err.message,true));return;}
  if(action==="refresh"){render().catch(err=>toast(err.message,true));}
  if(action==="apply-trend-dates"){
    const el=e.target.closest("[data-action='apply-trend-dates']");
    const start=$("#trend-start")?.value,end=$("#trend-end")?.value;
    if(!start||!end){toast("Choose both a start date and an end date.",true);return;}
    if(start>end){toast("Start date must be on or before end date.",true);return;}
    const kind=el.dataset.trendKind,id=el.dataset.trendId,mode=el.dataset.trendAttribution||"current";
    const run=kind==="cluster"||kind==="cluster-snapshots"?(kind==="cluster-snapshots"?showClusterSnapshots(id,90,start,end):showCluster(id,90,start,end)):kind==="tenant"||kind==="tenant-snapshots"?(kind==="tenant-snapshots"?showTenantSnapshots(Number(id),mode,90,start,end):showTenant(Number(id),mode,90,start,end)):kind==="bucket-snapshots"?showBucketSnapshots(Number(id),90,start,end):showBucket(Number(id),90,start,end);
    run.catch(err=>toast(err.message,true));
  }
  if(action==="create-backup"){
    const button=e.target.closest("[data-action='create-backup']");
    if(button){button.disabled=true;button.textContent="Creating backup…";}
    try{
      const result=await api("/api/master-admin/backups",{method:"POST"});
      toast("Backup created and integrity verified: "+result.filename);
      await renderMasterAdmin();
    }catch(err){toast(err.message,true);if(button){button.disabled=false;button.textContent="Create backup now";}}
    return;
  }
  if(action==="new-tenant")createTenantModal();
  if(action==="new-user")createUserModal();
  if(action==="bulk-assign")bulkAssignBucketsModal();
  const reset=e.target.closest("[data-reset-user]");if(reset){resetUserPasswordModal(Number(reset.dataset.resetUser));return;}
  const toggle=e.target.closest("[data-toggle-user]");if(toggle){try{await api("/api/auth/users/"+toggle.dataset.toggleUser+"/active",{method:"POST",body:JSON.stringify({is_active:toggle.dataset.active==="1"})});toast("User status updated");await renderUsers();}catch(err){toast(err.message,true);}return;}
  if(action==="close-modal")$("#modal-root").innerHTML="";
});
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&state.expandedChart)closeExpandedChart();});
$("#login-form").addEventListener("submit",async e=>{e.preventDefault();$("#login-error").textContent="";const form=new FormData(e.currentTarget);try{const d=await api("/api/auth/login",{method:"POST",body:JSON.stringify({username:form.get("username"),password:form.get("password")})});showApp(d.user);setView("overview");}catch(err){$("#login-error").textContent=err.message;}});
$("#logout-button").addEventListener("click",async()=>{try{await api("/api/auth/logout",{method:"POST"});}catch{}showLogin();});
$("#refresh-button").addEventListener("click",()=>render().catch(e=>toast(e.message,true)));
$("#content").addEventListener("submit",async e=>{
  if(e.target.id!=="master-settings-form")return;
  e.preventDefault();const f=new FormData(e.target);
  try{
    await api("/api/master-admin/settings",{method:"PUT",body:JSON.stringify({node_interval_minutes:Number(f.get("node_interval_minutes")),telemetry_retention_days:Number(f.get("telemetry_retention_days")),daily_collection_time:f.get("daily_collection_time"),current_password:f.get("current_password")})});
    toast("Collector cadence and telemetry retention settings saved.");
    await renderMasterAdmin();
  }catch(err){toast(err.message,true);}
});
$("#content").addEventListener("submit",async e=>{
  if(e.target.id!=="capacity-factors-form")return;
  e.preventDefault();const form=new FormData(e.target),button=e.target.querySelector("button[type=submit]");
  if(button){button.disabled=true;button.textContent="Saving…";}
  try{
    await api("/api/analytics/capacity-factors",{method:"PUT",body:JSON.stringify({dp:Number(form.get("dp")),rf:Number(form.get("rf")),eff:Number(form.get("eff"))})});
    toast("Capacity factors saved; report recalculated.");await renderCapacityReport();
  }catch(err){toast(err.message,true);if(button){button.disabled=false;button.textContent="Save & recalculate";}}
});
$("#content").addEventListener("change",async e=>{
  if(e.target.matches("[data-bucket-filter-option]")){
    const key=e.target.dataset.bucketFilterOption,value=e.target.value,selected=new Set(state.bucketUsageFilterDraft[key]||[]);
    if(e.target.checked)selected.add(value);else selected.delete(value);
    state.bucketUsageFilterDraft[key]=[...selected];
    updateBucketFilterGroup(e.target.closest("[data-bucket-filter-group]"));
    return;
  }
  if(e.target.matches("[data-report-column-toggle]")){
    const checkbox=e.target,reportId=checkbox.dataset.reportId,key=checkbox.dataset.reportColumnKey,panel=checkbox.closest(".table-panel");
    const visibility={...(state.reportColumnVisibility[reportId]||{})};
    if(!checkbox.checked&&!Object.entries(visibility).some(([name,visible])=>name!==key&&visible!==false)){
      checkbox.checked=true;toast("At least one column must remain visible.",true);return;
    }
    const previous=visibility[key]!==false;visibility[key]=checkbox.checked;
    try{
      saveReportColumnVisibility(reportId,visibility);applyReportColumnVisibility(panel,visibility);
      if(reportId==="provisioned"&&(key==="used_usable"||key==="used_bkt")){
        state.reportColumns[key]=checkbox.checked;
        await api("/api/analytics/report-column-preferences",{method:"PUT",body:JSON.stringify({used_usable:state.reportColumns.used_usable,used_bkt:state.reportColumns.used_bkt})});
      }
      toast("Visible columns updated.");
    }catch(err){
      visibility[key]=previous;saveReportColumnVisibility(reportId,visibility);checkbox.checked=previous;applyReportColumnVisibility(panel,visibility);toast(err.message,true);
    }
    return;
  }
  if(e.target.id==="trend-range" && e.target.value!=="custom"){const el=e.target,days=Number(el.value),kind=el.dataset.trendKind,id=el.dataset.trendId,mode=el.dataset.trendAttribution||"current";const run=kind==="cluster"||kind==="cluster-snapshots"?(kind==="cluster-snapshots"?showClusterSnapshots(id,days):showCluster(id,days)):kind==="tenant"||kind==="tenant-snapshots"?(kind==="tenant-snapshots"?showTenantSnapshots(Number(id),mode,days):showTenant(Number(id),mode,days)):kind==="bucket-snapshots"?showBucketSnapshots(Number(id),days):showBucket(Number(id),days);run.catch(err=>toast(err.message,true));return;}
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
$("#content").addEventListener("input",e=>{
  if(e.target.id==="bucket-filter"){const q=e.target.value.toLowerCase();$("tbody tr",$("#content")).forEach(row=>row.classList.toggle("hidden",!row.textContent.toLowerCase().includes(q)));return;}
  if(e.target.matches("[data-bucket-filter-search]")){
    const q=e.target.value.trim().toLowerCase(),group=e.target.closest("[data-bucket-filter-group]");
    group?.querySelectorAll(".bucket-usage-filter-option").forEach(option=>option.classList.toggle("hidden",!option.textContent.toLowerCase().includes(q)));
  }
});
(async()=>{try{const d=await api("/api/auth/me");showApp(d.user);await setView("overview");}catch{showLogin();}})();
