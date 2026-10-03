# Web testing contract

The production default is the real same-origin API under `/v1`. Mocking is opt-in:

```bash
VITE_NCL_MOCK=1 VITE_NCL_TEST=1 pnpm --dir web dev --host 127.0.0.1 --port 5180
```

- `VITE_NCL_MOCK=1` starts the browser MSW worker. Its handlers return the committed `contracts/examples/*` payloads.
- Without `VITE_NCL_MOCK=1`, every request uses the real `/v1` engine API through the Vite or nginx proxy.
- `VITE_NCL_TEST=1` is the only mode that exposes `window.__ncl`.

## Readiness and deterministic controls

Wait for either form of the same readiness signal:

```js
await page.locator("html[data-ncl-ready='true']").waitFor();
// or listen for window CustomEvent "ncl:ready" before navigation.
```

Readiness is emitted after the first globe frame and the initial API data load, not after the camera fly-in.

Test-only controls:

```js
await page.evaluate(() => window.__ncl?.setTime("2026-10-03T02:32:07.250Z"));
await page.evaluate(() => window.__ncl?.pause());
```

## Stable test IDs

| Test ID                   | Surface                                                    |
| ------------------------- | ---------------------------------------------------------- |
| `app-header`              | Global command header                                      |
| `mode-badge`              | Replay/live mode control                                   |
| `mode-error`              | Mode-switch error, including `LIVE_DISABLED`               |
| `source-health`           | Source status cluster                                      |
| `aoi-switcher`            | AOI picker opener                                          |
| `mission-screen`          | Mission workspace                                          |
| `globe-stage`             | Cesium scene container                                     |
| `globe-text-alternative`  | Screen-reader globe state                                  |
| `globe-playback-scrubber` | Globe timeline control                                     |
| `next-opportunity-card`   | Primary opportunity decision                               |
| `opportunity-phase`       | Pre-pass or in-swath phase label                           |
| `pass-playback-button`    | Pass play/pause action                                     |
| `opportunity-row`         | Opportunity list item; may repeat                          |
| `likelihood-interval`     | Historical likelihood block                                |
| `recent-looks-deck`       | Recent evidence strip                                      |
| `scene-card`              | Scene result; may repeat                                   |
| `open-aoi-detail`         | Mission-to-detail action                                   |
| `aoi-detail`              | AOI detail page                                            |
| `view-mode-tabs`          | True colour / SCL / compare tabs                           |
| `class-distribution`      | AOI SCL accounting                                         |
| `aoi-picker`              | Preset, saved-area, and draw-mode chooser                  |
| `aoi-draw-panel`          | On-globe drawing controls and coordinate-entry alternative |
| `aoi-draw-map`            | Real Cesium ellipsoid-picking surface while drawing        |
| `use-drawn-aoi`           | Commit the drawn polygon and start analysis                |
| `draw-vertex-count`       | Number of real globe or keyboard-entered vertices          |
| `aoi-preset-row`          | Preset result; repeats five times                          |
| `aoi-saved-row`           | Locally saved drawn area; repeats up to eight times        |
| `evidence-drawer`         | Evidence and provenance dialog                             |
| `attribution-panel`       | Attribution dialog                                         |
| `empty-archive`           | Completed empty archive state                              |
| `not-recorded-archive`    | Replay AOI whose archive was not recorded                  |
| `upstream-error`          | Named upstream error state                                 |
| `stream-progress`         | Independent analysis stage progress                        |
| `progress-orbit`          | Orbit-geometry progress row                                |
| `progress-archive`        | Catalogue/archive progress row                             |
| `progress-raster`         | Per-scene AOI pixel progress row                           |
| `progress-likelihood`     | Historical-likelihood progress row                         |
| `provenance-graph`        | Engine-returned provenance nodes and lineage summary       |
| `performance-overlay`     | Local-only `?perf=1` FPS/long-task overlay                 |

All test IDs are kebab-case. Prefer role and accessible name for actions; use test IDs for stateful regions and test hooks.

`job.result` is applied immediately: a `scene` result creates a filmstrip card, then
`scene_statistics` and `thumbnail_metadata` enrich that same card. Tests may therefore assert
cards independently of the final `job.completed` event.

Visual-round invariants:

- Header, globe mission plate, countdown, Cesium clock, and test hook all consume the same display
  clock. Mission offsets use one floor-based `T−HH:MM:SS` / `T+HH:MM:SS` formatter; the decision
  card switches to `In swath · T+MM:SS` between entry and exit, then selects the next opportunity.
- `stream-progress` is inside the outlook rail on desktop and in normal document flow at 390 px.
- Compact percentages use the product precision rules: broad likelihood intervals are integers,
  tile cloud is one decimal, and AOI accounting remains one decimal.
- The evidence drawer definition lists keep only `dt` and `dd` children; copy controls live inside
  the final `dd` so the root a11y suite's `definition-list` rule stays green.

## Commands

```bash
pnpm --dir web contract:check
pnpm --dir web check
pnpm --dir web build
pnpm --dir web test:e2e
pnpm --dir web perf:local  # requires a mock dev server on 127.0.0.1:5180
```

To reuse an already-running real engine and Vite server (the web suite uses the installed Chrome
channel at both 1440×900 and 390×844):

```bash
NCL_E2E_REAL=1 NCL_BASE_URL=http://127.0.0.1:5180 \
  pnpm --dir web exec playwright test --grep-invert @live-real

# Run once, serially, against an engine started with NCL_ALLOW_LIVE=1.
NCL_E2E_REAL=1 NCL_BASE_URL=http://127.0.0.1:5180 \
  pnpm --dir web exec playwright test --project=desktop-1440 --grep @live-real --workers=1
```

The repository-level browser suite runs with:

```bash
NCL_E2E_READY=1 pnpm --dir web exec playwright test --config ../tests/e2e/playwright.config.ts
```
