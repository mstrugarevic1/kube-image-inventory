import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app import models  # noqa: F401  (register models on Base.metadata)
from app.schemas import ContainerCreate, WorkloadCreate


@pytest.fixture
def db_session():
    """An isolated in-memory SQLite session, independent of the real inventory.db."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def make_workload(
    cluster_id: str,
    namespace: str = "default",
    name: str = "api",
    kind: str = "Deployment",
    container_name: str = "app",
    repository: str = "nginx",
    tag: str = "1.0",
) -> WorkloadCreate:
    return WorkloadCreate(
        cluster_id=cluster_id,
        namespace=namespace,
        name=name,
        kind=kind,
        desired_replicas=1,
        available_replicas=1,
        containers=[
            ContainerCreate(
                name=container_name,
                image_full=f"{repository}:{tag}",
                image_repository=repository,
                image_tag=tag,
                current_tag=tag,
            )
        ],
    )
