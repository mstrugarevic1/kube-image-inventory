.PHONY: install test lint run build deploy undeploy port-forward reset-db demo-up demo-run demo-down

install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

run:
	KUBE_IMAGE_INVENTORY_DEV_KUBECONFIG=true uvicorn app.main:app --reload

build:
	docker build -t kube-image-inventory .

deploy:
	kubectl apply -k deploy/kubernetes/base

undeploy:
	kubectl delete -k deploy/kubernetes/base

port-forward:
	kubectl port-forward -n kube-image-inventory svc/kube-image-inventory 8000:80

# The SQLite database is disposable. Reset it after schema changes or to start
# the multi-cluster demo from a clean slate.
reset-db:
	rm -f inventory.db

# --- Two-cluster Kind demo (see examples/multicluster/) ----------------------

demo-up:
	bash examples/multicluster/create-clusters.sh

demo-run: reset-db
	KUBE_ACCESS_MODE=multicontext CLUSTERS_CONFIG_PATH=./config/clusters.yaml uvicorn app.main:app --reload

demo-down:
	bash examples/multicluster/delete-clusters.sh
