SHELL := /bin/bash
.DEFAULT_GOAL := help

# Python used for verification. `make verify PYTHON=3.10` checks the PYNQ-Z2 compatible minimum (uv downloads it).
PYTHON ?= 3.12
UV ?= uv
IMAGE ?= field-device-sim:1.0.0
# Demo sertifika dizini (reference-system/certs/generate.sh üretir, git'e girmez) ve Mosquitto yapılandırması.
CERTS_DIR ?= $(abspath ../certs/out)
MOSQUITTO_DIR ?= $(abspath ../mosquitto)

export PYTHONPATH := src
export QBANK_CERTS_DIR := $(CERTS_DIR)
export QBANK_MOSQUITTO_DIR := $(MOSQUITTO_DIR)

# Tools come from the pinned requirements (D-28); nothing is installed into the system Python.
RUN := $(UV) run --python $(PYTHON) --no-project --with-requirements requirements-dev.txt

.PHONY: help certs compile verify run image

help: ## Hedefleri listeler
	@echo "field-device-sim Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

certs: ## Demo sertifikalarını üretir (varsa atlar; idempotent)
	@bash ../certs/generate.sh | tail -1

compile: ## requirements.in dosyalarından requirements.txt dosyalarını derler (uv pip compile, Python 3.10 için)
	$(UV) pip compile requirements.in -o requirements.txt --python-version 3.10 --no-header
	$(UV) pip compile requirements-dev.in -o requirements-dev.txt --python-version 3.10 --no-header

verify: certs ## ruff, mypy --strict, import-linter, pytest (birim, sözleşme, mimari, Docker'lı entegrasyon) ve coverage (domain+usecase >= %75)
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy
	$(RUN) lint-imports
	$(RUN) coverage run -m pytest
	$(RUN) coverage report --include="*/domain/*,*/usecase/*" --fail-under=75

run: certs ## Simülatörü yerelde çalıştırır (Mosquitto ayrıca çalışmalıdır): make run TERMINAL=terminal-001 INTERVAL=5
	$(UV) run --python $(PYTHON) --no-project --with-requirements requirements.txt python -m field_device_sim run --terminal-id $(or $(TERMINAL),terminal-001) --interval $(or $(INTERVAL),5)

image: ## Docker imajını üretir (sertifikalar imaja girmez; çalışırken /certs'e salt okunur bağlanır)
	docker build -t $(IMAGE) .
