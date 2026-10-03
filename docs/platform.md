# Platform design

## Repository contract

The application is one repository with the following boundaries.

```text
next-clear-look/
├── .github/workflows/
│   ├── ci.yml
│   └── live-source-health.yml       # non-blocking; never refreshes fixtures
├── contracts/
│   ├── openapi.yaml                 # only HTTP contract source
│   ├── events/*.schema.json         # SSE event schemas
│   ├── examples/*.json
│   └── generated/                   # checked for reproducible generation
├── docs/
│   ├── data-contracts.md
│   ├── replay-design.md
│   ├── quality-plan.md
│   ├── architecture.md
│   └── attribution.md
├── engine/
│   ├── pyproject.toml
│   ├── src/ncl_engine/
│   │   ├── api/                     # FastAPI boundary
│   │   ├── analysis/                # analysis workflow and response products
│   │   ├── domain/                  # models, geometry and clock
│   │   ├── raster/                  # COG windows, mosaics and SCL accounting
│   │   ├── sources/                 # live, cache and fixture adapters
│   │   └── storage/                 # SQLite schema and access
│   └── tests/
│       ├── unit/
│       ├── property/
│       ├── golden/
│       └── contract/
├── fixtures/
│   ├── blobs/sha256/
│   ├── presets/singapore-coast/
│   └── schemas/manifest-v1.schema.json
├── tests/
│   ├── integration/
│   ├── offline/
│   ├── performance/
│   └── compose.offline.yml
├── tools/                            # fixture, contract and repo checks
├── web/
│   ├── package.json
│   ├── public/                       # includes Cesium runtime assets
│   ├── src/
│   │   ├── api/generated/
│   │   ├── data/                    # API/SSE clients only; no upstreams
│   │   └── ...                      # screen composition and presentation
│   ├── tests/
│   └── playwright.config.ts
├── .dockerignore
├── .editorconfig
├── .gitignore
├── .python-version                  # 3.12
├── docker-compose.yml
├── Dockerfile.engine
├── Dockerfile.web
├── Makefile
├── package.json                     # workspace + exact packageManager
├── pnpm-lock.yaml                   # root workspace lock
└── README.md
```

Generated API clients may be committed for clean web builds, but `contracts/openapi.yaml` remains authoritative. Fixtures and goldens are inputs, not generated at startup. Runtime SQLite/cache files go under ignored `.local/`, never `fixtures/`.

## Toolchain

### Python

- Python is pinned to 3.12 (`requires-python = ">=3.12,<3.13"`).
- `uv.lock` is committed. `uv sync --frozen --all-groups` is the only dependency install path; CI fails if the lock changes.
- `ruff format --check` and `ruff check` cover `engine/`, Python tools and tests. Target is `py312`; line length is 100; import sorting and bugbear rules are enabled.
- `mypy --strict` is the type gate. Third-party gaps use narrow checked-in stubs or per-module overrides with comments; no global `ignore_missing_imports = true`.
- Pytest provides unit/contract tests and Hypothesis provides property tests. `make engine-unit` is a fast unit-only run with no coverage threshold. `make engine-coverage` measures the complete unit/contract/property/golden suite in one branch-coverage run, requires 85% overall, and keeps the fixture transport, clock and transport-politeness modules at 100%.
- `SOURCE_DATE_EPOCH`, `TZ=UTC`, and `PYTHONHASHSEED=0` stabilize generated artifacts and tests.

### Web

- Node is pinned in `.nvmrc` and CI; Corepack activates the exact `pnpm` version in root `package.json#packageManager`. A single committed lockfile is frozen in CI.
- TypeScript uses `strict`, `noUncheckedIndexedAccess`, and `exactOptionalPropertyTypes`.
- ESLint flat config uses typescript-eslint type-checked rules, React Hooks, JSX accessibility and import-boundary rules. Prettier is formatting only; ESLint owns correctness.
- Vitest + React Testing Library + MSW cover units, and Playwright's pinned Chromium covers browser gates. Axe runs through `@axe-core/playwright`.
- OpenAPI types are generated with a pinned generator. The browser imports those types/examples and never hand-maintains a competing transport model.
- Cesium is lazy-loaded and its worker, wasm and widget assets are copied at build time. Bundled NASA day/night images are the offline globe layers; no Cesium ion token is accepted or read.

### Supply chain

The Python and pnpm lockfiles are committed, container base versions are explicit, and GitHub
Actions use pinned SHAs. `make repo-check` rejects local-path dependencies, missing MIT metadata,
direct HTTP clients outside the transport boundary, stale contract artifacts and fixtures above
budget.

