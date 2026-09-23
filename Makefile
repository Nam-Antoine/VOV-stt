# vn-stt-corpus — targets named in CLAUDE.md.
#   make dev      start db + api + worker + caddy (and the Vite dev server hint)
#   make test     backend unit tests (verbatim gate lives here)
#   make pilot    run the §4.3 sweep and write pilot/RESULTS.md
#   make deploy   git pull + rebuild + migrate on the VPS
#   make export EP=<slug>   regenerate every export for one episode

SHELL := /bin/bash
COMPOSE ?= docker compose
PY ?= python3
BACKEND := backend
WEB := web
VENV := $(BACKEND)/.venv
DEMO_DIR := $(WEB)/public/demo
VENV_PY := $(VENV)/bin/python

.DEFAULT_GOAL := help
.PHONY: help env models dev dev-down dev-logs install install-backend install-web \
        test test-backend lint migrate revision seed pilot build deploy export \
        backfill fmt clean demo models-verify run

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.env:
	@cp .env.example .env
	@echo ".env created from .env.example — edit SECRET_KEY before deploying."

env: .env ## Create .env from .env.example if missing

# ---------------------------------------------------------------------------
# Models (PLAN §11 T0) — idempotent; safe to re-run.
# ---------------------------------------------------------------------------
models: ## Download ASR + VAD + diarization + punctuation models into ./models
	$(PY) scripts/download_models.py --dest models

models-verify: ## Re-check sha256s in models/MANIFEST.json without downloading
	$(PY) scripts/download_models.py --dest models --verify-only

# ---------------------------------------------------------------------------
# Local dev
# ---------------------------------------------------------------------------
install: install-backend install-web ## Install backend + frontend deps

install-backend: ## Create backend venv and install the package (editable)
	$(PY) -m venv $(VENV) 2>/dev/null || true
	$(VENV_PY) -m pip install -q --upgrade pip
	$(VENV_PY) -m pip install -e "$(BACKEND)[dev]"

install-web: ## npm install for the frontend
	cd $(WEB) && npm install

dev: .env ## Bring up db + api + worker + caddy (and migrate)
	$(COMPOSE) up -d --build db api worker caddy
	@echo "applying migrations..."
	@$(COMPOSE) exec -T api alembic upgrade head
	@$(COMPOSE) restart worker
	@$(COMPOSE) ps
	@echo ""
	@port=$$(grep -E '^HTTP_PORT=' .env | tail -1 | cut -d= -f2); port=$${port:-80}; \
	 echo "API      http://localhost:$$port/api/docs   (via caddy)"; \
	 echo "App      http://localhost:$$port/           (serves web/dist; run 'make build' after a UI change)"; \
	 echo "Frontend run 'cd web && npm run dev' for HMR on http://localhost:5173"

dev-down: ## Stop the stack
	$(COMPOSE) down

dev-logs: ## Tail all service logs
	$(COMPOSE) logs -f --tail=100

# ---------------------------------------------------------------------------
# Tests — CLAUDE.md rule 1: test_no_normalisation.py must stay green.
# ---------------------------------------------------------------------------
test: test-backend ## Run all tests

test-backend: ## Backend unit tests
	cd $(BACKEND) && $(PY) -m pytest -q app/tests

lint: ## Ruff check (skipped only when ruff is absent; a real failure fails)
	@cd $(BACKEND) && if $(PY) -c "import ruff" 2>/dev/null; then \
	  $(PY) -m ruff check app; \
	else echo "ruff not installed — skipped (CI runs it)"; fi

fmt: ## Ruff format
	cd $(BACKEND) && $(PY) -m ruff format app

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
migrate: ## alembic upgrade head (inside the api container)
	$(COMPOSE) run --rm api alembic upgrade head

revision: ## Create a migration: make revision M="add foo"
	$(COMPOSE) run --rm api alembic revision --autogenerate -m "$(M)"

seed: ## Seed the hotwords table (idempotent; also run by the initial migration)
	$(COMPOSE) run --rm api python -m app.seed

# ---------------------------------------------------------------------------
# Pilot (PLAN §4) — T2 gate. Needs a clip + reference.txt first.
# ---------------------------------------------------------------------------
pilot: ## Sweep §4.3 knobs and write pilot/RESULTS.md
	$(PY) pilot/run_pilot.py --clip pilot/clip_2min.wav --reference pilot/reference.txt \
	  --models models --out pilot/RESULTS.md

# ---------------------------------------------------------------------------
# Pipeline on one file, no web stack (PLAN §11 T1)
# ---------------------------------------------------------------------------
run: ## Transcribe one file: make run AUDIO=x.mp3 OUT=x.json
	@test -n "$(AUDIO)" -a -n "$(OUT)" || { \
	  echo "usage: make run AUDIO=x.mp3 OUT=x.json"; exit 1; }
	# --models is explicit: the default resolves relative to $(BACKEND), and the
	# models live at the repo root.
	cd $(BACKEND) && $(PY) -m app.pipeline.run \
	  --audio "$(abspath $(AUDIO))" \
	  --out "$(abspath $(OUT))" \
	  --models "$(abspath models)"

# ---------------------------------------------------------------------------
# Demo fixture for the Episode screen (web/public/demo, gitignored).
# Not client material: the audio is public sherpa-onnx test speech — see
# web/public/demo/README.md. --force is correct here and nowhere else: this
# fixture is disposable, unlike a real episode's raw JSON (PLAN §0.2).
# ---------------------------------------------------------------------------
demo: ## Regenerate web/public/demo/episode.json from episode.mp3
	@test -f $(DEMO_DIR)/episode.mp3 || { \
	  echo "missing $(DEMO_DIR)/episode.mp3 — see $(DEMO_DIR)/README.md"; exit 1; }
	cd $(BACKEND) && $(PY) -m app.pipeline.run \
	  --audio "$(abspath $(DEMO_DIR)/episode.mp3)" \
	  --out "$(abspath $(DEMO_DIR)/episode.json)" \
	  --models "$(abspath models)" \
	  --work-dir "$(abspath $(DEMO_DIR))" \
	  --force

# ---------------------------------------------------------------------------
# Build / deploy
# ---------------------------------------------------------------------------
build: ## Build the frontend into web/dist (served by caddy)
	cd $(WEB) && npm run build

deploy: ## VPS deploy (PLAN §11 T5)
	git pull
	$(COMPOSE) build
	$(COMPOSE) up -d
	$(COMPOSE) run --rm api alembic upgrade head

export: ## Regenerate every export for one episode: make export EP=<slug>
	@test -n "$(EP)" || (echo "usage: make export EP=<slug>" && exit 1)
	$(COMPOSE) run --rm api python -m app.exports --episode "$(EP)"

backfill: ## Enqueue transcribe jobs for audio with no transcript
	$(COMPOSE) run --rm api python scripts/backfill.py

clean: ## Remove build output and caches (never touches /data or models/)
	rm -rf $(WEB)/dist $(WEB)/node_modules/.vite
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name '.pytest_cache' -type d -prune -exec rm -rf {} +
