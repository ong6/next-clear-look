# Record/replay design

## Outcome

The checked-in demo is a closed, deterministic dataset. It starts in `replay` mode, reads only content-addressed fixtures, gets time from a frozen clock, and fails on an unknown request instead of reaching the internet. `live` and `record` are explicit operator choices.

This design supplies transport, clock, storage, and provenance interfaces. Scientific computation
stays in the engine, while presentation stays in the web application.

## Modes and guarantees

| Mode | Network | Clock | Cache behavior | Intended use |
|---|---|---|---|---|
| `replay` (default) | Denied; no fallback | Manifest `frozen_at`, advanced only explicitly | Read-only checked-in fixtures | Demo, tests, screenshots, normal offline startup |
| `live` | Allowlisted HTTPS upstreams | Real UTC clock through the same interface | Read/write runtime cache; never fixture files | Opt-in exploration |
| `record` | Allowlisted HTTPS upstreams | Operator-supplied frozen time plus real retrieval timestamps | Stages a new fixture generation atomically | Maintainer-only refresh |

Replay guarantees:

1. The same fixture revision, request and explicit clock operations yield byte-identical serialized source results.
2. DNS, proxy configuration and upstream availability cannot alter the result. An unrecorded request is `FixtureMiss`, not a network request.
3. Every body is SHA-256 checked before parsing. The manifest connects derived artifacts to all raw inputs.
4. Request matching includes method, canonical URL, canonical body digest, `Accept`, `Content-Type`, and `Range`; semantically different calls cannot alias.
5. Event timestamps, cache ages, countdown reference time and generated API timestamps come from the injected clock. Retrieval timing is evidence only and is never used in replay behavior.
6. Iteration is ordered explicitly: STAC Items by `(datetime,id)`, spacecraft by catalogue ID, object keys through canonical JSON, and SSE events by `(event_time,sequence)`.
7. CI runs with egress denied and with an unreachable proxy, so an accidental live dependency fails visibly.

Replay does not claim that the fixture is current, that upstream latency is reproduced, or that recorded data predicts acquisition/weather. It is an inspectable source snapshot.

## Components

```text
engine adapter
    |
    v
DataTransport.request(CanonicalRequest)
    |-- replay --> FixtureTransport --> manifest --> SHA-256 blobs
    |-- live ----> CacheTransport ----> AllowlistedHttpTransport
    `-- record --> RecordingTransport -> staging manifest + SHA-256 blobs

Clock.now()/advance_to()
    |-- replay --> FrozenClock(manifest.clock.frozen_at)
    `-- live ----> SystemUTCClock
```

Required interfaces:

```python
class Clock(Protocol):
    def now(self) -> datetime: ...          # aware UTC
    def advance_to(self, instant: datetime) -> None: ...  # replay only

class DataTransport(Protocol):
    async def request(self, request: CanonicalRequest) -> SourceSnapshot: ...

class FixtureStore(Protocol):
    def lookup(self, request: CanonicalRequest) -> StoredResponse: ...
    def open_blob(self, sha256: str) -> BinaryIO: ...
```

No engine or browser module may instantiate a system clock or HTTP client directly. Dependency-boundary tests enforce imports and constructor injection. The browser receives server time and event time from the contract; browser animation may use monotonic elapsed time, but decision values may not use `Date.now()`.

## Canonical request identity

A request key is the SHA-256 of canonical JSON containing:

```json
{
  "method": "POST",
  "url": "https://earth-search.aws.element84.com/v1/search",
  "headers": {
    "accept": "application/geo+json",
    "content-type": "application/json"
  },
  "body_sha256": "..."
}
```

- Normalize scheme/host case, remove default ports, preserve path case, sort query pairs, and reject URL fragments/user-info.
- JSON request bodies are UTF-8 canonical JSON (sorted keys, compact separators, finite numbers). Binary bodies are hashed as received.
- Only representation-changing headers participate: `Accept`, `Content-Type`, `Range`, and any future upstream version header. Hop-by-hop, auth, tracing, date, and User-Agent headers do not.
- Range syntax is normalized to one closed range, `bytes=<start>-<end>`. Suffix, open-ended, and multi-range requests are rejected in v1.

Exact matching is deliberate. It reveals hidden nondeterminism or contract drift instead of masking it with a similar fixture.

## Manifest and content-addressed storage

Planned repository shape:

```text
fixtures/
  presets/singapore-coast/
    manifest.json
  blobs/sha256/7d/7d6afad86d...    # full 64-hex digest is the filename
  schemas/manifest-v1.schema.json
```

Blobs are stored once across presets at `sha256/<first-two-hex>/<remaining-hex>`. The manifest is UTF-8 canonicalizable JSON and contains:

- `schema`, `fixture_set`, `recorded_at`, tool/schema versions;
- frozen clock (`frozen_at`, `timezone: UTC`, `tick_policy`);
- complete preset AOI GeoJSON and canonical query window;
- interactions with stable ID, method, URL, participating request headers, request-body digest, response status, safe headers, response-body `{sha256,size,path}`, and measured record duration;
- derived artifacts with source interaction/blob digests, parameters, media type, checksum and size;
- unique and per-source byte totals plus the enforced budget;
- required source attribution strings and source-policy revision URLs.

Safe response headers are an allowlist: media type/length/range, cache directives, ETag, Last-Modified, Date, Retry-After and server. Never serialize credentials, cookies, signed URLs, request IDs that encode identity, or local paths. URLs are rejected if they contain user-info or known signature parameters.

Manifest publication is transactional: write blobs, validate all data, write `manifest.json.tmp`, fsync where supported, atomically replace the manifest, then garbage-collect blobs not referenced by any manifest. A failed run leaves the prior generation usable.

## Recording normal HTTP

For CelesTrak and Earth Search, `RecordingTransport` wraps the same allowlisted client used by live mode:

1. Build and validate a canonical request.
2. Check source-specific policy before the socket is opened. The CelesTrak limiter uses a process lock plus durable last-success time and refuses a second request within two hours.
3. Make one request with bounded timeout. Do not retry CelesTrak. Earth Search may use the bounded retry policy in `data-contracts.md`.
4. Stream into a temporary hasher with a source-specific maximum size. A limit violation aborts without publishing.
5. Validate status, content type, declared length and parsed shape.
6. Move the body to its digest path and append the interaction to the staging manifest.

The recorder preserves raw bytes; canonical parsing output is derived and can be regenerated. HTTP compression is disabled for fixture capture (`Accept-Encoding: identity`) so byte sizes and digests have one meaning.

## Recording COG range reads

Production `rasterio` owns raster window reading. To observe its traffic, record mode gives
GDAL/rasterio an in-process loopback HTTP URL. The loopback range adapter maps only a
manifest-approved path to the validated remote asset URL:

1. Rasterio makes `HEAD`/`GET Range` calls to loopback.
2. The adapter forwards only closed ranges to the HTTPS allowlisted asset origin, pins the first ETag/Last-Modified, and rejects redirects to another origin.
3. It records every response through `RecordingTransport`, validates `206` and `Content-Range`, and returns the bytes to rasterio.
4. Duplicate ranges deduplicate naturally by body hash. A normalized interaction still records every distinct request range.
5. The derived AOI window records its source range digests, CRS/transform, pixel window, nodata, band, dtype, resampling label, library versions and output digest.

In replay, the same loopback adapter is backed only by `FixtureTransport`. This matters because GDAL may choose ranges based on TIFF metadata; the test exercises those real reads rather than replacing rasterio with a precomputed array. The adapter rejects a `200` response to `Range`, excessive range size, mismatched total length, overlapping bytes from different ETags, and a replay range not in the manifest.

The production recorder exercises rasterio through this adapter, so recorded range requests and
offline verification follow the same path as the application.

## Deterministic clock

Every preset manifest uses the one ISO-8601 UTC `frozen_at` selected for the fixture set by the
bounded backward search described below.

- `Clock.now()` returns the frozen instant until `advance_to()` is called.
- `advance_to()` may only move forward and only to a timestamp named in the replay event stream. Tests can construct an independent clock explicitly.
- SSE IDs are deterministic sequence numbers. Reconnect with `Last-Event-ID` resumes from the next recorded event without reading wall time.
- Cache freshness in replay is fixture metadata, not `now - recorded_at`; live freshness uses the system-clock implementation.
- Locale and time zone are pinned to `UTC` in engine containers and `TZ=UTC` in browser tests. Display-zone conversion is a pure consumer concern.
- Randomized tests use recorded seeds; production decision outputs must not depend on randomness unless a seed is part of the contract and provenance.

## Preset AOIs

Each preset is a reviewed file, not an arbitrary URL parameter:

```text
fixtures/presets/<slug>/
  aoi.geojson
  manifest.json     # generated, reviewed
```

`uv run --project engine python -m ncl_engine.fixtures record --preset all --clock <recording-instant>` invokes the engine's fixture pipeline, records its bounded STAC searches, lets rasterio read only the AOI windows it needs, and uses one shared CelesTrak query for the fixture set. The recorder searches backward by at most 72 hours and chooses the latest frozen time whose next Tuas opportunity is two to four hours later; `--clock` is the recording instant, not an operator-selected replay time. Presets have fixed geometry, stable slug and explicit maximum scenes. A single slug can be used during development, but the reviewed showcase generation is recorded together. Arbitrary user AOIs work in live/runtime cache but are never silently added to Git.

Adding a preset requires attribution review, an estimated byte budget, successful offline replay, semantic fixture diff, and explicit commit of the manifest and new blobs.

## Size budget

The hard repository gate is **less than 40 MiB total unique referenced fixture bytes**, measured from all manifests, not `du` and not the sum of references. The working allocation is:

| Category | Budget |
|---|---:|
| Shared OMM response plus DE421 excerpt | 0.5 MiB |
| Catalogue JSON for all presets | 12 MiB |
| Raw SCL ranges for six newest scenes | 2 MiB per preset |
| AOI-clipped PNGs (640 px, then 512/384 if needed) | 3 MiB per preset |
| Contract examples, SSE streams and engine goldens | 3 MiB |
| Manifests, attribution, metadata and headroom | Remainder |
| **Total ceiling** | **40 MiB** |

Individual raw COGs, full-resolution tile downloads and online basemap tiles are forbidden. No true-colour COG bytes are committed. Visual artifacts use reviewed AOI clips at a 640 px long edge, stepping down to 512 then 384 when needed, and a deterministic image encoding. CI reports largest blobs and fails at 40 MiB.

The checked-in fixture set includes the three-segment 2023–2027 DE421 excerpt, five AOI polygons,
the shared orbital-element response, STAC responses, recent-scene SCL ranges, and derived outputs.

## Refresh procedure

Refreshes are manual and reviewable, never a CI side effect:

1. Confirm no CelesTrak fetch for the canonical query succeeded in the last two hours.
2. Capture the UTC recording instant. The recorder deterministically derives the latest legal
   frozen time from the recorded OMM and writes both timestamps for review.
3. Run `make fixtures-record PRESET=all CLOCK=<ISO-UTC>` in explicit record mode.
4. The recorder stages and validates bodies, COG ranges, derived outputs, source policy metadata, and the 40 MiB ceiling.
5. Run `make fixtures-diff PRESET=singapore-coast`. Review scene IDs/epochs, ranges, class distributions, attribution years, blob additions/removals and all schema changes. Binary bytes alone are not a useful review.
6. Run `make offline-check` with egress denied, then the golden/contract gates. A refresh never automatically updates a golden expectation.
7. Commit only the reviewed manifest, referenced blobs and any intentional goldens. Keep the old fixture revision available through Git history, not duplicate directories.

If any source fails, validation fails, an asset version changes mid-read, or the budget is exceeded, discard staging and retain the old fixture. Never refresh just CelesTrak inside an otherwise old preset without moving the fixture generation and frozen clock together.

When publication fails only after all live responses were validated, a prompt
`make fixtures-record ... RESUME=1` may finish that same attempt from its local source cache. The
manifest records `origin: cache` for those interactions. A normal recording never reads the cache,
and the two-hour CelesTrak guard remains in force.

When code changes require derived outputs to be regenerated without moving the reviewed replay
clock, pass `FROZEN_AT=<existing-frozen-at>` together with `RESUME=1`. The recorder rejects a
future clock or one more than 72 hours before the recording instant, then revalidates the next
Tuas opportunity before publishing.
