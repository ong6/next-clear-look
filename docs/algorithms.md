# Next Clear Look algorithms

This is an implementation specification. Unless stated otherwise, coordinates are longitude/latitude in WGS84, distances are metres and instants are timezone-aware UTC. Algorithm versions shown here are part of derived-cache keys.

## 1. Orbit propagation (`sgp4-swath-v1`)

### 1.1 Inputs and validation

Fetch CelesTrak's named Sentinel-2 group as OMM JSON no more than once per two hours. Persist the exact response before parsing. Require, per object, `OBJECT_NAME`, `NORAD_CAT_ID`, `EPOCH`, `MEAN_MOTION`, `ECCENTRICITY`, `INCLINATION`, `RA_OF_ASC_NODE`, `ARG_OF_PERICENTER`, `MEAN_ANOMALY`, `BSTAR`, first/second mean-motion derivatives and `EPHEMERIS_TYPE=0`. Reject a duplicate NORAD ID or an epoch in the future by more than five minutes.

Build `skyfield.api.EarthSatellite.from_omm(timescale, record)`. Surface the SGP4 error code/message for any invalid propagated state; do not interpolate across one.

### 1.2 Time handling

- Parse OMM epochs and API bounds as aware UTC. Naive datetimes are invalid.
- Use one Skyfield `Timescale` with packaged leap-second/IERS data pinned by the application build. The provenance records its data/version.
- Use half-open query bounds `[start, end)` to prevent duplicates between adjacent jobs.
- Replay obtains `start/end/as_of` from the injected clock. Random seeds never use process time.
- Record `element_age = propagation_time - OMM_epoch`. Label predictions stale after 24 hours. SGP4 can calculate farther away, but product policy—not numerical success—controls whether it is shown.

### 1.3 Frames

The required chain is:

1. OMM mean elements and epoch are inputs to SGP4.
2. SGP4 produces position/velocity in **TEME** at the requested UTC instant.
3. Skyfield applies Earth orientation and rotates TEME into the Earth-fixed **ITRS** frame for that instant.
4. Convert ITRS Cartesian coordinates to WGS84 geodetic longitude, latitude and ellipsoidal height with `wgs84.geographic_position_of()`.

TEME axes must never be treated as ECEF. Tests compare a pinned OMM/time against a reference TEME vector, ITRS vector and geodetic point. Round only at JSON serialisation.

### 1.4 Coarse propagation step

Use a 20-second coarse step. A Sentinel-2 ground track moves roughly 7.5 km/s, so one segment is about 150 km—smaller than the 290 km nominal swath. To avoid missing a crossing between samples, the candidate test uses:

```text
distance(centroid, subpoint) <= 145 km + AOI enclosing radius + 100 km guard
```

The 100 km guard exceeds half a coarse segment with margin. Process in ≤6-hour vectorised chunks to bound memory and check cancellation. A property test shifts a synthetic closest approach throughout the 20-second interval and verifies candidate retention.

For globe trajectories, return one-minute geodetic samples by default. The browser interpolates; this sampling is not used to find opportunity boundaries.

## 2. Sentinel-2 MSI sensor model

The nominal MSI field of view produces a **290 km ground swath** at Sentinel-2 altitude. V1 models a symmetric 145 km cross-track half-width around the propagated sub-satellite ground track. This is a geometric envelope, not detector-level viewing geometry or a product footprint guarantee.

At each track vertex:

1. Compute the forward ground-track azimuth in the current vertex's local tangent plane from the
   adjacent geodetic subpoints. Do not reuse the previous segment's initial bearing; that drifts
   by tens of kilometres near the high-latitude turning point.
2. Offset the vertex by 145 km at azimuth −90° and +90° using `Geod.fwd`.
3. Join left offsets forward and right offsets in reverse to make the time-slice strip; densify geodesic edges so no segment exceeds 25 km.
4. Repair only benign ring orientation/precision issues. A self-intersection or hemisphere-scale polygon is an algorithm error, not a `buffer(0)` success.

An imaging-capable opportunity must be descending (`d(latitude)/dt < 0` around closest approach), the spacecraft must be sunlit using the pinned JPL ephemeris, and solar elevation at the AOI centroid must exceed 0°. Sentinel-2 is sun-synchronous and daytime acquisitions occur on the descending node; ascending/night passes are excluded.

**Acquisition-plan caveat:** this model has no Copernicus observation plan, detector availability, manoeuvre, downlink or processing information. Every output remains `kind=geometric_opportunity`; archive acquisition status is attached only after Earth Search evidence exists.

### Operational spacecraft reconciliation

Do not hard-code a fleet forever. On refresh:

