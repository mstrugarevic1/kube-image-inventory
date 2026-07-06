#!/usr/bin/env bash
# Remove the demo Kind clusters. Safe to rerun even if they don't exist.
set -euo pipefail

DEV_CLUSTER=kii-dev
PROD_CLUSTER=kii-prod

command -v kind >/dev/null 2>&1 || { echo "kind is required: https://kind.sigs.k8s.io/"; exit 1; }

for name in "$DEV_CLUSTER" "$PROD_CLUSTER"; do
    if kind get clusters 2>/dev/null | grep -qx "$name"; then
        echo "Deleting kind cluster '$name'..."
        kind delete cluster --name "$name"
    else
        echo "Kind cluster '$name' does not exist, skipping"
    fi
done
