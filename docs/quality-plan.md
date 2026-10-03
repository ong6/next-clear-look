# Quality plan and acceptance gates

## Definition of polished

“Polished” means every gate G1-G17 below is green on a clean clone and in CI. It is not a visual judgment substituted for evidence. Tests run against the contract and recorded inputs with a frozen clock; live upstream availability is never part of acceptance.

This plan defines externally observable behavior, fixtures, test layers and commands without prescribing engine algorithms or screens.

## Test layers

### Engine unit and property tests

Use `pytest`, `pytest-asyncio`, and Hypothesis under Python 3.12. Unit tests isolate parsing, validation, time injection, provenance, cache state, range transport and API serialization. Network calls are replaced by the strict fixture transport; a global socket-denial fixture fails any accidental egress.

Geometry properties test public engine interfaces, not implementation details:

- accepted GeoJSON round-trips to finite, valid output within the documented coordinate domain;
- empty/invalid/self-intersecting inputs produce typed contract errors rather than NaN, hangs or process errors;
- equivalent ring orientation and longitude representations produce equivalent coverage decisions;
- outputs remain valid and bounded for antimeridian, polar, tiny, concave and boundary-touching AOIs;
- interval outputs are ordered, non-overlapping where the contract requires, contained in the requested horizon and stable under deterministic re-evaluation;
- sampled trajectories contain finite values, monotonic UTC timestamps and contract-bounded payload sizes.

Hypothesis properties use 40 or 200 examples according to cost, with deadlines disabled and
shrinking enabled. Every production regression becomes a named example before its fix lands.

`make engine-unit` is deliberately a fast unit-only target with no coverage threshold. The
coverage gate is `make engine-coverage`: one branch-coverage run across unit, contract, property
and golden tests, with an 85% overall floor and 100% on the fixture transport, injected clock and
transport-politeness modules. The aggregate `make ci` runs both commands as G4.

### Pass-prediction goldens

Goldens pair a frozen clock, exact OMM blob digests, AOI GeoJSON and requested horizon with the contract-level pass result. Include the Singapore preset plus equatorial, antimeridian, high-latitude, no-intersection and boundary-contact cases. Compare stable identifiers, event ordering, input provenance, opportunity labels, and documented numeric/time tolerances. Do not compare incidental JSON key order or implementation-private intermediates.

`make engine-golden` only checks. `make golden-update CASE=<name>` is a maintainer action that prints a semantic before/after report and never runs in CI. A code change cannot silently bless its own output.

### Contract tests

`contracts/openapi.yaml` and referenced SSE JSON Schemas are the only wire contract. Static checks
use OpenAPI and JSON Schema validation, require an operation ID and realistic example for every
operation, and reject unresolved references. Examples include replay/live mode, frozen/source
times, provenance, empty/loading-complete/error semantics, and attribution strings.

Dynamic pytest tests boot the ASGI app in replay mode and exercise representative operations,
declared errors and deterministic SSE. Responses validate against OpenAPI, examples are executable,
and content types and cache headers are asserted. Web mocks use the contract examples, while the
generated TypeScript check fails on drift.

SSE tests split arbitrary byte chunks, reconnect with `Last-Event-ID`, reject non-monotonic IDs/timestamps, and compare the complete replay stream byte-for-byte under the frozen clock.

### Web unit tests

Use Vitest, React Testing Library, `@testing-library/user-event`, and MSW. Cover data-state reducers, clock/countdown behavior, API and SSE reconnect/error handling, provenance/attribution rendering, offline fallback selection, reduced motion, keyboard interaction, formatting boundaries and cleanup of Cesium resources. Fake time is mandatory; tests may not read the real clock or call the network.

Generated OpenAPI TypeScript types are checked for a clean diff. TypeScript is strict; ESLint includes React Hooks and accessibility rules. Console error/warning output fails tests unless explicitly asserted.

### Integration and end-to-end

Playwright uses pinned Chromium and fonts against `docker-compose.yml` in replay mode. Run two named projects:

- `desktop-1440`: viewport 1440 x 900, device scale factor 1;
- `mobile-390`: viewport 390 x 844, device scale factor 1, touch enabled.

Both exercise startup, preset load, deterministic time advancement, API/SSE recovery, history navigation, provenance access, no-data, malformed-fixture, service-error and offline states. Assertions use contract-visible labels and stable test IDs, not CSS structure. Each run fails on page errors, failed requests, unhandled promises or unexpected console warnings.

### Screenshot checks

Capture approved stable checkpoints at both viewports after fonts, tiles, data and a named replay timestamp are ready. Cesium animation advances to that timestamp and pauses; transitions/cursors are disabled; color profile, DPR and browser image are pinned. Playwright's `toHaveScreenshot` masks the WebGL canvas and uses `maxDiffPixelRatio: 0.01` for the DOM. Dynamic debug text and record-time durations are excluded from rendered checkpoints, not masked broadly.

Baseline updates use `make screenshots-update` and require human review. CI only checks.

### Accessibility

Run axe after initial ready state and after every major interactive state at both viewports. There must be zero `critical` or `serious` WCAG 2 A/AA violations. Automated checks are supplemented with tests for full keyboard reachability, visible focus, escape/focus restoration, meaningful names, live-region restraint, reduced motion, non-color status cues, and 200% zoom/reflow at 390 px. Any intentional axe exclusion names one issue and expiry; blanket exclusions fail review.

