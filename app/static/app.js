const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
if(window.Chart&&window.ChartZoom){Chart.register(ChartZoom);Chart.defaults.plugins.zoom={pan:{enabled:true,mode:"x",modifierKey:"shift"},zoom:{wheel:{enabled:true,speed:0.08},drag:{enabled:true,backgroundColor:"rgba(19,165,139,.12)",borderColor:"#13a58b",borderWidth:1},pinch:{enabled:true},mode:"x"}};}
const state = { user:null, view:"overview", masterConfigTab:"general", masterGeneralTab:"collection", backupPageSize:10, backupOffset:0, overview:null, clusters:[], tenants:[], buckets:[], selectedBuckets:[], reportColumns:{used_usable:true,used_bkt:true}, reportColumnVisibility:{}, bucketUsageFilters:{cluster:[],location:[],tenant:[]}, bucketUsageFilterDraft:{cluster:[],location:[],tenant:[]}, health:null, healthFilters:{startDate:"",endDate:"",status:"",page:1,pageSize:20}, charts:[], snapshotClusterId:null, snapshotRange:{days:90,startDate:null,endDate:null}, clusterDetailTab:"infra",clusterHistogramDate:null, snapshotContext:{type:null,id:null,attribution:"current",days:90,startDate:null,endDate:null},nodeSubsection:"health",nodePerformanceHours:6,performanceRangeHours:2,performanceStart:"",performanceEnd:"",performanceMetric:"cpu",performanceSelectedNodes:null,driveView:"graphs",driveNodeFilter:"all",driveFsFilter:"all",driveInventoryPage:1,driveSortKey:"node",driveSortDirection:1,networkHours:1,dashboardTimeRangePreset:"1h",historicalTimeRange:{mode:"relative",preset:"1h",startTs:null,endTs:null,timezone:"Asia/Kolkata"},historicalTimeRetentionDays:3,networkNodeFilter:"all",networkSelectedInterface:"all" };
const fmt = (n, digits=2) => n == null ? "—" : new Intl.NumberFormat("en-IN",{maximumFractionDigits:digits}).format(n);

const HISTORICAL_TIME_PRESETS = [
  ["5m",300000,"Last 5 minutes"],["15m",900000,"Last 15 minutes"],
  ["30m",1800000,"Last 30 minutes"],["1h",3600000,"Last 1 hour"],
  ["3h",10800000,"Last 3 hours"],["6h",21600000,"Last 6 hours"],
  ["12h",43200000,"Last 12 hours"],["24h",86400000,"Last 24 hours"],
  ["2d",172800000,"Last 2 days"],["7d",604800000,"Last 7 days"],
  ["30d",2592000000,"Last 30 days"]
];
const historicalIstToIso=value=>new Date(value+":00+05:30").toISOString();
const historicalIsoToIstInput=value=>new Date(value).toLocaleString("sv-SE",{timeZone:"Asia/Kolkata"}).replace(" ","T").slice(0,16);
function getHistoricalTimeBounds(now=Date.now()){
  const range=state.historicalTimeRange||{mode:"relative",preset:"1h"};
  if(range.mode==="absolute"&&range.startTs&&range.endTs)return {startTs:range.startTs,endTs:range.endTs};
  const preset=HISTORICAL_TIME_PRESETS.find(x=>x[0]===range.preset)||HISTORICAL_TIME_PRESETS[3];
  return {startTs:new Date(now-preset[1]).toISOString(),endTs:new Date(now).toISOString()};
}
function setHistoricalPreset(preset){
  if(!HISTORICAL_TIME_PRESETS.some(x=>x[0]===preset))return;
  state.historicalTimeRange={mode:"relative",preset,startTs:null,endTs:null,timezone:"Asia/Kolkata"};
  state.dashboardTimeRangePreset=preset;
}
function validateHistoricalTimeRange(start,end,retentionDays,now=Date.now()){
  if(!start||!end)return {valid:false,message:"Choose both a start and end time."};
  const a=Date.parse(historicalIstToIso(start)),b=Date.parse(historicalIstToIso(end));
  if(!Number.isFinite(a)||!Number.isFinite(b)||b<=a)return {valid:false,message:"The end time must be later than the start time."};
  if(b>now+60000)return {valid:false,message:"The end time cannot be in the future."};
  if(a<now-Math.max(1,Number(retentionDays)||3)*86400000)return {valid:false,message:"The selected range exceeds configured telemetry retention."};
  return {valid:true,startTs:new Date(a).toISOString(),endTs:new Date(b).toISOString()};
}
function historicalRangePicker(retentionDays,intervalMinutes,context){
  const selected=state.historicalTimeRange||{mode:"relative",preset:"1h"};
  const retentionMs=Math.max(1,Number(retentionDays)||3)*86400000;
  const bounds=getHistoricalTimeBounds();
  const presetMs=HISTORICAL_TIME_PRESETS.find(x=>x[0]===selected.preset)?.[1]||3600000;
  const from=selected.mode==="absolute"?historicalIsoToIstInput(bounds.startTs):historicalIsoToIstInput(new Date(Date.parse(bounds.endTs)-presetMs).toISOString());
  const to=historicalIsoToIstInput(bounds.endTs);
  const activePreset=HISTORICAL_TIME_PRESETS.find(x=>x[0]===selected.preset);
  const rangeLabel=selected.mode==="absolute"
    ? timestampLabel(selected.startTs).replace(" IST","")+" – "+timestampLabel(selected.endTs).replace(" IST","")
    : (activePreset?.[2]||"Last 1 hour");
  const buttons=HISTORICAL_TIME_PRESETS.filter(([,ms])=>ms<=retentionMs).map(([key,,label])=>'<button type="button" class="time-range-option '+(selected.mode==="relative"&&selected.preset===key?"active":"")+'" data-historical-range="'+key+'">'+label+'</button>').join("");
  return '<div class="historical-time-toolbar" data-historical-picker="'+esc(context)+'"><details class="time-range-dropdown"><summary><span class="time-range-icon">◷</span><span class="time-range-label">'+esc(rangeLabel)+'</span><span class="time-range-chevron">▾</span></summary><div class="time-range-popover"><div class="time-range-popover-heading"><strong>Time range</strong><span>IST · '+fmt(intervalMinutes||5,0)+' min cadence · '+fmt(retentionDays||3,0)+' day retention</span></div><div class="time-range-options">'+buttons+'</div><div class="time-range-custom"><div class="time-range-custom-heading">Custom range</div><label>From<input type="datetime-local" data-historical-start value="'+esc(from)+'"></label><label>To<input type="datetime-local" data-historical-end value="'+esc(to)+'"></label><div class="time-range-actions"><button type="button" class="primary-small" data-action="apply-historical-range">Apply</button><button type="button" class="subtle-button" data-action="reset-historical-range">Reset</button></div></div></div></details></div>';
}

