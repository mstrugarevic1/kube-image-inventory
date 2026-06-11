# Kubernetes Image Inventory

A Python CLI and web-based tool for inspecting Kubernetes workloads and reporting container images used across a cluster.

## Purpose

`kube-image-inventory` provides a consolidated view of all container images running in your Kubernetes cluster, helping platform teams track image versions, freshness, and security posture.

## Key Features

- **Cluster-wide Inventory**: Automatically discovers images across all namespaces and workload types.
- **Image Freshness**: Identifies when newer tags are available in the registry.
- **Vulnerability Reporting**: Integrates with Trivy Operator (if present) to display CVE counts.
- **CI/CD Integration**: Includes GitHub Actions for linting and testing.

## Tech Stack

- **Python 3.11**: Core logic and CLI.
- **Kubernetes Client**: Direct interaction with the cluster API.
- **Docker**: For containerized execution.
- **GitHub Actions**: Automated CI workflow with dependency caching.

## Getting Started

### Prerequisites

- Python 3.11+
- A valid `~/.kube/config` with read access to the cluster.

### Local Installation

```bash
# Install dependencies
pip install .[dev]

# Run tests
pytest
```

## Repository Structure

- `app/`: Main application logic.
- `deploy/`: Kubernetes manifests for cluster deployment.
- `.github/workflows/`: CI/CD configuration.
- `tests/`: Automated test suite.

## Usage

Refer to the inline help for CLI usage or the `Makefile` for common tasks like building images and running local scans.

> [!NOTE]
> This is a portfolio project demonstrating Kubernetes integration and Python tooling. It is not intended for high-security production environments without additional access controls.
