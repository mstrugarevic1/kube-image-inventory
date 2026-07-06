from types import SimpleNamespace
from unittest.mock import MagicMock

from app.cluster_config import ClusterDefinition
from app.inventory import collect_inventory_for_cluster, mark_scan_failed, mark_scan_started, mark_scan_success
from app.models import Cluster

from conftest import make_workload


def _container(name="app", image="nginx:1.27"):
    return SimpleNamespace(name=name, image=image)


def _pod_spec_template(containers):
    return SimpleNamespace(spec=SimpleNamespace(containers=containers))


def _deployment(namespace="default", name="api", replicas=2, available=2, image="nginx:1.27"):
    return SimpleNamespace(
        metadata=SimpleNamespace(namespace=namespace, name=name, labels={}, annotations={}),
        spec=SimpleNamespace(replicas=replicas, template=_pod_spec_template([_container(image=image)])),
        status=SimpleNamespace(available_replicas=available),
    )


def _empty():
    return SimpleNamespace(items=[])


def _clients_with_single_deployment(deployment):
    clients = MagicMock()
    clients.apps_v1.list_deployment_for_all_namespaces.return_value = SimpleNamespace(items=[deployment])
    clients.apps_v1.list_stateful_set_for_all_namespaces.return_value = _empty()
    clients.apps_v1.list_daemon_set_for_all_namespaces.return_value = _empty()
    clients.batch_v1.list_cron_job_for_all_namespaces.return_value = _empty()
    return clients


def test_collect_inventory_tags_workloads_with_cluster_id():
    cluster = ClusterDefinition(id="kind-dev", name="Dev", context="kind-dev", source="multicontext")
    clients = _clients_with_single_deployment(_deployment())

    workloads = collect_inventory_for_cluster(cluster, clients)

    assert len(workloads) == 1
    w = workloads[0]
    assert w.cluster_id == "kind-dev"
    assert w.namespace == "default"
    assert w.name == "api"
    assert w.kind == "Deployment"
    assert w.desired_replicas == 2
    assert w.available_replicas == 2
    assert w.containers[0].image_repository == "nginx"
    assert w.containers[0].image_tag == "1.27"


def test_collect_inventory_uses_request_timeout():
    cluster = ClusterDefinition(id="kind-dev", name="Dev", context="kind-dev", source="multicontext")
    clients = _clients_with_single_deployment(_deployment())

    collect_inventory_for_cluster(cluster, clients)

    _, kwargs = clients.apps_v1.list_deployment_for_all_namespaces.call_args
    assert "_request_timeout" in kwargs


def test_mark_scan_lifecycle_updates_cluster_row(db_session):
    db_session.add(Cluster(id="kind-dev", name="Dev"))
    db_session.commit()

    mark_scan_started(db_session, "kind-dev")
    db_session.commit()
    cluster = db_session.query(Cluster).filter_by(id="kind-dev").one()
    assert cluster.last_scan_started_at is not None
    assert cluster.last_successful_scan_at is None

    mark_scan_success(db_session, "kind-dev")
    db_session.commit()
    cluster = db_session.query(Cluster).filter_by(id="kind-dev").one()
    assert cluster.last_successful_scan_at is not None
    assert cluster.last_error is None

    mark_scan_failed(db_session, "kind-dev", "boom")
    db_session.commit()
    cluster = db_session.query(Cluster).filter_by(id="kind-dev").one()
    assert cluster.last_error == "boom"
    # last_successful_scan_at from the previous successful scan must be preserved
    assert cluster.last_successful_scan_at is not None


def test_save_inventory_upserts_and_adds_new_containers(db_session):
    db_session.add(Cluster(id="kind-dev", name="Dev"))
    db_session.commit()

    from app.inventory import save_inventory

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", tag="1.0")])
    db_session.commit()

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", tag="1.0")])
    db_session.commit()

    from app.models import Workload

    workloads = db_session.query(Workload).filter_by(cluster_id="kind-dev").all()
    assert len(workloads) == 1