## Runtime configuration and interfaces

The engine constructs dependencies once at startup:

```text
Settings
  mode: replay | live | record
  fixture_set: ncl-showcase
  fixtures_dir: read-only path
  state_dir: writable SQLite/cache path
  clock: FrozenClock | SystemUTCClock
  transport: FixtureTransport | CachedAllowlistedHttpTransport
```

The engine exposes an ASGI application that conforms to `contracts/openapi.yaml`, a
liveness/readiness probe, injected `Clock` and `DataTransport` boundaries, deterministic SSE
ordering, and provenance/attribution fields.

The web application consumes the generated API/SSE client, server-provided
clock/mode/provenance, and a build-time API base path. It exposes stable ready/replay-time hooks
for tests and uses bundled NASA imagery when offline.

No direct CelesTrak, Earth Search or COG request is allowed outside the data adapter. The optional
EOX browser layer is isolated from scientific data and never blocks replay readiness.

## Makefile interface

These targets are the public developer and CI interface; implementation scripts may evolve without changing the commands.

| Target | Required recipe/effect |
|---|---|
| `make bootstrap` | `uv sync --frozen --all-groups`; `corepack enable`; `pnpm install --frozen-lockfile`; does not install browsers |
| `make bootstrap-test` | Run `bootstrap`, then install the pinned Playwright Chromium build |
| `make dev` | Run `bootstrap`, then engine and Vite dev server concurrently with `NCL_MODE=replay`, frozen fixture clock and no live-source configuration |
| `make live` | Require `NCL_ALLOW_LIVE=1`, then start the same stack with allowlisted HTTP/cache enabled and a conspicuous live-mode log line |
| `make stop` | Stop local dev children/compose without deleting state or fixtures |
| `make repo-check` | Validate layout, locks, MIT metadata, import boundaries, contracts and fixture bytes |
| `make contract-check` | Validate OpenAPI/SSE schemas and examples, then fail if generated TypeScript has drifted |
| `make engine-static` | `uv run ruff format --check ...`, `uv run ruff check ...`, and `uv run mypy --strict ...` |
| `make engine-unit` | Run unit tests with sockets denied and replay clock injected; no coverage gate |
| `make engine-coverage` | Run the whole engine suite once with branch coverage; require 85% overall and 100% for critical deterministic modules |
| `make engine-property` | Run `engine/tests/property` with the configured Hypothesis example counts |
| `make engine-golden` | Recompute outputs from pinned inputs and compare approved pass goldens; never update |
| `make golden-update CASE=...` | Maintainer-only semantic regeneration of one named golden; refuses an empty `CASE` |
| `make fixtures-record PRESET=... CLOCK=...` | Explicit recorder; `CLOCK` is the recording instant and the recorder computes the frozen time |
| `make fixtures-diff PRESET=...` | Human-readable old/new source, scene, range, histogram, attribution and size diff |
| `make fixtures-check` | Manifest schema, hashes, request identities, range lineage, replay determinism and `<40 MiB` byte gates |
| `make offline-check` | Set dead proxies, validate fixtures, and run replay/transport tests with non-loopback sockets denied |
| `make api-contract` | Run replay ASGI and SSE contract tests against `contracts/openapi.yaml` |
| `make web-check` | Prettier, ESLint, strict TypeScript, generated-client diff and Vitest/RTL/MSW |
| `make integration` | Run service/SQLite/cache/SSE integration tests in the offline compose topology |
| `make e2e-desktop` | `pnpm --dir web exec playwright test --project=desktop-1440 --grep-invert '@visual|@a11y|@perf'` |
| `make e2e-mobile` | `pnpm --dir web exec playwright test --project=mobile-390 --grep-invert '@visual|@a11y|@perf'` |
| `make screenshots-check` | Run `@visual` cases in both projects with no baseline updates |
| `make screenshots-update` | Maintainer-only Playwright baseline update; never invoked by another target |
| `make a11y` | Run `@a11y` cases in both projects and keyboard/reflow assertions |
| `make perf` | Build production web assets and run browser, API and bundle budget checks against Compose |
| `make perf-local` | Report frame-rate and long-task measurements on a local GPU; non-blocking |
| `make compose-smoke` | Build production images, start default compose, wait for health, run smoke request inside the internal network, and always tear down without `-v` |
| `make ci` | Run G1-G16 plus `compose-smoke`, in gate order; G4 includes both `engine-unit` and `engine-coverage`, and output prints one pass/fail line per gate |

Every test target is non-interactive. Targets that update goldens/fixtures are deliberately excluded from `make ci` and have distinct imperative names.

## `docker-compose.yml`

