from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .k8s_client import KubernetesClients
from .models import Container, Workload

logger = logging.getLogger(__name__)


def collect_vulnerabilities_for_cluster(
    cluster_id: str,
    clients: KubernetesClients,
    db: Session,
) -> None:
    """Match Trivy Operator VulnerabilityReports to containers of one cluster.

    Trivy Operator is optional: if its CRDs are missing or inaccessible this
    logs an informational message and returns without raising, so a missing
    Trivy install never fails the surrounding inventory scan transaction.

    Every lookup is scoped to cluster_id, so a report can never update a
    workload belonging to a different cluster.
    """
    try:
        reports = clients.custom_objects.list_cluster_custom_object(
            group="aquasecurity.github.io",
            version="v1alpha1",
            plural="vulnerabilityreports",
        )
    except Exception as e:
        logger.info(
            "[%s] Trivy Operator VulnerabilityReports not found or not accessible: %s",
            cluster_id,
            e,
        )
        return

    for report in reports.get("items", []):
        labels = report["metadata"].get("labels", {})
        namespace = report["metadata"].get("namespace")

        # Trivy Operator labels:
        # trivy-operator.container.name
        # trivy-operator.resource.kind
        # trivy-operator.resource.name
        # trivy-operator.resource.namespace

        container_name = labels.get("trivy-operator.container.name")
        resource_kind = labels.get("trivy-operator.resource.kind")
        resource_name = labels.get("trivy-operator.resource.name")

        if not (container_name and resource_kind and resource_name):
            continue

        # Improve matching for ReplicaSets/Pods by stripping the hash suffix
        # to match with parent Deployments/StatefulSets in our DB
        match_name = resource_name
        match_kind = resource_kind

        if resource_kind == "ReplicaSet" and "-" in resource_name:
            match_name = resource_name.rsplit("-", 1)[0]
            match_kind = "Deployment"
        elif resource_kind == "Pod" and "-" in resource_name:
            parts = resource_name.rsplit("-", 2)
            if len(parts) >= 2:
                match_name = parts[0]

        summary = report.get("report", {}).get("summary", {})

        container = (
            db.query(Container)
            .join(Container.workload)
            .filter(
                Workload.cluster_id == cluster_id,
                Container.name == container_name,
                Workload.namespace == namespace,
            )
            .filter(
                (
                    (Workload.name == resource_name)
                    & (Workload.kind == resource_kind)
                )
                | ((Workload.name == match_name) & (Workload.kind == match_kind))
            )
            .first()
        )

        if container:
            container.critical_cve = summary.get("criticalCount", 0)
            container.high_cve = summary.get("highCount", 0)
            container.medium_cve = summary.get("mediumCount", 0)
            container.low_cve = summary.get("lowCount", 0)
            container.unknown_cve = summary.get("unknownCount", 0)
            container.vulnerability_report_name = report["metadata"]["name"]
