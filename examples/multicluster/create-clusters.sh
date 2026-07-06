#!/usr/bin/env bash
# Create two local Kind clusters and deploy sample workloads with drifted image
# tags, then write config/clusters.yaml so the app can scan both. Safe to rerun.
set -euo pipefail

DEV_CLUSTER=kii-dev
PROD_CLUSTER=kii-prod

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

command -v kind >/dev/null 2>&1 || { echo "kind is required: https://kind.sigs.k8s.io/"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required"; exit 1; }

for name in "$DEV_CLUSTER" "$PROD_CLUSTER"; do
    if kind get clusters 2>/dev/null | grep -qx "$name"; then
        echo "Kind cluster '$name' already exists, skipping creation"
    else
        echo "Creating kind cluster '$name'..."
        kind create cluster --name "$name"
    fi
done

echo "Deploying sample workload to kind-${DEV_CLUSTER} (nginx:1.27)..."
kubectl --context "kind-${DEV_CLUSTER}" apply -f "$SCRIPT_DIR/dev-workload.yaml"

echo "Deploying sample workload to kind-${PROD_CLUSTER} (nginx:1.26)..."
kubectl --context "kind-${PROD_CLUSTER}" apply -f "$SCRIPT_DIR/prod-workload.yaml"

echo "Waiting for deployments to become available..."
kubectl --context "kind-${DEV_CLUSTER}" -n default rollout status deployment/api --timeout=180s
kubectl --context "kind-${PROD_CLUSTER}" -n default rollout status deployment/api --timeout=180s

mkdir -p "$REPO_ROOT/config"
cp "$SCRIPT_DIR/clusters.yaml" "$REPO_ROOT/config/clusters.yaml"
echo "Wrote $REPO_ROOT/config/clusters.yaml"

echo ""
echo "Done. Two Kind clusters are ready:"
echo "  - kind-${DEV_CLUSTER}  (nginx:1.27)"
echo "  - kind-${PROD_CLUSTER} (nginx:1.26)"
echo ""
echo "Next: make demo-run"
