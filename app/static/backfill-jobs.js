(() => {
  "use strict";
  const $=(selector,root=document)=>root.querySelector(selector);
  const esc=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const api=async(path,options={})=>{
    const response=await fetch(path,{credentials:"same-origin",headers:{"Content-Type":"application/json"},...options});
    const body=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(body.detail||("Request failed: "+response.status));
    return body;
  };
  const today=new Date(),iso=d=>{const x=new Date(d);return [x.getFullYear(),String(x.getMonth()+1).padStart(2,"0"),String(x.getDate()).padStart(2,"0")].join("-");};
  const startDefault=new Date(today);startDefault.setDate(startDefault.getDate()-59);
  const statusLabel=s=>({queued:"Queued",running:"Running",paused:"Paused",completed:"Completed",failed:"Failed",cancelled:"Cancelled"}[s]||String(s||"Unknown"));
  const statusClass=s=>["queued","running","paused","completed","failed","cancelled"].includes(s)?s:"unknown";
  async function renderBackfillJobs(){
    const host=$("#master-config-panel")||$("#content");if(!host)return;
    $("#page-breadcrumb").textContent="MASTER CONFIGURATION";
    host.innerHTML='<div class="page-heading"><div><h1>Historical Backfill</h1><p>Recover daily capacity, bucket and storage-topology snapshots from Prometheus retention.</p></div><button class="secondary-button" id="bf-refresh">↻ Refresh jobs</button></div>'+
      '<section class="bf-create-section"><div class="bf-section-heading"><div><span class="config-kicker">01 / HISTORICAL RECOVERY</span><h2>Create a backfill job</h2><p>Select a configured cluster and the historical date range to recover.</p></div><span class="panel-tag">MAXIMUM 60 DAYS</span></div>'+
      '<form id="bf-form" class="panel bf-create-form"><div class="bf-form-fields"><label class="config-field bf-cluster-field"><span>MinIO cluster</span><select id="bf-cluster" class="form-control" required><option value="">Loading configured clusters…</option></select><small class="config-help">Only clusters on enabled Prometheus connections are available.</small></label>'+
      '<div class="bf-date-fields"><label class="config-field"><span>Start date</span><input id="bf-start" class="form-control" type="date" required value="'+iso(startDefault)+'"></label><label class="config-field"><span>End date</span><input id="bf-end" class="form-control" type="date" required value="'+iso(today)+'"></label></div>'+
      '<div class="bf-range-presets"><span>Quick range</span><button type="button" data-bf-range="7">7 days</button><button type="button" data-bf-range="30">30 days</button><button type="button" data-bf-range="60" class="active">60 days</button></div></div>'+
      '<div class="bf-create-footer"><p>Historical availability depends on Prometheus retention. Missing samples are recorded as partial or failed dates; existing snapshots are updated idempotently.</p><button class="primary-button" type="submit">Start backfill <span>→</span></button></div></form></section>'+
      '<section class="bf-jobs-section"><div class="bf-section-heading"><div><span class="config-kicker">02 / EXECUTION MONITORING</span><h2>Backfill jobs</h2><p>Track processing progress and inspect date-level outcomes retained in SQLite.</p></div></div>'+
      '<div id="bf-summary" class="bf-summary-grid"><div class="bf-summary-card"><span>Total jobs</span><strong>—</strong></div><div class="bf-summary-card"><span>Completed</span><strong>—</strong></div><div class="bf-summary-card"><span>In progress</span><strong>—</strong></div><div class="bf-summary-card"><span>Needs attention</span><strong>—</strong></div></div>'+
      '<div id="bf-list" class="bf-job-list"><div class="loading-state">Loading jobs…</div></div></section>';
    $("#bf-refresh").addEventListener("click",loadJobs);
    $("#bf-form").addEventListener("submit",createJob);
    host.querySelectorAll("[data-bf-range]").forEach(b=>b.addEventListener("click",()=>setRange(Number(b.dataset.bfRange))));
    await loadClusters();await loadJobs();
  }
  function setRange(days){
    const end=new Date(),start=new Date(end);start.setDate(start.getDate()-days+1);
    $("#bf-start").value=iso(start);$("#bf-end").value=iso(end);
    document.querySelectorAll("[data-bf-range]").forEach(b=>b.classList.toggle("active",Number(b.dataset.bfRange)===days));
  }
  async function loadClusters(){
    const select=$("#bf-cluster");if(!select)return;
    try{
      const data=await api("/api/master-admin/prometheus-connections"),options=[];
      (data.items||[]).filter(x=>x.enabled).forEach(endpoint=>(endpoint.clusters||[]).forEach(cluster=>options.push('<option value="'+esc(endpoint.location_id)+'|'+esc(cluster.cluster_id)+'">'+esc(cluster.cluster_name)+' · '+esc(endpoint.location_name)+'</option>')));
      select.innerHTML='<option value="">Select a configured cluster</option>'+options.join("");
      if(!options.length)select.insertAdjacentHTML("beforeend",'<option value="" disabled>No enabled clusters available</option>');
    }catch(err){select.innerHTML='<option value="">Unable to load configured clusters</option>';throw err;}
  }
  async function createJob(event){
    event.preventDefault();
    const [location_id,cluster_id]=($("#bf-cluster").value||"").split("|"),start_date=$("#bf-start").value,end_date=$("#bf-end").value;
    if(!location_id||!cluster_id){alert("Select a cluster first.");return;}
    if(!start_date||!end_date||start_date>end_date){alert("Choose a valid date range.");return;}
    const dayCount=Math.round((Date.parse(end_date+"T00:00:00")-Date.parse(start_date+"T00:00:00"))/86400000)+1;
    if(dayCount>60){alert("The maximum range is 60 calendar days.");return;}
    const button=event.currentTarget.querySelector("button[type=submit]");button.disabled=true;button.textContent="Queueing…";
    try{await api("/api/master-admin/backfill-jobs",{method:"POST",body:JSON.stringify({location_id,cluster_id,start_date,end_date})});await loadJobs();}
    catch(err){alert(err.message);}finally{button.disabled=false;button.innerHTML="Start backfill <span>→</span>";}
  }
  async function jobAction(id,action){
    try{await api("/api/master-admin/backfill-jobs/"+encodeURIComponent(id)+"/action",{method:"POST",body:JSON.stringify({action})});await loadJobs();}
    catch(err){alert(err.message);}
  }
  async function loadJobs(){
    const target=$("#bf-list");if(!target)return;
    try{
      const data=await api("/api/master-admin/backfill-jobs"),items=data.items||[];
      const completed=items.filter(j=>j.status==="completed").length,active=items.filter(j=>["queued","running"].includes(j.status)).length;
      const attention=items.filter(j=>["failed","paused"].includes(j.status)||(j.failed_days||0)>0).length;
      $("#bf-summary").innerHTML=[["Total jobs",items.length],["Completed",completed],["In progress",active],["Needs attention",attention]].map(([label,value])=>'<div class="bf-summary-card"><span>'+label+'</span><strong>'+value+'</strong></div>').join("");
      if(!items.length){target.innerHTML='<div class="panel bf-empty-state"><strong>No backfill jobs yet</strong><p>Create a job above to recover historical daily snapshots for a configured cluster.</p></div>';return;}
      target.innerHTML=items.map(j=>{
        const total=Number(j.total_days)||0,done=Number(j.completed_days)||0,progress=total?Math.min(100,Math.round(done*100/total)):0,actions=[];
        if(["queued","running"].includes(j.status))actions.push('<button class="secondary-button" data-bf-action="pause" data-bf-id="'+esc(j.job_id)+'">Pause</button>');
        if(["paused","failed"].includes(j.status))actions.push('<button class="secondary-button" data-bf-action="resume" data-bf-id="'+esc(j.job_id)+'">Resume</button>');
        if(j.status==="completed"&&Number(j.failed_days)>0)actions.push('<button class="secondary-button" data-bf-action="retry" data-bf-id="'+esc(j.job_id)+'">Retry failed dates</button>');
        if(["queued","running","paused","failed"].includes(j.status))actions.push('<button class="bf-cancel-action" data-bf-action="cancel" data-bf-id="'+esc(j.job_id)+'">Cancel</button>');
        return '<article class="panel bf-job-card"><div class="bf-job-top"><div><strong>'+esc(j.cluster_name)+'</strong><span>'+esc(j.location_name)+'</span></div><span class="bf-status '+statusClass(j.status)+'">'+esc(statusLabel(j.status))+'</span></div>'+
          '<div class="bf-job-dates">'+esc(j.start_date)+' <span>→</span> '+esc(j.end_date)+'</div><div class="bf-progress-heading"><span>Processing progress</span><strong>'+done+' / '+total+' dates · '+progress+'%</strong></div>'+
          '<div class="bf-progress-track" role="progressbar" aria-valuenow="'+progress+'" aria-valuemin="0" aria-valuemax="100" aria-label="Backfill progress"><span style="width:'+progress+'%"></span></div>'+
          '<div class="bf-outcomes"><span><i class="success"></i>'+Number(j.successful_days||0)+' successful</span><span><i class="partial"></i>'+Number(j.partial_days||0)+' partial</span><span><i class="failed"></i>'+Number(j.failed_days||0)+' failed</span></div>'+
          (actions.length?'<div class="bf-job-actions">'+actions.join("")+'</div>':'')+'</article>';
      }).join("");
      target.querySelectorAll("[data-bf-action]").forEach(b=>b.addEventListener("click",()=>jobAction(b.dataset.bfId,b.dataset.bfAction)));
    }catch(err){target.innerHTML='<div class="panel bf-empty-state"><strong>Unable to load backfill jobs</strong><p>'+esc(err.message)+'</p></div>';}
  }
  window.renderBackfillJobs=renderBackfillJobs;
})();