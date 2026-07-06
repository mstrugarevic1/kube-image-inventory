import pytest

from app.cluster_config import ClusterConfigError, get_enabled_clusters, load_clusters_config


def _write(tmp_path, content):
    p = tmp_path / "clusters.yaml"
    p.write_text(content)
    return str(p)


def test_valid_cluster_configuration(tmp_path):
    path = _write(
        tmp_path,
        """
clusters:
  - id: kind-dev
    name: Kind Development
    context: kind-dev
    environment: development
    enabled: true
  - id: kind-prod
    name: Kind Production
    context: kind-prod
    environment: production
    enabled: true
""",
    )
    clusters = load_clusters_config(path)
    assert len(clusters) == 2
    assert {c.id for c in clusters} == {"kind-dev", "kind-prod"}
    assert all(c.source == "multicontext" for c in clusters)


def test_duplicate_cluster_ids_rejected(tmp_path):
    path = _write(
        tmp_path,
        """
clusters:
  - id: kind-dev
    name: A
    context: kind-dev
  - id: kind-dev
    name: B
    context: kind-dev-2
""",
    )
    with pytest.raises(ClusterConfigError, match="Duplicate"):
        load_clusters_config(path)


def test_missing_context_rejected(tmp_path):
    path = _write(
        tmp_path,
        """
clusters:
  - id: kind-dev
    name: A
""",
    )
    with pytest.raises(ClusterConfigError):
        load_clusters_config(path)


def test_blank_context_rejected(tmp_path):
    path = _write(
        tmp_path,
        """
clusters:
  - id: kind-dev
    name: A
    context: "   "
""",
    )
    with pytest.raises(ClusterConfigError):
        load_clusters_config(path)


def test_disabled_clusters_parsed_but_excluded_from_enabled(tmp_path):
    path = _write(
        tmp_path,
        """
clusters:
  - id: kind-dev
    name: A
    context: kind-dev
    enabled: true
  - id: kind-prod
    name: B
    context: kind-prod
    enabled: false
""",
    )
    clusters = load_clusters_config(path)
    assert len(clusters) == 2

    enabled = get_enabled_clusters(clusters)
    assert [c.id for c in enabled] == ["kind-dev"]


def test_no_enabled_clusters_rejected(tmp_path):
    path = _write(
        tmp_path,
        """
clusters:
  - id: kind-dev
    name: A
    context: kind-dev
    enabled: false
""",
    )
    with pytest.raises(ClusterConfigError, match="enabled"):
        load_clusters_config(path)


def test_invalid_yaml_rejected(tmp_path):
    path = _write(tmp_path, "clusters: [unterminated, flow, sequence")
    with pytest.raises(ClusterConfigError):
        load_clusters_config(path)


def test_empty_cluster_list_rejected(tmp_path):
    path = _write(tmp_path, "clusters: []")
    with pytest.raises(ClusterConfigError):
        load_clusters_config(path)


def test_empty_file_rejected(tmp_path):
    path = _write(tmp_path, "")
    with pytest.raises(ClusterConfigError):
        load_clusters_config(path)


def test_missing_file_rejected(tmp_path):
    with pytest.raises(ClusterConfigError, match="not found"):
        load_clusters_config(str(tmp_path / "does-not-exist.yaml"))