The root compose file is the production-build offline demo, not a convenience wrapper around dev servers.

```yaml
services:
  engine:
    build:
      context: .
      dockerfile: Dockerfile.engine
      target: runtime
    environment:
      NCL_MODE: replay
      NCL_FIXTURE_SET: ncl-showcase
      NCL_FIXTURES_DIR: /app/fixtures
      NCL_STATE_DIR: /var/lib/ncl
      TZ: UTC
    volumes:
      - ./fixtures:/app/fixtures:ro
      - ncl-state:/var/lib/ncl
    networks: [ncl-internal]
    read_only: true
    tmpfs: [/tmp]
    healthcheck:
      test: [CMD, python, -m, ncl_engine.healthcheck]
      interval: 2s
      timeout: 1s
      retries: 20
      start_period: 10s

  web:
    build:
      context: .
      dockerfile: Dockerfile.web
      target: runtime
    depends_on:
      engine:
        condition: service_healthy
    ports: ["4173:8080"]
    networks: [edge, ncl-internal]
    read_only: true
    tmpfs: [/var/cache/nginx, /var/run]

networks:
  edge:
    driver: bridge
  ncl-internal:
    internal: true

volumes:
  ncl-state:
```

The web image serves static Vite/Cesium output and reverse-proxies the contract API/SSE path to `engine`; only port 4173 is published. The internal network has no default external route. Engine source/fixtures are read-only; only the named SQLite/cache volume is writable. Services run as non-root, have health checks, drop Linux capabilities and use `no-new-privileges`.

The engine service targets `linux/amd64`, matching CI and the pinned Python 3.12 rasterio wheel.
Apple Silicon Docker/Colima runs it through the standard registered amd64 emulator instead of
falling back to an unpinned local GDAL source build; the web image remains native.

`docker compose up --build` therefore starts replay without credentials or upstream DNS. Dependency/base-image download may be needed on a machine that has never built the clone; “offline” here means the running product has no upstream data dependency or egress. A separately reviewed `compose.live.yml` override adds external networking and `NCL_ALLOW_LIVE=1`; it is never selected by default or CI.

`make dev` provides the same data semantics outside Docker. It installs locked dependencies if absent, then starts the engine and web watcher; once dependencies are present, public data remains unnecessary. Both run paths expose the same frozen clock and fixture set.

## CI workflow

`.github/workflows/ci.yml` runs on pull requests and the default branch with least-privilege `contents: read`. It cancels superseded branch runs and has no source credentials.

1. Checkout pinned action SHA; set up Python 3.12, uv, pinned Node/Corepack and Docker Buildx.
2. Restore caches keyed only by `uv.lock`, `pnpm-lock.yaml`, browser version and Dockerfile digests. Never cache runtime SQLite or generated fixtures.
3. Run `make bootstrap-test` with frozen locks and the pinned browser.
4. Run `make ci` in the pinned Ubuntu image. Default compose uses its internal network, and the offline gate also installs socket/request guards and dead proxies.
5. Upload reports named in `quality-plan.md` even on failure. No fixture refresh or golden update is allowed.
6. Publish a gate summary G1-G17. Branch protection requires the aggregate job, not merely lint/unit jobs.

A separate scheduled `live-source-health.yml` may perform one bounded Earth Search search and small COG range probe. It does not query CelesTrak unless a durable shared two-hour limiter can be guaranteed, does not mutate fixtures, and is non-blocking for releases. Its job is early warning, not acceptance evidence.

## README outline

1. **One-sentence promise and honesty labels** — geometric opportunity, historical likelihood, never acquisition/weather claims.
2. **Thirty-second start** — `docker compose up --build`, open `http://localhost:4173`, explain that replay is offline/default.
3. **Alternative local development** — prerequisites and `make dev`; ports; stop command.
4. **What is real in the demo** — recorded OMM/STAC/COG provenance, frozen date, AOI, attribution and fixture revision.
5. **Architecture** — compact engine/web/contracts/fixtures flow and compute/animate boundary.
6. **Replay versus live** — guarantees, opt-in `make live`, upstream policy cautions and cache behavior.
7. **Repository map** — directories and responsibilities.
8. **Quality gates** — `make ci`, G1-G17 link, how to inspect reports; no badge without a required check behind it.
9. **Fixture refresh** — policy-aware command, semantic review and 40 MiB rule.
10. **Data sources, licences and exact attribution** — CelesTrak caveat, Earth Search, Copernicus, JPL, NASA and EOX.
11. **Scope and limitations** — scientific and operational non-claims.
12. **Contributing/security** — lock discipline, no secrets in fixtures, responsible disclosure and licence.
