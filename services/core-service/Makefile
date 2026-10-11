SHELL := /bin/bash
.DEFAULT_GOAL := help

IMAGE ?= core-service:1.0.0
# Ortam dosyası: run hedefi değişkenleri buradan alır (kullanıcının kendi .env dosyası; Claude Code okumaz, D-55).
ENV_FILE ?= ../../.env

.PHONY: help verify run image

help: ## Hedefleri listeler
	@echo "core-service Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

verify: ## Checkstyle, SpotBugs, ArchUnit, birim, sözleşme (kontrat, güvenlik, JDBC) ve entegrasyon testleri (Testcontainers; Docker Desktop açık olmalı), JaCoCo (domain ve usecase >= %75)
	./gradlew check

run: ## Servisi yerelde çalıştırır (127.0.0.1:8081): ENV_FILE içindeki değişkenlerle; postgres ayrıca çalışmalıdır (make up)
	@test -f "$(ENV_FILE)" || { echo "HATA: $(ENV_FILE) yok (ENV_FILE=... ile başka dosya verilebilir)"; exit 1; }
	set -a && . "$(ENV_FILE)" && set +a && CORE_DB_URL="$${CORE_DB_URL:-jdbc:postgresql://127.0.0.1:5432/core_db}" ./gradlew bootRun

image: ## Docker imajını üretir; build bağlamı depo kökü (redaksiyon kuralları contracts/ altından), .env ve anahtarlar bağlama girmez
	docker build -f Dockerfile -t $(IMAGE) ../..
