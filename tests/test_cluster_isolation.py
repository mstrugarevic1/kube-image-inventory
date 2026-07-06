from app.inventory import save_inventory
from app.models import Cluster, Workload

from conftest import make_workload


def _seed_clusters(db_session, *ids):
    for cluster_id in ids:
        db_session.add(Cluster(id=cluster_id, name=cluster_id, environment="test"))
    db_session.commit()


def test_same_workload_identity_can_exist_in_two_clusters(db_session):
    _seed_clusters(db_session, "kind-dev", "kind-prod")

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", tag="1.27")])
    save_inventory(db_session, "kind-prod", [make_workload("kind-prod", tag="1.26")])
    db_session.commit()

    dev = db_session.query(Workload).filter_by(cluster_id="kind-dev", namespace="default", name="api", kind="Deployment").one()
    prod = db_session.query(Workload).filter_by(cluster_id="kind-prod", namespace="default", name="api", kind="Deployment").one()

    assert dev.id != prod.id
    assert dev.containers[0].image_tag == "1.27"
    assert prod.containers[0].image_tag == "1.26"


def test_updating_cluster_a_does_not_update_cluster_b(db_session):
    _seed_clusters(db_session, "kind-dev", "kind-prod")

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", tag="1.27")])
    save_inventory(db_session, "kind-prod", [make_workload("kind-prod", tag="1.26")])
    db_session.commit()

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", tag="1.28")])
    db_session.commit()

    dev = db_session.query(Workload).filter_by(cluster_id="kind-dev", name="api").one()
    prod = db_session.query(Workload).filter_by(cluster_id="kind-prod", name="api").one()

    assert dev.containers[0].image_tag == "1.28"
    assert prod.containers[0].image_tag == "1.26"


def test_deleting_stale_workloads_scoped_to_one_cluster(db_session):
    _seed_clusters(db_session, "kind-dev", "kind-prod")

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", tag="1.27")])
    save_inventory(db_session, "kind-prod", [make_workload("kind-prod", tag="1.26")])
    db_session.commit()

    # kind-dev's latest scan found no workloads at all.
    save_inventory(db_session, "kind-dev", [])
    db_session.commit()

    assert db_session.query(Workload).filter_by(cluster_id="kind-dev").count() == 0
    assert db_session.query(Workload).filter_by(cluster_id="kind-prod").count() == 1


def test_failed_scan_preserves_previous_cluster_data(db_session):
    _seed_clusters(db_session, "kind-dev")

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", tag="1.27")])
    db_session.commit()

    # Simulate a scan that collects new data but then fails before commit.
    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", tag="9.9.9")])
    db_session.rollback()

    w = db_session.query(Workload).filter_by(cluster_id="kind-dev", name="api").one()
    assert w.containers[0].image_tag == "1.27"


def test_container_updates_remain_cluster_scoped(db_session):
    _seed_clusters(db_session, "kind-dev", "kind-prod")

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", container_name="app", tag="1.0")])
    save_inventory(db_session, "kind-prod", [make_workload("kind-prod", container_name="app", tag="1.0")])
    db_session.commit()

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", container_name="app", tag="2.0")])
    db_session.commit()

    dev_container = db_session.query(Workload).filter_by(cluster_id="kind-dev").one().containers[0]
    prod_container = db_session.query(Workload).filter_by(cluster_id="kind-prod").one().containers[0]

    assert dev_container.image_tag == "2.0"
    assert prod_container.image_tag == "1.0"
