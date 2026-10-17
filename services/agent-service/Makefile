SHELL := /bin/bash
.DEFAULT_GOAL := help

# Python used for verification (D-48: the image has 3.12.15, the development machine 3.12.x).
PYTHON ?= 3.12
UV ?= uv
IMAGE ?= agent-service:1.0.0
PORT ?= 8083

# Tools come from the pinned requirements (D-28); nothing is installed into the system Python.
RUN := $(UV) run --python $(PYTHON) --no-project --with-requirements requirements-dev.txt

.PHONY: help compile verify run image index index-force

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
	$(RUN) pytest

run: ## Servisi yerelde çalıştırır (127.0.0.1:$(PORT); Ollama adresi OLLAMA_BASE_URL, varsayılan 127.0.0.1:11434)
	$(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt \
		python -m uvicorn src.app.main:app --host 127.0.0.1 --port $(PORT) --no-access-log --timeout-graceful-shutdown 30

image: ## Docker imajını üretir (yapılandırma ve kod imaja girer; sır girmez)
	docker build -t $(IMAGE) .

index: ## Bilgi tabanını indeksler (data/raw/*.md, yalnız status: approved; idempotent). Ortamda AGENT_DB_* parolaları ve çalışan Ollama gerekir
	PYTHONPATH=. $(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt \
		python scripts/build_index.py

index-force: ## Tüm onaylı notları yeniden gömer (embedding modeli veya boyutu değiştiyse); indexed_at güncellenir, idempotent değildir
	PYTHONPATH=. $(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt \
		python scripts/build_index.py --force
