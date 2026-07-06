from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    context_name = Column(String, nullable=True)
    environment = Column(String, nullable=False, default="unknown")
    enabled = Column(Boolean, default=True, nullable=False)

    last_scan_started_at = Column(DateTime, nullable=True)
    last_scan_completed_at = Column(DateTime, nullable=True)
    last_successful_scan_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    workloads = relationship(
        "Workload", back_populates="cluster", cascade="all, delete-orphan"
    )


class Workload(Base):
    __tablename__ = "workloads"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(String, ForeignKey("clusters.id"), nullable=False, index=True)
    namespace = Column(String, index=True)
    name = Column(String, index=True)
    kind = Column(String, index=True)
    desired_replicas = Column(Integer, default=0)
    available_replicas = Column(Integer, default=0)
    labels = Column(JSON, default=dict)
    annotations = Column(JSON, default=dict)
    last_observed = Column(DateTime, default=datetime.utcnow)

    cluster = relationship("Cluster", back_populates="workloads")
    containers = relationship("Container", back_populates="workload", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("cluster_id", "namespace", "name", "kind", name="_cluster_workload_uc"),
    )


class Container(Base):
    __tablename__ = "containers"

    id = Column(Integer, primary_key=True, index=True)
    workload_id = Column(Integer, ForeignKey("workloads.id"))
    name = Column(String)
    image_full = Column(String)
    image_repository = Column(String)
    image_tag = Column(String)

    # Freshness info
    current_tag = Column(String)
    latest_tag = Column(String)
    freshness_status = Column(String, default="unknown")
    freshness_reason = Column(String)
    checked_at = Column(DateTime)

    # Vulnerability info
    critical_cve = Column(Integer, default=0)
    high_cve = Column(Integer, default=0)
    medium_cve = Column(Integer, default=0)
    low_cve = Column(Integer, default=0)
    unknown_cve = Column(Integer, default=0)
    vulnerability_report_name = Column(String)

    workload = relationship("Workload", back_populates="containers")


class RegistryCache(Base):
    __tablename__ = "registry_cache"

    id = Column(Integer, primary_key=True, index=True)
    image_repository = Column(String, unique=True, index=True)
    tags_json = Column(JSON)
    latest_tag = Column(String)
    last_updated = Column(DateTime, default=datetime.utcnow)