- map CelesTrak `SENTINEL-2A/B/C` to `sentinel-2a/-2b/-2c`;
- require a current non-decayed OMM;
- query recent Earth Search items and collect `properties.platform`;
- report `operational-observed` only when both catalogues agree; otherwise report `catalogued` with evidence fields.

The live spike at `2026-10-02T17:43:54Z` found current non-decayed OMMs and recent Singapore STAC acquisitions for all three values: `sentinel-2a`, `sentinel-2b`, `sentinel-2c`. This is time-bound evidence, not a permanent constant.

## 3. AOI intersection and opportunity refinement

### 3.1 Geometry normalisation

Accept valid Polygon/MultiPolygon only. Snap input coordinates to 1e-9 degrees for stable hashing, close rings, orient exteriors counter-clockwise and retain holes. Reject self-intersections with a useful pointer.

For antimeridian AOIs, unwrap longitudes around the circular-mean longitude, split at the chosen ±180° meridian, operate on parts, then wrap output to `[-180, 180)`. Never form a planar edge from +179° to −179°.

Distance/intersection work uses a local azimuthal-equidistant CRS centred on the AOI for AOIs up to the v1 area limit. This avoids UTM-zone and high-latitude failures. Cross-check boundaries with WGS84 geodesics. At |latitude| ≥80°, use the same local AEQD construction (or EPSG:3413/3031 for diagnostic rendering), not Web Mercator. Longitude is undefined exactly at a pole; preserve topology in projected space and emit a canonical 0° longitude only for a pole point.

### 3.2 Coarse scan and refinement

1. Run the guarded 20-second centroid scan from §1.4.
2. Group consecutive candidates per satellite/orbit. Expand each bracket by one coarse sample.
3. Define `f(t) = distance(projected subpoint(t), projected AOI) − 145000`.
4. Use bounded golden-section minimisation to find closest approach to ≤0.05 seconds. Discard if the minimum is positive.
5. On `[bracket_start, t_closest]` and `[t_closest, bracket_end]`, solve `f(t)=0` by bisection to ≤0.05 seconds. A bracket boundary already inside becomes the clipped entry/exit and sets `truncated=true`.
6. Construct the densified swath strip over the refined interval and require actual AOI intersection. Distance is the fast event function; polygon intersection is the final guard.
7. Evaluate direction/sun conditions at closest approach and apply the imaging-capable filter.

If disjoint AOI parts produce separated intervals, emit separate opportunities. Merge intervals only when their gap is under one second and satellite/AOI/source hashes match.

### 3.3 Opportunity fields

