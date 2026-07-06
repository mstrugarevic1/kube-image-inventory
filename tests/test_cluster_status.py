from datetime import datetime, timedelta

from app.models import Cluster
from app.services.cluster_status import derive_status

NOW = datetime(2026, 1, 1, 12, 0, 0)
STALE_AFTER = 1800


def test_never_scanned_is_unknown():
    cluster = Cluster(id="c", name="c")
    assert derive_status(cluster, STALE_AFTER, now=NOW) == "unknown"


def test_recent_successful_scan_is_healthy():
    cluster = Cluster(
        id="c",
        name="c",
        last_scan_started_at=NOW - timedelta(seconds=5),
        last_scan_completed_at=NOW - timedelta(seconds=1),
        last_successful_scan_at=NOW - timedelta(seconds=1),
        last_error=None,
    )
    assert derive_status(cluster, STALE_AFTER, now=NOW) == "healthy"


def test_never_successful_and_latest_failed_is_unreachable():
    cluster = Cluster(
        id="c",
        name="c",
        last_scan_started_at=NOW - timedelta(seconds=5),
        last_scan_completed_at=NOW - timedelta(seconds=1),
        last_successful_scan_at=None,
        last_error="connection refused",
    )
    assert derive_status(cluster, STALE_AFTER, now=NOW) == "unreachable"


def test_previously_successful_but_latest_failed_is_stale():
    cluster = Cluster(
        id="c",
        name="c",
        last_scan_started_at=NOW - timedelta(seconds=5),
        last_scan_completed_at=NOW - timedelta(seconds=1),
        last_successful_scan_at=NOW - timedelta(minutes=10),
        last_error="timeout",
    )
    assert derive_status(cluster, STALE_AFTER, now=NOW) == "stale"


def test_successful_but_old_scan_is_stale():
    cluster = Cluster(
        id="c",
        name="c",
        last_scan_started_at=NOW - timedelta(seconds=STALE_AFTER * 2),
        last_scan_completed_at=NOW - timedelta(seconds=STALE_AFTER * 2),
        last_successful_scan_at=NOW - timedelta(seconds=STALE_AFTER * 2),
        last_error=None,
    )
    assert derive_status(cluster, STALE_AFTER, now=NOW) == "stale"
