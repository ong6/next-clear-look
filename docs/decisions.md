# Design decisions

This document records the design decisions behind Next Clear Look, each with what the code does
and why, and the project README links here. IDs D1–D43 are stable so other documents can cite
them; an entry folded into another keeps a one-line stub pointing to where it now lives.

## Product honesty

- **D9 — Honest claims only.** A predicted overpass is a geometric opportunity ("acquisition is
  not guaranteed"); a clear-look chance is a historical likelihood ("not a weather forecast or
  acquisition promise"), shown with its trial counts and 90% interval, or null when data is
  insufficient. Accounts, alerts, forecasts, Sentinel-1, Landsat and tasking are out of scope.
  *Why:* the numbers are only useful if a reader can tell exactly what they promise.
- **D16 — No tile-cloud filter.** Earth Search is queried for `sentinel-2-l2a` with `intersects`
  on the AOI, newest first, paged by `next` links, with a STAC `fields` include/exclude list, and
  is never filtered on `eo:cloud_cover`. *Why:* tile cloud cover describes a whole ~110 km tile,
  so filtering on it would hide clear AOI looks and bias the history.
- **D31 — SCL taxonomy.** Clear surface is SCL 4 (vegetation), 5 (not vegetated), 6 (water) and
  7 (unclassified). Dark area (2), cloud shadow (3), cloud (8, 9), thin cirrus (10) and, by
  default, snow/ice (11) are valid but not clear; no data and saturated/defective (0, 1) are left
  out of the denominator. The web shows eight labelled groups and marks which count as surface.
  *Why:* unclassified pixels are visible ground the classifier could not name, and showing every
  group lets a reader check the arithmetic.
- **D43 — Per-preset surface policy and one 14-day window.** Snow/ice counts as surface only for
  a preset whose subject is ice; today that is Jakobshavn (`ICE_SURFACE_PRESETS` in
  `raster/scl.py`). The `surface_class_policy` is part of the scene-statistics and likelihood
  payloads, and the UI says "Snow/ice counted as surface for this area." The default opportunity
  list and the likelihood use the same half-open 14-day window starting at the clock. *Why:* at
  an ice front the ice is the subject rather than an obstruction, and one window keeps the list
  and the probability arithmetically consistent.

## Globe imagery

- **D10 — Bundled base imagery, optional close zoom.** Day: NASA Blue Marble NG with topography
  and bathymetry, October 2004 (`world.topo.bathy.200410.3x5400x2700.jpg`), plus a 20°×20°
  (~500 m) crop of the same set over each preset's region. Night: NASA Black Marble 2012
  (`dnb_land_ocean_ice.2012.3600x1800.jpg`), blended by Cesium lighting on the app clock, so the
  terminator is real. All seven files ship in `web/public/imagery/` (~11.9 MB of a 12 MB
  budget). If EOX Sentinel-2 cloudless 2024 (keyless, CC BY-NC-SA 4.0) answers a 5-second probe,
  it is shown below 2,500 km camera altitude. The selected scene's AOI-clipped true-colour PNG
  can be draped on the AOI. No ion or OpenStreetMap layer is used; without WebGL, a "3D globe
  unavailable" panel keeps the data usable. *Why:* replay must never depend on a map service,
  while close zoom still gets sharper imagery when the network allows.
- **D11 — Orbital hero view.** Spacecraft fly at altitude on 3D orbits, with the selected pass's
  ground track, a luminous swath ribbon, sky atmosphere and day/night lighting. Cesium's canvas
  logo and credits are hidden; the attribution panel lists every credit (Cesium, NASA, EOX,
  Copernicus, CelesTrak, Element 84). *Why:* watching the swath sweep the AOI explains an
  opportunity faster than a table, and one panel keeps credits complete.

## Data, fixtures and replay

- **D4 — Replay first.** The default mode replays the recorded `ncl-showcase` fixture set; both
  `docker compose up` and `make dev` start in replay, and live mode is opt-in (D24). *Why:* a
  deterministic, offline demo is reviewable and puts no load on public services.
- **D7** — Merged into D38.
- **D8 — Three public upstreams.** CelesTrak (Sentinel-2 orbital elements), Element 84 Earth
  Search (STAC catalogue) and the Sentinel-2 COGs on AWS are the only network sources; the JPL
  DE421 ephemeris is bundled (D21). *Why:* all three are open and keyless, so anyone can
  re-record, and a short allowlist is easy to audit.
- **D12 — One fixture set with a chosen clock.** `fixtures/fixture-set.json` describes
  `ncl-showcase`: `frozen_at`, `recorded_at`, one CelesTrak response shared by all presets, the
  DE421 excerpt, the preset manifests and the budget; blobs live under `fixtures/blobs/sha256/`.
  `frozen_at` is the latest instant in the 72 hours before recording, within 48 hours of every
  element epoch, whose next Tuas opportunity is 2–4 hours later; STAC windows end at it. *Why:*
  the demo opens on an approaching pass with fresh elements, and no later data leaks in.
- **D13** — Merged into D42.
- **D14 — Fixture budget.** Under 40 MiB in total: orbital elements plus ephemeris ≤ 512 KiB;
  catalogue JSON ≤ 12 MiB; native SCL ranges for the six newest recent datatakes ≤ 2 MiB per
  preset; derived 640 px AOI PNGs ≤ 3 MiB per preset; examples, goldens and SSE ≤ 3 MiB. History
  keeps class counts plus source-range SHA-256 with `bytes_bundled: false`, and no true-colour
  COG bytes are committed; `make fixtures-check` enforces all of it. *Why:* the repository stays
  quick to clone while replay stays reproducible from committed bytes.
- **D15 — The recorder is the engine.** `python -m ncl_engine.fixtures record|check|diff` runs
  the engine's own query builders and pipeline (recording needs `NCL_ALLOW_RECORD=1`) and writes
  derived opportunities, statistics, PNGs and likelihood into the manifests; replay verifies blob
  hashes and imports them at startup. `make fixtures-check` re-reads recorded SCL ranges through
  rasterio and requires identical statistics. *Why:* hand-written requests or results would let
  fixtures drift from what the code computes.
- **D17 — One transport layer.** `sources/transport/` holds `CanonicalRequest`, the snapshot
  types, the HTTP, cache, politeness and fixture transports, and the loopback adapter that GDAL
  reads COGs through. Typed adapters (`sources/live.py`, `sources/replay.py`) sit on top and
  return records and bytes; SCL counting lives in `raster/scl.py`. *Why:* live, recording and
  replay share one request path, so replay exercises the same code as live.
- **D18 — Request identity.** Every request has a `request_key_sha256` from
  `CanonicalRequest.key()`, and every snapshot an `origin` of `network | cache | fixture`. Blobs
  live at `sha256/<first 2 hex>/<all 64 hex>`. One `SourceId` enum is used everywhere:
  `celestrak | earth-search | sentinel-cogs | jpl-de421`. *Why:* content addressing deduplicates
  blobs and makes every provenance link verifiable.
- **D19 — GDAL configured in one place.** `gdal_environment()` sets
  `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`, `GDAL_INGESTED_BYTES_AT_OPEN=16384`,
  `GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES` and `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif` over a
  pinned rasterio wheel. Replay fails closed: JSON must match exactly, and a COG range is served
  only when recorded bytes for the same URL and ETag cover it. *Why:* GDAL's range pattern
  depends on these settings, so pinning them makes recorded ranges sufficient on replay.
- **D20 — Upstream politeness.** CelesTrak is single-flight, cached for two hours and never
  retried; Earth Search allows 2 concurrent requests; COG range reads allow 4 concurrent
  requests and up to 3 attempts with backoff. *Why:* these are free public services, and
  CelesTrak blocks clients that poll it too often.
- **D21 — Bundled ephemeris.** A DE421 excerpt covering 2023-01-01 to 2028-01-01 is committed,
  built from a local file by `tools/build_ephemeris.py` with `jplephem`. Time uses
  `load.timescale(builtin=True)`, so the engine never downloads at runtime. *Why:* Skyfield
  would otherwise fetch files on first use, which breaks offline and deterministic runs.
- **D42 — Five presets at product scale.** Presets live in `fixtures/presets/<slug>/aoi.geojson`
  and the engine seeds them. Tuas (`singapore-coast`, id `aoi_sg_tuas_coast`) is
  `[103.62, 1.24, 103.77, 1.36]`. The rest are at least 100 km² and contain their feature:
  `rotterdam-port` (Maasvlakte) `[3.93, 51.91, 4.10, 52.01]`, `atacama-works` (evaporation ponds)
  `[-68.42, -23.72, -68.22, -23.50]`, `sundarbans-delta` (tidal channels)
  `[89.35, 21.62, 89.50, 21.76]` and `jakobshavn-ice-front` (calving front)
  `[-50.25, 69.10, -49.75, 69.25]`. Sundarbans deliberately spans MGRS tiles 45QYD/45QYE; the
  others prefer one tile. *Why:* each story must be visible at Sentinel-2 scale, and one
  multi-tile case exercises datatake mosaicking.

## Engine

- **D1 — Python engine.** Python 3.12 with FastAPI, sgp4 and Skyfield (orbits), shapely and pyproj
  (geometry), rasterio (COG reads) and SQLite plus a content-addressed blob cache. *Why:* mature,
  pinned libraries cover every step in one process with no external services.
- **D3 — Contract first.** `contracts/openapi.yaml` and one JSON Schema per SSE event type under
  `contracts/events/` define the API; the engine and web conform to them. *Why:* both sides can
  change independently, and drift fails a test rather than a demo.
- **D5 — The engine computes, the browser animates.** Propagation, swath intersection, SCL
  statistics and likelihood run in the engine; the browser interpolates its trajectory samples and
  renders them. *Why:* each algorithm has one implementation, tested in Python against goldens.
- **D6 — One repository.** `engine/`, `web/`, `contracts/`, `fixtures/` and `docs/` live
  together, with `tools/` and root `tests/`. *Why:* contract, fixture and code changes land in
  one commit and are checked together.
- **D22 — Engine layout.** `engine/src/ncl_engine/` holds `api`, `domain`, `orbit`, `raster`,
  `likelihood`, `analysis`, `jobs`, `sources` (with `transport/`), `provenance`, `storage` and
  `fixtures` (the recorder CLI), plus `healthcheck.py`. The app factory `ncl_engine.main:create_app`
  serves on port 8000 in the container and 4200 under `make dev`. Tests live in
  `engine/tests/{unit,contract,property,golden}` and root
  `tests/{integration,offline,performance,e2e}`. *Why:* domain logic stays testable apart from HTTP,
  storage and transport.
- **D23 — Injected clock.** The `Clock` protocol in `domain/clock.py` has only `now()`;
  `FrozenClock` adds `advance_to()` and never moves backwards. Timeouts, retries, heartbeats and
  rate limits use the event loop's monotonic time, and the engine clock stays frozen in replay. The
  browser's display clock is the mode clock plus monotonic elapsed time times the playback rate;
  play, pause and scrub are client-only. *Why:* wall time never leaks into results.
- **D24 — Two modes.** The API has `live | replay` only. `PUT /mode` returns 409
  `LIVE_DISABLED` unless `NCL_ALLOW_LIVE=1`; `Mode` reports `live_available` and
  `fixture_recorded_at`, and `ModeSwitchRequest` carries no clock. *Why:* network access is an
  explicit operator choice, never a UI toggle away.
- **D25 — Historical likelihood.** History covers up to three years of deduplicated acquisitions
  within ±45 days of the same local calendar date. Acquisition trials walk each platform and
  relative orbit's 10-day repeat cycle (`sat:relative_orbit`) and match observed acquisitions within
  ±5 days, so no historical orbital elements are needed. A clear trial succeeds when AOI clear is at
  least 70%, fails below that, and is excluded when valid coverage is under 95% or unknown. Both get
  Beta(1 + successes, 1 + failures) posteriors; 100,000 seeded draws of their product give P(≥1
  clear look) over the predicted opportunity days (one per local date) in the next 7 and 14 days,
  with a 90% interval, or null below 20 trials of either kind. *Why:* it answers the real question
  from observed history, with uncertainty and sample size on show.
- **D26 — SSE and state.** Each event validates against `contracts/events/envelope.schema.json`
  and its own schema. In replay, `emitted_at` is the frozen clock and IDs derive from request
  fingerprints, so replay streams are byte-stable. Replay state lives in
  `replay-<set>.sqlite`, rebuilt on every boot; live state lives in `live.sqlite`. *Why:*
  byte-stable streams can be compared against goldens, and replay can never inherit stale state.
- **D27 — Swath geometry is engine output.** `TrajectorySample` carries `swath_left` and
  `swath_right`, and `Opportunity` carries `swath_footprint`, from the nominal 290 km swath.
  *Why:* the globe draws exactly the geometry the opportunity test used.
- **D28 — Explicit scene states.** Scenes report `analysis_state` (`queued | reading |
  analysing | ready | failed | not_recorded`), `analysis_error`, nullable `valid_pixels`,
  `thumbnail_status` (`ready | pending | not_bundled | failed`), `collection`, `footprint`,
  `stac_self_url` and `meta.archive_state`; the default archive window is [clock − 30 days,
  clock). `listScenes` may return 202 while a search is pending. *Why:* "not yet searched" must
  never render as an empty archive.
- **D29 — AOI model.** AOIs carry `origin` (`preset | user`), `preset{slug, locality, story,
  climate_tags}`, `centroid`, `area_km2`, `geometry_sha256` and `replay_coverage`. In replay, a
  drawn AOI gets opportunities from the recorded elements, scenes marked `not_recorded`, and an
  `insufficient-data` likelihood. *Why:* drawing stays useful offline without inventing
  archive data.
- **D30 — Further contract fields.** Health reports `{status, last_success_at, reason}` per
  upstream. Opportunities carry `element_age_seconds` and `illumination` (Sun at or below 0°:
  dropped; below 15°: `low_sun`; else `daylight`). Likelihoods carry history bounds and
  `computed_at`; provenance nodes carry `label`, `source_id`, `fixture_interaction_id` and
  `available_offline`; every resource has a `provenance_id`. Job stages are `catalogue | orbit |
  archive | raster | likelihood | finalise`. *Why:* each caveat a user needs is a field, not
  something the UI infers.
- **D32 — One attribution source.** `GET /attributions` returns the data-source credits
  (CelesTrak, Earth Search, Sentinel-2 COGs, JPL DE421) with dates from the fixture set; the web
  renders them verbatim and adds only its own basemap and runtime credits. *Why:* licence text
  is maintained once, next to the data it describes.
- **D33 — Generated types, no Python client.** `openapi-typescript` generates the TypeScript
  types into `web/src/api/generated/`, and `contract-check` fails on drift. Engine contract tests
  diff Pydantic response models against `contracts/openapi.yaml` and validate replay responses
  and SSE events against the contracts. *Why:* the contract stays the one source of truth.
- **D41 — Seasonal history from SCL overviews.** History reads each acquisition's SCL from the
  coarsest common overview that still gives the AOI at least 5,000 pixels, recording the overview
  factor in provenance; recent filmstrip scenes use native 20 m SCL. An acquisition is one datatake
  (`s2:datatake_id`): its tiles are mosaicked on one local equal-area AOI grid, and AOI pixels
  outside every tile count as no data, lowering valid coverage. *Why:* hundreds of past looks fit a
  small byte budget, and multi-tile AOIs count once per pass.

## Web

- **D2 — React and Cesium, no ion.** The web is React, TypeScript and Vite with CesiumJS, using
  no Cesium ion token or ion services. *Why:* a real 3D globe without account-bound services
  works from a clean clone for anyone.
- **D34 — Test hooks.** `ncl:ready` is a window `CustomEvent` plus `html[data-ncl-ready]`, fired
  after the first globe frame and first data load, before the camera fly-in. `window.__ncl`
  (`setTime()`, `pause()`) exists only when `VITE_NCL_TEST=1`, and `data-testid` values are
  kebab-case. *Why:* tests wait on a real signal instead of timeouts, and production ships no test
  controls.
- **D35 — Same origin.** In compose, nginx serves the web on port 4173 and proxies `/v1/` to the
  engine on 8000 with buffering off. Under `make dev`, Vite on 5173 proxies `/v1` to the engine
  on 4200. *Why:* one origin removes CORS, and unbuffered proxying keeps SSE live.
- **D36 — Sealed compose network.** `web` joins an `edge` bridge and the internal network; the
  engine joins only the internal network, which has no outbound route. The engine healthcheck has a
  10 s start period, and both containers run read-only with all capabilities dropped. *Why:* the
  replay engine physically cannot reach the internet, which proves offline operation.
- **D40 — Real engine by default.** Dev and compose talk to the real engine; MSW mocks are used
  only in unit tests and when `VITE_NCL_MOCK=1`. *Why:* what people see in development is what
  ships.

## Quality gates

- **D37 — Gates.** `make ci` runs gates G1–G17 (`tools/run_gates.py`). Frame-rate and long-task
  budgets are report-only and measured locally by `make perf-local`, while `make perf` blocks on
  load, LCP, CLS, per-endpoint API p95 and bundle budgets. Screenshot checks mask the WebGL canvas
  and allow `maxDiffPixelRatio: 0.01` for the DOM. Every OpenAPI operation has a realistic
  example, including 202s, live mode, an empty archive and insufficient data. *Why:* headless CI
  has no GPU, so only deterministic measurements may block a merge.
- **D38 — Offline from a clean clone.** `make bootstrap` installs locked dependencies (one root
  `pnpm-lock.yaml` with a workspace file, plus uv); browser downloads are separate in
  `make bootstrap-test`. After that, `make dev` and `docker compose up` need no upstream service.
  *Why:* a contributor can run and review the product without network access or accounts.
- **D39 — Coverage.** `make engine-coverage` runs the unit, contract, property and golden suites
  in one run with branch coverage and an 85% floor; `tools/check_coverage.py` requires 100% for
  `domain/clock.py`, `sources/transport/fixture.py` and `sources/transport/polite.py`.
  `make engine-unit` runs without a coverage gate, and both are part of `make ci`. *Why:* the
  modules that guarantee determinism and upstream politeness must have no untested branch.