### Performance budgets

Measure the production build in replay mode on the pinned CI Chromium image. Warm the container, then use five cold browser contexts for load and a 100-request API sample after five warmups. Report raw samples and p50/p95. Frame-rate and long-task budgets are reported only by `make perf-local`, because headless CI has no representative GPU. API latency uses the per-endpoint budgets in `docs/architecture.md` rather than one aggregate threshold.

| Measure | Desktop budget | Mobile budget | Method |
|---|---:|---:|---|
| App ready (navigation start to contract-defined `ncl:ready`) | p95 <= 2.5 s | p95 <= 3.5 s | Five cold contexts, local compose, fixture cache warm |
| Largest Contentful Paint | p75 <= 2.5 s | p75 <= 3.0 s | Playwright PerformanceObserver |
| Cumulative Layout Shift | <= 0.10 | <= 0.10 | Web Vitals collection |
| Animation frame rate (report only) | p10 >= 50 fps | p10 >= 45 fps | `make perf-local`; 10 s visible replay segment; no DevTools throttling |
| Long tasks (report only) | no task > 200 ms | no task > 250 ms | `make perf-local`; PerformanceObserver |
| Replay API latency | Per-endpoint p95 budgets in `architecture.md` | same | 100 sequential requests inside compose network; 250 ms maximum |
| Initial JS, Brotli | <= 1.2 MiB | <= 1.2 MiB | Vite bundle manifest; lazy Cesium chunk reported separately |

These are regression budgets for the pinned CI machine, not production SLAs. A runner-class change requires re-baselining in a dedicated review; it does not justify silently widening thresholds.

## Acceptance gates

Every command runs from the repository root and exits non-zero on failure. The Makefile definitions are specified in `platform.md`.

| Gate | Acceptance condition | Exact command |
|---|---|---|
| **G1 Repository reproducibility** | Required paths, committed lockfiles, no local-path dependencies, and generated files are current. | `make repo-check` |
| **G2 Contract validity** | OpenAPI and SSE schemas lint, resolve, include examples, and generate stable Python/TypeScript types. | `make contract-check` |
| **G3 Engine static quality** | Ruff format/lint and strict type checking pass on engine, tools and Python tests. | `make engine-static` |
| **G4 Engine tests and coverage** | Parser, cache, clock, provenance, transport and error-path units pass with network denied; the aggregate also runs whole-suite coverage. | `make engine-unit` (`make ci` also runs `make engine-coverage`) |
| **G5 Geometry properties** | All configured Hypothesis geometry/interface properties pass. | `make engine-property` |
| **G6 Pass goldens** | All pass-prediction contract goldens match within reviewed tolerances; no update occurs. | `make engine-golden` |
| **G7 Fixture integrity** | Manifests validate; request matching, hashes, COG ranges and derived lineage verify; unique fixtures stay below 40 MiB. | `make fixtures-check` |
| **G8 Forced-offline replay** | The full replay suite passes with sockets denied and proxy variables pointed at `127.0.0.1:9`; no fixture miss falls through. | `make offline-check` |
| **G9 API contract** | Every live ASGI response/error and SSE event validates against `contracts/openapi.yaml`/event schemas. | `make api-contract` |
| **G10 Web static and unit quality** | ESLint, TypeScript strict mode, Vitest/RTL/MSW, generated-client diff and console hygiene pass. | `make web-check` |
| **G11 Service integration** | Web, API, SQLite/WAL, fixture cache and SSE work together in the offline compose topology. | `make integration` |
| **G12 Desktop E2E** | The required flows pass in Chromium at exactly 1440 x 900. | `make e2e-desktop` |
| **G13 Mobile E2E** | The same required flows and reflow/gesture cases pass at exactly 390 x 844. | `make e2e-mobile` |
| **G14 Screenshot regression** | Approved desktop and mobile DOM checkpoints remain within the 1% pixel-difference ceiling with WebGL masked. | `make screenshots-check` |
| **G15 Accessibility** | Axe has zero serious/critical findings and keyboard/focus/reduced-motion checks pass at both widths. | `make a11y` |
| **G16 Performance** | Load, LCP, CLS, per-endpoint API-latency and bundle budgets pass; frame-rate and long tasks are reported by `make perf-local`. | `make perf` |
| **G17 Clean-clone run and aggregate** | Production images build, `docker compose up` becomes healthy without upstream access, smoke checks pass, and G1-G16 all pass. | `make ci` |

The sole acceptance command for a release candidate is therefore `make ci`; its output preserves one line per gate so a failure still points to the responsible suite.

## Evidence and failure handling

CI uploads coverage output, Playwright reports and failure artifacts, test results, browser performance
samples, bundle/API reports and fixture-size evidence. Artifacts contain no credentials or
unredacted signed URLs.

Flaky reruns do not turn red into green. CI may rerun once only to classify a failure; either failure keeps the gate red. Quarantined tests do not count toward acceptance. Live-source probes are a separate scheduled/non-blocking workflow and can never replace replay acceptance.
