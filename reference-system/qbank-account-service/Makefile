SHELL := /bin/bash
.DEFAULT_GOAL := help

IMAGE ?= qbank-account-service:1.0.0
# Demo sertifika dizini (reference-system/certs/generate.sh üretir, git'e girmez).
CERTS_DIR ?= $(abspath ../certs/out)

.PHONY: help certs verify run image

help: ## Hedefleri listeler
	@echo "qbank-account-service Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

certs: ## Demo sertifikalarını üretir (varsa atlar; idempotent)
	@bash ../certs/generate.sh | tail -1

verify: certs ## Checkstyle, SpotBugs, ArchUnit, birim, sözleşme, API sözleşmesi ve mTLS testleri, JaCoCo
	QBANK_CERTS_DIR="$(CERTS_DIR)" ./gradlew check

run: certs ## Servisi yerelde çalıştırır (mTLS: 9444, sağlık: 127.0.0.1:9544)
	QBANK_CERTS_DIR="$(CERTS_DIR)" ./gradlew bootRun

image: ## Docker imajını üretir (sertifikalar imaja girmez; çalışırken /certs'e salt okunur bağlanır)
	docker build -t $(IMAGE) .