const bytes = n => { if(n==null)return "—"; const value=Number(n); if(!Number.isFinite(value))return "—"; if(value>=1024**4)return (value/1024**4).toFixed(2)+" TiB"; if(value>=1024**3)return (value/1024**3).toFixed(1)+" GiB"; if(value>=1024**2)return (value/1024**2).toFixed(1)+" MiB"; if(value>=1024)return (value/1024).toFixed(1)+" KiB"; return value.toFixed(0)+" B"; };
const tibValue = n => n == null ? "—" : (n/1024**4).toFixed(2);
const pct = (used,total) => used == null || !total ? null : Math.max(0,Math.min(100,used/total*100));
const esc = s => String(s ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const dateLabel = s => s ? new Date(s+"T00:00:00").toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"}) : "—";
const timestampLabel = s => s ? new Intl.DateTimeFormat("en-IN",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",hour12:true,timeZone:"Asia/Kolkata"}).format(new Date(s))+" IST" : "Not collected";
const snapshotTimestampLabel = s => s ? new Intl.DateTimeFormat("en-IN",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:true,timeZone:"Asia/Kolkata"}).format(new Date(s))+" IST" : "Not collected";
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
function panel(title,subtitle,body,tag="",headerExtra=""){const chartId=body.match(/<canvas id="([^"]+)"/)?.[1];return `<section class="panel ${chartId?"chart-panel":""}"><div class="panel-header"><div><h3>${title}</h3><p>${subtitle||""}</p></div><div class="panel-header-actions">${tag?`<span class="panel-tag">${tag}</span>`:""}${headerExtra}${chartId?`${chartId==="object-size-histogram"?"":`<div class="chart-zoom-controls" role="group" aria-label="Chart zoom controls"><button type="button" data-chart-zoom="in" data-chart-id="${chartId}" title="Zoom in" aria-label="Zoom in">+</button><button type="button" data-chart-zoom="out" data-chart-id="${chartId}" title="Zoom out" aria-label="Zoom out">−</button><button type="button" data-chart-zoom="reset" data-chart-id="${chartId}" title="Reset zoom" aria-label="Reset zoom">Reset</button></div>`}<button type="button" class="chart-expand-button" data-expand-chart="${chartId}" aria-label="Expand ${esc(title)} chart" title="Expand chart">⛶</button>`:""}</div></div>${body}</section>`;}

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
      return cell&&!cell.hidden&&getComputedStyle(cell).display!=="none"?cell.textContent.replace(/\s+/g," ").trim():"";
    });
  });
  if(!visibleKeys.length||!rows.length){toast("There is no visible table data to export.",true);return;}
  const csv="\uFEFF"+[headers.filter(cell=>visibleKeys.includes(cell.dataset.reportColumnKey)).map(cell=>cell.innerText.replace(/\s+/g," ").trim()),...rows].map(row=>row.map(csvCell).join(",")).join("\r\n");
  const blob=new Blob([csv],{type:"text/csv;charset=utf-8;"}),url=URL.createObjectURL(blob),link=document.createElement("a");
  const title=panel.querySelector(".table-heading h3")?.textContent||"minio-report";
  const filename=title.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")||"minio-report";
  link.href=url;link.download=filename+"-"+new Date().toISOString().slice(0,10)+".csv";document.body.append(link);link.click();link.remove();URL.revokeObjectURL(url);
}
function ensureChartControls(instance){
  const canvas=instance?.canvas;
  const panelEl=canvas?.closest(".panel");
  const header=panelEl?.querySelector(".panel-header");
  if(!canvas||!panelEl||!header)return;
  let actions=header.querySelector(".panel-header-actions");
  if(!actions){
    actions=document.createElement("div");
    actions.className="panel-header-actions";
    header.append(actions);
  }
  // Object-size distribution is a categorical histogram: keep fullscreen, omit zoom controls.
  if(canvas.id!=="object-size-histogram"&&!actions.querySelector('[data-chart-id="'+CSS.escape(canvas.id)+'"][data-chart-zoom]')){
    const controls=document.createElement("div");
    controls.className="chart-zoom-controls";
    controls.setAttribute("role","group");
    controls.setAttribute("aria-label","Chart zoom controls");
    [["in","+","Zoom in"],["out","−","Zoom out"],["reset","Reset","Reset zoom"]].forEach(([action,label,title])=>{
      const button=document.createElement("button");
      button.type="button";
      button.dataset.chartZoom=action;
      button.dataset.chartId=canvas.id;
      button.title=title;
      button.setAttribute("aria-label",title);
      button.textContent=label;
      controls.append(button);
    });
    actions.prepend(controls);
  }
  if(!actions.querySelector('[data-expand-chart="'+CSS.escape(canvas.id)+'"]')){
    const expand=document.createElement("button");
    expand.type="button";
    expand.className="chart-expand-button";
    expand.dataset.expandChart=canvas.id;
    expand.title="Expand chart";
    expand.setAttribute("aria-label","Expand chart");
    expand.textContent="⛶";
    actions.append(expand);
  }
  panelEl.classList.add("chart-panel");
}
function chart(id,labels,sets,type="line",yMin=null,ySuffix=""){if(!window.Chart)return;const canvas=$("#"+id);if(!canvas)return;const instance=new Chart(canvas,{type,data:{labels,datasets:sets.map(s=>({label:s.label,data:s.data,borderColor:s.color,backgroundColor:s.color+"18",borderWidth:2,borderDash:s.dash?[7,5]:[],pointRadius:labels.length>45?1.5:3,pointHoverRadius:5,tension:s.raw?0:.25,fill:false}))},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},plugins:{legend:{position:"bottom",labels:{usePointStyle:true,boxWidth:7,font:{size:10}}},tooltip:{callbacks:{label:ctx=>ctx.dataset.label+": "+(ctx.parsed.y==null?"—":new Intl.NumberFormat("en-IN",{maximumFractionDigits:3}).format(ctx.parsed.y)+ySuffix)}}},scales:{x:{grid:{display:false},ticks:{autoSkip:true,maxTicksLimit:11,maxRotation:45,minRotation:0,font:{size:9},color:"#94a0af"}},y:{...(yMin===null?{}:{min:yMin}),grid:{color:"#edf1f5"},ticks:{font:{size:9},color:"#94a0af",callback:value=>new Intl.NumberFormat("en-IN",{maximumFractionDigits:3}).format(value)+ySuffix}}}}});state.charts.push(instance);ensureChartControls(instance);}
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
  const selectedDate=data?.snapshot_date||"";
  const availableDates=data?.available_dates||[];
  const minDate=availableDates.length?availableDates[availableDates.length-1]:"";
  const maxDate=availableDates.length?availableDates[0]:"";
  const dateControl='<label class="histogram-date-control">Snapshot date<input type="date" class="form-control" data-cluster-hist-date value="'+esc(selectedDate)+'" min="'+esc(minDate)+'" max="'+esc(maxDate)+'"></label>';
  const controls='<div class="histogram-toolbar">'+dateControl+'<span>Display</span><div class="tenant-chart-controls"><button type="button" class="active" data-histogram-mode="graph" aria-pressed="true">Graph</button><button type="button" data-histogram-mode="table" aria-pressed="false">Table</button></div></div>';
  if(!data||data.status==="unavailable"||!data.distribution?.length)
    return panel(title,"Historical snapshot · "+(selectedDate?dateLabel(selectedDate):"No snapshot selected"),controls+'<div class="empty-state"><strong>Object-size distribution unavailable</strong><p>No complete distribution is available for the selected snapshot date.</p></div>');
  const partial=data.status==="partial";
  const note=partial?'<div class="chart-note"><strong>Partial histogram:</strong> '+data.buckets_available+' of '+data.buckets_expected+' buckets reported a distribution. Totals and percentages are withheld to avoid under-reporting.</div>':"";
  const rows=data.distribution;
  const tableRows=rows.map(x=>'<tr><td>'+esc(histogramRangeLabel(x.range))+'</td><td class="histogram-number">'+fmt(x.object_count,0)+'</td><td class="histogram-number">'+(x.percentage==null?'—':fmt(x.percentage,2)+'%')+'</td></tr>').join("");
  const graph='<div class="histogram-view" data-histogram-view="graph"><div class="chart-wrap histogram-chart-wrap"><canvas id="object-size-histogram"></canvas></div></div>';
  const tabular='<div class="histogram-view hidden" data-histogram-view="table"><div class="table-scroll"><table class="histogram-table"><thead><tr><th>OBJECT SIZE RANGE</th><th class="histogram-number">OBJECT COUNT</th><th class="histogram-number">PERCENTAGE</th></tr></thead><tbody>'+tableRows+'</tbody></table></div></div>';
  return panel(title,"Snapshot "+dateLabel(data.snapshot_date)+" · Object count by object-size range",controls+graph+tabular+'<div class="histogram-summary"><strong>'+(data.total_objects==null?"—":fmt(data.total_objects,0))+'</strong><span>objects represented in histogram</span><span>'+data.buckets_available+'/'+data.buckets_expected+' buckets with distribution data</span></div>'+note);
}
function drawObjectSizeHistogram(data){
  if(!data||!["available","partial"].includes(data.status)||!data.distribution?.length)return;
  const canvas=$("#object-size-histogram");if(!canvas||!window.Chart)return;
  const rows=[...data.distribution].sort((a,b)=>a.object_count-b.object_count);
  const instance=new Chart(canvas,{type:"bar",data:{labels:rows.map(x=>histogramRangeLabel(x.range)),datasets:[{label:"Objects",data:rows.map(x=>x.object_count),backgroundColor:"#13a58b",borderRadius:4,barThickness:"flex",maxBarThickness:24}]},options:{indexAxis:"y",responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},plugins:{legend:{display:false},tooltip:{callbacks:{afterLabel:ctx=>{const x=rows[ctx.dataIndex];return x.percentage==null?"":x.percentage.toFixed(2)+"% of objects";}}}},scales:{x:{beginAtZero:true,grid:{color:"#edf1f5"},ticks:{font:{size:10},callback:v=>new Intl.NumberFormat("en-IN",{notation:"compact"}).format(v)}},y:{grid:{display:false},ticks:{font:{size:10},color:"#64748b"}}}}});
  state.charts.push(instance);
  ensureChartControls(instance);
}
function setView(view){
  if(view==="master-admin"){view="master-config";state.masterConfigTab="general";}
  else if(view==="prometheus-connections"){view="master-config";state.masterConfigTab="prometheus";}
  else if(view==="backfill-jobs"){view="master-config";state.masterConfigTab="backfill";}
  state.view=view;
  $$(".nav-link").forEach(b=>b.classList.toggle("active",b.dataset.view===(["bucket-usage-report","raw-capacity-report"].includes(view)?"capacity-report":view)));
  $("#page-breadcrumb").textContent=(["capacity-report","bucket-usage-report","raw-capacity-report"].includes(view)?"REPORTS":view==="master-config"?"MASTER CONFIGURATION":view.replaceAll("-"," ")).toUpperCase();
  render().catch(e=>toast(e.message,true));
}
async function renderMasterConfiguration(){
  const tabs=[["general","General Configuration"],["prometheus","Prometheus Configuration"],["backfill","Historical Backfill"]];
  const active=state.masterConfigTab;
  $("#content").innerHTML=pageHead("Master Configuration","Manage application settings, Prometheus connections and historical collection.")+
    '<div class="master-config-tabs" role="tablist" aria-label="Master Configuration">'+
    tabs.map(([key,label])=>'<button type="button" role="tab" class="master-config-tab'+(active===key?' active':'')+'" data-master-config-tab="'+key+'" aria-selected="'+(active===key)+'">'+label+'</button>').join("")+
    '</div><section id="master-config-panel" class="master-config-panel" role="tabpanel" aria-label="'+tabs.find(([key])=>key===active)[1]+'"><div class="loading-state">Loading configuration…</div></section>';
  if(active==="general") await renderMasterAdmin();
  else if(active==="prometheus") await window.renderPrometheusConnections();
  else if(active==="backfill") await window.renderBackfillJobs();
}
function setMasterConfigTab(tab){
  if(!["general","prometheus","backfill"].includes(tab))return;
  state.masterConfigTab=tab;
  renderMasterConfiguration().catch(e=>toast(e.message,true));
}
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
  else if(state.view==="master-config" && state.user.is_master_admin) await renderMasterConfiguration();
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
  const asOf=dataAsOf?snapshotTimestampLabel(dataAsOf):"Unavailable — one or more filtered clusters have no bucket snapshot",summary=filters.cluster.length||filters.location.length||filters.tenant.length?"Filtered view · ":"";
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
  const [d,backups]=await Promise.all([
    api("/api/master-admin/settings"),
    api("/api/master-admin/backups?limit="+state.backupPageSize+"&offset="+state.backupOffset)
  ]);
  const s=d.settings,u=d.telemetry_usage||{},host=$("#master-config-panel")||$("#content");
  const rows=backups.items.map(b=>'<tr><td><span class="cell-strong">'+esc(b.filename)+'</span></td><td>'+timestampLabel(b.created_at)+'</td><td>'+fmt(b.size_bytes/1024/1024,2)+' MiB</td><td>'+(b.integrity==="verified"?pill("success")+' Verified':pill("failed")+' Check failed')+'</td><td><a class="table-link" href="'+esc(b.download_url)+'">Download ↓</a></td></tr>').join("");
  const cleanup=u.last_cleanup_status||"Pending";
  const generalTabs='<div class="general-config-tabs" role="tablist" aria-label="General configuration sections">'+
    '<button type="button" role="tab" aria-selected="'+(state.masterGeneralTab==="collection")+'" class="general-config-tab '+(state.masterGeneralTab==="collection"?"active":"")+'" data-general-config-tab="collection">Collection Settings</button>'+
    '<button type="button" role="tab" aria-selected="'+(state.masterGeneralTab==="backups")+'" class="general-config-tab '+(state.masterGeneralTab==="backups"?"active":"")+'" data-general-config-tab="backups">Database Backups</button></div>';
  const collectionPanel='<section class="config-section"><div class="config-section-heading"><div><span class="config-kicker">01 / COLLECTION POLICY</span><h2>Collection settings</h2><p>Control high-frequency infrastructure collection and daily snapshot timing.</p></div><span class="panel-tag">LIVE SETTINGS</span></div>'+
    '<div class="config-settings-grid"><form id="master-settings-form" class="panel config-settings-form"><div class="config-field-grid">'+
    '<label class="config-field"><span>Node, drive and filesystem interval</span><span class="config-input-wrap"><input class="form-control" type="number" name="node_interval_minutes" min="1" max="60" step="1" value="'+s.node_interval_minutes+'" required><small>minutes</small></span><small class="config-help">Default 5 minutes · Valid range 1–60</small></label>'+
    '<label class="config-field"><span>Detailed telemetry retention</span><span class="config-input-wrap"><input class="form-control" type="number" name="telemetry_retention_days" min="1" max="90" step="1" value="'+s.telemetry_retention_days+'" required><small>days</small></span><small class="config-help">Default 3 days · Valid range 1–90</small></label>'+
    '<label class="config-field config-field-wide"><span>Daily capacity, bucket and pool collection time</span><span class="config-input-wrap"><input class="form-control" type="time" name="daily_collection_time" value="'+esc(s.daily_collection_time)+'" required><small>IST</small></span><small class="config-help">Daily historical snapshots use Asia/Kolkata time. This is separate from high-frequency node and drive collection.</small></label>'+
    '</div><div class="config-form-footer"><div><strong>Changes take effect automatically</strong><p>The scheduler checks settings every 60 seconds. Retention cleanup runs daily. Reducing retention removes expired samples at the next cleanup; deleted samples cannot be restored by increasing retention.</p></div><button class="primary-button" type="submit">Review &amp; save settings</button></div></form>'+
    '<aside class="panel config-footprint"><div class="panel-header"><div><h3>Infrastructure telemetry</h3><p>Current high-frequency data footprint</p></div><span class="panel-tag">RETENTION</span></div><div class="config-stat-list">'+
    '<div><span>Collection runs</span><strong>'+fmt(u.collection_runs,0)+'</strong></div><div><span>Node samples</span><strong>'+fmt(u.node_samples,0)+'</strong></div><div><span>Drive samples</span><strong>'+fmt(u.drive_samples,0)+'</strong></div><div><span>Database size</span><strong>'+fmt((u.database_size_bytes||0)/1024/1024,2)+' MiB</strong></div></div>'+
    '<div class="config-cleanup-note"><span class="config-status-dot '+(cleanup==="success"?"is-good":cleanup==="failed"?"is-bad":"")+'"></span><div><strong>Last retention cleanup · '+esc(cleanup)+'</strong><p>'+(u.last_cleanup_at?timestampLabel(u.last_cleanup_at):"Not yet run")+(u.last_cleanup_error?" · "+esc(u.last_cleanup_error):"")+'</p></div></div>'+
    '<p class="config-footnote">Database size includes configuration and report data. SQLite may reuse freed pages without shrinking the database file. WAL size: '+fmt((u.wal_size_bytes||0)/1024/1024,2)+' MiB.</p></aside></div></section>';
  const total=Number(backups.total_count??backups.count??0),from=total?state.backupOffset+1:0,to=Math.min(state.backupOffset+state.backupPageSize,total),pages=Math.max(1,Math.ceil(total/state.backupPageSize));
  const backupPanel='<section class="config-section"><div class="config-section-heading"><div><span class="config-kicker">02 / DATA PROTECTION</span><h2>Database backups</h2><p>Create, verify, download and safely clean up application database backups.</p></div><button class="primary-small" data-action="create-backup">Create backup now</button></div>'+
    '<div class="panel config-backup-panel"><div class="config-backup-summary"><div class="config-backup-icon">▣</div><div><strong>'+total+' backup file(s)</strong><p>Automatic retention: 14 days · Keep at least 5 latest verified backups.</p></div><span class="config-verified-tag">Integrity checks enabled</span></div>'+
    '<div class="backup-table-toolbar"><label>Rows per page <select id="backup-page-size" class="form-control"><option value="10" '+(state.backupPageSize===10?"selected":"")+'>10</option><option value="25" '+(state.backupPageSize===25?"selected":"")+'>25</option><option value="50" '+(state.backupPageSize===50?"selected":"")+'>50</option><option value="100" '+(state.backupPageSize===100?"selected":"")+'>100</option></select></label><span>Showing '+from+'–'+to+' of '+total+'</span></div>'+
    '<div class="table-scroll"><table class="config-backup-table"><thead><tr><th>BACKUP FILE</th><th>CREATED</th><th>SIZE</th><th>INTEGRITY</th><th></th></tr></thead><tbody>'+(rows||'<tr><td colspan="5" class="empty-state">No database backups found.</td></tr>')+'</tbody></table></div>'+
    '<div class="backup-pagination"><span>Page '+Math.min(Math.floor(state.backupOffset/state.backupPageSize)+1,pages)+' of '+pages+'</span><div><button type="button" class="secondary-button" data-action="backup-page-prev" '+(state.backupOffset===0?"disabled":"")+'>Previous</button><button type="button" class="secondary-button" data-action="backup-page-next" '+(to>=total?"disabled":"")+'>Next</button></div></div>'+
    '<p class="config-footnote">Backups use SQLite online backup and are verified with PRAGMA integrity_check. Cleanup only considers application-managed backups, never follows symbolic links, and preserves unverified files for investigation.</p></div></section>'+
    '<section class="config-section backup-cleanup-section"><div class="config-section-heading"><div><span class="config-kicker">03 / BACKUP HOUSEKEEPING</span><h2>Cleanup old backups</h2><p>Preview eligible backups before deleting anything. Unverified files are never automatically removed.</p></div></div>'+
    '<div class="panel backup-cleanup-panel"><div class="backup-cleanup-fields"><label class="config-field"><span>Delete backups older than</span><span class="config-input-wrap"><input id="backup-retention-days" class="form-control" type="number" min="1" max="365" value="14" required><small>days</small></span></label>'+
    '<label class="config-field"><span>Preserve at least</span><span class="config-input-wrap"><input id="backup-minimum-keep" class="form-control" type="number" min="1" max="100" value="5" required><small>verified backups</small></span></label></div>'+
    '<div class="backup-cleanup-footer"><p>Cleanup requires Master Admin password confirmation. The latest verified backups are protected even when older than the selected retention period.</p><button type="button" class="secondary-button" data-action="review-backup-cleanup">Review eligible backups</button></div></div></section>';
  host.innerHTML=pageHead("General Configuration","Manage collection schedules, telemetry retention and database protection.")+generalTabs+(state.masterGeneralTab==="collection"?collectionPanel:backupPanel);
}

