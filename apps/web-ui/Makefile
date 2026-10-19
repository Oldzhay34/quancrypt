SHELL := /bin/bash
.DEFAULT_GOAL := help

# The UI is built and tested with the Node version of docs/VERSIONS.md (.nvmrc). A non-interactive shell may find an older
# system Node, so nvm is loaded when it exists.
NVM_LOAD := export NVM_DIR="$${NVM_DIR:-$$HOME/.nvm}"; [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh" && nvm use >/dev/null 2>&1 || true

.PHONY: help install verify run image gen-api

help: ## Hedefleri listeler
	@echo "apps/web-ui Makefile"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)$$/  make \1\t\2/'

install: ## Bağımlılıkları package-lock.json'a göre kurar (npm ci)
	@$(NVM_LOAD); npm ci

verify: ## Biçim, lint, tip denetimi ve birim testleri (npm run verify)
	@$(NVM_LOAD); npm run verify

run: ## Geliştirme sunucusu: http://127.0.0.1:8080/#token=<.quancrypt/session.token>
	@$(NVM_LOAD); npm run dev

gen-api: ## contracts/openapi dosyalarından API tiplerini yeniden üretir
	@$(NVM_LOAD); npm run gen:api

image: ## Docker imajını üretir (web-ui:1.0.0)
	docker build -t web-ui:1.0.0 .