Every opportunity contains (with its stable ID keyed by AOI, platform and orbit revolution rather
than the search grid's refined timestamp):

- stable `id`, `kind=geometric_opportunity`, `aoi_id`, `satellite_id`, `platform`;
- `entry_time`, `closest_time`, `exit_time`, `duration_seconds`, `truncated`;
- `direction`, `satellite_sunlit`, `aoi_sun_elevation_deg`;
- `swath_width_km`, `minimum_ground_track_distance_km`, closest WGS84 subpoint/altitude;
- `acquisition_status=unknown|observed|not_observed` and optional matched scene;
- OMM epoch/hash, ephemeris hash, element age, propagation/refinement versions and caveat;
- `provenance_id`.

The spike produced 6 past and 5 future opportunities. Five Earth Search acquisitions all matched; one past opportunity had no archive acquisition.

## 4. STAC and raster statistics (`scl-aoi-v1`)

### 4.1 STAC query and scene/tile selection

POST to `https://earth-search.aws.element84.com/v1/search`:

```json
{
  "collections": ["sentinel-2-l2a"],
  "intersects": {"type": "Polygon", "coordinates": []},
  "datetime": "<from>/<to>",
  "limit": 100,
  "sortby": [{"field": "properties.datetime", "direction": "desc"}]
}
```

Follow `rel=next` links to the configured history limit. Do **not** filter on `eo:cloud_cover`: it is tile-wide and may discard a clear AOI. Require `scl` and `visual` assets, `proj:epsg`, geometry, `platform`, `datetime` and a tile/grid code.

Group items by exact `s2:datatake_id`; per-tile datetimes in one acquisition may differ by seconds.
Transform every tile and the AOI to one local equal-area AOI grid. Mosaic all intersecting tiles,
preferring classified pixels in overlap, and rasterise the complete AOI mask independently of the
tile extents. AOI pixels outside every tile therefore remain SCL 0 and count as no-data in the
full-AOI denominator. A result below 95% valid AOI coverage is stored but cannot be `usable`.

Record the raw STAC response hash and, per asset, URL, strong ETag/version, length and requested-range hashes.

### 4.2 Windowed COG reads

For each selected SCL asset:

1. Transform the AOI geometry from EPSG:4326 to the scene CRS with `always_xy=True`.
2. Derive and clamp the minimal raster window from AOI bounds.
3. Filmstrip scenes stay at native 20 m SCL and are processed in chunks of at most 1.5 million
   pixels. Seasonal-history counts use the coarsest common COG overview that still gives the full
   AOI mask at least 5,000 valid-or-excluded pixels. Reopen every source with Rasterio's
   `overview_level` for that factor, so the read comes from the overview rather than merely
   resampling the base layer. Record the factor in provenance and use nearest-neighbour
   reprojection.
4. Derive the exact output affine transform from the selected source level and destination grid.
5. Rasterise the projected AOI using pixel-centre semantics (`all_touched=false`). This makes the denominator stable and avoids boundary inflation.

Recent datatakes and seasonal-history datatakes run through a shared four-worker bound. GDAL may
open multiple loopback connections, but all transport coroutines are dispatched onto the calling
async event loop and the shared transport semaphore permits at most four active COG range reads
across the process. Results are restored to catalogue order before likelihood calculation.

SCL classes are:

| Value | Meaning | Valid denominator? | Clear? |
|---:|---|---|---|
| 0 | No data | No | No |
| 1 | Saturated/defective | No | No |
| 2 | Dark-area/cast-shadow category (baseline-dependent label) | Yes | No |
| 3 | Cloud shadow | Yes | No |
| 4 | Vegetation | Yes | Yes |
| 5 | Not vegetated | Yes | Yes |
| 6 | Water | Yes | Yes |
| 7 | Unclassified/low-confidence clear surface | Yes | Yes |
| 8 | Medium-probability cloud | Yes | No |
| 9 | High-probability cloud | Yes | No |
| 10 | Thin cirrus | Yes | No |
| 11 | Snow/ice | Yes | Only for an ice-subject area |

Therefore:

```text
inside = rasterised AOI pixel centres
valid  = inside AND SCL in {2..11}
clear  = inside AND SCL in {4,5,6,7}
clear_percent = 100 * count(clear) / count(valid)
valid_coverage_percent = 100 * count(valid) / count(inside)
```

The default surface set is `{4,5,6,7}`. An area whose subject is ice may declare
`{4,5,6,7,11}`; Jakobshavn does, so snow/ice is evidence of visible subject surface there rather
than an obscurant. `surface_class_policy` appears in both statistics and likelihood responses,
including the explicit `snow_ice_counted_as_surface` flag. If `count(valid)=0`,
`clear_percent=null` and the scene is unusable. Persist all 12 class counts so the definition can
be audited or recomputed.

### 4.3 True-colour thumbnail

Read only the AOI window from the `visual`/TCI asset. Choose the nearest overview for the
configured long edge (640 px by default), read RGB with bilinear resampling, rasterise the same
AOI into the output grid, set alpha 0 outside or where all source bands are nodata and alpha 255
elsewhere, then encode a deterministic RGBA PNG. Return source/output dimensions, overview,
SHA-256, byte length and provenance. Never use the STAC preview as the AOI thumbnail.

The live spike used full-resolution SCL and factor-2 TCI overviews. Its three AOI clear values were 69.9007%, 92.1478% and 2.5907%, while tile cloud values were 37.938815%, 32.858709% and 73.122436%. GDAL received 11,215,940 response-body bytes for all SCL and TCI windows.

## 5. Historical likelihood (`seasonal-beta-acquisition-clear-v1`)

### 5.1 Trial construction

Use two explicit trial populations from a cyclic ±45-day seasonal window over at most the prior three years:

1. **Acquisition trials.** Use `sat:relative_orbit` and each Sentinel platform's ten-day repeat
   cycle, beginning at that platform/path's first observed acquisition (so Sentinel-2C is never
   charged for pre-launch years). Match actual archive acquisitions one-to-one to the nearest
   unclaimed repeat slot. An expected opportunity with an acquisition is a success; one without
   is a failure. Current OMMs are never propagated backward as historical truth.
2. **Clear trials.** Read a coarse full-AOI SCL mosaic for every deduplicated seasonal datatake
   over up to three years, without generating a thumbnail. A success has at least 95% valid AOI
   coverage and `clear_percent ≥70`; an evaluated look below the clear threshold is a failure.
3. A scene whose SCL evidence is unavailable or corrupt is excluded from the clear posterior with its reason. It is not silently counted as cloudy.
4. Multiple tiled Items for one platform/datatake/acquisition are mosaicked first and count as one acquisition.

Require 20 evaluated trials for each posterior. If the seasonal AOI pool is short, return
`insufficient-data`; do not turn the six recent filmstrip scenes into the historical sample or pool
a global/tile climatology without an explicit future model version.

