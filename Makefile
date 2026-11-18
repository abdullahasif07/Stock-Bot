.PHONY: help install dev backend frontend test build docker-build docker-run prebuild clean

VENV   ?= .venv
PY     := $(VENV)/bin/python
PORT   ?= 8001

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[33m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install backend + frontend dependencies
	test -d $(VENV) || python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements-dev.txt
	cd react-frontend && npm install
	test -f .env || cp .env.example .env

backend: ## Run the API with auto-reload on :$(PORT) (default 8001)
	$(VENV)/bin/uvicorn backend.main:app --reload --port $(PORT)

frontend: ## Run the Vite dev server on :5173 (proxies /api to the backend)
	cd react-frontend && VITE_DEV_API=http://localhost:$(PORT) npm run dev

dev: ## Run backend and frontend together
	@trap 'kill 0' INT TERM EXIT; $(MAKE) backend & $(MAKE) frontend & wait

test: ## Run backend tests
	$(PY) -m pytest

build: ## Build the frontend into react-frontend/dist (served by FastAPI)
	cd react-frontend && npm run build

prebuild: ## Download the embedding model and pre-index popular 10-Ks
	$(PY) -m backend.scripts.prebuild

docker-build: ## Build the production image
	docker build -t stockbot .

docker-run: ## Run the production image on :8000 using .env
	docker run --rm -p 8000:8000 --env-file .env stockbot

clean: ## Remove caches and build output (keeps downloaded models/indexes)
	find . -type d -name __pycache__ -not -path "./$(VENV)/*" -prune -exec rm -rf {} +
	rm -rf react-frontend/dist .pytest_cache backend/data/cache
