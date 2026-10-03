SHELL := /bin/bash
.DEFAULT_GOAL := help

UV := uv
PY := $(UV) run --project engine python
PYTEST := $(UV) run --project engine pytest
PLAYWRIGHT := pnpm --dir web exec playwright
COMPOSE := docker compose --project-name ncl-platform
NCL_CHROMIUM_USE_METAL ?= $(if $(filter Darwin,$(shell uname -s)),1,0)

.PHONY: help bootstrap bootstrap-test dev live stop repo-check contract-check engine-static
.PHONY: engine-unit engine-coverage engine-property engine-golden golden-update fixtures-record fixtures-diff
.PHONY: fixtures-check offline-check api-contract web-check integration e2e-desktop e2e-mobile
.PHONY: screenshots-check screenshots-update a11y perf perf-local compose-smoke ci

help:
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "%-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap: ## Install locked Python and web dependencies (not browsers).
	$(UV) sync --project engine --frozen --all-groups
	corepack enable
	@$(PY) tools/require_path.py package.json --owner web
	@$(PY) tools/require_path.py pnpm-lock.yaml --owner web
	pnpm install --frozen-lockfile

bootstrap-test: bootstrap ## Install the pinned Chromium browser after normal bootstrap.
	PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=120000 $(PLAYWRIGHT) install chromium

dev: bootstrap ## Start the offline replay engine on 4200 and Vite on 5173.
	NCL_MODE=replay NCL_ALLOW_LIVE=0 $(PY) tools/dev.py --mode replay

live: bootstrap ## Start explicit allowlisted live mode (requires NCL_ALLOW_LIVE=1).
	@test "$(NCL_ALLOW_LIVE)" = "1" || { echo "live mode requires NCL_ALLOW_LIVE=1" >&2; exit 2; }
	NCL_ALLOW_LIVE=1 $(PY) tools/dev.py --mode live

stop: ## Stop local development processes and the compose project without deleting state.
	$(PY) tools/dev.py --stop

repo-check: ## G1: repository layout, lock, boundary and fixture reproducibility.
	$(PY) tools/repo_check.py

contract-check: ## G2: OpenAPI/SSE schemas, examples and generated clients.
	@$(PY) tools/require_path.py contracts/validate.py --owner engine
	$(PY) contracts/validate.py
	@$(PY) tools/run_package_script.py web contract:check

engine-static: ## G3: Ruff formatting/lint and strict mypy.
	$(UV) run --project engine ruff format --check engine tools tests
	$(UV) run --project engine ruff check engine tools tests
	$(UV) run --project engine mypy --config-file engine/pyproject.toml --strict \
		engine/src engine/tests tools tests

engine-unit: ## G4: engine unit tests with denied external sockets (no coverage gate).
	$(PYTEST) engine/tests/unit --disable-socket --allow-hosts=127.0.0.1 -ra

engine-coverage: ## Whole-suite branch coverage (85%; critical policy modules 100%).
	mkdir -p .local/reports
	$(PYTEST) engine/tests/unit engine/tests/contract engine/tests/property engine/tests/golden \
		--disable-socket --allow-hosts=127.0.0.1 --cov=ncl_engine --cov-branch \
		--cov-report=term-missing --cov-report=json:.local/reports/engine-coverage.json \
		--cov-fail-under=85
	$(PY) tools/check_coverage.py .local/reports/engine-coverage.json

engine-property: ## G5: deterministic property tests and seed report.
	@$(PY) tools/require_path.py engine/tests/property --owner engine
	HYPOTHESIS_PROFILE=ci $(PYTEST) engine/tests/property -ra

engine-golden: ## G6: recompute and compare approved engine goldens.
	@$(PY) tools/require_path.py engine/tests/golden --owner engine
	$(PYTEST) engine/tests/golden -ra

golden-update: ## Regenerate exactly one named golden (CASE is required).
	@test -n "$(CASE)" || { echo "golden-update requires CASE=<name>" >&2; exit 2; }
	NCL_UPDATE_GOLDEN=1 $(PYTEST) engine/tests/golden -k "$(CASE)" -ra

fixtures-record: ## Record through the engine pipeline; CLOCK is the recording instant.
	@test -n "$(PRESET)" || { echo "fixtures-record requires PRESET=<slug>" >&2; exit 2; }
	@test -n "$(CLOCK)" || { echo "fixtures-record requires CLOCK=<ISO-UTC>" >&2; exit 2; }
	NCL_ALLOW_RECORD=1 $(PY) -m ncl_engine.fixtures record --preset "$(PRESET)" \
		--clock "$(CLOCK)" $(if $(FROZEN_AT),--frozen-at "$(FROZEN_AT)",) \
		$(if $(filter 1,$(RESUME)),--resume,)

fixtures-diff: ## Show a semantic fixture diff (PRESET is required).
	@test -n "$(PRESET)" || { echo "fixtures-diff requires PRESET=<slug>" >&2; exit 2; }
	$(PY) -m ncl_engine.fixtures diff --preset "$(PRESET)"

fixtures-check: ## G7: fixture schemas, hashes, replay, lineage and byte budgets.
	$(PY) -m ncl_engine.fixtures check

