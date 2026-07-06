from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .cluster_config import ClusterConfigError, ClusterDefinition, get_enabled_clusters, resolve_clusters
from .config import settings
from .db import SessionLocal
from .inventory import (
    collect_inventory_for_cluster,
    mark_scan_failed,
    mark_scan_started,
    mark_scan_success,
    save_inventory,
    sync_clusters,
)
from .k8s_client import get_k8s_clients
from .models import Container
from .registry import compare_tags, get_latest_tag
from .services.cluster_status import build_cluster_status_views
from .trivy import collect_vulnerabilities_for_cluster

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

_refresh_lock = asyncio.Lock()

MAX_LOGGED_ERROR_LENGTH = 500


def _sanitize_error(error: BaseException) -> str:
    """Return a short, log-safe representation of an exception.

    Kubernetes client exceptions may embed request URLs but never kubeconfig
    credentials, tokens, or certificate data (those live only in the client
    Configuration object, which is never included in exception messages).
    """
    message = str(error).strip() or error.__class__.__name__
    message = " ".join(message.split())
    if len(message) > MAX_LOGGED_ERROR_LENGTH:
        message = message[:MAX_LOGGED_ERROR_LENGTH].rstrip() + "..."
    return message


async def refresh_cluster(cluster: ClusterDefinition) -> None:
    logger.info("[%s] Starting inventory scan", cluster.id)

    db = SessionLocal()
    try:
        mark_scan_started(db, cluster.id)
        db.commit()
    finally:
        db.close()

    try:
        clients = get_k8s_clients(cluster, settings.KUBECONFIG_PATH or None)
        workloads = collect_inventory_for_cluster(cluster, clients)
    except Exception as e:
        sanitized = _sanitize_error(e)
        logger.error("[%s] Kubernetes API unavailable: %s", cluster.id, sanitized)
        db = SessionLocal()
        try:
            mark_scan_failed(db, cluster.id, sanitized)
            db.commit()
        finally:
            db.close()
        return

    db = SessionLocal()
    try:
        save_inventory(db, cluster.id, workloads)
        collect_vulnerabilities_for_cluster(cluster.id, clients, db)
        mark_scan_success(db, cluster.id)
        db.commit()
        logger.info("[%s] Inventory scan completed", cluster.id)
    except Exception as e:
        db.rollback()
        sanitized = _sanitize_error(e)
        logger.error("[%s] Failed to persist inventory: %s", cluster.id, sanitized)
        db2 = SessionLocal()
        try:
            mark_scan_failed(db2, cluster.id, sanitized)
            db2.commit()
        finally:
            db2.close()
    finally:
        db.close()


async def update_freshness() -> None:
    """Refresh registry freshness info, making at most one registry lookup
    per unique image repository per refresh cycle."""
    db = SessionLocal()
    try:
        containers = db.query(Container).all()
        repo_latest_tag: dict[str, str | None] = {}

        for c in containers:
            if c.image_tag == "latest" or "@sha256" in c.image_full:
                c.freshness_status = "unknown"
                c.freshness_reason = "latest tag or digest used"
                continue

            if c.image_repository not in repo_latest_tag:
                repo_latest_tag[c.image_repository] = await get_latest_tag(c.image_repository)
            latest = repo_latest_tag[c.image_repository]

            if latest:
                c.latest_tag = latest
                c.freshness_status = compare_tags(c.image_tag, latest)
                c.freshness_reason = f"Latest semver tag found: {latest}"
                c.checked_at = datetime.utcnow()
            else:
                c.freshness_status = "error"
                c.freshness_reason = "Could not fetch tags from registry"

        db.commit()
    except Exception as e:
        logger.error("Failed to update freshness: %s", _sanitize_error(e))
        db.rollback()
    finally:
        db.close()


async def _do_refresh_all_clusters() -> dict:
    try:
        clusters = resolve_clusters(settings)
    except ClusterConfigError as e:
        logger.error("Cluster configuration error: %s", e)
        return {"status": "error", "detail": str(e)}

    enabled = get_enabled_clusters(clusters)

    db = SessionLocal()
    try:
        sync_clusters(db, clusters)
        db.commit()
    finally:
        db.close()

    for cluster in enabled:
        try:
            await refresh_cluster(cluster)
        except Exception as e:
            # Isolation boundary: one cluster's unexpected failure must never
            # stop the others from being scanned.
            logger.error("[%s] Unexpected error during scan: %s", cluster.id, _sanitize_error(e))

    await update_freshness()

    db = SessionLocal()
    try:
        views = build_cluster_status_views(db, settings.CLUSTER_STALE_AFTER_SECONDS)
    finally:
        db.close()

    healthy = sum(1 for v in views if v.status == "healthy")
    stale = sum(1 for v in views if v.status in ("stale", "unreachable"))
    total_workloads = sum(v.workload_count for v in views)
    total_images = sum(v.image_count for v in views)

    logger.info(
        "Multi-cluster refresh completed:\n"
        "- %d configured clusters\n"
        "- %d healthy\n"
        "- %d stale\n"
        "- %d workloads\n"
        "- %d container images",
        len(enabled),
        healthy,
        stale,
        total_workloads,
        total_images,
    )
    return {"status": "completed", "clusters": len(enabled)}


async def refresh_all_clusters() -> dict:
    if _refresh_lock.locked():
        logger.info("Refresh already in progress; ignoring new request")
        return {"status": "already_running"}
    async with _refresh_lock:
        return await _do_refresh_all_clusters()


def start_background_tasks() -> None:
    scheduler.add_job(
        refresh_all_clusters,
        "interval",
        seconds=settings.SCAN_INTERVAL_SECONDS,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Background tasks started with interval %ss", settings.SCAN_INTERVAL_SECONDS)
