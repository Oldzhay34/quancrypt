SHELL := /bin/bash
.DEFAULT_GOAL := help

IMAGE ?= qbank-payment-service:1.0.0
# Demo sertifika dizini (reference-system/certs/generate.sh üretir, git'e girmez).
CERTS_DIR ?= $(abspath ../certs/out)

.PHONY: help certs verify run image

help: ## Hedefleri listeler
	@echo "qbank-payment-service Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

certs: ## Demo sertifikalarını üretir (varsa atlar; idempotent)
	@bash ../certs/generate.sh | tail -1

verify: certs ## Checkstyle, SpotBugs, ArchUnit, birim, sözleşme, mTLS/JWT, MQTT (Testcontainers) testleri, JaCoCo; Docker Desktop açık olmalı
	QBANK_CERTS_DIR="$(CERTS_DIR)" ./gradlew check

run: certs ## Servisi yerelde çalıştırır (mTLS: 9445, sağlık: 127.0.0.1:9545); hesap servisi ve Mosquitto ayrıca çalışmalıdır
	QBANK_CERTS_DIR="$(CERTS_DIR)" ./gradlew bootRun

image: ## Docker imajını üretir; build bağlamı reference-system/ dizinidir (sözleşme şeması için), certs/ bağlama girmez
	docker build -f Dockerfile -t $(IMAGE) ..
