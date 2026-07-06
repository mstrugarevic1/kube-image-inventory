from unittest.mock import patch

from app.cluster_config import ClusterDefinition
from app.k8s_client import get_k8s_clients


def _fake_load_kube_config(config_file=None, context=None, client_configuration=None):
    # Emulate different clusters ending up with different endpoints, so tests
    # can prove configurations do not leak between clusters.
    client_configuration.host = f"https://{context}.example.com"


def test_correct_context_passed_to_configuration():
    cluster = ClusterDefinition(id="kind-dev", name="Dev", context="kind-dev", source="multicontext")

    with patch("app.k8s_client.config.load_kube_config", side_effect=_fake_load_kube_config) as mock_load:
        clients = get_k8s_clients(cluster)

    mock_load.assert_called_once()
    assert mock_load.call_args.kwargs["context"] == "kind-dev"
    assert clients.apps_v1.api_client.configuration.host == "https://kind-dev.example.com"


def test_independent_configurations_for_different_contexts():
    dev = ClusterDefinition(id="kind-dev", name="Dev", context="kind-dev", source="multicontext")
    prod = ClusterDefinition(id="kind-prod", name="Prod", context="kind-prod", source="multicontext")

    with patch("app.k8s_client.config.load_kube_config", side_effect=_fake_load_kube_config):
        dev_clients = get_k8s_clients(dev)
        prod_clients = get_k8s_clients(prod)

    dev_config = dev_clients.apps_v1.api_client.configuration
    prod_config = prod_clients.apps_v1.api_client.configuration

    assert dev_config is not prod_config
    assert dev_config.host == "https://kind-dev.example.com"
    assert prod_config.host == "https://kind-prod.example.com"
    # Building the second cluster's clients must not have mutated the first.
    assert dev_config.host == "https://kind-dev.example.com"


def test_clients_for_same_cluster_share_one_api_client():
    cluster = ClusterDefinition(id="kind-dev", name="Dev", context="kind-dev", source="multicontext")

    with patch("app.k8s_client.config.load_kube_config", side_effect=_fake_load_kube_config):
        clients = get_k8s_clients(cluster)

    assert clients.apps_v1.api_client is clients.core_v1.api_client
    assert clients.apps_v1.api_client is clients.batch_v1.api_client
    assert clients.apps_v1.api_client is clients.custom_objects.api_client


def test_incluster_source_uses_incluster_loader():
    cluster = ClusterDefinition(id="local-cluster", name="Local", context=None, source="incluster")

    with patch("app.k8s_client.config.load_incluster_config") as mock_incluster, \
            patch("app.k8s_client.config.load_kube_config") as mock_kubeconfig:
        get_k8s_clients(cluster)

    mock_incluster.assert_called_once()
    mock_kubeconfig.assert_not_called()


def test_kubeconfig_path_forwarded():
    cluster = ClusterDefinition(id="kind-dev", name="Dev", context="kind-dev", source="multicontext")

    with patch("app.k8s_client.config.load_kube_config", side_effect=_fake_load_kube_config) as mock_load:
        get_k8s_clients(cluster, kubeconfig_path="/tmp/my-kubeconfig")

    assert mock_load.call_args.kwargs["config_file"] == "/tmp/my-kubeconfig"