async function reviewBackupCleanup(){
  const retentionDays=Number($("#backup-retention-days")?.value||14),minimumKeep=Number($("#backup-minimum-keep")?.value||5);
  if(!Number.isInteger(retentionDays)||retentionDays<1||retentionDays>365||!Number.isInteger(minimumKeep)||minimumKeep<1||minimumKeep>100){toast("Enter valid retention and minimum backup values.",true);return;}
  try{
    const preview=await api("/api/master-admin/backups/cleanup/preview",{method:"POST",body:JSON.stringify({retention_days:retentionDays,minimum_keep:minimumKeep})});
    const candidates=preview.candidates||[],preserved=preview.preserved||[],unverified=preview.unverified||[];
    const names=candidates.map(item=>'<li><strong>'+esc(item.filename)+'</strong><span>'+fmt(item.size_bytes/1024/1024,2)+' MiB</span></li>').join("");
    $("#modal-root").innerHTML='<div class="modal-backdrop config-confirm-backdrop"><section class="modal config-confirm-dialog backup-cleanup-dialog" role="dialog" aria-modal="true" aria-labelledby="backup-cleanup-title"><div class="modal-header"><div><h2 id="backup-cleanup-title">Review backup cleanup</h2><p>Only the verified, expired application backups listed below will be deleted.</p></div><button type="button" class="modal-close" data-action="close-modal" aria-label="Close">×</button></div>'+
      '<div class="backup-cleanup-preview-stats"><div><strong>'+candidates.length+'</strong><span>Eligible files</span></div><div><strong>'+fmt((preview.eligible_size_bytes||0)/1024/1024,2)+' MiB</strong><span>Potential space reclaimed</span></div><div><strong>'+preserved.length+'</strong><span>Verified backups preserved</span></div></div>'+
      (candidates.length?'<ul class="backup-cleanup-candidate-list">'+names+'</ul>':'<div class="backup-cleanup-empty">No backups meet the selected cleanup criteria.</div>')+
      '<p class="backup-cleanup-safety">'+preserved.length+' verified backup(s) will be preserved, including the newest '+minimumKeep+'. '+unverified.length+' unverified backup(s) will not be deleted.</p>'+
      (candidates.length?'<form id="backup-cleanup-confirm-form"><label class="config-field"><span>Confirm with Master Admin password</span><input class="form-control" type="password" name="current_password" autocomplete="current-password" required></label><p class="form-error" id="backup-cleanup-error" role="alert"></p><div class="form-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="danger-button" type="submit">Confirm cleanup</button></div></form>':'<div class="form-actions"><button type="button" class="secondary-button" data-action="close-modal">Close</button></div>')+
      '</section></div>';
    const form=$("#backup-cleanup-confirm-form");
    if(form)form.addEventListener("submit",async event=>{
      event.preventDefault();const button=form.querySelector("button[type=submit]");button.disabled=true;button.textContent="Cleaning up…";
      try{
        const result=await api("/api/master-admin/backups/cleanup",{method:"POST",body:JSON.stringify({retention_days:retentionDays,minimum_keep:minimumKeep,preview_token:preview.preview_token,current_password:new FormData(form).get("current_password")})});
        $("#modal-root").innerHTML="";toast("Backup cleanup completed: "+result.deleted_count+" file(s), "+fmt(result.deleted_size_bytes/1024/1024,2)+" MiB reclaimed.");state.backupOffset=0;await renderMasterAdmin();
      }catch(err){$("#backup-cleanup-error").textContent=err.message;button.disabled=false;button.textContent="Confirm cleanup";}
    });
    form?.querySelector("input[name=current_password]")?.focus();
  }catch(err){toast(err.message,true);}
}
function rangeControl(days,kind,id,attribution="current") {
  const options=[[7,"Last 7 days"],[30,"Last 30 days"],[90,"Last 90 days"],[180,"Last 6 months"],[365,"Last 12 months"],[730,"Last 2 years"],[1825,"Last 5 years"],[3650,"Last 10 years"]];
  const context=kind==="cluster"||kind==="cluster-snapshots"?state.snapshotRange:state.snapshotContext;
  const custom=Boolean(context?.startDate&&context?.endDate);
  const selected=options.find(([value])=>Number(days)===value)||options[3];
  const rangeLabel=custom?dateLabel(context.startDate)+" – "+dateLabel(context.endDate):selected[1];
  const startValue=custom?context.startDate:"",endValue=custom?context.endDate:"";
  return '<div class="toolbar trend-controls"><details class="time-range-dropdown"><summary><span class="time-range-icon">◷</span><span class="time-range-label">'+esc(rangeLabel)+'</span><span class="time-range-chevron">▾</span></summary><div class="time-range-popover"><div class="time-range-popover-heading"><strong>Trend period</strong><span>Daily snapshots</span></div><select id="trend-range" class="form-control" data-trend-kind="'+kind+'" data-trend-id="'+esc(id)+'" data-trend-attribution="'+attribution+'">'+options.map(([value,label])=>'<option value="'+value+'" '+(!custom&&Number(days)===value?'selected':'')+'>'+label+'</option>').join("")+'<option value="custom" '+(custom?'selected':'')+'>Custom range</option></select><div class="time-range-custom"><div class="time-range-custom-heading">Custom dates</div><label>From<input type="date" id="trend-start" class="form-control" aria-label="Start date" value="'+esc(startValue)+'"></label><label>To<input type="date" id="trend-end" class="form-control" aria-label="End date" value="'+esc(endValue)+'"></label><div class="time-range-actions"><button class="primary-small" data-action="apply-trend-dates" data-trend-kind="'+kind+'" data-trend-id="'+esc(id)+'" data-trend-attribution="'+attribution+'">Apply</button></div></div></div></details></div>';
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
function clusterDetailTabs(active){
  const tabs=[["infra","Infrastructure Status"],["capacity","Capacity & Forecast"],["objects","Object & Bucket Analysis"],["snapshots","Daily Snapshots"]];
  return '<nav class="cluster-detail-tabs" role="tablist">'+tabs.map(([key,label])=>'<button type="button" role="tab" class="'+(key===active?'active':'')+'" data-cluster-detail-tab="'+key+'" aria-selected="'+(key===active?'true':'false')+'">'+label+'</button>').join("")+'</nav>';
}
function clusterKpiCard(label,value,hint,tone="neutral"){
  return '<article class="cluster-kpi-card '+tone+'"><small>'+esc(label)+'</small><strong>'+value+'</strong><span>'+esc(hint||"")+'</span></article>';
}
function clusterKpiGroup(title,cards){
  return '<section class="cluster-kpi-group"><h3>'+title+'</h3><div class="cluster-kpi-grid">'+cards.join("")+'</div></section>';
}
function clusterQuorumHint(topology){
  const sets=topology?.erasure_sets||[];
  if(!sets.length)return "Erasure-set quorum metrics unavailable";
  const read=sets.map(x=>x.read_quorum),write=sets.map(x=>x.write_quorum);
  if(read.every(x=>x!=null)&&write.every(x=>x!=null)&&new Set(read).size===1&&new Set(write).size===1)
    return "Read / write quorum "+read[0]+" / "+write[0]+" · data/parity layout not exposed";
  return "Read/write quorum varies by erasure set · data/parity layout not exposed";
}
async function showCluster(id,days=90,startDate=null,endDate=null,tab=state.clusterDetailTab||"infra"){
  if(state.snapshotClusterId&&state.snapshotClusterId!==id)state.clusterHistogramDate=null;
  state.snapshotClusterId=id;state.snapshotRange={days,startDate,endDate};state.clusterDetailTab=tab;
  const d=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"?"+trendQuery(days,startDate,endDate));
  const x=d.latest||{},series=d.series||[],bucket=d.latest_bucket_summary||{};
  let topology=null,hist=null;
  if(tab==="infra")topology=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"/topology").catch(()=>null);
  if(tab==="objects"){
    const chosen=state.clusterHistogramDate||null;
    const url="/api/analytics/object-size-distribution/cluster/"+encodeURIComponent(id)+(chosen?"?snapshot_date="+encodeURIComponent(chosen):"");
    hist=await api(url);
    state.clusterHistogramDate=hist.snapshot_date||null;
  }
  clearCharts();
  const section=(title,subtitle,content,toolbar="")=>'<section class="analytics-section"><div class="analytics-section-heading"><div><h2>'+title+'</h2><p>'+subtitle+'</p></div>'+toolbar+'</div>'+content+'</section>';
  const pageHeader=pageHead(esc(d.cluster.name),"Cluster · "+esc(d.cluster.location_name)+" · "+esc(id),'<button class="subtle-button" data-view="clusters">← All clusters</button>')+clusterDetailTabs(tab);
  const topologyBody='<div class="cluster-experience-links"><article class="cluster-experience-card"><div class="cluster-action-icon">⌁</div><div><strong>Node Infrastructure</strong><p>Monitor node availability, CPU, memory, drive health, filesystem utilisation and network performance over time.</p><button class="primary-small" data-action="open-node-infrastructure">Explore infrastructure →</button></div></article><article class="cluster-experience-card"><div class="cluster-action-icon">▦</div><div><strong>Storage Topology</strong><p>Inspect storage pools, erasure sets, drive distribution and read/write quorum.</p><button class="primary-small" data-action="open-storage-topology">Explore topology →</button></div></article></div>';
  if(tab==="infra"){
    const nodes=topology?.nodes||[];
    const driveCoverage=nodes.length>0&&nodes.every(n=>n.drives_online!=null&&n.drives_offline!=null);
    const drivesOnline=driveCoverage?nodes.reduce((sum,n)=>sum+Number(n.drives_online||0),0):null;
    const drivesOffline=driveCoverage?nodes.reduce((sum,n)=>sum+Number(n.drives_offline||0),0):null;
    const used=x.raw_total_bytes!=null&&x.raw_free_bytes!=null?Math.max(0,x.raw_total_bytes-x.raw_free_bytes):null;
    const usage=x.raw_total_bytes>0&&used!=null?used/x.raw_total_bytes*100:null;
    const status=x.metrics_available===true?(x.nodes_offline===0?"ONLINE":x.nodes_offline>0?"DEGRADED":"UNKNOWN"):"UNKNOWN";
    const statusTone=status==="ONLINE"?"good":status==="DEGRADED"?"warning":"neutral";
    const kpi1=[
      clusterKpiCard("STATUS",status,x.metrics_available?"Latest cluster snapshot":"Cluster metrics unavailable",statusTone),
      clusterKpiCard("BACKEND","MinIO / Erasure","MinIO object storage","neutral"),
      clusterKpiCard("BUCKETS",fmt(bucket.active_bucket_count,0),bucket.snapshot_date?"Bucket snapshot "+dateLabel(bucket.snapshot_date):"Inventory count","neutral"),
      clusterKpiCard("OBJECTS",bucket.objects==null?"—":fmt(bucket.objects,0),bucket.objects==null?"Incomplete bucket metric coverage":"Across cluster buckets","neutral"),
      clusterKpiCard("TOTAL USAGE",bytes(used),"Raw capacity consumed","neutral"),
      clusterKpiCard("EC DATA / PARITY","N/A",clusterQuorumHint(topology),"neutral")
    ];
    const kpi2=[
      clusterKpiCard("DISKS ONLINE",drivesOnline==null?"—":fmt(drivesOnline,0),driveCoverage?"Sum of node drive metrics":"Drive health coverage incomplete",drivesOnline!=null?"good":"neutral"),
      clusterKpiCard("DISKS OFFLINE",drivesOffline==null?"—":fmt(drivesOffline,0),driveCoverage?"Sum of node drive metrics":"Drive health coverage incomplete",drivesOffline===0?"good":drivesOffline>0?"warning":"neutral"),
      clusterKpiCard("TOTAL CAPACITY",bytes(x.raw_total_bytes),"Raw capacity","neutral"),
      clusterKpiCard("USED",bytes(used),"Raw used capacity","neutral"),
      clusterKpiCard("AVAILABLE",bytes(x.raw_free_bytes),"Raw free capacity","good"),
      clusterKpiCard("USAGE",usage==null?"—":fmt(usage,1)+"%",usage==null?"Utilization unavailable":usage>=80?"High capacity utilization":usage>=70?"Capacity utilization warning":"Raw capacity utilization",usage>=80?"warning":"good")
    ];
    const growth=x.growth_bytes_per_day==null?null:x.growth_bytes_per_day*30;
    const kpi3=[
      clusterKpiCard("VERSIONS",bucket.versions==null?"—":fmt(bucket.versions,0),"Includes delete markers",bucket.versions==null?"neutral":"neutral"),
      clusterKpiCard("DELETE MARKERS",bucket.delete_markers==null?"—":fmt(bucket.delete_markers,0),"Separate from version count","neutral"),
      clusterKpiCard("REPLICATION RULES", "N/A","Requires read-only bucket replication configuration access","neutral"),
      clusterKpiCard("NODES ONLINE",x.nodes_online==null?"—":fmt(x.nodes_online,0),"Latest cluster snapshot",x.nodes_online!=null?"good":"neutral"),
      clusterKpiCard("NODES OFFLINE",x.nodes_offline==null?"—":fmt(x.nodes_offline,0),"Latest cluster snapshot",x.nodes_offline===0?"good":x.nodes_offline>0?"warning":"neutral"),
      clusterKpiCard("30-DAY EST. GROWTH",growth==null?"—":bytes(growth),x.growth_bytes_per_day==null?"Growth estimate unavailable":fmt(x.growth_bytes_per_day/1024**3,2)+" GiB/day estimated rate","neutral")
    ];
    const groups=clusterKpiGroup("Cluster & object summary",kpi1)+clusterKpiGroup("Capacity & drive health",kpi2)+clusterKpiGroup("Storage metadata & availability",kpi3);
    $("#content").innerHTML=pageHeader+
      section("Infrastructure status","Current cluster state and key storage signals. Missing telemetry is shown as unavailable, not zero.",'<div class="cluster-infrastructure-kpis">'+groups+'</div>')+
      section("Infrastructure workspaces","Drill into detailed node telemetry and storage layout.",'<section class="panel cluster-action-panel">'+topologyBody+'</section>');
    return;
  }
  if(tab==="capacity"){
    const toolbar=rangeControl(days,"cluster",id);
    $("#content").innerHTML=pageHeader+
      section("Capacity & forecast","Analyze capacity consumption, quota, growth and projected exhaustion.",'<div class="detail-grid cluster-capacity-summary"><div class="detail-card"><small>RAW CAPACITY</small><strong>'+bytes(x.raw_total_bytes)+'</strong></div><div class="detail-card"><small>RAW FREE</small><strong>'+bytes(x.raw_free_bytes)+'</strong></div><div class="detail-card"><small>PROJECTED DAYS TO FULL</small><strong>'+((x.days_to_full==null||x.days_to_full<=0)?"N/A":fmt(x.days_to_full,0)+" days")+'</strong></div></div><div class="panel-grid cluster-chart-grid">'+
      panel("Capacity trend","Daily raw used, free and total capacity",'<div class="chart-wrap"><canvas id="cluster-chart"></canvas></div>',days+" DAYS")+
      panel("Bucket quota trend","Sum of bucket quotas across active buckets",quotaPanelBody(series))+
      panel("Growth trend","30-day estimated growth rate · GiB/day",'<div class="chart-wrap"><canvas id="cluster-growth-chart"></canvas></div>')+
      panel("Days to full trend","Only projections up to 1,825 days (5 years) are shown",series.some(r=>r.days_to_full!=null&&r.days_to_full>0)?'<div class="chart-wrap"><canvas id="cluster-days-full-chart"></canvas></div>':'<div class="chart-empty-state"><strong>No reliable planning forecast</strong><p>A forecast requires at least 14 daily observations, declining free capacity and an estimated time to full within 5 years.</p></div>')+'</div>',toolbar);
    const labels=series.map(r=>dateLabel(r.snapshot_date));
    chart("cluster-chart",labels,[{label:"Used TiB",data:series.map(r=>r.raw_total_bytes==null||r.raw_free_bytes==null?null:(r.raw_total_bytes-r.raw_free_bytes)/1024**4),color:"#13a58b"},{label:"Free TiB",data:series.map(r=>r.raw_free_bytes==null?null:r.raw_free_bytes/1024**4),color:"#4779d8"},{label:"Total TiB",data:series.map(r=>r.raw_total_bytes==null?null:r.raw_total_bytes/1024**4),color:"#d9922e",dash:true}],"line",null," TiB");
    chart("cluster-growth-chart",labels,[{label:"Estimated growth GiB/day",data:series.map(r=>r.growth_bytes_per_day==null?null:r.growth_bytes_per_day/1024**3),color:"#d9922e"}]);
    if(series.some(r=>r.days_to_full!=null&&r.days_to_full>0))chart("cluster-days-full-chart",labels,[{label:"Projected days to full",data:series.map(r=>r.days_to_full==null||r.days_to_full<=0?null:r.days_to_full),color:"#4779d8"}],"line",0," days");
    chart("cluster-quota-chart",labels,[{label:"Bucket quota TiB",data:series.map(r=>r.bucket_quota_bytes==null?null:r.bucket_quota_bytes/1024**4),color:"#d9922e"}]);
    return;
  }
  if(tab==="objects"){
    const toolbar=rangeControl(days,"cluster",id);
    const labels=series.map(r=>dateLabel(r.snapshot_date));
    const objectTrend=series.map(r=>r.bucket_object_count);
    const versionTrend=series.map(r=>r.bucket_version_count);
    const deleteTrend=series.map(r=>r.bucket_delete_marker_count);
    const note='<div class="chart-note">Daily trend values are withheld when bucket metric coverage is incomplete. Version totals include delete markers; delete markers are also shown separately.</div>';
    $("#content").innerHTML=pageHeader+
      section("Object & bucket analysis","Understand object growth, versioning, delete markers and object-size distribution.",note+'<div class="panel-grid cluster-chart-grid">'+
      panel("Object trend","Total objects across active buckets when metrics are complete",'<div class="chart-wrap"><canvas id="cluster-object-chart"></canvas></div>')+
      panel("Version count trend","Total object versions including delete markers",'<div class="chart-wrap"><canvas id="cluster-version-chart"></canvas></div>')+
      panel("Delete marker trend","Delete markers across all buckets",'<div class="chart-wrap"><canvas id="cluster-delete-marker-chart"></canvas></div>')+
      objectSizeHistogram(hist,"Object size distribution")+'</div>',toolbar);
    chart("cluster-object-chart",labels,[{label:"Objects",data:objectTrend,color:"#4779d8"}]);
    chart("cluster-version-chart",labels,[{label:"Versions",data:versionTrend,color:"#13a58b"}]);
    chart("cluster-delete-marker-chart",labels,[{label:"Delete markers",data:deleteTrend,color:"#d9922e"}]);
    drawObjectSizeHistogram(hist);
  }
}
function renderNetworkWorkspace(data){
  const available=data.available_interfaces||[];
  const nodes=[...new Set(available.map(x=>x.node_name))].sort((a,b)=>a.localeCompare(b));
  if(state.networkNodeFilter!=="all"&&!nodes.includes(state.networkNodeFilter))state.networkNodeFilter="all";
  const filtered=available.filter(x=>state.networkNodeFilter==="all"||x.node_name===state.networkNodeFilter);
  const selectedKey=state.networkSelectedInterface||"all";
  const selected=selectedKey==="all"?null:filtered.find(x=>x.node_name+"|"+x.interface_name+"|"+x.instance===selectedKey)||null;
  const selectOptions='<option value="all" '+(selectedKey==="all"?'selected':'')+'>All interfaces</option>'+filtered.map(x=>{const key=x.node_name+"|"+x.interface_name+"|"+x.instance;return '<option value="'+esc(key)+'" '+(key===selectedKey?'selected':'')+'>'+esc(x.interface_name+' · '+x.node_name+' · '+x.instance)+'</option>';}).join("");
  const nodeOptions='<option value="all">All nodes</option>'+nodes.map(n=>'<option value="'+esc(n)+'" '+(state.networkNodeFilter===n?'selected':'')+'>'+esc(n)+'</option>').join("");
  const stats=data.statistics||[];
  const filteredStats=stats.filter(x=>(state.networkNodeFilter==="all"||x.node_name===state.networkNodeFilter)&&(state.networkSelectedInterface==="all"||!state.networkSelectedInterface||(x.node_name+"|"+x.interface_name+"|"+x.instance)===state.networkSelectedInterface));
  const fmtRate=v=>v==null?'—':bytes(v)+'/s';
  const metricStat=(m,k)=>m&&m[k]!=null?fmtRate(m[k]):'—';
  const rows=filteredStats.map(s=>{
    const m=s.metrics||{};
    return '<tr><td><span class="cell-strong">'+esc(s.node_name)+'</span></td><td>'+esc(s.interface_name)+'</td>'+
      '<td>'+metricStat(m.rx_bytes_per_second,'average')+'</td><td>'+metricStat(m.tx_bytes_per_second,'average')+'</td>'+
      '<td>'+ (m.rx_packets_per_second?.average==null?'—':fmt(m.rx_packets_per_second.average,1)+' pkt/s')+'</td>'+
      '<td>'+ (m.tx_packets_per_second?.average==null?'—':fmt(m.tx_packets_per_second.average,1)+' pkt/s')+'</td>'+
      '<td>'+ (m.rx_errors_per_second?.average==null?'—':fmt(m.rx_errors_per_second.average,3))+' / '+(m.tx_errors_per_second?.average==null?'—':fmt(m.tx_errors_per_second.average,3))+'</td>'+
      '<td>'+ (m.rx_drops_per_second?.average==null?'—':fmt(m.rx_drops_per_second.average,3))+' / '+(m.tx_drops_per_second?.average==null?'—':fmt(m.tx_drops_per_second.average,3))+'</td>'+
      '<td>'+fmt(s.sample_count,0)+'</td></tr>';
  }).join("");
  const charts=filtered.length?'<div class="panel-grid network-chart-grid">'+
    panel("Throughput","Receive and transmit · bytes/sec",'<div class="chart-wrap"><canvas id="network-throughput-chart"></canvas></div>')+
    panel("Packets","Receive and transmit · packets/sec",'<div class="chart-wrap"><canvas id="network-packets-chart"></canvas></div>')+
    panel("Errors","Receive and transmit · errors/sec",'<div class="chart-wrap"><canvas id="network-errors-chart"></canvas></div>')+
    panel("Drops","Receive and transmit · drops/sec",'<div class="chart-wrap"><canvas id="network-drops-chart"></canvas></div>')+'</div>':
    '<div class="chart-empty-state"><strong>No network interfaces in this range</strong><p>Network telemetry has not been recorded for the selected range or node.</p></div>';
  return '<div class="network-filter-toolbar"><label>Node<select data-network-node-filter>'+nodeOptions+'</select></label><label>Interface<select data-network-interface-filter>'+selectOptions+'</select></label><span class="network-filter-meta">Samples '+fmt(data.sample_count,0)+' · '+fmt(data.interval_minutes,0)+' min cadence · '+esc(timestampLabel(data.start_ts))+' – '+esc(timestampLabel(data.end_ts))+'</span></div>'+
    (data.truncated?'<div class="detail-card"><strong>Data limited to 20,000 samples</strong><p class="muted">Statistics are based on the returned subset. Select a node/interface to narrow the query.</p></div>':'')+
    (filtered.length?charts:'')+
    '<section class="panel table-panel"><div class="panel-header"><div><h3>Interface summary</h3><p>Average rates across the selected range; missing metric values remain unavailable.</p></div></div>'+
    '<div class="table-wrap"><table><thead><tr><th>Node</th><th>Interface</th><th>RX avg</th><th>TX avg</th><th>RX packets</th><th>TX packets</th><th>Errors/s RX / TX</th><th>Drops/s RX / TX</th><th>Samples</th></tr></thead><tbody>'+
    (rows||'<tr><td colspan="9" class="muted">No samples found.</td></tr>')+'</tbody></table></div></section>'+
    (data.sample_count===0?'<div class="chart-empty-state"><strong>No samples available</strong><p>Try a longer time range or wait for the next collection.</p></div>':'');
}
async function showClusterTopology(id, section="infra-overview"){
  if(section==="network"&&state.topologyClusterId!==id){state.networkNodeFilter="all";state.networkSelectedInterface="all";}
  const d=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"/topology");
  state.topologyClusterId=id;state.topologySection=section;
  const storageView=section==="storage-overview"||section==="pools"||section==="sets";
  const tabs=storageView?[["storage-overview","Overview"],["pools","Pools"],["sets","Erasure Sets"]]:[["infra-overview","Overview"],["nodes","Node Health & Performance"],["drives","Drives & Filesystems"],["network","Network"]];
  const tabHtml='<div class="tabs">'+tabs.map(([key,label])=>'<button class="tab '+(section===key?'active':'')+'" data-topology-tab="'+key+'">'+label+'</button>').join("")+'</div>';
  const nodeSubsection=state.nodeSubsection||"health";
  const nodeSubTabsHtml='<div class="tabs node-subtabs">'+[["health","Availability"],["performance","CPU & Memory Trends"],["collection","Collection Health"],["reports","Performance Reports"]].map(([key,label])=>'<button class="tab '+(nodeSubsection===key?'active':'')+'" data-node-subtab="'+key+'">'+label+'</button>').join("")+'</div>';
  const nodes=d.nodes||[],drives=d.drives||[],pools=d.pools||[],sets=d.erasure_sets||[];
  const driveCountsComplete=nodes.length>0&&nodes.every(n=>n.drives_online!=null&&n.drives_offline!=null);
  const drivesOnline=driveCountsComplete?nodes.reduce((sum,n)=>sum+n.drives_online,0):null;
  const drivesOffline=driveCountsComplete?nodes.reduce((sum,n)=>sum+n.drives_offline,0):null;
  const nodeRows=nodes.map(n=>{
    const ne=n.node_exporter_up===1,ms=n.minio_scrape_up===1;
    const mem=n.memory_total_bytes&&n.memory_used_bytes!=null?n.memory_used_bytes/n.memory_total_bytes*100:null;
    return '<tr><td><span class="cell-strong">'+esc(n.node_name)+'</span></td><td>'+pill(ne?'Online':n.node_exporter_up===0?'Offline':'Unknown')+'</td><td>'+pill(ms?'Reachable':n.minio_scrape_up===0?'Unreachable':'Unknown')+'</td><td>'+(n.cpu_utilization_pct==null?'—':fmt(n.cpu_utilization_pct,1)+'%')+'</td><td>'+(mem==null?'—':fmt(mem,1)+'%')+'</td><td>'+(n.load1==null?'—':fmt(n.load1,2))+'</td><td>'+(n.drives_online??'—')+'</td><td>'+(n.drives_offline??'—')+'</td></tr>';
  });
  const driveState=v=>v.filesystem_readonly===1?"readonly":v.filesystem_readonly===0?"writable":"unknown";
  const driveHasErrors=v=>Number(v.availability_errors||0)>0||Number(v.io_errors||0)>0||Number(v.timeout_errors||0)>0;
  const driveGroups=[...new Set([...drives.map(v=>v.node_name),...nodes.map(n=>n.node_name)])].sort((a,b)=>a.localeCompare(b));
  const selectedDriveRows=drives.filter(v=>state.driveNodeFilter==="all"||v.node_name===state.driveNodeFilter);
  const selectedNodeRows=nodes.filter(n=>state.driveNodeFilter==="all"||n.node_name===state.driveNodeFilter);
  const driveInventorySummary={
    total:selectedDriveRows.length,
    online:selectedNodeRows.length&&selectedNodeRows.every(n=>n.drives_online!=null)?selectedNodeRows.reduce((sum,n)=>sum+n.drives_online,0):null,
    offline:selectedNodeRows.length&&selectedNodeRows.every(n=>n.drives_offline!=null)?selectedNodeRows.reduce((sum,n)=>sum+n.drives_offline,0):null,
    fsReported:selectedDriveRows.filter(v=>v.filesystem_used_pct!=null).length,
    readonly:selectedDriveRows.filter(v=>v.filesystem_readonly===1).length,
    errors:selectedDriveRows.filter(driveHasErrors).length,
    fsUsed:selectedDriveRows.reduce((sum,v)=>sum+(Number(v.filesystem_used_bytes)||0),0),
    fsTotal:selectedDriveRows.reduce((sum,v)=>sum+(Number(v.filesystem_total_bytes)||0),0)
  };
  const driveInventoryHtml=()=>{
    const filteredGroups=driveGroups.filter(name=>state.driveNodeFilter==="all"||name===state.driveNodeFilter);
    const nodeOptions=driveGroups.map(name=>'<option value="'+esc(name)+'" '+(state.driveNodeFilter===name?'selected':'')+'>'+esc(name)+'</option>').join("");
    const rows=selectedDriveRows.map(v=>{
      const total=Number(v.filesystem_total_bytes||v.total_bytes)||0;
      const used=Number(v.filesystem_used_bytes??v.used_bytes)||0;
      const free=Math.max(0,total-used);
      const util=v.filesystem_used_pct!=null?Number(v.filesystem_used_pct):(total?used/total*100:null);
      const status=driveState(v),errors=[v.availability_errors??0,v.io_errors??0,v.timeout_errors??0];
      const searchText=[v.node_name,v.drive_path,v.mountpoint].join(" ").toLowerCase();
      const barClass=util>=90?"critical":util>=75?"warning":"normal";
      const bar=util==null?"—":'<div class="drive-utilization"><div class="drive-util-track"><span class="'+barClass+'" style="width:'+Math.max(0,Math.min(100,util))+'%"></span></div><strong>'+fmt(util,1)+'%</strong></div>';
      const statusLabel=status==="readonly"?"Read-only":status==="writable"?"Writable":"Unknown";
      return '<tr data-drive-row data-drive-status="'+status+'" data-drive-error="'+(driveHasErrors(v)?'1':'0')+'" data-drive-search="'+esc(searchText)+'" data-drive-node="'+esc(v.node_name)+'" data-drive-capacity="'+total+'" data-drive-used="'+used+'" data-drive-free="'+free+'" data-drive-util="'+(util==null?-1:util)+'" data-drive-errors="'+errors.reduce((sum,n)=>sum+Number(n||0),0)+'" data-drive-filter-visible="1">'+
        '<td><span class="cell-strong">'+esc(v.node_name)+'</span></td>'+
        '<td><span class="cell-strong">'+esc(v.drive_path)+'</span></td>'+
        '<td>'+esc(v.mountpoint||"—")+'</td>'+
        '<td>'+esc(v.filesystem_type||v.filesystem||"—")+'</td>'+
        '<td>'+bytes(total||null)+'</td><td>'+bytes(used)+'</td><td>'+bytes(total?free:null)+'</td>'+
        '<td>'+bar+'</td><td>'+pill(statusLabel)+'</td>'+
        '<td class="drive-error-counts"><span class="'+(Number(errors[0])>0?'has-error':'')+'">'+errors[0]+'</span> / <span class="'+(Number(errors[1])>0?'has-error':'')+'">'+errors[1]+'</span> / <span class="'+(Number(errors[2])>0?'has-error':'')+'">'+errors[2]+'</span></td></tr>';
    }).join("");
    const weightedFsPct=driveInventorySummary.fsTotal>0?driveInventorySummary.fsUsed/driveInventorySummary.fsTotal*100:null;
    const selectionLabel=state.driveNodeFilter==="all"?"All nodes":state.driveNodeFilter;
    return '<div class="drive-inventory-workspace"><div class="metric-grid drive-inventory-summary">'+
      metric("TOTAL DRIVES",fmt(driveInventorySummary.total,0),selectionLabel,"▤")+
      metric("ONLINE DRIVES",driveInventorySummary.online==null?"—":fmt(driveInventorySummary.online,0),"MinIO-reported node counts","✓",driveInventorySummary.online!=null&&driveInventorySummary.offline===0)+
      metric("OFFLINE DRIVES",driveInventorySummary.offline==null?"—":fmt(driveInventorySummary.offline,0),"MinIO-reported node counts","!")+
      metric("FS UTILIZATION",weightedFsPct==null?"—":fmt(weightedFsPct,1)+"%",driveInventorySummary.fsReported+" drives with filesystem data","◉")+
      metric("READ-ONLY FS",fmt(driveInventorySummary.readonly,0),"Filesystem state","◈")+
      metric("DRIVES WITH ERRORS",fmt(driveInventorySummary.errors,0),"Any availability / I/O / timeout errors","!",driveInventorySummary.errors===0)+'</div>'+
      '<section class="panel drive-inventory-filter-panel"><div class="drive-inventory-filters"><label>NODE<select class="form-control" data-drive-node-filter><option value="all" '+(state.driveNodeFilter==="all"?'selected':'')+'>All nodes</option>'+nodeOptions+'</select></label><label>FILESYSTEM STATE<select class="form-control" data-drive-state-filter><option value="all" '+(state.driveFsFilter==="all"?'selected':'')+'>All drives</option><option value="writable" '+(state.driveFsFilter==="writable"?'selected':'')+'>Writable</option><option value="readonly" '+(state.driveFsFilter==="readonly"?'selected':'')+'>Read-only</option><option value="unknown" '+(state.driveFsFilter==="unknown"?'selected':'')+'>Unknown</option><option value="errors" '+(state.driveFsFilter==="errors"?'selected':'')+'>With errors</option></select></label><label class="drive-inventory-search">SEARCH<input class="form-control" type="search" data-drive-search placeholder="Node, drive path or mountpoint"></label><button type="button" class="secondary-button drive-export-button" data-drive-export>↓ Export filtered drives</button></div></section>'+
      '<section class="panel drive-inventory-node-list"><div class="panel-header"><div><h3>Drive inventory</h3><p>Cluster-wide inventory · one drive per row · use sorting and filters to locate drives quickly.</p></div><span class="panel-tag">'+filteredGroups.length+' node(s)</span></div>'+
      '<div class="table-scroll"><table class="drive-inventory-table drive-inventory-flat"><thead><tr>'+["NODE","DRIVE / PATH","MOUNTPOINT","FILESYSTEM","CAPACITY","USED","FREE","UTILIZATION","STATE","ERRORS A / I / T"].map((label,i)=>'<th><button type="button" class="drive-sort-button" data-drive-sort="'+["node","path","mountpoint","filesystem","capacity","used","free","utilization","state","errors"][i]+'">'+label+' <span class="sort-indicator" aria-hidden="true"></span></button></th>').join("")+'</tr></thead><tbody>'+ (rows||'<tr><td colspan="10" class="empty-state">No drive records are available for this cluster snapshot.</td></tr>')+'</tbody></table></div>'+
      '<div class="drive-inventory-pagination"><span data-drive-page-summary>Showing 0 drives</span><label>Rows per page<select class="form-control" data-drive-page-size><option>25</option><option>50</option><option>100</option></select></label><div><button type="button" class="secondary-button" data-drive-page="prev">← Previous</button><span data-drive-page-number>Page 1</span><button type="button" class="secondary-button" data-drive-page="next">Next →</button></div></div>'+
      '<div class="chart-empty-state drive-search-empty hidden"><strong>No matching drives</strong><p>Adjust the search term or filters.</p></div></section></div>';
  };
  const applyDriveInventoryTable=()=>{
    const table=$("#content .drive-inventory-flat");if(!table)return;
    const rows=[...table.querySelectorAll("[data-drive-row]")];
    const q=($("#content [data-drive-search]")?.value||"").trim().toLowerCase();
    const stateFilter=$("#content [data-drive-state-filter]")?.value||"all";
    const nodeFilter=$("#content [data-drive-node-filter]")?.value||"all";
    let filtered=rows.filter(row=>(!q||row.dataset.driveSearch.includes(q))&&(nodeFilter==="all"||row.dataset.driveNode===nodeFilter)&&(stateFilter==="all"||(stateFilter==="errors"?row.dataset.driveError==="1":row.dataset.driveStatus===stateFilter)));
    const sortKey=state.driveSortKey||"node",direction=state.driveSortDirection||1;
    const indexMap={node:0,path:1,mountpoint:2,filesystem:3,capacity:4,used:5,free:6,utilization:7,state:8,errors:9};
    filtered.sort((a,b)=>{
      const i=indexMap[sortKey],av=a.cells[i]?.textContent.trim()||"",bv=b.cells[i]?.textContent.trim()||"";
      const numeric=["capacity","used","free","utilization","errors"].includes(sortKey);
      const dataKey={capacity:"driveCapacity",used:"driveUsed",free:"driveFree",utilization:"driveUtil",errors:"driveErrors"}[sortKey];
      const an=dataKey?Number(a.dataset[dataKey]):NaN,bn=dataKey?Number(b.dataset[dataKey]):NaN;
      const cmp=numeric&&Number.isFinite(an)&&Number.isFinite(bn)?an-bn:av.localeCompare(bv,undefined,{numeric:true,sensitivity:"base"});
      return cmp*direction;
    });
    const pageSize=Number($("#content [data-drive-page-size]")?.value||25),pageCount=Math.max(1,Math.ceil(filtered.length/pageSize));
    state.driveInventoryPage=Math.min(Math.max(1,state.driveInventoryPage||1),pageCount);
    rows.forEach(row=>row.classList.add("hidden"));
    filtered.forEach(row=>table.querySelector("tbody").append(row));
    const start=(state.driveInventoryPage-1)*pageSize;
    filtered.slice(start,start+pageSize).forEach(row=>row.classList.remove("hidden"));
    $("#content [data-drive-page-summary]").textContent=filtered.length?"Showing "+(start+1)+"–"+Math.min(start+pageSize,filtered.length)+" of "+filtered.length+" drives":"Showing 0 drives";
    $("#content [data-drive-page-number]").textContent="Page "+state.driveInventoryPage+" of "+pageCount;
    $("#content [data-drive-page=prev]").disabled=state.driveInventoryPage<=1;
    $("#content [data-drive-page=next]").disabled=state.driveInventoryPage>=pageCount;
    $("#content .drive-search-empty")?.classList.toggle("hidden",filtered.length>0);
    table.querySelectorAll("[data-drive-sort]").forEach(button=>button.querySelector(".sort-indicator").textContent=button.dataset.driveSort===sortKey?(direction===1?"▲":"▼"):"");
    rows.forEach(row=>row.dataset.driveFilterVisible=filtered.includes(row)?"1":"0");
  };
  window.applyDriveInventoryTable=applyDriveInventoryTable;
  const poolRows=pools.map(p=>'<tr><td>'+esc(p.pool_id)+'</td><td>'+p.erasure_set_count+'</td><td>'+(p.online_drives??'—')+'</td><td>'+(p.healing_drives??'—')+'</td></tr>');
  const setRows=sets.map(s=>'<tr><td>'+esc(s.pool_id)+'</td><td>'+esc(s.set_id)+'</td><td>'+(s.status_value??'—')+'</td><td>'+(s.online_drives??'—')+'</td><td>'+(s.healing_drives??'—')+'</td><td>'+(s.read_quorum??'—')+'</td><td>'+(s.write_quorum??'—')+'</td></tr>');

  let trendData=null,performanceData=null;
  let networkData=null;
  const rangeBounds=getHistoricalTimeBounds();
  if(section==="network"){
    const networkParams=new URLSearchParams({start_ts:rangeBounds.startTs,end_ts:rangeBounds.endTs});
    if(state.networkNodeFilter!=="all")networkParams.set("node_name",state.networkNodeFilter);
    if(state.networkSelectedInterface&&state.networkSelectedInterface!=="all"){const p=state.networkSelectedInterface.split("|");if(p.length===3){networkParams.set("node_name",p[0]);networkParams.set("interface_name",p[1]);networkParams.set("instance",p[2]);}}
    networkData=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"/network/performance-series?"+networkParams.toString());
  }
  if(section==="nodes"&&nodeSubsection==="health"){
    const trendParams=new URLSearchParams({start_ts:rangeBounds.startTs,end_ts:rangeBounds.endTs});
    trendData=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"/topology/trends?"+trendParams.toString());
  }
  if(section==="drives"){
    const trendParams=new URLSearchParams({start_ts:rangeBounds.startTs,end_ts:rangeBounds.endTs});
    trendData=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"/topology/trends?"+trendParams.toString());
  }
  if(section==="nodes"||section==="infra-overview"){
    performanceData=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"/nodes/performance?hours="+state.nodePerformanceHours);
    if(nodeSubsection==="performance"){
    const seriesParams=new URLSearchParams();
    seriesParams.set("start_ts",rangeBounds.startTs);
    seriesParams.set("end_ts",rangeBounds.endTs);
    (state.performanceSelectedNodes||[]).forEach(name=>seriesParams.append("node_names",name));
    var performanceSeriesData=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"/nodes/performance-series?"+seriesParams.toString());
    }
  }
  const trendControls=trendData?'<span class="infra-toolbar-meta">Historical trends · '+fmt(trendData.sample_count||0,0)+' samples · '+fmt(trendData.interval_minutes||5,0)+' min cadence</span>':'';
  const trendSamples=trendData?.samples||[];
  const trendLabels=trendSamples.map(x=>snapshotTimestampLabel(x.snapshot_ts));
  const performanceTrendPanel=(title,description,canvasId)=>'<section class="panel"><div class="panel-header"><div><h3>'+title+'</h3><p>'+description+'</p></div></div>'+(performanceData?.samples?.length?'<div class="chart-wrap health-trend-chart"><canvas id="'+canvasId+'"></canvas></div>':'<div class="chart-empty-state"><strong>No historical samples available</strong><p>No telemetry was stored in the selected averaging window.</p></div>')+'</section>';
  const trendPanel=(title,description,canvasId)=>'<section class="panel"><div class="panel-header"><div><h3>'+title+'</h3><p>'+description+'</p></div></div>'+(trendSamples.length?'<div class="chart-wrap health-trend-chart"><canvas id="'+canvasId+'"></canvas></div>':'<div class="chart-empty-state"><strong>No historical samples available</strong><p>No telemetry was stored in the selected date range.</p></div>')+'</section>';
  const infraOverview='<div class="metric-grid">'+
    metric("NODES",nodes.length,nodes.filter(n=>n.node_exporter_up===1).length+" Node Exporter targets reachable","⌁")+
    metric("DRIVES",drives.length,drivesOnline==null?"Online/offline counts unavailable":drivesOnline+" online · "+drivesOffline+" offline","▤")+
    metric("CPU AVG",performanceData?.nodes?.some(n=>n.avg_cpu_pct!=null)?fmt(performanceData.nodes.filter(n=>n.avg_cpu_pct!=null).reduce((sum,n)=>sum+n.avg_cpu_pct,0)/performanceData.nodes.filter(n=>n.avg_cpu_pct!=null).length,1)+"%":"—","Selected averaging window","◉")+
    metric("MEMORY AVG",performanceData?.nodes?.some(n=>n.avg_memory_used_pct!=null)?fmt(performanceData.nodes.filter(n=>n.avg_memory_used_pct!=null).reduce((sum,n)=>sum+n.avg_memory_used_pct,0)/performanceData.nodes.filter(n=>n.avg_memory_used_pct!=null).length,1)+"%":"—","Selected averaging window","◈")+
    metric("NODE EXPORTER",nodes.filter(n=>n.node_exporter_up===1).length+" / "+nodes.length,"Reachable nodes","◉")+
    metric("MINIO SCRAPES",nodes.filter(n=>n.minio_scrape_up===1).length+" / "+nodes.length,"Reachable MinIO targets","◈")+'</div>'+
    (performanceData?.samples?.length?'<div class="health-infra-trend-grid">'+performanceTrendPanel("CPU utilization trend","Average CPU utilization across nodes · selected window","infra-overview-cpu")+performanceTrendPanel("Memory utilization trend","Average memory utilization across nodes · selected window","infra-overview-memory")+'</div>':'');
  const storageOverview='<div class="metric-grid">'+
    metric("STORAGE POOLS",pools.length,"Pools discovered","▦")+
    metric("ERASURE SETS",sets.length,"Sets discovered","◫")+
    metric("DRIVES",drives.length,"Drives reported by MinIO","▤")+
    metric("ONLINE DRIVES",pools.every(p=>p.online_drives!=null)?pools.reduce((sum,p)=>sum+p.online_drives,0):"—","Reported online drive count","◇")+'</div>'+
    table("Storage pools","Pool counts and drive state derived from discovered erasure-set metrics.",["POOL","ERASURE SETS","ONLINE DRIVES","HEALING DRIVES"],poolRows);
  let body="";
  if(section==="infra-overview") body=infraOverview;
  const perfNodes=performanceData?.nodes||[],perfSamples=performanceData?.samples||[];
  const perfToolbar='<div class="toolbar node-performance-range"><span class="cell-muted">AVERAGING WINDOW</span>'+[2,6,12,24].map(h=>'<button class="secondary-button '+(state.nodePerformanceHours===h?'active':'')+'" data-node-hours="'+h+'">'+h+'h</button>').join("")+'</div>';
  const perfRows=perfNodes.map(n=>'<tr><td><span class="cell-strong">'+esc(n.node_name)+'</span></td><td>'+(n.avg_cpu_pct==null?'—':fmt(n.avg_cpu_pct,1)+'%')+'</td><td>'+(n.avg_memory_used_pct==null?'—':fmt(n.avg_memory_used_pct,1)+'%')+'</td><td>'+(n.avg_load1==null?'—':fmt(n.avg_load1,2))+'</td><td>'+fmt(n.sample_count,0)+'</td><td>'+(n.node_exporter_availability_pct==null?'—':fmt(n.node_exporter_availability_pct,1)+'%')+'</td></tr>');
  const cadenceStatusLabels={on_schedule:"on schedule",faster_than_configured:"faster than configured",slower_than_configured:"slower than configured",irregular:"irregular",insufficient_history:"insufficient history"};
  const observedCadence=performanceData?.observed_interval_minutes==null?"not enough history":fmt(performanceData.observed_interval_minutes,1)+" min";
  const cadenceStatus=cadenceStatusLabels[performanceData?.cadence_status]||"unknown";
  const expectedIntervals=performanceData?.expected_intervals??performanceData?.expected_samples??0;
  const intervalCoverage=performanceData?.interval_coverage_pct??performanceData?.coverage_pct??0;
  const perfCoverage=performanceData?'<p class="cell-muted">Collection runs: '+fmt(performanceData.sample_count,0)+' · configured cadence: '+fmt(performanceData.interval_minutes,0)+' min · intervals covered: '+fmt(performanceData.covered_intervals,0)+' / '+fmt(expectedIntervals,0)+' ('+fmt(intervalCoverage,1)+'%) · observed median cadence: '+observedCadence+' · '+cadenceStatus+(performanceData.excess_runs?' · '+fmt(performanceData.excess_runs,0)+' additional runs':'')+'</p>':'';
  const missingIntervalWindows=performanceData?.missing_interval_windows||[];
  const missingIntervalPanel=performanceData?(performanceData.missing_intervals>0?table("Missing collection intervals","Expected collection windows with no recorded node telemetry run.",["EXPECTED FROM","EXPECTED TO"],missingIntervalWindows.map(w=>'<tr><td>'+snapshotTimestampLabel(w.start_ts)+'</td><td>'+snapshotTimestampLabel(w.end_ts)+'</td></tr>'),"No missing intervals.")+(performanceData.missing_interval_windows_truncated?'<p class="cell-muted">Showing the most recent '+fmt(missingIntervalWindows.length,0)+' of '+fmt(performanceData.missing_intervals,0)+' missing intervals.</p>':''):'<section class="panel"><div class="panel-header"><div><h3>Missing collection intervals</h3><p>No expected collection windows were missed in the selected time range.</p></div></div></section>'):"";
  const intervalStatusCounts=performanceData?.interval_status_counts||{success:0,partial:0,failed:0,missing:0};
  const reliabilityTrend=performanceData?.reliability_trend||[];
  const reliabilityPanel=performanceData?'<div class="metric-grid">'+
    metric("SUCCESSFUL INTERVALS",fmt(intervalStatusCounts.success,0),"Completed without reported family errors","✓",intervalStatusCounts.success>0)+
    metric("PARTIAL INTERVALS",fmt(intervalStatusCounts.partial,0),"Collection completed with family errors","◒")+
    metric("FAILED INTERVALS",fmt(intervalStatusCounts.failed,0),"Collection attempt recorded as failed","!")+
    metric("MISSING INTERVALS",fmt(intervalStatusCounts.missing,0),"No collection attempt recorded","—")+
    '</div>'+panel("Collection reliability trend","Hourly count of expected intervals by recorded outcome. Missing means no run was recorded; it is not classified as a failure.",'<div class="chart-wrap health-trend-chart"><canvas id="infra-collection-reliability"></canvas></div>'):"";
  const ps=performanceSeriesData||{};
  const selectedNames=state.performanceSelectedNodes===null?(ps.available_nodes||[]):state.performanceSelectedNodes;
  const metricTabs=[["cpu","CPU"],["memory","Memory"],["load","Load"],["filesystem_utilization","Disk / Filesystem Utilization"]];
  const nodeCount=(ps.available_nodes||[]).length;
  const selectedCount=selectedNames.length;
  const nodeFilterLabel=selectedCount===nodeCount?"All nodes":selectedCount===0?"No nodes":selectedCount+" of "+nodeCount+" nodes";
  const nodeFilter='<details class="report-column-menu node-performance-filter"><summary class="subtle-button"><span>Nodes · '+nodeFilterLabel+'</span> <span>▾</span></summary><div class="report-column-options"><div class="node-filter-actions"><button type="button" class="table-link" data-action="select-all-performance-nodes">All nodes</button><button type="button" class="table-link" data-action="clear-performance-nodes">Clear</button></div>'+(ps.available_nodes||[]).map(name=>'<label><input type="checkbox" data-performance-node value="'+esc(name)+'" '+(selectedNames.includes(name)?'checked':'')+'> <span>'+esc(name)+'</span></label>').join("")+'</div></details>';
  const timePresets=[["5m","Last 5m"],["15m","15m"],["30m","30m"],["1h","1h"],["3h","3h"],["6h","6h"],["12h","12h"],["24h","24h"],["2d","2d"],["7d","7d"],["30d","30d"]];
  const perfRange=nodeFilter;
  const customRange="";
  const metricTabsHtml='<div class="tabs">'+metricTabs.map(([key,label])=>'<button class="tab '+(state.performanceMetric===key?'active':'')+'" data-performance-metric="'+key+'">'+label+'</button>').join("")+'</div>';
  const metricLabels={cpu:["CPU utilization","%"],memory:["Memory utilization","%"],load:["System load",""],filesystem_utilization:["Filesystem utilization","%"]};
  const metricField={cpu:"cpu_utilization_pct",memory:"memory_used_pct",load:"load1"};
  let graphLabels=[],graphSets=[],statRows=[];
  if(state.performanceMetric==="filesystem_utilization"){
    const grouped=new Map();
    (ps.drive_series||[]).forEach(row=>{const node=row.node_name;if(!selectedNames.includes(node))return;const key=node+" · "+(row.mountpoint||row.drive_path);if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(row);});
    const allStamps=[...new Set((ps.drive_series||[]).filter(x=>selectedNames.includes(x.node_name)).map(x=>x.snapshot_ts))].sort();
    graphLabels=allStamps.map(snapshotTimestampLabel);
    graphSets=[...grouped.entries()].map(([label,rows],i)=>({label,data:allStamps.map(ts=>{const row=rows.find(x=>x.snapshot_ts===ts);return row?.filesystem_used_pct??null;}),raw:true,color:["#4776c7","#16a085","#d99a35","#8b6ccf","#d9534f","#64748b"][i%6]}));
    for(const [label,rows] of grouped){const values=rows.map(x=>x.filesystem_used_pct).filter(x=>x!=null);statRows.push('<tr><td>'+esc(label)+'</td><td>'+fmt(values.length?values.reduce((a,b)=>a+b,0)/values.length:null,1)+'%</td><td>'+fmt(values.length?Math.min(...values):null,1)+'%</td><td>'+fmt(values.length?Math.max(...values):null,1)+'%</td><td>'+fmt(values.at(-1),1)+'%</td><td>'+values.length+'</td></tr>');}
  }else{
    const field=metricField[state.performanceMetric];
    const selectedSeries=(ps.series||[]).filter(x=>selectedNames.includes(x.node_name));
    graphLabels=[...new Set(selectedSeries.map(x=>x.snapshot_ts))].sort().map(snapshotTimestampLabel);
    graphSets=selectedNames.map((name,i)=>({label:name,data:graphLabels.map(label=>{const row=selectedSeries.find(x=>x.node_name===name&&snapshotTimestampLabel(x.snapshot_ts)===label);return row?.[field]??null;}),raw:true,color:["#4776c7","#16a085","#d99a35","#8b6ccf","#d9534f","#64748b","#0f766e","#b45309"][i%8]}));
    for(const name of selectedNames){const stats=ps.statistics?.[name]?.[state.performanceMetric];if(!stats)continue;statRows.push('<tr><td>'+esc(name)+'</td><td>'+fmt(stats.average,3)+'</td><td>'+fmt(stats.minimum,3)+'</td><td>'+fmt(stats.maximum,3)+'</td><td>'+fmt(stats.latest,3)+'</td><td>'+fmt(stats.sample_count,0)+'</td></tr>');}
  }
  const perfGraph='<section class="panel"><div class="panel-header"><div><h3>'+metricLabels[state.performanceMetric][0]+'</h3><p>Raw recorded samples · '+fmt(ps.interval_minutes||5,0)+'-minute collection cadence · '+fmt(ps.sample_count||0,0)+' node samples</p></div></div>'+(graphLabels.length?'<div class="chart-wrap health-trend-chart"><canvas id="node-performance-explorer-chart"></canvas></div>':'<div class="chart-empty-state"><strong>No samples available</strong><p>No matching telemetry was recorded for this range and node selection.</p></div>')+'</section>';
  const perfStats=table("Per-node statistics","Average, minimum, maximum, latest value and sample count for the selected range.",["NODE / FILESYSTEM","AVG","MIN","MAX","LATEST","SAMPLES"],statRows);
  const nodePerformancePicker=historicalRangePicker(performanceSeriesData?.retention_days||3,performanceSeriesData?.interval_minutes||5,"performance");
  const nodePerformanceBody='<div class="infra-compact-toolbar"><div class="infra-toolbar-left">'+metricTabsHtml+'</div>'+nodePerformancePicker+'</div>'+perfGraph+perfStats;
  const nodeHealthBody=table("Node availability","Node Exporter and MinIO scrape status are shown independently.",["NODE","NODE EXPORTER","MINIO TARGET","CPU (LATEST)","MEMORY (LATEST)","LOAD 1M","DRIVES UP","DRIVES DOWN"],nodeRows);
  const nodeCollectionBody=perfToolbar+perfCoverage+missingIntervalPanel+reliabilityPanel;
  const nodeReportsBody=perfToolbar+table("Node performance report","Average, minimum and peak values for each node over the selected window.",["NODE","CPU AVG / MIN / PEAK","MEMORY AVG / MIN / PEAK","LOAD AVG / PEAK","SAMPLES","EXPORTER AVAILABILITY"],perfNodes.map(n=>'<tr><td><span class="cell-strong">'+esc(n.node_name)+'</span></td><td>'+fmt(n.avg_cpu_pct,1)+'% / '+fmt(n.min_cpu_pct,1)+'% / '+fmt(n.max_cpu_pct,1)+'%</td><td>'+fmt(n.avg_memory_used_pct,1)+'% / '+fmt(n.min_memory_used_pct,1)+'% / '+fmt(n.max_memory_used_pct,1)+'%</td><td>'+fmt(n.avg_load1,2)+' / '+fmt(n.max_load1,2)+'</td><td>'+fmt(n.sample_count,0)+'</td><td>'+fmt(n.node_exporter_availability_pct,1)+'%</td></tr>'));
  if(section==="nodes") body=nodeSubTabsHtml+(nodeSubsection==="health"?'<div class="infra-compact-toolbar">'+historicalRangePicker(trendData?.retention_days||3,trendData?.interval_minutes||5,"availability")+trendControls+'</div><div class="health-infra-trend-grid">'+
    trendPanel("Node Exporter availability","Percentage of nodes reporting successfully","infra-node-availability")+
    trendPanel("MinIO scrape availability","Percentage of MinIO node targets reporting","infra-minio-availability")+
    '</div>'+nodeHealthBody:nodeSubsection==="performance"?nodePerformanceBody:nodeSubsection==="collection"?nodeCollectionBody:nodeReportsBody);
  const driveSubTabs='<div class="tabs drives-subtabs" role="tablist" aria-label="Drives and filesystems views"><button type="button" role="tab" aria-selected="'+(state.driveView==="graphs")+'" class="tab '+(state.driveView==="graphs"?"active":"")+'" data-drive-view="graphs">Graphs</button><button type="button" role="tab" aria-selected="'+(state.driveView==="inventory")+'" class="tab '+(state.driveView==="inventory"?"active":"")+'" data-drive-view="inventory">Drive Inventory</button></div>';
  const driveGraphs=trendControls+'<div class="health-infra-trend-grid">'+
    trendPanel("Drive availability","MinIO-reported online and offline drive counts across the cluster","infra-drive-availability")+
    trendPanel("Drive error counters","Cumulative availability, I/O and timeout errors reported by drives","infra-drive-errors")+
    trendPanel("Filesystem utilization","Weighted utilization across monitored MinIO data filesystems","infra-filesystem-trend")+
    '</div>';
  if(section==="drives") body=state.driveView==="graphs"?'<div class="infra-compact-toolbar"><div class="infra-toolbar-left">'+driveSubTabs+trendControls+'</div>'+historicalRangePicker(trendData?.retention_days||3,trendData?.interval_minutes||5,"drives")+'</div>'+driveGraphs.replace(trendControls,""):driveSubTabs+driveInventoryHtml();
  if(section==="network") body=renderNetworkWorkspace(networkData);
  if(section==="storage-overview") body=storageOverview;
  if(section==="pools") body=table("Storage pools","Pool capacity is not inferred where no pool-level capacity metric was discovered.",["POOL","ERASURE SETS","ONLINE DRIVES","HEALING DRIVES"],poolRows);
  if(section==="sets") body=table("Erasure sets","Status is shown as the raw MinIO metric value; quorum values are not interpreted as a health enum.",["POOL","SET","STATUS VALUE","ONLINE DRIVES","HEALING DRIVES","READ QUORUM","WRITE QUORUM"],setRows);
  const errors=Object.keys(d.family_errors||{}).length?'<div class="detail-card" style="margin-bottom:14px"><strong>Some topology metric families are unavailable</strong><p class="muted">'+esc(JSON.stringify(d.family_errors))+'</p></div>':'';
  clearCharts();
  const pageTitle=storageView?"Storage Topology":"Node Infrastructure";
  const pageSubtitle=storageView?"MinIO storage pools, erasure sets and quorum topology":"Node availability, compute resources, drive health, filesystem and network telemetry";
  const pageSnapshot='<span class="page-heading-snapshot">'+(section==="network"?"Latest network sample ":"Snapshot ")+esc(snapshotTimestampLabel(storageView?d.topology_snapshot_ts:section==="network"?(networkData.series||[]).at(-1)?.snapshot_ts:d.node_snapshot_ts))+'</span>';
  const timePickerContext=section==="network"?"network":section==="drives"&&state.driveView==="graphs"?"drives":section==="nodes"&&nodeSubsection==="health"?"availability":section==="nodes"&&nodeSubsection==="performance"?"performance":null;
  const timePickerRetention=networkData?.retention_days||trendData?.retention_days||performanceSeriesData?.retention_days||3;
  const timePickerInterval=networkData?.interval_minutes||trendData?.interval_minutes||performanceSeriesData?.interval_minutes||5;
  state.historicalTimeRetentionDays=timePickerRetention;
  const sharedTimePicker=timePickerContext?historicalRangePicker(timePickerRetention,timePickerInterval,timePickerContext):"";
  const networkToolbarEnd=[body.indexOf('<div class="detail-card">'),body.indexOf('<div class="panel-grid network-chart-grid">'),body.indexOf('<div class="chart-empty-state">')].filter(index=>index>=0).sort((a,b)=>a-b)[0];
  const networkToolbar=section==="network"?body.slice(0,networkToolbarEnd):"";
  const networkContent=section==="network"?body.slice(networkToolbar.length):body;
  body=body.replaceAll("__HIST_PICKER__",sharedTimePicker);
  const toolbarHtml=section==="network"?' <div class="infra-compact-toolbar"><div class="infra-toolbar-left">'+networkToolbar+'</div>'+sharedTimePicker+'</div>':section==="nodes"&&nodeSubsection==="performance"||section==="nodes"&&nodeSubsection==="health"||section==="drives"&&state.driveView==="graphs"?"":sharedTimePicker;
  $("#content").innerHTML=pageHead(esc(d.cluster.name)+" — "+pageTitle,pageSubtitle+pageSnapshot,'<button class="subtle-button" data-action="back-to-cluster-overview">← Back to cluster</button>')+errors+tabHtml+toolbarHtml+networkContent;
  if(section==="drives"&&state.driveView==="inventory")applyDriveInventoryTable();
  if(performanceData?.samples?.length&&section==="infra-overview"){
    const overviewLabels=performanceData.samples.map(x=>snapshotTimestampLabel(x.snapshot_ts));
    chart("infra-overview-cpu",overviewLabels,[{label:"Average CPU",data:performanceData.samples.map(x=>x.avg_cpu_pct),color:"#16a085"}],"line",0,"%");
    chart("infra-overview-memory",overviewLabels,[{label:"Average memory used",data:performanceData.samples.map(x=>x.avg_memory_used_pct),color:"#4776c7"}],"line",0,"%");
  }
  if(trendSamples.length&&section==="nodes"&&nodeSubsection==="health"){
    chart("infra-node-availability",trendLabels,[{label:"Node Exporter up",data:trendSamples.map(x=>x.node_exporter_availability_pct),color:"#16a085"}],"line",0,"%");
    chart("infra-minio-availability",trendLabels,[{label:"MinIO scrape up",data:trendSamples.map(x=>x.minio_scrape_availability_pct),color:"#4776c7"}],"line",0,"%");
  }
  if(graphLabels.length&&section==="nodes"&&nodeSubsection==="performance"){
    chart("node-performance-explorer-chart",graphLabels,graphSets,"line",0,metricLabels[state.performanceMetric][1]);
  }
  if(reliabilityTrend.length&&section==="nodes"&&nodeSubsection==="collection"){
    const reliabilityLabels=reliabilityTrend.map(x=>snapshotTimestampLabel(x.bucket_start_ts));
    chart("infra-collection-reliability",reliabilityLabels,[
      {label:"Successful",data:reliabilityTrend.map(x=>x.success_intervals),color:"#16a085"},
      {label:"Partial",data:reliabilityTrend.map(x=>x.partial_intervals),color:"#d99a35"},
      {label:"Failed",data:reliabilityTrend.map(x=>x.failed_intervals),color:"#d9534f"},
      {label:"Missing",data:reliabilityTrend.map(x=>x.missing_intervals),color:"#94a0af"}
    ],"line",0,"");
  }
  if(networkData&&section==="network"){
    const allSeries=networkData.series||[];
    const series=(!state.networkSelectedInterface||state.networkSelectedInterface==="all")?allSeries:allSeries.filter(x=>(x.node_name+"|"+x.interface_name+"|"+x.instance)===state.networkSelectedInterface);
    const keys=[...new Set(series.map(x=>x.node_name+"|"+x.interface_name+"|"+x.instance))];
    const colors=["#16a085","#4776c7","#d99a35","#8b6ccf","#d9534f","#2d9cdb","#6b9e40","#b05aa2"];
    const stamps=[...new Set(series.map(x=>x.snapshot_ts))].sort();
    const labels=stamps.map(timestampLabel);
    const datasets=(rx,tx,unit)=>keys.flatMap((key,i)=>{const group=series.filter(x=>(x.node_name+"|"+x.interface_name+"|"+x.instance)===key);const iface=key.split("|");const name=state.networkSelectedInterface==="all"?iface[0]+" / "+iface[1]:iface[1];return [{label:name+" RX",data:stamps.map(ts=>group.find(x=>x.snapshot_ts===ts)?.[rx]??null),color:colors[(i*2)%colors.length]},{label:name+" TX",data:stamps.map(ts=>group.find(x=>x.snapshot_ts===ts)?.[tx]??null),color:colors[(i*2+1)%colors.length]}];});
    chart("network-throughput-chart",labels,datasets("rx_bytes_per_second","tx_bytes_per_second","bytes/s"),"line",0,"bytes/s");
    chart("network-packets-chart",labels,datasets("rx_packets_per_second","tx_packets_per_second","packets/s"),"line",0,"packets/s");
    chart("network-errors-chart",labels,datasets("rx_errors_per_second","tx_errors_per_second","errors/s"),"line",0,"errors/s");
    chart("network-drops-chart",labels,datasets("rx_drops_per_second","tx_drops_per_second","drops/s"),"line",0,"drops/s");
  }
  if(trendSamples.length&&section==="drives"){
    chart("infra-drive-availability",trendLabels,[{label:"Drives online",data:trendSamples.map(x=>x.drives_online),color:"#16a085"},{label:"Drives offline",data:trendSamples.map(x=>x.drives_offline),color:"#d9534f"}],"line",0,"");
    chart("infra-drive-errors",trendLabels,[{label:"Availability errors",data:trendSamples.map(x=>x.availability_errors),color:"#d99a35"},{label:"I/O errors",data:trendSamples.map(x=>x.io_errors),color:"#8b6ccf"},{label:"Timeout errors",data:trendSamples.map(x=>x.timeout_errors),color:"#64748b"}],"line",0,"");
    chart("infra-filesystem-trend",trendLabels,[{label:"Filesystem used",data:trendSamples.map(x=>x.filesystem_weighted_used_pct??x.filesystem_used_pct),color:"#d99a35"}],"line",0,"%");
  }
}

