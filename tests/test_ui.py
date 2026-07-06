import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app import models  # noqa: F401
from app.db import Base
from app.inventory import save_inventory
from app.models import Cluster

from conftest import make_workload


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    async def fake_refresh():
        return {"status": "completed"}

    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "resolve_clusters", lambda settings: [])
    monkeypatch.setattr(main_module, "sync_clusters", lambda db, clusters: None)
    monkeypatch.setattr(main_module, "start_background_tasks", lambda: None)
    monkeypatch.setattr(main_module, "refresh_all_clusters", fake_refresh)

    main_module.app.dependency_overrides[main_module.get_db] = override_get_db

    db = session_factory()
    db.add_all([Cluster(id="kind-dev", name="Kind Development"), Cluster(id="kind-prod", name="Kind Production")])
    db.commit()
    save_inventory(db, "kind-dev", [make_workload("kind-dev", repository="nginx", tag="1.27")])
    save_inventory(db, "kind-prod", [make_workload("kind-prod", repository="nginx", tag="1.26")])
    db.commit()
    db.close()

    with TestClient(main_module.app) as test_client:
        yield test_client

    main_module.app.dependency_overrides.clear()


def test_all_clusters_shows_every_workload(client):
    resp = client.get("/?cluster=all")
    assert resp.status_code == 200
    assert "Kind Development" in resp.text or "kind-dev" in resp.text
    body = resp.text
    assert body.count('class="inventory-row"') == 2


def test_specific_cluster_filters_workloads(client):
    resp = client.get("/?cluster=kind-dev")
    assert resp.status_code == 200
    assert resp.text.count('class="inventory-row"') == 1
    assert "1.27" in resp.text
    assert "1.26" not in resp.text


def test_image_drift_detected_across_clusters(client):
    resp = client.get("/?cluster=all")
    assert resp.status_code == 200
    assert "Image Drift" in resp.text
    assert "nginx" in resp.text


def test_ready_endpoint(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
