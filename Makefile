SHELL := /bin/bash
.DEFAULT_GOAL := help

# Her birinin altında Makefile'ı olan dizinler doğrulanır (docker-local skill'i, bölüm 3).
VERIFY_DIRS := $(wildcard services/*) $(wildcard apps/*) data-platform ml

# Ek profiller: make up PROFILES="app data". `postgres` profilsizdir, her zaman kalkar (D-53).
PROFILES ?=
ENV_FILE ?= .env
COMPOSE := docker compose --env-file "$(ENV_FILE)" $(foreach p,$(PROFILES),--profile $(p))

.PHONY: help up down ps logs db-reset verify-all check-env

help: ## Hedefleri listeler
	@echo "Quancrypt kök Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

# Fail-closed (D-57): .env yoksa veya hâlâ CHANGE_ME yer tutucusu içeriyorsa hiçbir şey başlamaz.
# Yalnızca anahtar adları yazdırılır, değerler yazdırılmaz.
check-env:
	@if [ ! -f "$(ENV_FILE)" ]; then \
	  echo "HATA: $(ENV_FILE) yok. 'cp .env.example .env' ile oluşturup CHANGE_ME değerlerini doldurun."; exit 1; \
	fi
	@keys="$$(tr -d '\r' < "$(ENV_FILE)" | sed -nE "s/^[[:space:]]*(export[[:space:]]+)?([A-Za-z0-9_]+)[[:space:]]*=[[:space:]]*[\"']?CHANGE_ME[\"']?[[:space:]]*$$/\2/p")"; \
	if [ -n "$$keys" ]; then \
	  echo "HATA: $(ENV_FILE) içinde CHANGE_ME yer tutucusu olan anahtarlar var:"; echo "$$keys" | sed 's/^/  /'; exit 1; \
	fi

up: check-env ## Servisleri başlatır ve healthy olmalarını bekler: make up PROFILES="app data"
	$(COMPOSE) up -d --wait

down: ## Servisleri durdurur (volume'leri silmez): make down PROFILES="app data"
	$(COMPOSE) down

ps: ## Servis durumunu listeler: make ps PROFILES="app data"
	$(COMPOSE) ps

logs: ## Logları izler: make logs S=<servis> (S verilmezse hepsi)
	$(COMPOSE) logs -f --tail=200 $(S)

db-reset: ## Volume'leri SİLER (tüm veritabanı verisi gider); önce onay ister
	@echo "UYARI: Bu komut pgdata dahil tüm compose volume'lerini ve içindeki veriyi siler."
	@read -r -p "Devam etmek için 'evet' yazın: " answer; \
	if [ "$$answer" != "evet" ]; then echo "İptal edildi."; exit 1; fi; \
	$(COMPOSE) down -v

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
