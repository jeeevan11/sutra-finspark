SHELL := /bin/bash
PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip
API := http://localhost:8000/api

.PHONY: up down demo bench test deliverables export-sample-data venv dev-backend dev-frontend

up:
	docker compose up -d --build

down:
	docker compose down

## Start the live replay (backend must be up: `make up` or `make dev-backend`)
demo:
	@curl -sf -X POST $(API)/replay/start -H 'Content-Type: application/json' -d '{"speed": 20}' \
		&& echo "" && echo "Replay running at x20 — open http://localhost:3000"

venv:
	@test -d backend/.venv || python3 -m venv backend/.venv
	@$(PIP) install -q -r backend/requirements.txt

test: venv
	cd backend && .venv/bin/python -m pytest tests -q

bench: venv
	cd backend && .venv/bin/python -m bench.benchmark

deliverables: bench export-sample-data
	@echo "deliverables/ regenerated"

export-sample-data: venv
	cd backend && .venv/bin/python ../scripts/export_sample_data.py

dev-backend: venv
	cd backend && SUTRA_BUS=memory SUTRA_DATA_DIR=data .venv/bin/python -m uvicorn sutra.main:app --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev
