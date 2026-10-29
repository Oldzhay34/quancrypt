SHELL := /bin/bash
.DEFAULT_GOAL := help

# Python used for verification (D-48: the image has 3.12.15, the development machine 3.12.x).
PYTHON ?= 3.12
UV ?= uv
IMAGE ?= ingest-api:1.0.0
PORT ?= 8084
# The environment file the corpus command line reads (the user's own .env; Claude Code never reads it, D-55).
ENV_FILE ?= ../.env
ARGS ?= --help

# Tools come from the pinned requirements (D-28); nothing is installed into the system Python. The package lives in src/.
RUN := PYTHONPATH=src $(UV) run --python $(PYTHON) --no-project --with-requirements requirements-dev.txt

.PHONY: help compile verify run image e2e corpus

help: ## Hedefleri listeler
	@echo "data-platform Makefile"
	@echo
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z0-9-]+):.*## (.*)$$/  make \1\t\2/'

compile: ## requirements.in dosyasından requirements.txt dosyasını derler (uv pip compile)
	$(UV) pip compile requirements.in -o requirements.txt --python-version 3.12 --no-header

verify: ## ruff, mypy --strict, import-linter, pytest (birim, sözleşme ve gerçek PostgreSQL entegrasyonu; Docker kapalıysa başarısız olur) ve domain+usecase kapsamı >= %75
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy
	$(RUN) lint-imports
	$(RUN) coverage run -m pytest -m "not e2e"
	$(RUN) coverage report --include="*/domain/*,*/usecase/*" --fail-under=75

run: ## ingest-api'yi yerelde çalıştırır (127.0.0.1:$(PORT)); ortamda WAREHOUSE_DB_* ve INTERNAL_SERVICE_TOKEN gerekir
	PYTHONPATH=src $(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt \
		python -m uvicorn quancrypt_data.api.ingest:app --host 127.0.0.1 --port $(PORT) --no-access-log --timeout-graceful-shutdown 30

image: ## Docker imajını üretir; build bağlamı depo kökü (olay şemaları contracts/ altından), sır girmez
	docker build -f Dockerfile -t $(IMAGE) ..

corpus: ## Korpus komut satırı (host'ta; ENV_FILE içindeki değişkenlerle): make corpus ARGS="corpus clone --offset 0 --limit 25"
	@test -f "$(ENV_FILE)" || { echo "HATA: $(ENV_FILE) yok (ENV_FILE=... ile başka dosya verilebilir)"; exit 1; }
	set -a && . "$(ENV_FILE)" && set +a && PYTHONPATH=src $(UV) run --python $(PYTHON) --no-project --with-requirements requirements-corpus.txt \
		python -m quancrypt_data.api.cli $(ARGS)

e2e: ## Uçtan uca test (P6.1): çalışan yığın ister (postgres, core-service, ingest-api; geçici compose, bkz. README); make verify dışında
	$(RUN) pytest -m e2e -p no:cacheprovider
