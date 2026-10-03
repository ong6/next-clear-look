# `ncl-showcase` recorded fixture set

This directory is the closed, deterministic data set used by the default replay product.
`fixture-set.json` is the entry point; each preset manifest references content-addressed source and
derived blobs under `blobs/sha256/`.

- Fixture status: `ready`
- Chosen replay clock (`frozen_at`): `2026-10-01T01:37:48.308302Z`
- Publication completed (`recorded_at`): `2026-10-03T01:28:47.076771Z`
- Shared CelesTrak response: one response retrieved at `2026-10-02T19:35:36.011051Z` and reused
  from the policy cache for the final all-preset publication; no second group query was made
- JPL DE421 excerpt coverage: 2023-01-01 through 2027-12-31

## Preset accounting

`Referenced bytes` is the sum of unique blob references in that preset manifest; shared OMM and
ephemeris bytes are reported only in the fixture-set budget below. `Seasonal looks` are
deduplicated datatakes with coarse-overview SCL counts. Their source range digests and interaction
IDs are retained, but history-only COG range bodies are not bundled. `14-day opportunities / days`
distinguishes listed passes from the distinct opportunity days used by the likelihood model.

| Preset | Recorded bbox | Recent scenes | Seasonal looks | 14-day opportunities / days | Referenced bytes | Catalogue JSON | Recent SCL ranges | Derived PNG | Derived JSON |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Singapore coast | `[103.62, 1.24, 103.77, 1.36]` | 6 | 65 | 5 / 5 | 3,955,150 | 502,229 | 970,150 | 2,384,025 | 92,187 |
| Rotterdam port | `[3.93, 51.91, 4.10, 52.01]` | 6 | 141 | 9 / 7 | 4,326,448 | 1,098,821 | 349,361 | 2,688,182 | 178,627 |
| Atacama works | `[-68.42, -23.72, -68.22, -23.50]` | 6 | 63 | 5 / 5 | 4,661,021 | 1,015,222 | 867,241 | 2,662,442 | 104,561 |
| Sundarbans delta | `[89.35, 21.62, 89.50, 21.76]` | 6 | 62 | 5 / 5 | 3,424,618 | 1,023,520 | 623,064 | 1,664,303 | 103,886 |
| Jakobshavn ice front | `[-50.25, 69.10, -49.75, 69.25]` | 6 | 162 | 12 / 9 | 4,428,176 | 1,192,542 | 823,021 | 2,199,375 | 201,718 |

Tuas keeps its original reviewed geometry unchanged. Every other AOI is above 100 km² and visibly
contains its named feature. Their geodesic areas are Rotterdam 130.02 km², Atacama 497.33 km²,
Sundarbans 240.63 km² and Jakobshavn 332.07 km². Visual review of the clearest derived PNG confirms
Maasvlakte 2 port land/harbours, the Salar evaporation-pond fields, Sundarbans tidal
islands/channels, and the Sermeq Kujalleq/Jakobshavn glacier-front landscape are in frame.
Sundarbans deliberately crosses 45QYD/45QYE; the other presets prefer a single tile. Catalogue JSON
is 4,832,334 bytes without a tile-cloud filter, below the 12 MiB ceiling.

Every opportunity list and likelihood uses the same half-open window,
`2026-10-01T01:37:48.308302Z` to `2026-10-15T01:37:48.308302Z`. The 14-day list count matches the
likelihood's `opportunity_count` for every preset. Multiple passes on one local date in the area's time zone count as one
`opportunity_day` in the probability calculation. Jakobshavn's policy includes snow/ice (SCL 11)
as surface in both recent scene statistics and the likelihood; the other four presets do not.

## Whole-set budget

| Category | Bytes | Limit |
|---|---:|---:|
| Shared OMM + ephemeris | 248,064 | 524,288 |
| Catalogue JSON | 4,832,334 | 12,582,912 |
| Recent native-SCL range bytes | 3,632,833 | 2,097,152 per preset |
| Derived AOI PNGs | 11,598,327 | 3,145,728 per preset |
| Examples, goldens and SSE | 49,394 | 3,145,728 |
| Unique referenced blobs | 21,043,473 | 41,943,040 |
| Repository fixture material | 22,013,372 | 41,943,040 |

No true-colour COG bytes or history-only SCL range bytes are committed. Recent scenes use native
20 m SCL mosaics; seasonal histories use the coarsest overview that retains at least 5,000
valid-or-excluded AOI pixels. Every history JSON records `source_range_sha256`, overview factor,
class counts and `bytes_bundled: false`.

## Verification

From the repository root:

```bash
make fixtures-check
make offline-check
```

The recorded run validates five manifests, 783 unique blobs, request identities, hashes, history
provenance, recent-statistic byte equality through rasterio, deterministic replay and the
whole/per-category budgets. `make offline-check` repeats the validation with dead proxies and then
runs the replay/transport suite with non-loopback sockets denied.