offline-check: ## G8: fixture replay under dead proxies and socket denial.
	HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 \
	ALL_PROXY=http://127.0.0.1:9 NO_PROXY=127.0.0.1,localhost \
	$(PY) -m ncl_engine.fixtures check
	HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 \
	ALL_PROXY=http://127.0.0.1:9 NO_PROXY=127.0.0.1,localhost \
	$(PYTEST) tests/offline engine/tests/unit/transport --disable-socket --allow-hosts=127.0.0.1 -q

api-contract: ## G9: replay ASGI responses and SSE against the canonical contracts.
	@$(PY) tools/require_path.py engine/src/ncl_engine/main.py --owner engine
	@$(PY) tools/require_path.py engine/tests/contract --owner engine
	$(PYTEST) engine/tests/contract -ra

web-check: ## G10: web static analysis, generated diff, units and coverage.
	$(PY) tools/run_package_script.py web check

integration: ## G11: service, SQLite, cache and SSE tests in offline compose.
	@$(PY) tools/require_path.py engine/src/ncl_engine/main.py --owner engine
	@set -eu; trap '$(COMPOSE) -f docker-compose.yml -f tests/compose.offline.yml down' EXIT; \
	$(COMPOSE) -f docker-compose.yml -f tests/compose.offline.yml up -d --build --wait; \
	NCL_INTEGRATION_BASE_URL=http://127.0.0.1:4173 $(PYTEST) tests/integration -ra

e2e-desktop: ## G12: desktop Chromium flows at 1440x900.
	@set -eu; trap '$(COMPOSE) down' EXIT; VITE_NCL_TEST=1 $(COMPOSE) up -d --build --wait; \
	NCL_E2E_READY=1 $(PLAYWRIGHT) test --config ../tests/e2e/playwright.config.ts --project=desktop-1440 \
		--grep-invert '@visual|@a11y|@perf'

e2e-mobile: ## G13: mobile Chromium flows at 390x844.
	@set -eu; trap '$(COMPOSE) down' EXIT; VITE_NCL_TEST=1 $(COMPOSE) up -d --build --wait; \
	NCL_E2E_READY=1 $(PLAYWRIGHT) test --config ../tests/e2e/playwright.config.ts --project=mobile-390 \
		--grep-invert '@visual|@a11y|@perf'

screenshots-check: ## G14: DOM screenshot regressions with the WebGL canvas masked.
	@set -eu; trap '$(COMPOSE) down' EXIT; VITE_NCL_TEST=1 $(COMPOSE) up -d --build --wait; \
	NCL_E2E_READY=1 $(PLAYWRIGHT) test --config ../tests/e2e/playwright.config.ts --grep '@visual'

screenshots-update: ## Update screenshot baselines for human review; never used by CI.
	@set -eu; trap '$(COMPOSE) down' EXIT; VITE_NCL_TEST=1 $(COMPOSE) up -d --build --wait; \
	NCL_E2E_READY=1 $(PLAYWRIGHT) test --config ../tests/e2e/playwright.config.ts \
		--grep '@visual' --update-snapshots

a11y: ## G15: axe plus keyboard/reflow checks at both viewports.
	@set -eu; trap '$(COMPOSE) down' EXIT; VITE_NCL_TEST=1 $(COMPOSE) up -d --build --wait; \
	NCL_E2E_READY=1 $(PLAYWRIGHT) test --config ../tests/e2e/playwright.config.ts --grep '@a11y'

perf: ## G16: blocking load/LCP/CLS/API/bundle budgets; GPU metrics are report-only.
	$(PY) tools/run_package_script.py web build
	node tests/performance/bundle_budget.mjs
	@set -eu; trap '$(COMPOSE) down' EXIT; VITE_NCL_TEST=1 $(COMPOSE) up -d --build --wait; \
	NCL_CHROMIUM_USE_METAL=$(NCL_CHROMIUM_USE_METAL) NCL_E2E_READY=1 $(PLAYWRIGHT) test \
		--config ../tests/e2e/playwright.config.ts --grep '@perf-ci' --workers=1; \
	$(PY) tests/performance/api_latency.py

perf-local: ## Report local frame-rate and long-task measurements (non-blocking).
	@set -eu; trap '$(COMPOSE) down' EXIT; VITE_NCL_TEST=1 $(COMPOSE) up -d --build --wait; \
	NCL_CHROMIUM_USE_METAL=$(NCL_CHROMIUM_USE_METAL) NCL_E2E_READY=1 $(PLAYWRIGHT) test \
		--config ../tests/e2e/playwright.config.ts --grep '@perf-local'

compose-smoke: ## G17: build and smoke-test the production offline topology.
	@set -eu; trap '$(COMPOSE) down' EXIT; \
	$(COMPOSE) up -d --build --wait; \
	$(COMPOSE) exec -T web wget -qO- http://engine:8000/v1/health >/dev/null; \
	curl --fail --silent --show-error http://127.0.0.1:4173/v1/health >/dev/null

ci: ## Run G1-G17 in order and print one result line per gate.
	$(PY) tools/run_gates.py
