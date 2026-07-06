from app.inventory import save_inventory
from app.models import Cluster
from app.services.image_drift import get_image_drift

from conftest import make_workload


def test_drift_detected_when_tags_differ(db_session):
    db_session.add_all([Cluster(id="kind-dev", name="Dev"), Cluster(id="kind-prod", name="Prod")])
    db_session.commit()

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", repository="nginx", tag="1.27")])
    save_inventory(db_session, "kind-prod", [make_workload("kind-prod", repository="nginx", tag="1.26")])
    db_session.commit()

    rows = get_image_drift(db_session)

    assert len(rows) == 1
    assert rows[0].repository == "nginx"
    assert rows[0].tags_by_cluster == {"kind-dev": "1.27", "kind-prod": "1.26"}


def test_no_drift_when_tags_match(db_session):
    db_session.add_all([Cluster(id="kind-dev", name="Dev"), Cluster(id="kind-prod", name="Prod")])
    db_session.commit()

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", repository="nginx", tag="1.27")])
    save_inventory(db_session, "kind-prod", [make_workload("kind-prod", repository="nginx", tag="1.27")])
    db_session.commit()

    assert get_image_drift(db_session) == []


def test_drift_filtered_to_selected_clusters(db_session):
    db_session.add_all([Cluster(id="kind-dev", name="Dev"), Cluster(id="kind-prod", name="Prod")])
    db_session.commit()

    save_inventory(db_session, "kind-dev", [make_workload("kind-dev", repository="nginx", tag="1.27")])
    save_inventory(db_session, "kind-prod", [make_workload("kind-prod", repository="nginx", tag="1.26")])
    db_session.commit()

    rows = get_image_drift(db_session, cluster_ids=["kind-dev"])
    assert rows == []


def test_digest_tags_are_shortened(db_session):
    db_session.add_all([Cluster(id="kind-dev", name="Dev"), Cluster(id="kind-prod", name="Prod")])
    db_session.commit()

    save_inventory(
        db_session,
        "kind-dev",
        [make_workload("kind-dev", repository="nginx", tag="sha256:" + "a" * 64)],
    )
    save_inventory(
        db_session,
        "kind-prod",
        [make_workload("kind-prod", repository="nginx", tag="sha256:" + "b" * 64)],
    )
    db_session.commit()

    rows = get_image_drift(db_session)
    assert len(rows) == 1
    assert rows[0].tags_by_cluster["kind-dev"] == "sha256:" + "a" * 12
    assert rows[0].tags_by_cluster["kind-prod"] == "sha256:" + "b" * 12
