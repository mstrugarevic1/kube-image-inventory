from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime

class ContainerBase(BaseModel):
    name: str
    image_full: str
    image_repository: str
    image_tag: str
    current_tag: Optional[str] = None
    latest_tag: Optional[str] = None
    freshness_status: str = "unknown"
    freshness_reason: Optional[str] = None
    checked_at: Optional[datetime] = None
    critical_cve: int = 0
    high_cve: int = 0
    medium_cve: int = 0
    low_cve: int = 0
    unknown_cve: int = 0

class ContainerCreate(ContainerBase):
    pass

class Container(ContainerBase):
    id: int
    workload_id: int

    class Config:
        from_attributes = True

class WorkloadBase(BaseModel):
    cluster_id: str
    namespace: str
    name: str
    kind: str
    desired_replicas: int = 0
    available_replicas: int = 0
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    last_observed: datetime = Field(default_factory=datetime.utcnow)

class WorkloadCreate(WorkloadBase):
    containers: List[ContainerCreate] = []

class Workload(WorkloadBase):
    id: int
    containers: List[Container] = []

    class Config:
        from_attributes = True

class Summary(BaseModel):
    total_workloads: int
    total_images: int
    outdated_images: int
    unknown_freshness: int
    critical_cves: int
    high_cves: int
    last_scan_time: Optional[datetime]
