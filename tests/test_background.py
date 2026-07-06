from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.background as background
from app import models  # noqa: F401
from app.cluster_config import ClusterDefinition
from app.db import Base
from app.models import Cluster


@pytest.fixture
def test_sessionmaker():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all([Cluster(id="kind-dev", name="Dev"), Cluster(id="kind-prod", name="Prod")])
    db.commit()
    db.close()
    return factory


@pytest.mark.asyncio
async def test_one_cluster_failure_does_not_stop_another(monkeypatch, test_sessionmaker):
    monkeypatch.setattr(background, "SessionLocal", test_sessionmaker)

    dev = ClusterDefinition(id="kind-dev", name="Dev", context="kind-dev", source="multicontext")
    prod = ClusterDefinition(id="kind-prod", name="Prod", context="kind-prod", source="multicontext")

    def fake_get_k8s_clients(cluster, kubeconfig_path=None):
        if cluster.id == "kind-dev":
            raise RuntimeError("connection refused")
        return MagicMock()

    monkeypatch.setattr(background, "get_k8s_clients", fake_get_k8s_clients)
    monkeypatch.setattr(background, "collect_inventory_for_cluster", lambda cluster, clients: [])
    monkeypatch.setattr(background, "collect_vulnerabilities_for_cluster", lambda cid, clients, db: None)

    await background.refresh_cluster(dev)
    await background.refresh_cluster(prod)

    db = test_sessionmaker()
    dev_row = db.query(Cluster).filter_by(id="kind-dev").one()
    prod_row = db.query(Cluster).filter_by(id="kind-prod").one()
    db.close()

    assert dev_row.last_error is not None
    assert dev_row.last_successful_scan_at is None

    assert prod_row.last_error is None
    assert prod_row.last_successful_scan_at is not None


@pytest.mark.asyncio
async def test_successful_scan_updates_timestamps(monkeypatch, test_sessionmaker):
    monkeypatch.setattr(background, "SessionLocal", test_sessionmaker)

    dev = ClusterDefinition(id="kind-dev", name="Dev", context="kind-dev", source="multicontext")

    monkeypatch.setattr(background, "get_k8s_clients", lambda cluster, kubeconfig_path=None: MagicMock())
    monkeypatch.setattr(background, "collect_inventory_for_cluster", lambda cluster, clients: [])
    monkeypatch.setattr(background, "collect_vulnerabilities_for_cluster", lambda cid, clients, db: None)

    await background.refresh_cluster(dev)

    db = test_sessionmaker()
    row = db.query(Cluster).filter_by(id="kind-dev").one()
    db.close()

    assert row.last_scan_started_at is not None
    assert row.last_scan_completed_at is not None
    assert row.last_successful_scan_at is not None
    assert row.last_error is None


@pytest.mark.asyncio
async def test_failed_scan_becomes_unreachable_before_first_success(monkeypatch, test_sessionmaker):
    monkeypatch.setattr(background, "SessionLocal", test_sessionmaker)

    dev = ClusterDefinition(id="kind-dev", name="Dev", context="kind-dev", source="multicontext")

    def raise_error(cluster, kubeconfig_path=None):
        raise RuntimeError("no route to host")

    monkeypatch.setattr(background, "get_k8s_clients", raise_error)

    await background.refresh_cluster(dev)

    from app.services.cluster_status import derive_status

    db = test_sessionmaker()
    row = db.query(Cluster).filter_by(id="kind-dev").one()
    db.close()

    assert row.last_error is not None
    assert derive_status(row, stale_after_seconds=1800) == "unreachable"


@pytest.mark.asyncio
async def test_refresh_all_clusters_rejects_concurrent_calls():
    async with background._refresh_lock:
        result = await background.refresh_all_clusters()
    assert result == {"status": "already_running"}
