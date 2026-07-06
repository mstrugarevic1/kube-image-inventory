from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Container, Workload


@dataclass
class ImageDriftRow:
    repository: str
    tags_by_cluster: dict[str, str] = field(default_factory=dict)


def _display_tag(tag: str) -> str:
    if tag.startswith("sha256:"):
        digest = tag[len("sha256:"):]
        return f"sha256:{digest[:12]}"
    return tag


def get_image_drift(db: Session, cluster_ids: Optional[list[str]] = None) -> list[ImageDriftRow]:
    """Find image repositories running with more than one distinct tag across clusters.

    Implemented as a single grouped query plus in-memory aggregation - no
    separate service layer is needed for an MVP of this size.
    """
    query = db.query(
        Container.image_repository,
        Workload.cluster_id,
        Container.image_tag,
    ).join(Workload, Container.workload_id == Workload.id)

    if cluster_ids:
        query = query.filter(Workload.cluster_id.in_(cluster_ids))

    grouped: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for repository, cluster_id, tag in query.all():
        grouped[repository][cluster_id].add(_display_tag(tag))

    rows: list[ImageDriftRow] = []
    for repository, by_cluster in grouped.items():
        distinct_tags = {tag for tags in by_cluster.values() for tag in tags}
        if len(distinct_tags) <= 1:
            continue
        rows.append(
            ImageDriftRow(
                repository=repository,
                tags_by_cluster={
                    cluster_id: "/".join(sorted(tags)) for cluster_id, tags in by_cluster.items()
                },
            )
        )

    rows.sort(key=lambda r: r.repository)
    return rows
