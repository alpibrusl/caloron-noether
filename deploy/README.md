# Deployment

## Docker Compose (local / small team)

```bash
# Set API keys
export ANTHROPIC_API_KEY="sk-ant-..."
export GITEA_TOKEN="..."  # created after first Gitea boot
export REPO="caloron/my-project"

# Start everything
cd deploy/docker
docker compose up -d

# Run a sprint
docker compose exec coordinator python3 /app/orchestrator.py \
  "Build a REST API for user management"

# Check status
curl http://localhost:3000  # Gitea UI
docker compose exec worker-1 curl http://localhost:7710/status
```

### Scaling workers

```bash
docker compose up -d --scale worker-1=3
```

## Kubernetes (production / enterprise)

### Prerequisites

- Kubernetes cluster (1.26+)
- kubectl configured
- Helm 3.x

### Create secrets

```bash
kubectl create secret generic caloron-secrets \
  --from-literal=ANTHROPIC_API_KEY="sk-ant-..." \
  --from-literal=GOOGLE_API_KEY="..." \
  --from-literal=GITEA_TOKEN="..." \
  --from-literal=POSTGRES_PASSWORD="strongpassword"
```

### Deploy

```bash
cd deploy/k8s

# Default: 1 coordinator, 2 workers, Gitea, Postgres
helm install caloron .

# Custom: 5 workers, auto-scale to 20
helm install caloron . \
  --set worker.replicas=5 \
  --set worker.maxReplicas=20

# Bring your own Gitea/GitHub
helm install caloron . \
  --set gitea.enabled=false \
  --set config.giteaUrl=https://gitea.company.com
```

### Architecture

```
┌─────────────────────────────────────────────┐
│  Kubernetes Cluster                         │
│                                             │
│  ┌─────────────┐    ┌──────────────────┐   │
│  │ Coordinator │    │  Workers (HPA)   │   │
│  │ Deployment  │───→│  2-10 replicas   │   │
│  │ (1 replica) │    │  caloron-shell   │   │
│  └─────────────┘    └──────────────────┘   │
│         │                    │              │
│         ▼                    ▼              │
│  ┌─────────────┐    ┌──────────────────┐   │
│  │   Gitea     │    │    Postgres      │   │
│  │ StatefulSet │    │  StatefulSet     │   │
│  │  + PVC      │    │   + PVC         │   │
│  └─────────────┘    └──────────────────┘   │
│                                             │
│  NetworkPolicy: workers can only reach      │
│  Gitea + Postgres + LLM APIs (port 443)    │
└─────────────────────────────────────────────┘
```

### Monitoring

Workers expose `/health` and `/status` endpoints for liveness/readiness probes.

The coordinator logs all sprint events to stdout (visible via `kubectl logs`).

### Uninstall

```bash
helm uninstall caloron
kubectl delete pvc --selector app=gitea
kubectl delete pvc --selector app=postgres
```
