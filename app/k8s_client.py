from __future__ import annotations

import logging
from dataclasses import dataclass

from kubernetes import client, config

from .cluster_config import ClusterDefinition

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT_SECONDS = 10


@dataclass
class KubernetesClients:
    apps_v1: client.AppsV1Api
    core_v1: client.CoreV1Api
    batch_v1: client.BatchV1Api
    custom_objects: client.CustomObjectsApi


def get_k8s_clients(
    cluster: ClusterDefinition,
    kubeconfig_path: str | None = None,
) -> KubernetesClients:
    """Build an isolated set of Kubernetes API clients for one cluster definition.

    Each call creates its own client.Configuration() and client.ApiClient(), so
    building clients for one cluster never overwrites or affects clients already
    built for another cluster. The Kubernetes Python client's process-global
    default configuration is never mutated.
    """
    configuration = client.Configuration()

    if cluster.source == "incluster":
        config.load_incluster_config(client_configuration=configuration)
        logger.info("[%s] Loaded in-cluster Kubernetes config", cluster.id)
    else:
        config.load_kube_config(
            config_file=kubeconfig_path or None,
            context=cluster.context,
            client_configuration=configuration,
        )
        logger.info(
            "[%s] Loaded kubeconfig context %r",
            cluster.id,
            cluster.context or "(current-context)",
        )

    api_client = client.ApiClient(configuration=configuration)

    return KubernetesClients(
        apps_v1=client.AppsV1Api(api_client),
        core_v1=client.CoreV1Api(api_client),
        batch_v1=client.BatchV1Api(api_client),
        custom_objects=client.CustomObjectsApi(api_client),
    )
