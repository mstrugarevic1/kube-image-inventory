from unittest.mock import MagicMock

from app.inventory import save_inventory
from app.models import Cluster
from app.trivy import collect_vulnerabilities_for_cluster

from conftest import make_workload


def _report(namespace="default", container="app", resource_name="api", resource_kind="Deployment"):
    return {
        "metadata": {
            "name": "report-1",
            "namespace": namespace,
            "labels": {
                "trivy-operator.container.name": container,
                "trivy-operator.resource.kind": resource_kind,
                "trivy-operator.resource.name": resource_name,
                "trivy-operator.resource.namespace": namespace,
            },
        },
        "report": {
            "summary": {
                "criticalCount": 3,
                "highCount": 5,
                "mediumCount": 1,
                "lowCount": 0,
                "unknownCount": 0,
            }
        },
    }


def _clients_with_reports(reports):
    clients = MagicMock()
    clients.custom_objects.list_cluster_custom_object.return_value = {"items": reports}
    return clients


def test_report_only_updates_container_in_matching_cluster(db_session):
    db_session.add_all([Cluster(id="kind-dev", name="Dev"), Cluster(id="kind-prod", name="Prod")])
    db_session.commit()

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", container_name="app")])
    save_inventory(db_session, "kind-prod", [make_workload("kind-prod", container_name="app")])
    db_session.commit()

    clients = _clients_with_reports([_report()])
    collect_vulnerabilities_for_cluster("kind-dev", clients, db_session)
    db_session.commit()

    from app.models import Workload

    dev_container = db_session.query(Workload).filter_by(cluster_id="kind-dev").one().containers[0]
    prod_container = db_session.query(Workload).filter_by(cluster_id="kind-prod").one().containers[0]

    assert dev_container.critical_cve == 3
    assert dev_container.high_cve == 5
    assert prod_container.critical_cve == 0
    assert prod_container.high_cve == 0


def test_missing_crds_do_not_raise(db_session):
    db_session.add(Cluster(id="kind-dev", name="Dev"))
    db_session.commit()
    save_inventory(db_session, "kind-dev", [make_workload("kind-dev")])
    db_session.commit()

    clients = MagicMock()
    clients.custom_objects.list_cluster_custom_object.side_effect = Exception("CRD not found")

    # Must not raise.
    collect_vulnerabilities_for_cluster("kind-dev", clients, db_session)

    from app.models import Workload

    container = db_session.query(Workload).filter_by(cluster_id="kind-dev").one().containers[0]
    assert container.critical_cve == 0
