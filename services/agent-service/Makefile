SHELL := /bin/bash
.DEFAULT_GOAL := help

# Python used for verification (D-48: the image has 3.12.15, the development machine 3.12.x).
PYTHON ?= 3.12
UV ?= uv
IMAGE ?= agent-service:1.0.0
PORT ?= 8083

# Tools come from the pinned requirements (D-28); nothing is installed into the system Python.
RUN := $(UV) run --python $(PYTHON) --no-project --with-requirements requirements-dev.txt

.PHONY: help compile verify run image index index-force gen-contracts integration eval

help: ## Hedefleri listeler
	@echo "agent-service Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

compile: ## requirements.in dosyasından requirements.txt dosyasını derler (uv pip compile)
	$(UV) pip compile requirements.in -o requirements.txt --python-version 3.12 --no-header

verify: ## ruff, mypy --strict, import-linter ve pytest (Ollama'ya bağlı testler dahil; Ollama kapalıysa başarısız olur)
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy
	$(RUN) lint-imports
	$(RUN) pytest -m "not integration"

run: ## Servisi yerelde çalıştırır (127.0.0.1:$(PORT); Ollama adresi OLLAMA_BASE_URL, varsayılan 127.0.0.1:11434)
	$(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt \
		python -m uvicorn src.app.main:app --host 127.0.0.1 --port $(PORT) --no-access-log --timeout-graceful-shutdown 30

image: ## Docker imajını üretir; build bağlamı depo kökü (araç kontratları ve redaksiyon kuralları contracts/ altından), sır girmez
	docker build -f Dockerfile -t $(IMAGE) ../..

index: ## Bilgi tabanını indeksler (data/raw/*.md, yalnız status: approved; idempotent). Ortamda AGENT_DB_* parolaları ve çalışan Ollama gerekir
	PYTHONPATH=. $(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt \
		python scripts/build_index.py

index-force: ## Tüm onaylı notları yeniden gömer (embedding modeli veya boyutu değiştiyse); indexed_at güncellenir, idempotent değildir
	PYTHONPATH=. $(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt \
		python scripts/build_index.py --force

# Generated pydantic models of the service contracts (D-04: src/tools/contracts/; never edited by hand).
CODEGEN := $(RUN) datamodel-codegen --input-file-type openapi --output-model-type pydantic_v2.BaseModel \
	--target-python-version 3.12 --use-standard-collections --use-union-operator --disable-timestamp --use-double-quotes --field-constraints --use-annotated --formatters black isort

gen-contracts: ## contracts/openapi'den src/tools/contracts/ pydantic modellerini üretir (elle düzenlenmez)
	$(CODEGEN) --input ../../contracts/openapi/core-service.yaml --output src/tools/contracts/core_service.py
	$(CODEGEN) --allow-remote-refs --input ../../contracts/openapi/analyzer-service.yaml --output src/tools/contracts/analyzer_service

integration: ## Araç entegrasyon testleri: çalışan core-service ve analyzer-service ister (make verify dışında, D-238)
	$(RUN) pytest -m integration -p no:cacheprovider

eval: ## Değerlendirme (P4.7): çalışan yığın (app ve demo profili, PROJECT_ROOT=reference-system), Ollama ve ortamda AGENT_DB_*, INTERNAL_SERVICE_TOKEN, QUANCRYPT_SESSION_TOKEN gerekir; core-service'te yeni bir değerlendirme projesi açar; docs/eval_report.md ve docs/eval_results.jsonl yazar, bir hedef tutmaz veya ölçülemezse 3 ile biter
	PYTHONPATH=. $(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt \
		python scripts/evaluate.py
