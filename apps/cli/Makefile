SHELL := /bin/bash
.DEFAULT_GOAL := help

PYTHON ?= 3.12
UV ?= uv

export PYTHONPATH := src

# Tools come from the pinned requirements (D-28); nothing is installed into the system Python.
RUN := $(UV) run --python $(PYTHON) --no-project --with-requirements requirements-dev.txt

.PHONY: help compile verify integration

help: ## Hedefleri listeler
	@echo "apps/cli Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

compile: ## requirements.in dosyalarından requirements.txt dosyalarını derler (uv pip compile)
	$(UV) pip compile requirements.in -o requirements.txt --python-version 3.12 --no-header
	$(UV) pip compile requirements-dev.in -o requirements-dev.txt --python-version 3.12 --no-header

verify: ## ruff, mypy --strict, import-linter ve pytest (birim, sözleşme, mimari; entegrasyon hariç) ve coverage (domain+usecase >= %75)
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy
	$(RUN) lint-imports
	$(RUN) coverage run -m pytest -m "not integration"
	$(RUN) coverage report --include="*/domain/*,*/usecase/*" --fail-under=75

integration: ## QBank kopyasında `quancrypt init` uçtan uca: Docker, derlenmiş imajlar ve QUANCRYPT_HOME (docker-compose.yml + .env) ister
	$(RUN) pytest -m integration -p no:cacheprovider
