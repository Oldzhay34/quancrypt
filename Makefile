SHELL := /bin/bash
.DEFAULT_GOAL := help

# Her birinin altında Makefile'ı olan dizinler doğrulanır (docker-local skill'i, bölüm 3).
VERIFY_DIRS := $(wildcard services/*) $(wildcard apps/*) data-platform ml

.PHONY: help up down ps logs verify-all

help: ## Hedefleri listeler
	@echo "Quancrypt kök Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

# TODO(P0.1-1): up, down, ps ve logs P0.3'te (docker-compose.yml ile birlikte) tanımlanacak.
up: ## docker compose ile servisleri başlatır (P0.3'te tanımlanacak)
	@echo "P0.3'te tanımlanacak"

down: ## docker compose ile servisleri durdurur (P0.3'te tanımlanacak)
	@echo "P0.3'te tanımlanacak"

ps: ## Çalışan servisleri listeler (P0.3'te tanımlanacak)
	@echo "P0.3'te tanımlanacak"

logs: ## Servis loglarını gösterir: make logs S=<servis> (P0.3'te tanımlanacak)
	@echo "P0.3'te tanımlanacak"

verify-all: ## Her servisin `make verify` hedefini sırayla çalıştırır ve özet basar
	@found=0; failed=0; summary=""; \
	for d in $(VERIFY_DIRS); do \
	  if [ -f "$$d/Makefile" ]; then \
	    found=1; \
	    echo "=== $$d: make verify"; \
	    if $(MAKE) -C "$$d" verify; then r="GEÇTİ"; else r="BAŞARISIZ"; failed=1; fi; \
	    summary="$$summary$$(printf '%-40s %s' "$$d" "$$r")\n"; \
	  fi; \
	done; \
	if [ "$$found" -eq 0 ]; then echo "henüz doğrulanacak servis yok"; exit 0; fi; \
	echo; echo "Özet"; printf "$$summary"; \
	exit $$failed
