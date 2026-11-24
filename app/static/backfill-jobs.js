(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const api = async (path, options={}) => {
    const response = await fetch(path,{credentials:"same-origin",headers:{"Content-Type":"application/json"},...options});
    const body = await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(body.detail || ("Request failed: "+response.status));
    return body;
  };
  const today = new Date();
  const iso = d => { const x=new Date(d); return [x.getFullYear(),String(x.getMonth()+1).padStart(2,"0"),String(x.getDate()).padStart(2,"0")].join("-"); };
  const startDefault = new Date(today); startDefault.setDate(startDefault.getDate()-59);
  async function renderBackfillJobs(){
    const host=$("#content"); if(!host)return;
    $("#page-breadcrumb").textContent="HISTORICAL BACKFILL";
    host.innerHTML='<div class="page-heading"><div><h1>Historical backfill</h1><p>Backfill daily capacity, bucket and topology snapshots from Prometheus retention.</p></div><button class="secondary-button" id="bf-refresh">↻ Refresh</button></div><section class="panel"><div class="panel-header"><div><h2>Start a backfill</h2><p>Choose an enabled cluster and a date range of up to 60 calendar days. Each date is processed as a durable scheduler checkpoint.</p></div></div><form id="bf-form" class="settings-form"><div class="form-grid"><label>Cluster<select id="bf-cluster" required><option value="">Loading configured clusters…</option></select></label><label>Start date<input id="bf-start" type="date" required value="'+iso(startDefault)+'"></label><label>End date<input id="bf-end" type="date" required value="'+iso(today)+'"></label></div><div class="form-actions"><button class="primary-button" type="submit">Start backfill</button></div><p class="form-hint">Historical data availability depends on the Prometheus retention period. Missing samples are recorded as partial or failed dates; existing snapshots are updated idempotently.</p></form></section><section class="panel"><div class="panel-header"><div><h2>Backfill jobs</h2><p>Progress and date-level outcomes are retained in SQLite.</p></div></div><div id="bf-list" class="table-scroll"><div class="loading-state">Loading jobs…</div></div></section>';
    $("#bf-refresh").addEventListener("click",loadJobs);
    $("#bf-form").addEventListener("submit",createJob);
    await loadClusters(); await loadJobs();
  }
  async function loadClusters(){
    const select=$("#bf-cluster"); if(!select)return;
    try{
      const data=await api("/api/master-admin/prometheus-connections");
      const options=[];
      (data.items||[]).filter(x=>x.enabled).forEach(endpoint=>(endpoint.clusters||[]).forEach(cluster=>{
        options.push('<option value="'+esc(endpoint.location_id)+'|'+esc(cluster.cluster_id)+'">'+esc(cluster.cluster_name)+' · '+esc(endpoint.location_name)+'</option>');
      }));
      select.innerHTML='<option value="">Select a configured cluster</option>'+options.join("");
    }catch(err){select.innerHTML='<option value="">Unable to load configured clusters</option>';throw err;}
  }
  async function createJob(event){
    event.preventDefault();
    const [location_id,cluster_id]=($("#bf-cluster").value||"").split("|");
    const start_date=$("#bf-start").value,end_date=$("#bf-end").value;
    if(!location_id||!cluster_id){alert("Select a cluster first.");return;}
    if(!start_date||!end_date||start_date>end_date){alert("Choose a valid date range.");return;}
    if((Date.parse(end_date)-Date.parse(start_date))/86400000+1>60){alert("The maximum range is 60 calendar days.");return;}
    const button=event.currentTarget.querySelector("button[type=submit]");button.disabled=true;
    try{await api("/api/master-admin/backfill-jobs",{method:"POST",body:JSON.stringify({location_id,cluster_id,start_date,end_date})});await loadJobs();}
    catch(err){alert(err.message);}finally{button.disabled=false;}
  }
  async function jobAction(id,action){
    try{await api("/api/master-admin/backfill-jobs/"+encodeURIComponent(id)+"/action",{method:"POST",body:JSON.stringify({action})});await loadJobs();}
    catch(err){alert(err.message);}
  }
  async function loadJobs(){
    const target=$("#bf-list");if(!target)return;
    try{
      const data=await api("/api/master-admin/backfill-jobs");
      if(!data.items.length){target.innerHTML='<p class="empty-state">No historical backfill jobs have been created.</p>';return;}
      target.innerHTML='<table><thead><tr><th>Cluster</th><th>Date range</th><th>Progress</th><th>Outcome</th><th>Status</th><th>Actions</th></tr></thead><tbody>'+
      data.items.map(j=>{
        const pct=j.total_days?Math.round(j.completed_days*100/j.total_days):0;
        const actions=[];
        if(["queued","running"].includes(j.status))actions.push('<button class="table-link" data-bf-action="pause" data-bf-id="'+esc(j.job_id)+'">Pause</button>');
        if(["paused","failed"].includes(j.status))actions.push('<button class="table-link" data-bf-action="resume" data-bf-id="'+esc(j.job_id)+'">Resume</button>');
        if(j.status==="completed"&&j.failed_days>0)actions.push('<button class="table-link" data-bf-action="retry" data-bf-id="'+esc(j.job_id)+'">Retry failed dates</button>');
        if(["queued","running","paused","failed"].includes(j.status))actions.push('<button class="table-link" data-bf-action="cancel" data-bf-id="'+esc(j.job_id)+'">Cancel</button>');
        return '<tr><td><strong>'+esc(j.cluster_name)+'</strong><br><small>'+esc(j.location_name)+'</small></td><td>'+esc(j.start_date)+' → '+esc(j.end_date)+'</td><td>'+j.completed_days+'/'+j.total_days+' ('+pct+'%)<div class="progress-track"><span style="width:'+pct+'%"></span></div></td><td>'+j.successful_days+' success · '+j.partial_days+' partial · '+j.failed_days+' failed</td><td>'+esc(j.status)+'</td><td>'+actions.join(" · ")+'</td></tr>';
      }).join("")+'</tbody></table>';
      target.querySelectorAll("[data-bf-action]").forEach(button=>button.addEventListener("click",()=>jobAction(button.dataset.bfId,button.dataset.bfAction)));
    }catch(err){target.innerHTML='<p class="form-error">'+esc(err.message)+'</p>';}
  }
  window.renderBackfillJobs=renderBackfillJobs;
})();