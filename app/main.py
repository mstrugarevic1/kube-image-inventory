from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, text
import logging

from .cluster_config import resolve_clusters
from .config import settings
from .db import SessionLocal, init_db, get_db
from .models import Cluster, Container, Workload
from .inventory import sync_clusters
from .services.cluster_status import build_cluster_status_views
from .services.image_drift import get_image_drift
from .background import start_background_tasks, refresh_all_clusters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Kubernetes Image Inventory")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
async def startup_event():
    init_db()

    # Fail fast with a clear message if the configured access mode cannot be
    # resolved (missing/invalid cluster config, duplicate ids, etc).
    clusters = resolve_clusters(settings)

    db = SessionLocal()
    try:
        sync_clusters(db, clusters)
        db.commit()
    finally:
        db.close()

    start_background_tasks()
    await refresh_all_clusters()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, cluster: str = "all", db: Session = Depends(get_db)):
    clusters = db.query(Cluster).order_by(Cluster.name).all()

    workload_query = db.query(Workload)
    if cluster != "all":
        workload_query = workload_query.filter(Workload.cluster_id == cluster)
    workloads = workload_query.order_by(Workload.namespace, Workload.name).all()

    container_query = db.query(Container).join(Workload, Container.workload_id == Workload.id)
    if cluster != "all":
        container_query = container_query.filter(Workload.cluster_id == cluster)

    total_images = container_query.count()
    outdated_images = container_query.filter(Container.freshness_status == "outdated").count()
    unknown_freshness = container_query.filter(Container.freshness_status == "unknown").count()

    vuln_summary = container_query.with_entities(
        func.sum(Container.critical_cve),
        func.sum(Container.high_cve),
    ).first()
    critical_cves = (vuln_summary[0] or 0) if vuln_summary else 0
    high_cves = (vuln_summary[1] or 0) if vuln_summary else 0

    last_scan_query = workload_query
    last_scan = last_scan_query.order_by(Workload.last_observed.desc()).first()
    last_scan_time = last_scan.last_observed if last_scan else None

    cluster_ids = None if cluster == "all" else [cluster]
    image_drift = get_image_drift(db, cluster_ids=cluster_ids)
    drift_cluster_ids = clusters if cluster == "all" else [c for c in clusters if c.id == cluster]

    return templates.TemplateResponse(request, "index.html", {
        "clusters": clusters,
        "selected_cluster": cluster,
        "workloads": workloads,
        "show_cluster_column": cluster == "all",
        "cluster_status_rows": build_cluster_status_views(db, settings.CLUSTER_STALE_AFTER_SECONDS),
        "image_drift": image_drift,
        "drift_clusters": drift_cluster_ids,
        "summary": {
            "total_workloads": len(workloads),
            "total_images": total_images,
            "outdated_images": outdated_images,
            "unknown_freshness": unknown_freshness,
            "critical_cves": critical_cves,
            "high_cves": high_cves,
            "last_scan_time": last_scan_time,
        },
    })


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        cluster_count = db.query(Cluster).count()
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Not ready")

    return {"status": "ready", "configured_clusters": cluster_count}


@app.post("/refresh")
async def manual_refresh(request: Request, cluster: str = "all"):
    result = await refresh_all_clusters()
    if result.get("status") == "already_running":
        return RedirectResponse(url=f"/?cluster={cluster}&refresh=busy", status_code=303)
    return RedirectResponse(url=f"/?cluster={cluster}", status_code=303)
