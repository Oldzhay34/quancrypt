SHELL := /bin/bash
.DEFAULT_GOAL := help

PYTHON ?= 3.12
UV ?= uv
# The environment file the command line reads (the user's own .env; Claude Code never reads it, D-55).
ENV_FILE ?= ../.env
ARGS ?= --help

RUN := PYTHONPATH=src $(UV) run --python $(PYTHON) --no-project --with-requirements requirements-dev.txt

.PHONY: help compile verify ml scope-dataset

help: ## Hedefleri listeler
	@echo "ml Makefile"
	@echo
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z0-9-]+):.*## (.*)$$/  make \1\t\2/'

compile: ## requirements.in dosyasından requirements.txt dosyasını derler (uv pip compile)
	$(UV) pip compile requirements.in -o requirements.txt --python-version 3.12 --no-header

verify: ## ruff, mypy --strict, import-linter, pytest (birim, sözleşme, gerçek PostgreSQL; Docker kapalıysa başarısız olur) ve domain+usecase kapsamı >= %75
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy
	$(RUN) lint-imports
	$(RUN) coverage run -m pytest -m "not ollama"
	$(RUN) coverage report --include="*/domain/*,*/usecase/*" --fail-under=75

ollama-check: ## Yerel Ollama'daki embedding modeliyle tek gömme denemesi (P7.3; make verify dışında)
	$(RUN) pytest -m ollama

ml: ## ml komut satırı (host'ta; ENV_FILE içindeki değişkenlerle): make ml ARGS="label-export"
	@test -f "$(ENV_FILE)" || { echo "HATA: $(ENV_FILE) yok (ENV_FILE=... ile başka dosya verilebilir)"; exit 1; }
	set -a && . "$(ENV_FILE)" && set +a && PYTHONPATH=src $(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt \
		python -m quancrypt_ml.api.cli $(ARGS)

scope-dataset: ## Kapsam veri setini şablonlardan yeniden üretir (scripts/build_scope_dataset.py) ve böler (ml scope-split)
	PYTHONPATH=src $(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt python scripts/build_scope_dataset.py
	PYTHONPATH=src $(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt python -m quancrypt_ml.api.cli scope-split