async function showClusterSnapshots(id,days=90,startDate=null,endDate=null){
  state.snapshotClusterId=id;state.snapshotRange={days,startDate,endDate};state.clusterDetailTab="snapshots";
  const section=(title,subtitle,content,toolbar="")=>'<section class="analytics-section"><div class="analytics-section-heading"><div><h2>'+title+'</h2><p>'+subtitle+'</p></div>'+toolbar+'</div>'+content+'</section>';
  const d=await api("/api/analytics/clusters/"+encodeURIComponent(id)+"?"+trendQuery(days,startDate,endDate));
  const rows=(d.series||[]).map(r=>`<tr><td>${dateLabel(r.snapshot_date)}</td><td>${bytes(r.raw_total_bytes)}</td><td>${bytes(r.raw_free_bytes)}</td><td>${bytes(r.usable_total_bytes)}</td><td>${bytes(r.usable_free_bytes)}</td><td>${r.nodes_online??"—"}</td><td>${r.nodes_offline??"—"}</td><td>${r.bucket_object_count==null?"—":fmt(r.bucket_object_count,0)}</td><td>${r.bucket_version_count==null?"—":fmt(r.bucket_version_count,0)}</td><td>${r.bucket_delete_marker_count==null?"—":fmt(r.bucket_delete_marker_count,0)}</td><td>${r.growth_bytes_per_day==null?"—":fmt(r.growth_bytes_per_day/1024**3)+" GiB"}</td><td>${r.days_to_full==null?"—":fmt(r.days_to_full,0)+" days"}</td><td>${pill(!!r.metrics_available)}</td></tr>`);
  clearCharts();
  $("#content").innerHTML=pageHead(esc(d.cluster.name),"Cluster · "+esc(d.cluster.location_name)+" · "+esc(id),'<button class="subtle-button" data-view="clusters">← All clusters</button>')+clusterDetailTabs("snapshots")+
    section("Daily snapshots","Historical daily cluster metrics and stored bucket analytics.",table("Snapshot history",rows.length+" snapshot(s) · "+(startDate&&endDate?dateLabel(startDate)+" – "+dateLabel(endDate):"Last "+days+" days"),["DATE","RAW TOTAL","RAW FREE","USABLE TOTAL","USABLE FREE","ONLINE","OFFLINE","OBJECTS","VERSIONS","DELETE MARKERS","GROWTH / DAY","DAYS TO FULL","STATUS"],rows,"No daily snapshots are available for this date range."),rangeControl(days,"cluster-snapshots",id));
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
  const actions=`<div class="heading-actions"><button class="subtle-button ${current?'active':''}" data-tenant-mode="current" data-tenant-id="${id}" aria-pressed="${current}">Current ownership</button><button class="subtle-button ${!current?'active':''}" data-tenant-mode="historical" data-tenant-id="${id}" aria-pressed="${!current}">Historical ownership</button><button class="subtle-button" data-view="tenants">← All tenants</button>${rangeControl(days,"tenant",id,attribution)}</div>`;
  const hasHistoricalSnapshots=Array.isArray(d.series)&&d.series.length>0;
  const noHistoricalAttribution=!current&&!hasHistoricalSnapshots;
  const hasQuota=(d.series||[]).some(r=>r.quota_bytes!=null);
  const capacityControls='<div class="tenant-chart-controls"><span>Y-axis scale</span><button type="button" data-tenant-scale="zero" class="'+(state.tenantCapacityScale==="zero"?"active":"")+'">Zero-based</button><button type="button" data-tenant-scale="zoom" class="'+(state.tenantCapacityScale==="zoom"?"active":"")+'">Zoomed</button></div>';
  const charts=noHistoricalAttribution
    ? panel("No historical attribution available","No bucket snapshots were attributed to this tenant during the selected period.",'<div class="empty-state"><strong>No historical ownership records found</strong><p>Bucket ownership was assigned after the relevant daily snapshots. Historical reporting will populate as new daily snapshots are collected under this tenant\'s ownership.</p><p>To view the historical usage of buckets assigned to this tenant today, switch to <strong>Current ownership</strong>.</p></div>')
    : panel("Tenant capacity and quota trend",current?"Daily usage and summed bucket quotas for currently assigned buckets · GiB":"Daily usage and quotas based on historical snapshot attribution · GiB",capacityControls+'<div class="chart-wrap"><canvas id="tenant-chart"></canvas></div>'+(hasQuota?'':'<div class="chart-note"><span class="chart-note-icon">ⓘ</span><strong>Quota not configured for the buckets attributed to this tenant.</strong></div>'))+
      panel("Tenant object trend","Daily object count across attributed buckets",'<div class="chart-wrap"><canvas id="tenant-object-chart"></canvas></div>')+objectSizeHistogram(hist,"Tenant object size distribution");
  $("#content").innerHTML=pageHead(esc(d.tenant.name),subtitle,actions)+
    `<div class="detail-grid"><div class="detail-card"><small>DESCRIPTION</small><strong style="font-size:14px">${esc(d.tenant.description||"—")}</strong></div><div class="detail-card"><small>STATUS</small><strong style="font-size:14px">${d.tenant.is_active?"Active":"Inactive"}</strong></div></div>`+
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
    panel("Bucket usage and quota trend","Daily usage and quota in TiB",'<div class="chart-wrap"><canvas id="bucket-chart"></canvas></div>',"",rangeControl(days,"bucket",id))+
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
    return `<tr><td><span class="cell-strong">${esc(n.cluster_name)}</span><br><span class="cell-muted">${esc(n.location_name)}</span></td><td>${snapshotTimestampLabel(n.snapshot_ts)}</td><td>${pill(status)}</td><td>${fmt(c.node_exporter_up,0)} / ${fmt(c.node_count,0)}</td><td>${fmt(c.minio_scrape_up,0)} / ${fmt(c.node_count,0)}</td><td>${fmt(c.drive_count,0)}</td><td>${fmt(c.availability_error_drives,0)} / ${fmt(c.io_error_drives,0)} / ${fmt(c.timeout_error_drives,0)}</td><td>${esc(errorText||"—")}</td></tr>`;
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
  const zoomControl=e.target.closest("[data-chart-zoom]");if(zoomControl){const instance=state.charts.find(item=>item.canvas?.id===zoomControl.dataset.chartId);if(!instance)return;const action=zoomControl.dataset.chartZoom;if(action==="in")instance.zoom(1.2);else if(action==="out")instance.zoom(0.8);else if(action==="reset")instance.resetZoom();return;}
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
  const generalConfigTab=e.target.closest("[data-general-config-tab]");if(generalConfigTab){state.masterGeneralTab=generalConfigTab.dataset.generalConfigTab;state.backupOffset=0;renderMasterAdmin().catch(err=>toast(err.message,true));return;}
  const masterConfigTab=e.target.closest("[data-master-config-tab]");if(masterConfigTab){setMasterConfigTab(masterConfigTab.dataset.masterConfigTab);return;}
  const reportView=e.target.closest("[data-report-view]");if(reportView){setView(reportView.dataset.reportView);return;}
  const view=e.target.closest("[data-view]");if(view){e.preventDefault();setView(view.dataset.view);return;}
  const clusterDetailTab=e.target.closest("[data-cluster-detail-tab]");if(clusterDetailTab){const tab=clusterDetailTab.dataset.clusterDetailTab;state.clusterDetailTab=tab;if(tab==="snapshots")showClusterSnapshots(state.snapshotClusterId,state.snapshotRange.days,state.snapshotRange.startDate,state.snapshotRange.endDate).catch(err=>toast(err.message,true));else showCluster(state.snapshotClusterId,state.snapshotRange.days,state.snapshotRange.startDate,state.snapshotRange.endDate,tab).catch(err=>toast(err.message,true));return;}
  const cluster=e.target.closest("[data-cluster]");if(cluster){try{await showCluster(cluster.dataset.cluster);}catch(err){toast(err.message,true);}return;}
  const tenant=e.target.closest("[data-tenant]");if(tenant){try{await showTenant(tenant.dataset.tenant);}catch(err){toast(err.message,true);}return;}
  const tenantMode=e.target.closest("[data-tenant-mode]");if(tenantMode){try{await showTenant(Number(tenantMode.dataset.tenantId),tenantMode.dataset.tenantMode);}catch(err){toast(err.message,true);}return;}
  const tenantScale=e.target.closest("[data-tenant-scale]");if(tenantScale){state.tenantCapacityScale=tenantScale.dataset.tenantScale;const c=state.snapshotContext;if(c?.type==="tenant")showTenant(c.id,c.attribution,c.days,c.startDate,c.endDate).catch(err=>toast(err.message,true));return;}
  const bucket=e.target.closest("[data-bucket]");if(bucket){try{await showBucket(bucket.dataset.bucket);}catch(err){toast(err.message,true);}return;}
  const assign=e.target.closest("[data-assign]");if(assign){assignBucketModal(Number(assign.dataset.assign));return;}
  const topologyTab=e.target.closest("[data-topology-tab]");if(topologyTab){showClusterTopology(state.topologyClusterId,topologyTab.dataset.topologyTab).catch(err=>toast(err.message,true));return;}
  const historicalRange=e.target.closest("[data-historical-range]");if(historicalRange){setHistoricalPreset(historicalRange.dataset.historicalRange);showClusterTopology(state.topologyClusterId,state.topologySection).catch(err=>toast(err.message,true));return;}
  const rangeAction=e.target.closest("[data-action='apply-historical-range'],[data-action='reset-historical-range']");
  if(rangeAction?.dataset.action==="apply-historical-range"){
    const check=validateHistoricalTimeRange($("#content [data-historical-start]")?.value,$("#content [data-historical-end]")?.value,state.historicalTimeRetentionDays);
    if(!check.valid){toast(check.message,true);return;}
    state.historicalTimeRange={mode:"absolute",preset:null,startTs:check.startTs,endTs:check.endTs,timezone:"Asia/Kolkata"};
    showClusterTopology(state.topologyClusterId,state.topologySection).catch(err=>toast(err.message,true));return;
  }
  if(rangeAction?.dataset.action==="reset-historical-range"){
    setHistoricalPreset("1h");
    showClusterTopology(state.topologyClusterId,state.topologySection).catch(err=>toast(err.message,true));return;
  }
  const driveViewTab=e.target.closest("[data-drive-view]");if(driveViewTab){state.driveView=driveViewTab.dataset.driveView;showClusterTopology(state.topologyClusterId,"drives").catch(err=>toast(err.message,true));return;}
  const driveExport=e.target.closest("[data-drive-export]");if(driveExport){const rows=[...$("#content").querySelectorAll("[data-drive-row][data-drive-filter-visible='1']")];if(!rows.length){toast("No matching drive rows to export.",true);return;}const csvCell=value=>'"'+String(value??"").replace(/"/g,'""')+'"';const headers=["Node","Drive / Path","Mountpoint","Filesystem","Capacity","Used","Free","Utilization","State","Availability Errors","I/O Errors","Timeout Errors"];const data=rows.map(row=>{const cells=[...row.cells].map(cell=>cell.textContent.replace(/\s+/g," ").trim());const errorParts=(cells[9]||"").split("/").map(value=>value.trim());return [...cells.slice(0,9),...errorParts];});const csv="\uFEFF"+[headers,...data].map(row=>row.map(csvCell).join(",")).join("\r\n");const blob=new Blob([csv],{type:"text/csv;charset=utf-8;"}),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download="drive-inventory-"+new Date().toISOString().slice(0,10)+".csv";document.body.append(link);link.click();link.remove();URL.revokeObjectURL(url);toast("Drive inventory CSV exported.");return;}
  const driveSort=e.target.closest("[data-drive-sort]");if(driveSort){if(state.driveSortKey===driveSort.dataset.driveSort)state.driveSortDirection*=-1;else{state.driveSortKey=driveSort.dataset.driveSort;state.driveSortDirection=1;}window.applyDriveInventoryTable();return;}
  const drivePage=e.target.closest("[data-drive-page]");if(drivePage){state.driveInventoryPage=Math.max(1,(state.driveInventoryPage||1)+(drivePage.dataset.drivePage==="next"?1:-1));window.applyDriveInventoryTable();return;}
  const nodeSubTab=e.target.closest("[data-node-subtab]");if(nodeSubTab){state.nodeSubsection=nodeSubTab.dataset.nodeSubtab;showClusterTopology(state.topologyClusterId,"nodes").catch(err=>toast(err.message,true));return;}
  const nodeHours=e.target.closest("[data-node-hours]");if(nodeHours){state.nodePerformanceHours=Number(nodeHours.dataset.nodeHours);showClusterTopology(state.topologyClusterId,"nodes").catch(err=>toast(err.message,true));return;}

  const performanceMetric=e.target.closest("[data-performance-metric]");if(performanceMetric){state.performanceMetric=performanceMetric.dataset.performanceMetric;showClusterTopology(state.topologyClusterId,"nodes").catch(err=>toast(err.message,true));return;}
  const action=e.target.closest("[data-action]")?.dataset.action;

  if(action==="select-all-performance-nodes"){state.performanceSelectedNodes=null;showClusterTopology(state.topologyClusterId,"nodes").catch(err=>toast(err.message,true));return;}
  if(action==="clear-performance-nodes"){state.performanceSelectedNodes=[];showClusterTopology(state.topologyClusterId,"nodes").catch(err=>toast(err.message,true));return;}
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
  if(action==="backup-page-prev"){state.backupOffset=Math.max(0,state.backupOffset-state.backupPageSize);renderMasterAdmin().catch(err=>toast(err.message,true));return;}
  if(action==="backup-page-next"){state.backupOffset+=state.backupPageSize;renderMasterAdmin().catch(err=>toast(err.message,true));return;}
  if(action==="review-backup-cleanup"){reviewBackupCleanup();return;}
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
  e.preventDefault();const form=e.target;if(!form.reportValidity())return;
  const values={node_interval_minutes:Number(form.elements.node_interval_minutes.value),telemetry_retention_days:Number(form.elements.telemetry_retention_days.value),daily_collection_time:form.elements.daily_collection_time.value};
  $("#modal-root").innerHTML='<div class="modal-backdrop config-confirm-backdrop"><section class="modal config-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="config-confirm-title"><div class="modal-header"><div><h2 id="config-confirm-title">Confirm configuration changes</h2><p>Enter your Master Admin password to save these settings.</p></div><button type="button" class="modal-close" data-action="close-modal" aria-label="Close">×</button></div><form id="master-settings-confirm-form"><label class="config-field"><span>Master Admin password</span><input class="form-control" type="password" name="current_password" autocomplete="current-password" required autofocus></label><p class="form-error" id="config-confirm-error" role="alert"></p><div class="form-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-small" type="submit">Confirm &amp; save</button></div></form></section></div>';
  const confirmForm=$("#master-settings-confirm-form");
  confirmForm.addEventListener("submit",async event=>{
    event.preventDefault();const button=confirmForm.querySelector("button[type=submit]");button.disabled=true;button.textContent="Saving…";
    try{
      await api("/api/master-admin/settings",{method:"PUT",body:JSON.stringify({...values,current_password:new FormData(confirmForm).get("current_password")})});
      $("#modal-root").innerHTML="";toast("Collection settings saved successfully.");await renderMasterAdmin();
    }catch(err){$("#config-confirm-error").textContent=err.message;button.disabled=false;button.textContent="Confirm & save";}
  });
  confirmForm.querySelector("input[name=current_password]").focus();
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
  if(e.target.matches("[data-network-node-filter]")){state.networkNodeFilter=e.target.value;state.networkSelectedInterface="all";showClusterTopology(state.topologyClusterId,"network").catch(err=>toast(err.message,true));return;}
  if(e.target.matches("[data-network-interface-filter]")){state.networkSelectedInterface=e.target.value;showClusterTopology(state.topologyClusterId,"network").catch(err=>toast(err.message,true));return;}
  if(e.target.matches("[data-drive-node-filter]")){state.driveNodeFilter=e.target.value;state.driveInventoryPage=1;showClusterTopology(state.topologyClusterId,"drives").catch(err=>toast(err.message,true));return;}
  if(e.target.matches("[data-drive-state-filter]")){state.driveFsFilter=e.target.value;state.driveInventoryPage=1;window.applyDriveInventoryTable();return;}
  if(e.target.id==="backup-page-size"){state.backupPageSize=Number(e.target.value)||10;state.backupOffset=0;renderMasterAdmin().catch(err=>toast(err.message,true));return;}
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
  if(e.target.matches("[data-cluster-hist-date]")){state.clusterHistogramDate=e.target.value||null;showCluster(state.snapshotClusterId,state.snapshotRange.days,state.snapshotRange.startDate,state.snapshotRange.endDate,"objects").catch(err=>toast(err.message,true));return;}
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
$("#content").addEventListener("change",e=>{if(e.target.matches("[data-performance-node]")){const checked=$$("[data-performance-node]:checked",$("#content")).map(el=>el.value);state.performanceSelectedNodes=checked;showClusterTopology(state.topologyClusterId,"nodes").catch(err=>toast(err.message,true));}});
$("#content").addEventListener("input",e=>{
  if(e.target.matches("[data-drive-search]")){state.driveInventoryPage=1;window.applyDriveInventoryTable();return;}
  if(e.target.matches("[data-drive-page-size]")){state.driveInventoryPage=1;window.applyDriveInventoryTable();return;}
  if(e.target.id==="bucket-filter"){const q=e.target.value.toLowerCase();$("tbody tr",$("#content")).forEach(row=>row.classList.toggle("hidden",!row.textContent.toLowerCase().includes(q)));return;}
  if(e.target.matches("[data-bucket-filter-search]")){
    const q=e.target.value.trim().toLowerCase(),group=e.target.closest("[data-bucket-filter-group]");
    group?.querySelectorAll(".bucket-usage-filter-option").forEach(option=>option.classList.toggle("hidden",!option.textContent.toLowerCase().includes(q)));
  }
});
(async()=>{try{const d=await api("/api/auth/me");showApp(d.user);await setView("overview");}catch{showLogin();}})();

document.addEventListener("toggle",function(event){const d=event.target;if(!d.matches(".time-range-dropdown")||!d.open)return;const p=d.querySelector(".time-range-popover");if(!p)return;d.classList.toggle("popover-align-right",p.getBoundingClientRect().right>window.innerWidth-8);},true);