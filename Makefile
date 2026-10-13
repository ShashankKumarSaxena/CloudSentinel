.PHONY: help setup demo dev test check smoke git-init train-model
PROJECT_PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

help:
	@printf 'CloudSentinel Phase 1\n\nmake setup     Install dependencies\nmake demo      Build and serve the local workspace on :8000\nmake dev       Run API + Vite development mode\nmake test      Run isolated backend tests\nmake check     Run tests, TypeScript, and production build\nmake smoke     Check the running application\nmake train-model  Train and evaluate the activity model\nmake git-init  Initialize and commit locally\n'
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
