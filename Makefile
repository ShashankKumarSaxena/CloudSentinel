.PHONY: help setup setup-dev demo dev test check format format-check smoke train-model create-admin preflight docker-config
PROJECT_PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

help:
	@printf 'CloudSentinel\n\nmake setup         Install demo dependencies\nmake setup-dev     Install production SDKs and developer tools\nmake create-admin  Create the first local administrator\nmake demo          Build and serve the offline demo on :8000\nmake dev           Run API and Vite development servers\nmake format        Format Python and frontend source\nmake check         Check formatting, tests, types, and build\nmake preflight     Check current configuration without cloud access\nmake smoke         Inspect a running local server\nmake docker-config Validate demo and production Compose files\n'
setup:
	bash scripts/setup.sh
setup-dev:
	bash scripts/setup.sh --dev
demo:
	bash scripts/demo.sh
dev:
	bash scripts/dev.sh
test:
	$(PROJECT_PYTHON) -m unittest discover -s backend/tests -v
format:
	$(PROJECT_PYTHON) -m black backend scripts
	npm --prefix frontend run format
format-check:
	$(PROJECT_PYTHON) -m black --check backend scripts
	npm --prefix frontend run format:check
check: format-check test
	npm --prefix frontend run check
	npm --prefix frontend run build
preflight:
	$(PROJECT_PYTHON) scripts/preflight.py
smoke:
	$(PROJECT_PYTHON) scripts/smoke_test.py
train-model:
	$(PROJECT_PYTHON) scripts/train_model.py
create-admin:
	$(PROJECT_PYTHON) scripts/manage_users.py create-admin
docker-config:
	docker compose config --quiet
	docker compose -f deploy/production/compose.yaml config --quiet
