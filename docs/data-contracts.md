# Next Clear Look data contracts

Status: verified 2026-10-03 SGT. This document specifies source-data boundaries and shared
interfaces; it does not choose orbit, geometry, probability, or presentation algorithms.

## Shared ingestion rules

1. Replay is the default. A caller must explicitly select `NCL_MODE=live` before any public-network request is possible.
2. Keep the exact response bytes before parsing. Each accepted response gets a SHA-256 digest, safe response headers, request identity, retrieval time, and upstream URL. Derived records refer to those digests.
3. Validate at the adapter boundary. Never pass an HTTP error page, an unvalidated `200`, a truncated range, a stale mixed-version COG, or malformed JSON to the engine.
4. A live failure may use the latest previously validated cache entry, labelled with its age. It may never silently manufacture an empty success. Replay misses are hard errors and never fall through to live HTTP.
5. Strip `Authorization`, cookies, client IP headers, signed query strings, and other secrets before fixture storage. The sources below are keyless; seeing credentials is itself an error.
6. Use bounded concurrency (two Earth Search requests and four COG ranges globally; one single-flight CelesTrak request). Honor `Retry-After`. CelesTrak errors are not retried automatically.
7. All parsed times become aware UTC instants. Preserve the source text beside the normalized value. Record the injected application clock separately from retrieval time.

The common adapter output is:

```text
SourceSnapshot {
  source_id, canonical_request, retrieved_at, status,
  safe_response_headers, body_sha256, body_size, body_path,
  parsed_value | validation_error
}
```

The engine uses `DataTransport.request(method, url, body, headers) -> SourceSnapshot`, a
`Clock.now() -> UTC instant`, and provenance references that survive into contract responses. The
web application receives replay/live mode, frozen time, source labels, retrieval times and
attribution strings through `contracts/openapi.yaml`. No other module calls a data upstream
directly.

## CelesTrak GP data in OMM JSON

### Request

| Property | Contract |
|---|---|
| Endpoint | `GET https://celestrak.org/NORAD/elements/gp.php` |
| Query | `NAME=SENTINEL-2&FORMAT=JSON` exactly; use the `.org` origin, not a redirected legacy hostname |
| Headers | `Accept: application/json`; an honest product `User-Agent`; no cache-bypass headers |
| Authentication | None |
| Live cadence | At most one successful download for this named set per two hours, process-wide, including developers and CI sharing the cache |
| Recorded result | HTTP 200; 1,256 bytes; three records for NORAD 40697, 42063 and 60989 |

The endpoint and query syntax are documented in [CelesTrak GP data formats](https://celestrak.org/NORAD/documentation/gp-data-formats.php). The [usage policy](https://celestrak.org/usage-policy.php) says to fetch only what is needed and only once per update; GP data updates once every two hours.

### Response shape and validation

The response is a bare JSON array, not an OMM XML envelope. Each object currently has:

| Field | JSON type | Meaning needed at this boundary |
|---|---|---|
| `OBJECT_NAME`, `OBJECT_ID` | string | Human name and international designator |
| `NORAD_CAT_ID` | integer | Stable catalogue identifier; the v1 allowlist is 40697/42063/60989 |
| `EPOCH` | string | UTC element epoch; CelesTrak omits a trailing `Z`, so the adapter must add UTC explicitly after parsing |
| `MEAN_MOTION`, `ECCENTRICITY`, `INCLINATION` | number | OMM orbital fields, with the OMM-defined units |
| `RA_OF_ASC_NODE`, `ARG_OF_PERICENTER`, `MEAN_ANOMALY` | number | Angular OMM fields in degrees |
| `EPHEMERIS_TYPE`, `ELEMENT_SET_NO`, `REV_AT_EPOCH` | integer | Element metadata |
| `CLASSIFICATION_TYPE` | string | Expected `U` for these public objects |
| `BSTAR`, `MEAN_MOTION_DOT`, `MEAN_MOTION_DDOT` | number | OMM drag and mean-motion derivative fields |

Require HTTP 200, JSON content, a non-empty array, unique integer catalogue IDs, finite numeric fields, and parseable epochs. Preserve all fields even if the engine does not currently consume them. A missing A/B/C spacecraft is a degraded-data condition, not permission to reuse another spacecraft's elements. An unexpected future Sentinel record may be retained in raw data but is excluded from v1 until the engine contract opts in.

### Policy, licence and attribution

CelesTrak makes the service freely available, but its site does not grant these GP values a named open-data licence. Treat the usage policy—not a presumed CC licence—as the redistribution boundary: ship the narrow recorded response required by the demo, do not mirror or bulk redistribute catalogues, identify the source, and keep the two-hour cache.

Exact in-product text (the date is data):

> Orbital elements: [CelesTrak](https://celestrak.org), retrieved 2026-10-02 UTC.

This is a product attribution, not a claim that CelesTrak prescribed that wording.

### Failures and caching

Documented failures include `301` for a wrong/legacy domain, `403` for excessive or repeated downloads, `404` for bad/retired URLs, and `50x` service errors. CelesTrak explicitly says machine clients must stop on every non-200; repeated 301/403/404 responses can lead to firewall blocking. Also handle timeout, malformed JSON, empty arrays, missing spacecraft, and elements whose epoch age violates the engine's input-freshness requirement.

Cache a validated `200` for **at least two hours**, keyed by the canonical query. Use a process/file lock so concurrent workers cannot double-fetch. After two hours, one worker may refresh; on any failure retain the prior snapshot as explicitly stale and stop further CelesTrak attempts for that run. CI and default demo only read the checked-in fixture.

## Element 84 Earth Search STAC

### Request

| Property | Contract |
|---|---|
| Endpoint | `POST https://earth-search.aws.element84.com/v1/search` |
| Content | `Content-Type: application/json`, `Accept: application/geo+json` |
| Authentication | None; public HTTPS assets in returned Items also require no AWS credentials |
| STAC conformance | STAC API 1.0.0 Item Search with query and sort extensions, as advertised by the API root |
| Develop-spike observation | HTTP 200; 63,247 bytes; three matched/returned Items |

Canonical Singapore preset body:

```json
{
  "collections": ["sentinel-2-l2a"],
  "datetime": "<archive-start>/<frozen_at>",
  "fields": {"include": ["id", "collection", "geometry", "bbox", "properties", "assets", "links"]},
  "intersects": {
    "type": "Polygon",
    "coordinates": [[[103.62,1.24],[103.77,1.24],[103.77,1.36],[103.62,1.36],[103.62,1.24]]]
  },
  "limit": 100,
  "sortby": [{"direction": "desc", "field": "properties.datetime"}]
}
```

The date interval belongs to this fixture generation, not to wall time, and its upper bound is the fixture's `frozen_at`. Live callers construct an equivalent bounded interval from an injected clock. A whole-tile cloud filter is forbidden: every scene is retained so AOI-level SCL evidence, rather than catalogue metadata, determines clear percentage.

### Response shape and validation

The response is a GeoJSON/STAC `FeatureCollection` with `features[]`, `links[]`, `numberMatched`/`numberReturned` (and, on some versions, equivalent `context.matched`/`context.returned`). Each Item must have:

- `type: Feature`, STAC version, stable `id`, `collection: sentinel-2-l2a`, polygon `geometry`, and WGS84 `bbox`;
- `properties.datetime`, `platform`, `constellation`, `eo:cloud_cover`, `proj:epsg`, grid identifiers, and processing metadata;
- `assets.scl` and `assets.visual`, each with an HTTPS `href`, media type, roles, `proj:shape`, `proj:transform`, and raster/EO band metadata where advertised;
- provenance links, especially `self`, `collection`, `root`, `license`, and `derived_from` when supplied.

Validate geometry and bounds, unique IDs, parseable UTC times, finite cloud cover in `[0,100]`, supported EPSG, HTTPS asset origins on an allowlist, and COG asset dimensions/transforms. Sort Items locally by `(datetime, id)` after validation even though the request asks the service to sort. Never substitute `eo:cloud_cover` for AOI-level evidence.

The recorded Items are `S2C_48NUG_20261001_0_L2A`, `S2B_48NUG_20260926_0_L2A`, and `S2A_48NUG_20260903_0_L2A`.

### Policy, licence and attribution

[Earth Search](https://github.com/Element84/earth-search) describes the API as free to use, best effort, with no guaranteed service. No numeric public rate limit or separate licence for the hosted catalogue metadata is published in that project. The `sentinel-2-l2a` Collection links to the Sentinel Data Legal Notice and currently labels its licence `proprietary`; do not interpret that label as ownership by Element 84. Rights in imagery and derived values follow the Copernicus notice below.

Exact in-product catalogue text:

> Catalogue: [Earth Search by Element 84](https://earth-search.aws.element84.com/v1).

No attribution text is claimed to be mandatory for the API; this text makes provenance visible.

### Failures and caching

Handle `400` validation errors, `404` collection/item errors, `429` throttling, `5xx`, timeout/DNS/TLS failures, invalid GeoJSON, empty results, missing assets, and dead asset links. Earth Search documents known catalogue gaps and occasional stale asset links, so a valid Item does not prove its asset exists. For 429/5xx, honor `Retry-After` and use capped exponential backoff with jitter only in explicit live mode; never paginate or broaden the AOI automatically.

Cache the canonical request body for 15 minutes for a moving live interval and for 24 hours when the interval is closed in the past. Cache an individual Item by `(collection, id, updated)`; replacing it requires a newly validated Item. Replay keeps the recorded bytes indefinitely by digest. At most two Earth Search calls may be in flight.

## Sentinel-2 Level-2A cloud-optimized GeoTIFF assets

### Request

Asset URLs come only from a validated Earth Search Item, not from filename construction. The v1 reads:

- `assets.scl`: 20 m `uint8` scene-classification COG used as raw AOI evidence;
- `assets.visual`: 10 m rendered true-colour COG used for AOI-clipped imagery;
- `assets.thumbnail`: optional JPEG for a low-cost placeholder, never for pixel statistics.

For a COG, send `GET <asset.href>` with `Range: bytes=<inclusive-start>-<inclusive-end>`, `Accept: image/tiff`, and an honest User-Agent. No authentication or requester-pays AWS credentials are required for the HTTPS `sentinel-cogs.s3.us-west-2.amazonaws.com` URLs returned by this collection. Require `206`, `Accept-Ranges: bytes`, an exactly matching `Content-Range`, and the requested byte count. A `200` response to a range request is rejected before reading a whole object.

The public HTTPS distribution publishes no numeric request quota or SLA. The client therefore caps itself at four concurrent ranges, coalesces adjacent reads when the raster library permits, caches immutable responses, and backs off on throttling instead of treating the absence of a published number as unlimited capacity.

The recorded SCL asset is:

```text
https://sentinel-cogs.s3.us-west-2.amazonaws.com/
  sentinel-s2-l2a-cogs/48/N/UG/2026/10/
  S2C_48NUG_20261001_0_L2A/SCL.tif
```

Observed structure: EPSG:32648; 5,490 x 5,490 pixels; 20 m transform `[20,0,300000,0,-20,200040]`; 512 x 512 Deflate-compressed tiles with horizontal predictor; no-data `0`. The object advertised 2,131,378 bytes, ETag `40ee9d2ed2adf61811798e4bb40c3782`, `Cache-Control: public, max-age=31536000, immutable`, and `Last-Modified: Thu, 01 Oct 2026 09:59:16 GMT`. ETag is a version token, not assumed to be a content hash.

SCL pixel values follow the Sentinel-2 L2A classification code list: 0 no-data, 1 saturated/defective, 2 dark-area pixels, 3 cloud shadows, 4 vegetation, 5 non-vegetated, 6 water, 7 unclassified, 8 medium-probability cloud, 9 high-probability cloud, 10 thin cirrus, 11 snow/ice. The data adapter returns raw window values, no-data, grid transform, CRS, per-class counts, and provenance. Clear/valid interpretation belongs to the scientific pipeline.

### Policy, licence and attribution

Copernicus Sentinel Data is free, full and open under the [Sentinel Data Legal Notice](https://dataspace.copernicus.eu/terms-and-conditions). Public redistribution must identify the source. Because Next Clear Look clips, summarizes, and renders the source, use the notice for modified data.

Exact in-product text, with the acquisition year substituted per scene:

> Contains modified Copernicus Sentinel data 2026.

The same notice covers the STAC-linked visual/SCL assets. Keep the Earth Search catalogue attribution adjacent in provenance so hosting/processing is not confused with data ownership.

### Failures and caching

Handle `403` access/policy errors, `404` missing or stale object links, `416` unsatisfiable ranges, `429`, S3 `503 Slow Down`, timeout/reset, truncated bodies, wrong media types, malformed TIFF directories, unsupported codecs, missing CRS/transform, and an ETag changing between range reads. Do not retry 403/404/416. A bounded retry is allowed for 429/503/transport failures in explicit live mode only. Cancel all reads for an asset if its version token changes; never combine byte ranges from different versions.

COG responses are immutable per scene in the observed service. Cache ranges indefinitely by `(URL, ETag-or-Last-Modified, start, end, body SHA-256)`, merge only contiguous verified ranges from the same version, and cache derived windows by the ordered source digests plus window/grid parameters. Eviction is LRU outside checked-in presets. The checked-in replay stores only ranges actually touched and remains subject to the 40 MiB fixture budget.

## Basemap

### Optional online close-zoom layer: EOX Sentinel-2 cloudless 2024

| Property | Contract |
|---|---|
| Template | `https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg` |
| Authentication | None |
| Licence | CC BY-NC-SA 4.0 |
| Availability | Community-funded, best effort, no SLA or numeric request quota |
| Mode | Optional browser enhancement when reachable; never required for startup or replay |

Each successful request returns one rendered JPEG tile plus ordinary HTTP cache validators. Treat any redirect away from the documented HTTPS origin, non-image body, decode error, timeout, `403`, `404`, `429`, or `5xx` as unavailable and switch to the bundled globe imagery. Do not loop over failed tiles and do not substitute a third-party mirror.

Exact visible attribution:

> Sentinel-2 cloudless – https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2024)

Preserve browser HTTP caching, do not bulk-download or prefetch, do not create an offline tile archive from this service, and switch to the offline layer after errors rather than retrying aggressively.

### Offline/default choice: NASA day/night imagery

Bundle NASA Blue Marble NG (`world.200412.3x5400x2700.jpg`) for the day side and NASA Black Marble 2012 (`dnb_land_ocean_ice.2012.3600x1800.jpg`) for the night side. Cesium lighting uses the application clock so the terminator is real. Both single-image assets are available without a runtime request and are added explicitly to the globe; Cesium's default base layer is disabled.

Exact visible attribution includes:

> NASA Blue Marble and Black Marble imagery.

The offline assets are covered by the web build. If they are absent or corrupt, the globe reports
a local asset error; it does not treat the optional EOX layer as an offline substitute.

## Cache and provenance summary

| Source | Live cache | Error behavior | Fixture rule |
|---|---|---|---|
| CelesTrak OMM | Minimum 2 h, single-flight | Stop on any non-200; stale labelled snapshot allowed | One narrow response; no bulk mirror |
| Earth Search search | 15 min moving / 24 h closed interval | Bounded retry only for 429/5xx; never broaden silently | Canonical POST body and exact response |
| STAC Item | `(collection,id,updated)` | Reject malformed/missing required assets | Preserve raw Item inside search response |
| COG ranges | Indefinite per immutable asset version | Never mix ETags; reject full-body `200` | Only touched ranges plus derived window |
| EOX tiles | Browser HTTP cache | Fall back locally | Never record or prefetch EOX tiles |
| NASA day/night imagery | Build/package lifetime | Local error, no network fallback | Bundled with the web build |

The fixture manifest, source timestamps, and attribution strings are API-visible inputs. They are not UI decorations and must remain testable through the contract.
