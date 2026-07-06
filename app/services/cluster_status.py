from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Cluster, Container, Workload

MAX_ERROR_LENGTH = 200


def derive_status(cluster: Cluster, stale_after_seconds: int, now: Optional[datetime] = None) -> str:
    """Derive a cluster's display status from its scan history.

    This is the single place cluster status is computed, so the dashboard and
    any future API surface stay consistent.
    """
    now = now or datetime.utcnow()

    if cluster.last_scan_started_at is None:
        return "unknown"

    if cluster.last_successful_scan_at is None:
        return "unreachable" if cluster.last_error else "unknown"

    if cluster.last_error:
        return "stale"

    age_seconds = (now - cluster.last_successful_scan_at).total_seconds()
    if age_seconds > stale_after_seconds:
        return "stale"

    return "healthy"


@dataclass
class ClusterStatusView:
    cluster_id: str
    name: str
    environment: str
    status: str
    last_successful_scan_at: Optional[datetime]
    last_error: Optional[str]
    workload_count: int
    image_count: int


def _shorten_error(error: Optional[str]) -> Optional[str]:
    if not error:
        return None
    if len(error) <= MAX_ERROR_LENGTH:
        return error
    return error[:MAX_ERROR_LENGTH].rstrip() + "..."


def build_cluster_status_views(db: Session, stale_after_seconds: int) -> list[ClusterStatusView]:
    """Build one status row per configured cluster, ordered by name."""
    views: list[ClusterStatusView] = []
    for cluster in db.query(Cluster).order_by(Cluster.name).all():
        workload_count = db.query(Workload).filter_by(cluster_id=cluster.id).count()
        image_count = (
            db.query(Container)
            .join(Workload, Container.workload_id == Workload.id)
            .filter(Workload.cluster_id == cluster.id)
            .count()
        )
        views.append(
            ClusterStatusView(
                cluster_id=cluster.id,
                name=cluster.name,
                environment=cluster.environment,
                status=derive_status(cluster, stale_after_seconds),
                last_successful_scan_at=cluster.last_successful_scan_at,
                last_error=_shorten_error(cluster.last_error),
                workload_count=workload_count,
                image_count=image_count,
            )
        )
    return views
