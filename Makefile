# The author's deployment, on the box it runs on: the include below brings in
# its deploy targets from outside this repo. Elsewhere it finds nothing, so
# `make test` and `make run` work and `make deploy` refuses.
FLEET_MK := $(HOME)/dev/reverse-proxy/make/fleet.mk
-include $(FLEET_MK)
ifeq ($(wildcard $(FLEET_MK)),)
_FLEET_SAVED_GOAL := $(.DEFAULT_GOAL)
.PHONY: fleet-missing
fleet-missing:
	@echo "deploy: there is no deployment here; run it yourself with make run (README, Running it yourself)" >&2; exit 1
deploy install-units: fleet-missing
.DEFAULT_GOAL := $(_FLEET_SAVED_GOAL)
endif

.PHONY: test run

test:
	uv run --extra dev pytest -q

# Run it yourself, in Docker: http://127.0.0.1:8090 (compose.override.yml).
# Needs a .env (cp .env.example .env, then set the two BirdNET-Go paths). Its
# own compose project, with only this repo's compose files, so it can't take
# over a deployment's container on the same host.
run:
	mkdir -p logs
	env -u COMPOSE_FILE \
	COMPOSE_PROJECT_NAME=birdhouse-local \
	BIRDHOUSE_LOG_DIR=./logs \
	GIT_SHA=$$(git rev-parse --short HEAD) \
	BUILD_TIME=$$(date -u +%Y-%m-%dT%H:%M:%SZ) \
	docker compose up --build
