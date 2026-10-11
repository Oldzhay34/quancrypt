SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help verify

help: ## Hedefleri listeler
	@echo "analyzer-service Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

verify: ## Checkstyle, SpotBugs, ArchUnit, birim ve sözleşme testleri (yol güvenliği dahil) ve JaCoCo (domain ve usecase satır kapsamı >= %75)
	./gradlew check
