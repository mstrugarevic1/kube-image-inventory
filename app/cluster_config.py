"""Cluster configuration loading and access-mode resolution.

This module is responsible for turning the application's configuration
(``KUBE_ACCESS_MODE`` and friends) into a concrete list of :class:`ClusterDefinition`
objects that the rest of the application can use to build Kubernetes clients and
scan workloads.

Three access modes are supported:

- ``incluster``: represent the cluster the app is running in as a single cluster.
- ``multicontext``: load an explicit, validated list of kubeconfig contexts from
  ``CLUSTERS_CONFIG_PATH``. Only clusters listed there are ever scanned.
- ``auto``: prefer in-cluster credentials, fall back to a multi-context config file
  if one exists, and otherwise fall back to the local kubeconfig's current context
  (the original single-cluster local development workflow).
"""

from __future__ import annotations

import logging
import os
from typing import Literal

import yaml
from kubernetes import client, config
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

ClusterSource = Literal["multicontext", "incluster", "local"]


class ClusterConfigError(Exception):
    """Raised when cluster configuration is missing, invalid, or ambiguous."""


class ClusterDefinition(BaseModel):
    """A single, validated cluster the application is allowed to scan."""

    id: str
    name: str
    context: str | None = None
    environment: str = "unknown"
    enabled: bool = True
    source: ClusterSource = "multicontext"

    @field_validator("id", "name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class _ClusterConfigEntry(BaseModel):
    """Raw schema for one entry in clusters.yaml. Context is required here."""

    id: str
    name: str
    context: str
    environment: str = "unknown"
    enabled: bool = True

    @field_validator("id", "name", "context")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class _ClustersFile(BaseModel):
    clusters: list[_ClusterConfigEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_non_empty(self) -> "_ClustersFile":
        if not self.clusters:
            raise ValueError("clusters list must not be empty")
        return self


def load_clusters_config(path: str) -> list[ClusterDefinition]:
    """Load and validate the multi-context cluster configuration file.

    Returns all parsed clusters (enabled and disabled). Raises ClusterConfigError
    on any validation failure, with a message safe to log (no credentials are
    ever read from this file).
    """
    if not os.path.isfile(path):
        raise ClusterConfigError(f"Cluster configuration file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        try:
            raw = yaml.safe_load(fh)
        except yaml.YAMLError as e:
            raise ClusterConfigError(f"Invalid YAML in cluster configuration '{path}': {e}") from e

    if raw is None:
        raise ClusterConfigError(f"Cluster configuration file is empty: {path}")

    try:
        parsed = _ClustersFile.model_validate(raw)
    except Exception as e:
        raise ClusterConfigError(f"Invalid cluster configuration '{path}': {e}") from e

    ids = [entry.id for entry in parsed.clusters]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ClusterConfigError(
            f"Duplicate cluster id(s) in '{path}': {', '.join(sorted(duplicates))}"
        )

    clusters = [
        ClusterDefinition(
            id=entry.id,
            name=entry.name,
            context=entry.context,
            environment=entry.environment,
            enabled=entry.enabled,
            source="multicontext",
        )
        for entry in parsed.clusters
    ]

    if not any(c.enabled for c in clusters):
        raise ClusterConfigError(f"No enabled clusters configured in '{path}'")

    return clusters


def get_enabled_clusters(clusters: list[ClusterDefinition]) -> list[ClusterDefinition]:
    return [c for c in clusters if c.enabled]


def _build_incluster_definition(settings) -> ClusterDefinition:
    return ClusterDefinition(
        id=settings.INCLUSTER_CLUSTER_ID,
        name=settings.INCLUSTER_CLUSTER_NAME,
        context=None,
        environment=settings.INCLUSTER_CLUSTER_ENVIRONMENT,
        enabled=True,
        source="incluster",
    )


def _build_local_dev_definition() -> ClusterDefinition:
    return ClusterDefinition(
        id="local-kubeconfig",
        name="Local Kubeconfig",
        context=None,
        environment="development",
        enabled=True,
        source="local",
    )


def _incluster_credentials_available() -> bool:
    try:
        config.load_incluster_config(client_configuration=client.Configuration())
        return True
    except config.ConfigException:
        return False


def resolve_clusters(settings) -> list[ClusterDefinition]:
    """Resolve the configured access mode into a list of ClusterDefinitions.

    Only clusters returned here (filtered through get_enabled_clusters) are ever
    scanned - kubeconfig contexts that are not explicitly listed are never touched.
    """
    mode = settings.KUBE_ACCESS_MODE

    if mode == "incluster":
        return [_build_incluster_definition(settings)]

    if mode == "multicontext":
        return load_clusters_config(settings.CLUSTERS_CONFIG_PATH)

    if mode == "auto":
        if _incluster_credentials_available():
            logger.info("Auto mode: in-cluster credentials detected")
            return [_build_incluster_definition(settings)]

        if os.path.isfile(settings.CLUSTERS_CONFIG_PATH):
            logger.info(
                "Auto mode: using multi-context configuration at %s",
                settings.CLUSTERS_CONFIG_PATH,
            )
            return load_clusters_config(settings.CLUSTERS_CONFIG_PATH)

        if settings.KUBE_IMAGE_INVENTORY_DEV_KUBECONFIG:
            logger.info("Auto mode: falling back to local kubeconfig current-context")
            return [_build_local_dev_definition()]

        raise ClusterConfigError(
            "Auto mode could not find in-cluster credentials or a cluster "
            f"configuration file at '{settings.CLUSTERS_CONFIG_PATH}', and "
            "KUBE_IMAGE_INVENTORY_DEV_KUBECONFIG is not enabled."
        )

    raise ClusterConfigError(f"Unknown KUBE_ACCESS_MODE: {mode!r}")
