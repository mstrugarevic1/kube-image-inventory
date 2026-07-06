from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Tuple

from sqlalchemy.orm import Session

from .cluster_config import ClusterDefinition
from .config import settings
from .k8s_client import KubernetesClients
from .models import Cluster, Container, Workload
from .schemas import ContainerCreate, WorkloadCreate

logger = logging.getLogger(__name__)


def parse_image(image_full: str) -> Tuple[str, str, str]:
    if "@sha256:" in image_full:
        repo, digest = image_full.split("@", 1)
        return repo, digest, image_full

    if ":" in image_full:
        parts = image_full.rsplit(":", 1)
        repo = parts[0]
        tag = parts[1]
        if "/" not in tag:
            return repo, tag, image_full

    return image_full, "latest", f"{image_full}:latest"


def collect_inventory_for_cluster(
    cluster: ClusterDefinition,
    clients: KubernetesClients,
) -> List[WorkloadCreate]:
    """Collect all supported workload types from one cluster into memory.

    Raises on any Kubernetes API failure - the caller is responsible for
    isolating that failure to this cluster and continuing with others.
    """
    timeout = settings.KUBE_REQUEST_TIMEOUT_SECONDS
    workloads: List[WorkloadCreate] = []

    deps = clients.apps_v1.list_deployment_for_all_namespaces(_request_timeout=timeout)
    for item in deps.items:
        workloads.append(_normalize_workload(item, "Deployment", cluster.id))

    stss = clients.apps_v1.list_stateful_set_for_all_namespaces(_request_timeout=timeout)
    for item in stss.items:
        workloads.append(_normalize_workload(item, "StatefulSet", cluster.id))

    dss = clients.apps_v1.list_daemon_set_for_all_namespaces(_request_timeout=timeout)
    for item in dss.items:
        workloads.append(_normalize_workload(item, "DaemonSet", cluster.id))

    cjs = clients.batch_v1.list_cron_job_for_all_namespaces(_request_timeout=timeout)
    for item in cjs.items:
        workloads.append(_normalize_workload(item, "CronJob", cluster.id))

    return workloads


def _normalize_workload(item, kind: str, cluster_id: str) -> WorkloadCreate:
    namespace = item.metadata.namespace
    name = item.metadata.name

    desired = 0
    available = 0

    if kind == "Deployment":
        desired = item.spec.replicas or 0
        available = item.status.available_replicas or 0
        pod_template = item.spec.template
    elif kind == "StatefulSet":
        desired = item.spec.replicas or 0
        available = item.status.ready_replicas or 0
        pod_template = item.spec.template
    elif kind == "DaemonSet":
        desired = item.status.desired_number_scheduled or 0
        available = item.status.number_ready or 0
        pod_template = item.spec.template
    elif kind == "CronJob":
        desired = 1
        available = 1 if item.status.active else 0
        pod_template = item.spec.job_template.spec.template
    else:
        pod_template = None

    containers = []
    if pod_template:
        for c in pod_template.spec.containers:
            repo, tag, full = parse_image(c.image)
            containers.append(
                ContainerCreate(
                    name=c.name,
                    image_full=c.image,
                    image_repository=repo,
                    image_tag=tag,
                    current_tag=tag,
                )
            )

    return WorkloadCreate(
        cluster_id=cluster_id,
        namespace=namespace,
        name=name,
        kind=kind,
        desired_replicas=desired,
        available_replicas=available,
        labels=item.metadata.labels or {},
        annotations=item.metadata.annotations or {},
        containers=containers,
    )


def sync_clusters(db: Session, clusters: List[ClusterDefinition]) -> None:
    """Upsert Cluster rows for the configured clusters, preserving scan status."""
    for cluster in clusters:
        row = db.query(Cluster).filter_by(id=cluster.id).first()
        if row is None:
            row = Cluster(id=cluster.id)
            db.add(row)
        row.name = cluster.name
        row.context_name = cluster.context
        row.environment = cluster.environment
        row.enabled = cluster.enabled


def mark_scan_started(db: Session, cluster_id: str) -> None:
    row = db.query(Cluster).filter_by(id=cluster_id).first()
    if row is not None:
        row.last_scan_started_at = datetime.utcnow()


def mark_scan_success(db: Session, cluster_id: str) -> None:
    now = datetime.utcnow()
    row = db.query(Cluster).filter_by(id=cluster_id).first()
    if row is not None:
        row.last_scan_completed_at = now
        row.last_successful_scan_at = now
        row.last_error = None


def mark_scan_failed(db: Session, cluster_id: str, error: str) -> None:
    row = db.query(Cluster).filter_by(id=cluster_id).first()
    if row is not None:
        row.last_scan_completed_at = datetime.utcnow()
        row.last_error = error


def save_inventory(db: Session, cluster_id: str, workloads: List[WorkloadCreate]) -> None:
    """Upsert workloads/containers for one cluster and delete stale ones.

    Only ever queries and mutates rows scoped to cluster_id - workloads belonging
    to other clusters are never read or modified. Does not commit or roll back;
    the caller controls the transaction so this can be combined atomically with
    scan-status bookkeeping.
    """
    seen_keys = set()

    for w_data in workloads:
        seen_keys.add((w_data.namespace, w_data.name, w_data.kind))

        existing_w = db.query(Workload).filter_by(
            cluster_id=cluster_id,
            namespace=w_data.namespace,
            name=w_data.name,
            kind=w_data.kind,
        ).first()

        if existing_w:
            existing_w.desired_replicas = w_data.desired_replicas
            existing_w.available_replicas = w_data.available_replicas
            existing_w.labels = w_data.labels
            existing_w.annotations = w_data.annotations
            existing_w.last_observed = datetime.utcnow()

            existing_containers = {c.name: c for c in existing_w.containers}
            new_container_names = {c.name for c in w_data.containers}

            for c_name in list(existing_containers.keys()):
                if c_name not in new_container_names:
                    db.delete(existing_containers[c_name])

            for c_data in w_data.containers:
                if c_data.name in existing_containers:
                    c = existing_containers[c_data.name]
                    if c.image_full != c_data.image_full:
                        c.image_full = c_data.image_full
                        c.image_repository = c_data.image_repository
                        c.image_tag = c_data.image_tag
                        c.current_tag = c_data.image_tag
                        c.freshness_status = "unknown"
                else:
                    new_c = Container(**c_data.model_dump())
                    new_c.workload = existing_w
                    db.add(new_c)
        else:
            new_w = Workload(
                cluster_id=cluster_id,
                namespace=w_data.namespace,
                name=w_data.name,
                kind=w_data.kind,
                desired_replicas=w_data.desired_replicas,
                available_replicas=w_data.available_replicas,
                labels=w_data.labels,
                annotations=w_data.annotations,
            )
            db.add(new_w)
            db.flush()
            for c_data in w_data.containers:
                new_c = Container(**c_data.model_dump())
                new_c.workload_id = new_w.id
                db.add(new_c)

    stale_workloads = db.query(Workload).filter_by(cluster_id=cluster_id).all()
    for w in stale_workloads:
        if (w.namespace, w.name, w.kind) not in seen_keys:
            db.delete(w)
