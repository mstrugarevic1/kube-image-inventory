from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Kubernetes Image Inventory"
    DATABASE_URL: str = "sqlite:///./inventory.db"

    # K8s access
    # Deprecated: kept for backward compatibility with the original single-cluster
    # local dev workflow. Prefer KUBE_ACCESS_MODE.
    KUBE_IMAGE_INVENTORY_DEV_KUBECONFIG: bool = False

    # Access mode: "auto", "incluster" or "multicontext"
    KUBE_ACCESS_MODE: str = "auto"
    # Path to a kubeconfig file. Empty string means "use the client library default"
    # (KUBECONFIG env var or ~/.kube/config).
    KUBECONFIG_PATH: str = ""
    # Path to the explicit multi-cluster configuration file.
    CLUSTERS_CONFIG_PATH: str = "./config/clusters.yaml"
    # A cluster is considered stale if its last successful scan is older than this.
    CLUSTER_STALE_AFTER_SECONDS: int = 1800
    # Per-request timeout (seconds) for Kubernetes API calls.
    KUBE_REQUEST_TIMEOUT_SECONDS: int = 10

    # Identity used to represent the current cluster in "incluster" mode.
    INCLUSTER_CLUSTER_ID: str = "local-cluster"
    INCLUSTER_CLUSTER_NAME: str = "Local Cluster"
    INCLUSTER_CLUSTER_ENVIRONMENT: str = "local"

    # Scan
    SCAN_INTERVAL_SECONDS: int = 900

    class Config:
        env_file = ".env"


settings = Settings()
