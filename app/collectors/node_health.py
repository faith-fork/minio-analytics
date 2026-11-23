from __future__ import annotations
import json, logging, uuid
from datetime import datetime, timezone
from app.collectors.topology_collector import collect_topology_snapshot
from app.config.loader import LocationConfig
from app.database.database import initialize_database, transaction
from app.database.persistence import sync_configuration

logger=logging.getLogger(__name__)

def collect_node_health(locations:list[LocationConfig],snapshot_ts:datetime|None=None)->list[dict]:
    """Persist timestamped node/drive/filesystem samples without overwriting daily topology."""
    target=snapshot_ts or datetime.now(timezone.utc)
    if target.tzinfo is None or target.utcoffset() is None:raise ValueError("snapshot_ts must be timezone-aware")
    initialize_database();sync_configuration(locations);results=[]
    for location in locations:
        for cluster in location.clusters:
            run_id=str(uuid.uuid4())
            try:
                snap=collect_topology_snapshot(location,cluster,target,include_pool_health=False)
                snapshot_text=snap.snapshot_ts.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
                collected_text=snap.collected_at.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
                run_status = "partial" if snap.family_errors else "success"
                with transaction() as c:
                    c.execute("""INSERT INTO node_health_runs
                    (run_id,cluster_id,snapshot_ts,collected_at,family_errors_json,node_count,drive_count,status)
                    VALUES(?,?,?,?,?,?,?,?)""",(run_id,cluster.id,snapshot_text,collected_text,json.dumps(snap.family_errors,sort_keys=True),len(snap.nodes),len(snap.drives),run_status))
                    for n in snap.nodes:
                        c.execute("""INSERT INTO node_health_metrics(run_id,cluster_id,node_name,node_exporter_instance,minio_instance,node_exporter_up,minio_scrape_up,cpu_utilization_pct,memory_total_bytes,memory_available_bytes,memory_used_bytes,load1,drives_online,drives_offline)
                        VALUES(:run_id,:cluster_id,:node_name,:node_exporter_instance,:minio_instance,:node_exporter_up,:minio_scrape_up,:cpu_utilization_pct,:memory_total_bytes,:memory_available_bytes,:memory_used_bytes,:load1,:drives_online,:drives_offline)""",{"run_id":run_id,"cluster_id":cluster.id,**n})
                    for d in snap.drives:
                        c.execute("""INSERT INTO drive_health_metrics(run_id,cluster_id,node_name,server,drive_path,mountpoint,total_bytes,used_bytes,free_bytes,availability_errors,io_errors,timeout_errors,filesystem_total_bytes,filesystem_available_bytes,filesystem_free_bytes,filesystem_readonly,filesystem_used_bytes,filesystem_used_pct)
                        VALUES(:run_id,:cluster_id,:node_name,:server,:drive_path,:mountpoint,:total_bytes,:used_bytes,:free_bytes,:availability_errors,:io_errors,:timeout_errors,:filesystem_total_bytes,:filesystem_available_bytes,:filesystem_free_bytes,:filesystem_readonly,:filesystem_used_bytes,:filesystem_used_pct)""",{"run_id":run_id,"cluster_id":cluster.id,**d})
                results.append({"cluster_id":cluster.id,"run_id":run_id,"nodes":len(snap.nodes),"drives":len(snap.drives),"family_errors":snap.family_errors,"status":run_status})
            except Exception as exc:
                logger.exception("Node health collection failed for %s",cluster.id)
                failed_snapshot_text = target.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
                failed_collected_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
                try:
                    with transaction() as c:
                        c.execute("""INSERT INTO node_health_runs
                        (run_id,cluster_id,snapshot_ts,collected_at,family_errors_json,node_count,drive_count,status,error_text)
                        VALUES(?,?,?,?, '{}',0,0,'failed',?)""",
                        (run_id,cluster.id,failed_snapshot_text,failed_collected_text,
                         "Collection failed; inspect scheduler logs for details."))
                except Exception:
                    logger.exception("Unable to persist failed node-health outcome for %s",cluster.id)
                results.append({"cluster_id":cluster.id,"run_id":run_id,"error":str(exc),"status":"failed"})
    return results