### 5.2 Posterior and horizon probability

Use independent weak uniform priors for acquisition and clear-given-acquisition:

```text
p_acquisition ~ Beta(1 + acquired, 1 + not_acquired)
p_clear       ~ Beta(1 + usable_acquisitions, 1 + unusable_acquisitions)
```

For every Monte Carlo draw, sample both posteriors and combine them for each distinct local
opportunity day. Multiple satellite passes on the same day share one likelihood draw because
cloud persistence makes treating them as independent trials unjustified. With `N_days` distinct
opportunity days:

```text
p_usable_j = p_acquisition_j * p_clear_j
q_j = P(at least one acquired, usable look | p_usable_j, N_days)
    = 1 - (1 - p_usable_j)^N_days
```

Draw 100,000 paired values. The point estimate is `mean(q_j)`; the honest interval is the 5th–95th percentile (90% equal-tailed credible interval). Seed NumPy PCG64 with the first 64 bits of `sha256(aoi_hash | as_of | model_version)`, so replay is byte-stable. Check posterior sufficiency first: when either posterior has fewer than 20 evaluated trials, probability and interval are null even if `N_days=0`. With sufficient evidence and `N_days=0`, probability and both bounds are 0.

Return for each 7/14-day horizon: raw opportunity count, distinct opportunity-day count,
probability, and interval/level. `opportunity_count` remains audit and display evidence but is not
the exponent. Both horizons start at `window_start`; `window_end` is exactly 14 days later and is
also the default opportunity-list bound, so the listed rows are precisely the passes counted by
the model. Return both posteriors, their success/failure/excluded counts, threshold,
season/fallback tier, history bounds, `computed_at`, model version, Monte Carlo draws/seed and
provenance.

The generated sparse example is labelled `insufficient-data` and returns null probabilities instead of turning six recent SCL looks into false precision. Acquisition and excluded-history counts remain visible so the missing clear-evidence work is auditable.

This model assumes exchangeable opportunity days within a season. Grouping by day reduces but does not remove multi-day cloud autocorrelation. The interval is posterior parameter uncertainty, not a numerical weather forecast.

## 6. Hindcast validation

Validation operates on frozen source editions and never trains on the scored period.

1. For each evaluation cutoff, use the latest OMM captured **at or before** that cutoff; predict the following horizon.
2. Query all Earth Search `sentinel-2-l2a` items intersecting the AOI/time range without a cloud filter. Deduplicate tiled records by platform/datatake/acquisition.
3. Per platform, construct candidate pairs between predicted opportunities and acquisitions when scene footprint intersects the AOI and acquisition time is within ±15 minutes of predicted closest time.
4. Sort candidate pairs by absolute timing error and greedily claim the lowest-error unclaimed
   opportunity and acquisition. Never match one acquisition twice.
5. Report:
   - archive acquisition recall = matched acquisitions / actual acquisitions;
   - opportunity observation rate = matched opportunities / predicted opportunities;
   - signed, median absolute and p95 absolute timing error;
   - footprint intersection failures and platform-specific counts;
   - usable-day Brier score, log score and reliability bins once at least 50 out-of-sample days exist.
6. Investigate unmatched items by OMM age, platform, antimeridian/high-latitude geometry and STAC footprint. Do not tune the matching window on the final test period.

The committed hindcast fixture propagates one OMM edition up to about 19.4 days backward, which
is intentionally outside a defensible historical-element window. It nevertheless matches all 5
recorded acquisitions in the 20-day test: 100% acquisition recall, 83.33% opportunity observation
rate, 0.282 s median and 1.518 s p95 absolute timing error. These values test matching and geometry
for this AOI; they do **not** validate long-range OMM accuracy or acquisition planning.

## 7. Required tests

- Pinned OMM reference vectors through TEME, ITRS and WGS84.
- Coarse-step phase property test and entry/exit convergence below 0.05 s.
- Swath ring validity at equator, antimeridian, ±80° and pole-adjacent AOIs.
- Descending/ascending and sunlit/daylight filters around node/terminator boundaries.
- STAC pagination, multi-tile deterministic cover and no tile-cloud prefilter.
- Raster pixel-count golden tests at native and overview grids, including a stale overview whose
  pixels intentionally differ from the base layer.
- SCL class table/denominator tests including invalid-only pixels and the ice-subject policy.
- Thumbnail alpha and checksum golden test with pinned encoder.
- Beta closed-form moments, deterministic Monte Carlo, same-day pass grouping, `N_days=0`, leap-year New Year wrapping and fallback disclosure.
- One-to-one matching conflicts plus the five-acquisition recorded hindcast.
