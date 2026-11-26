# Road Intelligence Platform

An AI-powered urban road intelligence system that ingests sensor telemetry, detects road defects, monitors parking occupancy via ANPR cameras, and surfaces actionable insights through a real-time dashboard.

---

## Architecture Overview

The platform is built across five logical layers:

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 5 — Presentation                                         │
│  React + MapLibre dashboard  |  Grafana monitoring              │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4 — API Gateway                                          │
│  FastAPI backend  |  Nginx reverse proxy                        │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3 — Intelligence Services                                │
│  Perception pipeline  |  Parking ANPR service  |  MLflow        │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2 — Data Storage                                         │
│  PostgreSQL + PostGIS  |  Redis cache                           │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1 — Observability                                        │
│  Prometheus scraping  |  Grafana dashboards  |  Alerting        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quickstart

### Prerequisites

| Tool | Minimum Version |
|------|----------------|
| Docker | 24.x |
| Docker Compose | v2.x (plugin) |
| Python | 3.11+ |
| Node.js | 20.x |
| make | any |

### Clone and start

```bash
git clone https://github.com/your-org/road-intelligence.git
cd road-intelligence

# Download ML model weights (required for the ANPR service)
make download-weights

# Build images and start the full stack
make dev
```

Open your browser:

| URL | Description |
|-----|-------------|
| http://localhost:3000 | Frontend dashboard |
| http://localhost:8000/docs | Backend API (Swagger UI) |
| http://localhost:8001/docs | Parking ANPR service |
| http://localhost:5000 | MLflow experiment tracking |
| http://localhost:9090 | Prometheus |
| http://localhost:3001 | Grafana |

---

## Services

| Service | Internal Host | External Port | Description |
|---------|--------------|---------------|-------------|
| **backend** | `backend:8000` | 8000 | FastAPI REST API |
| **frontend** | `frontend:80` | 3000 | React SPA (Nginx) |
| **parking_anpr** | `parking_anpr:8001` | 8001 | ANPR + occupancy service |
| **postgres** | `postgres:5432` | 5432 | PostgreSQL 16 + PostGIS 3.4 |
| **redis** | `redis:6379` | 6379 | Redis 7.2 cache |
| **mlflow** | `mlflow:5000` | 5000 | ML experiment tracking |
| **prometheus** | `prometheus:9090` | 9090 | Metrics collection |
| **grafana** | `grafana:3000` | 3001 | Dashboards & alerting |

---

## Project Structure

```
road-intelligence/
├── backend/                    # FastAPI application (Agent 2)
│   ├── alembic/                #   Database migrations
│   ├── backend/                #   Application package
│   │   ├── main.py             #     Application entry point
│   │   ├── routers/            #     API route handlers
│   │   ├── models/             #     SQLAlchemy ORM models
│   │   ├── schemas/            #     Pydantic request/response schemas
│   │   └── services/           #     Business logic layer
│   ├── tests/                  #   Unit tests
│   └── requirements.txt
├── frontend/                   # React dashboard (Agent 3)
│   ├── src/
│   │   ├── components/         #   Reusable UI components
│   │   ├── pages/              #   Route-level page components
│   │   ├── hooks/              #   Custom React hooks
│   │   └── api/                #   API client layer
│   └── package.json
├── services/
│   └── parking_anpr/           # ANPR microservice (Agent 5)
│       ├── anpr.py             #   License plate recognition
│       ├── detector.py         #   YOLO-based vehicle detector
│       ├── occupancy.py        #   Lot occupancy calculator
│       ├── pipeline.py         #   Processing pipeline
│       ├── models/             #   Model weight management
│       └── tests/
├── road_intelligence/          # Core ML library (Agent 1)
│   ├── perception.py           #   Road defect perception
│   ├── routing.py              #   Route optimisation
│   ├── sensor_fusion.py        #   Multi-sensor data fusion
│   └── traffic.py              #   Traffic flow modelling
├── infrastructure/             # DevOps (Agent 8)
│   ├── docker/                 #   Docker Compose + Dockerfiles
│   ├── k8s/                    #   Kubernetes manifests
│   └── monitoring/             #   Prometheus rules + Grafana dashboard
├── tests/
│   ├── integration/            #   End-to-end API tests
│   └── performance/            #   Locust load tests
├── .github/workflows/          #   CI/CD pipeline
├── Makefile                    #   Developer task runner
└── README.md
```

---

## API Endpoints

### Backend (port 8000)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health + dependency status |
| `POST` | `/ingest/telemetry` | Ingest a road event from sensor/mobile |
| `GET` | `/events/nearby` | Query events near a lat/lon (radius metres) |
| `GET` | `/events` | Query events by bounding box |
| `GET` | `/segments/` | List road segments near a location |
| `GET` | `/segments/{id}` | Get a specific road segment |
| `PUT` | `/segments/{id}/score` | Update road condition score |
| `POST` | `/parking/observations` | Record a parking occupancy observation |
| `GET` | `/parking/availability` | Get parking availability near a location |
| `GET` | `/metrics` | Prometheus metrics (scraped automatically) |

### Parking ANPR Service (port 8001)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health |
| `POST` | `/anpr/detect` | Run ANPR on uploaded image frame |
| `GET` | `/parking/lots` | List registered parking lots |
| `POST` | `/parking/lots` | Register a new parking lot |
| `GET` | `/metrics` | Prometheus metrics |

---

## Model Weights

