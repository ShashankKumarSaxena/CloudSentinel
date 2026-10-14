.PHONY: help setup demo dev test check smoke git-init train-model create-admin docker-config
PROJECT_PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

help:
	@printf 'CloudSentinel Phase 3\n\nmake setup        Install dependencies\nmake create-admin Create the first administrator interactively\nmake demo         Build and serve the local workspace on :8000\nmake dev          Run API + Vite development mode\nmake test         Run isolated backend tests\nmake check        Run tests, TypeScript, and production build\nmake smoke        Check the running local application\nmake train-model  Train and evaluate the activity model\nmake docker-config Validate the Compose package\nmake git-init     Initialize and commit locally\n'
setup:
	bash scripts/setup.sh
demo:
	bash scripts/demo.sh
dev:
	bash scripts/dev.sh
test:
	$(PROJECT_PYTHON) -m unittest discover -s backend/tests -v
check: test
	npm --prefix frontend run check
	npm --prefix frontend run build
smoke:
	$(PROJECT_PYTHON) scripts/smoke_test.py
git-init:
	bash scripts/init-git.sh
train-model:
	$(PROJECT_PYTHON) scripts/train_model.py
create-admin:
	$(PROJECT_PYTHON) scripts/manage_users.py create-admin
docker-config:
	docker compose config --quiet
