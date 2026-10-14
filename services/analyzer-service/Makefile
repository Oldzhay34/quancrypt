SHELL := /bin/bash
.DEFAULT_GOAL := help

IMAGE ?= analyzer-service:1.0.0
# Ortam dosyası: run hedefi değişkenleri buradan alır (kullanıcının kendi .env dosyası; Claude Code okumaz, D-55).
ENV_FILE ?= ../../.env

.PHONY: help verify run image

help: ## Hedefleri listeler
	@echo "analyzer-service Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

verify: ## Checkstyle, SpotBugs, ArchUnit, birim, sözleşme ve QBank altın testleri, JaCoCo (domain ve usecase >= %75); önce reference-system'de 'bash certs/generate.sh' çalışmış olmalı
	./gradlew check

run: ## Servisi yerelde çalıştırır (127.0.0.1:8082): ENV_FILE içindeki INTERNAL_SERVICE_TOKEN ile; analiz kökü olarak PROJECT_ROOT izinlidir
	@test -f "$(ENV_FILE)" || { echo "HATA: $(ENV_FILE) yok (ENV_FILE=... ile başka dosya verilebilir)"; exit 1; }
	set -a && . "$(ENV_FILE)" && set +a && ANALYZER_ALLOWED_ROOTS="$${PROJECT_ROOT}" ./gradlew bootRun

image: ## Docker imajını üretir; build bağlamı depo kökü (sözlük ve redaksiyon kuralları contracts/ altından), .env ve anahtarlar bağlama girmez
	docker build -f Dockerfile -t $(IMAGE) ../..