The ANPR and road defect detection models are not committed to the repository. Download them before starting the stack:

```bash
make download-weights
```

This runs `services/parking_anpr/models/download_weights.py`, which downloads:

| Model | File | Size | Usage |
|-------|------|------|-------|
| YOLOv11-nano | `yolo11n.pt` | ~6 MB | Vehicle detection |
| YOLOv11-nano-seg | `yolo11n-seg.pt` | ~7 MB | Segmentation |

Weights are stored in `models/` and also mounted as a Docker volume (`model-weights`) for the `parking_anpr` container.

If the download fails at build time, mount the weights directory manually:

```bash
# Copy weights into the named volume
docker run --rm -v road_model-weights:/dst \
  -v $(pwd)/models:/src alpine cp /src/*.pt /dst/
```

## Licensed Dashcam Replay

The Driver HUD supports frame-by-frame replay of a user-selected local video. It does not retain the video or uploaded frames; only normalized detection events are published. See [dashcam replay guidance](docs/dashcam-replay.md) for the model, privacy controls, and local setup.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://roaduser:roadpass@postgres:5432/roadintelligence` | PostgreSQL async DSN |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `APP_ENV` | `production` | Runtime environment (`development`, `test`, `production`) |
| `LOG_LEVEL` | `info` | Log verbosity (`debug`, `info`, `warning`, `error`) |
| `MODEL_WEIGHTS_DIR` | `/app/weights` | Path to YOLO model weights inside the container |
| `TEST_API_URL` | `http://localhost:8000` | Base URL for integration and load tests |
| `GF_SECURITY_ADMIN_PASSWORD` | `roadintelligence2024` | Grafana admin password |

For local development, copy `.env.example` to `.env` and edit as needed:

```bash
cp .env.example .env
```

---

## Testing

### Unit tests

```bash
# All unit tests (backend + ANPR service)
make test

# Backend tests only
make test-backend

# ANPR service tests only (model-dependent tests skipped)
make test-anpr

# With coverage report
make test-coverage
```

### Integration tests

Requires the full stack to be running.

```bash
make dev-detached        # Start stack in background
make test-integration    # Run integration test suite
make down                # Stop stack
```

### Load / performance tests

```bash
# Headless 60-second run with 200 users
make test-performance

# Interactive Locust web UI at http://localhost:8089
locust -f tests/performance/locustfile.py --host http://localhost:8000
```

---

## Development

### Running locally (without Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn backend.main:app --reload --port 8000

# Frontend
cd frontend
npm ci
npm run dev      # Vite dev server on port 5173

# Parking ANPR service
cd services/parking_anpr
pip install -r requirements.txt
uvicorn parking_anpr_service:app --reload --port 8001
```

### Code style

```bash
make lint        # Flake8 (Python) + ESLint (TypeScript)
make format      # Black + isort (Python)
make typecheck   # mypy (Python)
```

### Database migrations

```bash
# Create a new migration (from inside the backend container or venv)
alembic revision --autogenerate -m "describe your change"

# Apply all pending migrations
make migrate

# Roll back one migration
make migrate-down
```

---

## Deployment: Kubernetes

### Prerequisites

- A Kubernetes cluster (1.28+)
- `kubectl` configured and pointing at your cluster
- Container images pushed to a registry accessible from the cluster

### Apply manifests

```bash
make k8s-apply
```

This applies the manifests in `infrastructure/k8s/` in dependency order:
1. `namespace.yaml` — creates the `road-intelligence` namespace
2. `postgres-deployment.yaml` — PostgreSQL/PostGIS + 5 Gi PVC
3. `backend-deployment.yaml` — 2-replica backend + HPA (2–8 pods at 70% CPU)
4. `frontend-deployment.yaml` — 2-replica frontend + LoadBalancer + Ingress

### Add the local hosts entry

```bash
echo "127.0.0.1 road-intelligence.local" | sudo tee -a /etc/hosts
```

Then visit: http://road-intelligence.local

### Tear down

```bash
make k8s-delete
```

---

## Monitoring

| Dashboard | URL | Credentials |
|-----------|-----|-------------|
| Grafana | http://localhost:3001 | admin / roadintelligence2024 |
| Prometheus | http://localhost:9090 | — |

Import the dashboard from `infrastructure/monitoring/grafana_dashboard.json` via **Grafana → Dashboards → Import**.

Alerting rules are defined in `infrastructure/monitoring/alerting_rules.yml` and loaded by Prometheus automatically via the Docker Compose volume mount.

---

## CI / CD

The GitHub Actions workflow in `.github/workflows/ci.yml` runs on every push and pull request:

1. **test-backend** — spins up PostgreSQL + Redis service containers, runs pytest
2. **test-parking-anpr** — runs ANPR unit tests (model-dependent tests excluded)
3. **test-frontend** — `npm ci`, lint, build
4. **build-and-push** — builds and pushes Docker images to GHCR (main branch only)

---

## Contributing

1. Fork the repository and create a feature branch from `main`.
2. Follow the per-agent folder structure described above.
3. Run `make lint` and `make test` before opening a pull request.
4. Write or update tests for every changed behaviour.
5. Keep pull requests focused — one concern per PR.
6. Update this README if you add new services, environment variables, or endpoints.

For questions or design discussions, open a GitHub Discussion before starting significant work.

---

*Built with Python 3.11 · FastAPI · PostgreSQL/PostGIS · Redis · React · Docker · Kubernetes*
