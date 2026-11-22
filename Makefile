# The fleet's gate (reverse-proxy make/fleet.mk, which includes the checkout
# guard): `make deploy` runs checkout-guard and fleet-check against this repo's
# fleet.yml first, and `make install-units` links deploy units (UNIT-1).
# Optional include: CI and other machines have no reverse-proxy checkout, and a
# plain include would stop make before any target runs. Without it, deploy
# refuses rather than running ungated.
FLEET_MK := $(HOME)/dev/reverse-proxy/make/fleet.mk
-include $(FLEET_MK)
ifeq ($(wildcard $(FLEET_MK)),)
_FLEET_SAVED_GOAL := $(.DEFAULT_GOAL)
.PHONY: fleet-missing
fleet-missing:
	@echo "deploy refused: $(FLEET_MK) not found (no reverse-proxy checkout here)" >&2; exit 1
deploy install-units: fleet-missing
.DEFAULT_GOAL := $(_FLEET_SAVED_GOAL)
endif

APP     ?= birdhouse
DOMAIN  ?= sgc.rayandhon.com
HOST    ?= $(APP).$(DOMAIN)
LOG_DIR ?= $(HOME)/$(APP)-logs

.PHONY: deploy preview logs stop

deploy:
	mkdir -p $(LOG_DIR)
	COMPOSE_PROJECT_NAME=$(APP) \
	SERVICE_HOST=$(HOST) \
	BIRDHOUSE_LOG_DIR=$(LOG_DIR) \
	GIT_SHA=$$(git rev-parse --short HEAD) \
	BUILD_TIME=$$(date -u +%Y-%m-%dT%H:%M:%SZ) \
	docker compose up -d --build --wait
	@$(FLEET_PROBE)

preview:
	mkdir -p $(HOME)/$(APP)-preview-logs
	COMPOSE_PROJECT_NAME=$(APP)-preview \
	SERVICE_HOST=$(APP)-preview.$(DOMAIN) \
	BIRDHOUSE_LOG_DIR=$(HOME)/$(APP)-preview-logs \
	docker compose up -d --build

logs:
	docker compose -p $(APP) logs -f

stop:
	docker compose -p $(APP) down
