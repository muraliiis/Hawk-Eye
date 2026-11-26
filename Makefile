# ── Road Intelligence Platform — Makefile ─────────────────────────────────────
#
# Usage:
#   make dev            Start the full development stack
#   make down           Tear down containers and volumes
#   make test           Run all Python unit tests
#   make test-integration  Run integration tests (requires running stack)
#   make build          Build all Docker images
#   make migrate        Run database migrations
#   make download-weights  Download ML model weights
#   make lint           Lint backend Python and frontend TypeScript
#   make logs           Stream all container logs

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ── Paths ─────────────────────────────────────────────────────────────────────

COMPOSE_FILE := infrastructure/docker/docker-compose.yml
BACKEND_DIR  := backend
FRONTEND_DIR := frontend
SERVICES_DIR := services

# ── Colour helpers ────────────────────────────────────────────────────────────

CYAN  := \033[36m
RESET := \033[0m
BOLD  := \033[1m

# ── Default target: help ──────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "$(BOLD)Road Intelligence Platform$(RESET)"
	@echo ""
	@echo "$(CYAN)Development$(RESET)"
	@echo "  make dev              Start full stack (build + up)"
	@echo "  make down             Stop containers and remove volumes"
	@echo "  make logs             Stream logs from all containers"
	@echo "  make ps               Show running container status"
	@echo ""
	@echo "$(CYAN)Testing$(RESET)"
	@echo "  make test             Run all Python unit tests"
	@echo "  make test-integration Run integration tests (stack must be running)"
	@echo "  make test-performance Run Locust load test (headless, 60s)"
	@echo "  make test-backend     Run backend unit tests only"
	@echo "  make test-anpr        Run parking ANPR unit tests only"
	@echo ""
	@echo "$(CYAN)Building$(RESET)"
	@echo "  make build            Build all Docker images"
	@echo "  make build-backend    Build backend image only"
	@echo "  make build-frontend   Build frontend image only"
	@echo "  make build-anpr       Build parking ANPR image only"
	@echo ""
	@echo "$(CYAN)Database$(RESET)"
	@echo "  make migrate          Run Alembic migrations (upgrade head)"
	@echo "  make migrate-down     Rollback last migration"
	@echo "  make db-shell         Open psql shell in postgres container"
	@echo ""
	@echo "$(CYAN)ML Weights$(RESET)"
	@echo "  make download-weights Download ML model weights"
	@echo "  make check-weights    List model weight files with sizes"
	@echo ""
	@echo "$(CYAN)Code Quality$(RESET)"
	@echo "  make lint             Lint Python + TypeScript"
	@echo "  make lint-python      Lint Python only (flake8)"
	@echo "  make lint-frontend    Lint TypeScript only (eslint)"
	@echo "  make format           Format Python (black + isort)"
	@echo ""

# ── Development ───────────────────────────────────────────────────────────────

.PHONY: dev
dev:
	@echo "$(CYAN)Starting Road Intelligence Platform stack...$(RESET)"
	docker compose -f $(COMPOSE_FILE) up --build --remove-orphans

.PHONY: dev-detached
dev-detached:
	@echo "$(CYAN)Starting stack in background...$(RESET)"
	docker compose -f $(COMPOSE_FILE) up --build --remove-orphans -d
	@echo "Stack started. Use 'make logs' to watch container output."

.PHONY: down
down:
	@echo "$(CYAN)Stopping containers and removing volumes...$(RESET)"
	docker compose -f $(COMPOSE_FILE) down -v --remove-orphans

.PHONY: restart
restart:
	@echo "$(CYAN)Restarting all services...$(RESET)"
	docker compose -f $(COMPOSE_FILE) restart

.PHONY: ps
ps:
	docker compose -f $(COMPOSE_FILE) ps

.PHONY: logs
logs:
	docker compose -f $(COMPOSE_FILE) logs -f

.PHONY: logs-backend
logs-backend:
	docker compose -f $(COMPOSE_FILE) logs -f backend

.PHONY: logs-anpr
logs-anpr:
	docker compose -f $(COMPOSE_FILE) logs -f parking_anpr

# ── Testing ───────────────────────────────────────────────────────────────────

.PHONY: test
test:
	@echo "$(CYAN)Running all Python unit tests...$(RESET)"
	python -m pytest services/parking_anpr/tests/ -v --tb=short
	@echo "$(CYAN)All unit tests complete.$(RESET)"

.PHONY: test-backend
test-backend:
	@echo "$(CYAN)Running backend unit tests...$(RESET)"
	pytest $(BACKEND_DIR)/tests/ -v --tb=short -q

.PHONY: test-anpr
test-anpr:
	@echo "$(CYAN)Running parking ANPR unit tests (skipping model-dependent)...$(RESET)"
	pytest $(SERVICES_DIR)/parking_anpr/tests/ -v --tb=short \
		--ignore=$(SERVICES_DIR)/parking_anpr/tests/test_detector.py

.PHONY: test-integration
test-integration:
	@echo "$(CYAN)Running integration tests against $(TEST_API_URL)...$(RESET)"
	@echo "Make sure the stack is running: make dev-detached"
	TEST_API_URL=$${TEST_API_URL:-http://localhost:8000} \
		python -m pytest tests/integration/ -v --tb=short

.PHONY: test-performance
test-performance:
	@echo "$(CYAN)Running Locust performance test (60s, 200 users)...$(RESET)"
	locust -f tests/performance/locustfile.py \
		--host $${TEST_API_URL:-http://localhost:8000} \
		--users 200 \
		--spawn-rate 10 \
		--run-time 60s \
		--headless \
		--csv=tests/performance/results

.PHONY: test-coverage
test-coverage:
	@echo "$(CYAN)Running tests with coverage report...$(RESET)"
	pytest $(BACKEND_DIR)/tests/ \
		--cov=$(BACKEND_DIR) \
		--cov-report=html:coverage_html \
		--cov-report=term-missing \
		-v
	@echo "Coverage report generated at coverage_html/index.html"

# ── Building ──────────────────────────────────────────────────────────────────

.PHONY: build
build: build-backend build-frontend build-anpr
	@echo "$(CYAN)All images built.$(RESET)"

.PHONY: build-backend
build-backend:
	@echo "$(CYAN)Building backend image...$(RESET)"
	docker build \
		-f infrastructure/docker/Dockerfile.backend \
		-t road-intelligence/backend:latest \
		$(BACKEND_DIR)/

.PHONY: build-frontend
build-frontend:
	@echo "$(CYAN)Building frontend image...$(RESET)"
	docker build \
		-f infrastructure/docker/Dockerfile.frontend \
		-t road-intelligence/frontend:latest \
		$(FRONTEND_DIR)/

.PHONY: build-anpr
build-anpr:
	@echo "$(CYAN)Building parking ANPR image...$(RESET)"
	docker build \
		-f infrastructure/docker/Dockerfile.parking_anpr \
		-t road-intelligence/parking-anpr:latest \
		$(SERVICES_DIR)/parking_anpr/

# ── Database ──────────────────────────────────────────────────────────────────

.PHONY: migrate
migrate:
	@echo "$(CYAN)Running Alembic migrations (upgrade head)...$(RESET)"
	cd $(BACKEND_DIR) && alembic upgrade head

.PHONY: migrate-down
migrate-down:
	@echo "$(CYAN)Rolling back last Alembic migration...$(RESET)"
	docker compose -f $(COMPOSE_FILE) exec backend \
		alembic downgrade -1

.PHONY: migrate-history
migrate-history:
	docker compose -f $(COMPOSE_FILE) exec backend alembic history --verbose

.PHONY: db-shell
db-shell:
	@echo "$(CYAN)Opening psql shell in postgres container...$(RESET)"
	docker compose -f $(COMPOSE_FILE) exec postgres \
		psql -U roaduser -d roadintelligence

# ── ML Model Weights ──────────────────────────────────────────────────────────

.PHONY: download-weights
download-weights:
	@echo "$(CYAN)Downloading ML model weights...$(RESET)"
	python services/parking_anpr/models/download_weights.py

.PHONY: check-weights
check-weights:
	@echo "$(CYAN)Checking model weight files...$(RESET)"
	@echo "--- services/parking_anpr/models/ ---"
	@ls -lh $(SERVICES_DIR)/parking_anpr/models/ 2>/dev/null || echo "(directory empty or missing)"
	@echo "--- models/ ---"
	@ls -lh models/ 2>/dev/null || echo "(directory empty or missing)"

.PHONY: download-weights-container
download-weights-container:
	@echo "$(CYAN)Downloading weights inside parking_anpr container...$(RESET)"
	docker compose -f $(COMPOSE_FILE) exec parking_anpr \
		python models/download_weights.py --dest /app/weights

# ── Code Quality ──────────────────────────────────────────────────────────────

.PHONY: lint
lint:
	@echo "$(CYAN)Linting Python code (flake8)...$(RESET)"
	flake8 backend/ services/ \
		--max-line-length=100 \
		--exclude=__pycache__,*.egg-info,.git,migrations,alembic \
		--extend-ignore=E203,W503
	@echo "$(CYAN)Lint complete.$(RESET)"

.PHONY: lint-python
lint-python:
	@echo "$(CYAN)Linting Python code (flake8)...$(RESET)"
	flake8 $(BACKEND_DIR)/ $(SERVICES_DIR)/ \
		--max-line-length=100 \
		--exclude=__pycache__,*.egg-info,.git,migrations,alembic \
		--extend-ignore=E203,W503

.PHONY: lint-frontend
lint-frontend:
	@echo "$(CYAN)Linting frontend TypeScript (eslint)...$(RESET)"
	cd $(FRONTEND_DIR) && npm run lint

.PHONY: format
format:
	@echo "$(CYAN)Formatting Python (black + isort)...$(RESET)"
	black $(BACKEND_DIR)/ $(SERVICES_DIR)/ --line-length 100
	isort $(BACKEND_DIR)/ $(SERVICES_DIR)/ --profile black

.PHONY: format-check
format-check:
	@echo "$(CYAN)Checking Python formatting...$(RESET)"
	black $(BACKEND_DIR)/ $(SERVICES_DIR)/ --check --line-length 100
	isort $(BACKEND_DIR)/ $(SERVICES_DIR)/ --profile black --check-only

.PHONY: typecheck
typecheck:
	@echo "$(CYAN)Running mypy type checks...$(RESET)"
	mypy $(BACKEND_DIR)/ --ignore-missing-imports

# ── Kubernetes ────────────────────────────────────────────────────────────────

.PHONY: k8s-apply
k8s-apply:
	@echo "$(CYAN)Applying Kubernetes manifests...$(RESET)"
	kubectl apply -f infrastructure/k8s/namespace.yaml
	kubectl apply -f infrastructure/k8s/postgres-deployment.yaml
	kubectl apply -f infrastructure/k8s/backend-deployment.yaml
	kubectl apply -f infrastructure/k8s/frontend-deployment.yaml

.PHONY: k8s-delete
k8s-delete:
	@echo "$(CYAN)Deleting Kubernetes resources...$(RESET)"
	kubectl delete namespace road-intelligence --ignore-not-found

.PHONY: k8s-status
k8s-status:
	kubectl get all -n road-intelligence

# ── Housekeeping ──────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	@echo "$(CYAN)Cleaning up Python cache files...$(RESET)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	rm -rf coverage_html/ .pytest_cache/ .mypy_cache/
	@echo "Clean complete."

.PHONY: clean-docker
clean-docker:
	@echo "$(CYAN)Removing dangling Docker images and volumes...$(RESET)"
	docker image prune -f
	docker volume prune -f
