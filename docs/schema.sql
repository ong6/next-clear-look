PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

BEGIN;

CREATE TABLE schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

INSERT INTO schema_meta(key, value) VALUES
    ('schema_version', '1'),
    ('created_for', 'next-clear-look');

CREATE TABLE engine_mode (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    mode TEXT NOT NULL CHECK (mode IN ('live', 'replay')),
    effective_clock TEXT NOT NULL,
    network_enabled INTEGER NOT NULL CHECK (network_enabled IN (0, 1)),
    live_available INTEGER NOT NULL CHECK (live_available IN (0, 1)),
    fixture_set TEXT,
    fixture_recorded_at TEXT,
    updated_at TEXT NOT NULL,
    CHECK ((mode = 'live' AND network_enabled = 1) OR (mode = 'replay' AND network_enabled = 0))
) STRICT;

CREATE TABLE raw_blobs (
    sha256 TEXT PRIMARY KEY CHECK (length(sha256) = 64),
    byte_length INTEGER NOT NULL CHECK (byte_length >= 0),
    media_type TEXT,
    storage_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE source_requests (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('celestrak', 'earth-search', 'sentinel-cogs', 'jpl-de421')),
    request_key_sha256 TEXT NOT NULL CHECK (length(request_key_sha256) = 64),
    origin TEXT NOT NULL CHECK (origin IN ('network', 'cache', 'fixture')),
    fixture_interaction_id TEXT,
    method TEXT NOT NULL CHECK (method IN ('GET', 'HEAD', 'POST')),
    url TEXT NOT NULL,
    request_body_sha256 TEXT CHECK (request_body_sha256 IS NULL OR length(request_body_sha256) = 64),
    requested_range_start INTEGER,
    requested_range_end INTEGER,
    response_status INTEGER,
    response_blob_sha256 TEXT REFERENCES raw_blobs(sha256),
    etag TEXT,
    last_modified TEXT,
    fetched_at TEXT NOT NULL,
    fresh_until TEXT,
    error_code TEXT,
    CHECK (
        (requested_range_start IS NULL AND requested_range_end IS NULL)
        OR (requested_range_start >= 0 AND requested_range_end >= requested_range_start)
    )
) STRICT;

CREATE UNIQUE INDEX source_requests_identity_idx ON source_requests(
    source, method, url, ifnull(request_body_sha256, ''),
    ifnull(requested_range_start, -1), ifnull(requested_range_end, -1), fetched_at
);
CREATE INDEX source_requests_cache_idx ON source_requests(source, method, url, fresh_until DESC);

CREATE TABLE provenance_nodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('raw_input', 'derived', 'request', 'algorithm', 'geometry')),
    artifact_type TEXT NOT NULL,
    label TEXT NOT NULL,
    source_id TEXT CHECK (source_id IS NULL OR source_id IN ('celestrak', 'earth-search', 'sentinel-cogs', 'jpl-de421')),
    request_key_sha256 TEXT CHECK (request_key_sha256 IS NULL OR length(request_key_sha256) = 64),
    fixture_interaction_id TEXT,
    available_offline INTEGER NOT NULL CHECK (available_offline IN (0, 1)),
    sha256 TEXT CHECK (sha256 IS NULL OR length(sha256) = 64),
    algorithm_version TEXT,
    parameters_json TEXT CHECK (parameters_json IS NULL OR json_valid(parameters_json)),
    source_request_id TEXT REFERENCES source_requests(id),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE provenance_edges (
    from_node_id TEXT NOT NULL REFERENCES provenance_nodes(id) ON DELETE CASCADE,
    to_node_id TEXT NOT NULL REFERENCES provenance_nodes(id) ON DELETE CASCADE,
    relation TEXT NOT NULL CHECK (relation IN ('input_to', 'generated_by', 'describes', 'derived_from')),
    PRIMARY KEY (from_node_id, to_node_id, relation),
    CHECK (from_node_id <> to_node_id)
) STRICT, WITHOUT ROWID;

CREATE INDEX provenance_edges_to_idx ON provenance_edges(to_node_id);

CREATE TABLE aois (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    origin TEXT NOT NULL CHECK (origin IN ('preset', 'user')),
    preset_json TEXT CHECK (preset_json IS NULL OR json_valid(preset_json)),
    geometry_geojson TEXT NOT NULL CHECK (json_valid(geometry_geojson)),
    centroid_geojson TEXT NOT NULL CHECK (json_valid(centroid_geojson)),
    replay_coverage_json TEXT NOT NULL CHECK (json_valid(replay_coverage_json)),
    geometry_sha256 TEXT NOT NULL CHECK (length(geometry_sha256) = 64),
    min_lon REAL NOT NULL CHECK (min_lon BETWEEN -180 AND 180),
    min_lat REAL NOT NULL CHECK (min_lat BETWEEN -90 AND 90),
    max_lon REAL NOT NULL CHECK (max_lon BETWEEN -180 AND 180),
    max_lat REAL NOT NULL CHECK (max_lat BETWEEN -90 AND 90),
    timezone TEXT NOT NULL DEFAULT 'UTC',
    area_km2 REAL NOT NULL CHECK (area_km2 > 0 AND area_km2 <= 250000),
    vertex_count INTEGER NOT NULL CHECK (vertex_count BETWEEN 4 AND 10000),
    provenance_node_id TEXT REFERENCES provenance_nodes(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (min_lat <= max_lat)
) STRICT;

CREATE UNIQUE INDEX aois_geometry_idx ON aois(geometry_sha256);

CREATE TABLE satellites (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    norad_catalog_id INTEGER NOT NULL UNIQUE CHECK (norad_catalog_id > 0),
    platform TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('operational-observed', 'catalogued', 'stale', 'retired')),
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE omm_records (
    id TEXT PRIMARY KEY,
    satellite_id TEXT NOT NULL REFERENCES satellites(id),
    epoch TEXT NOT NULL,
    raw_blob_sha256 TEXT NOT NULL REFERENCES raw_blobs(sha256),
    source_request_id TEXT NOT NULL REFERENCES source_requests(id),
    parsed_json TEXT NOT NULL CHECK (json_valid(parsed_json)),
    inserted_at TEXT NOT NULL,
    UNIQUE (satellite_id, epoch, raw_blob_sha256)
) STRICT;

CREATE INDEX omm_records_lookup_idx ON omm_records(satellite_id, epoch DESC);

CREATE TABLE trajectories (
    id TEXT PRIMARY KEY,
    satellite_id TEXT NOT NULL REFERENCES satellites(id),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    sample_interval_seconds INTEGER NOT NULL CHECK (sample_interval_seconds BETWEEN 1 AND 600),
    frame TEXT NOT NULL,
    samples_json TEXT NOT NULL CHECK (json_valid(samples_json)),
    algorithm_version TEXT NOT NULL,
    derived_key_sha256 TEXT NOT NULL UNIQUE CHECK (length(derived_key_sha256) = 64),
    provenance_node_id TEXT NOT NULL REFERENCES provenance_nodes(id),
    created_at TEXT NOT NULL,
    CHECK (start_time < end_time)
) STRICT;

CREATE INDEX trajectories_window_idx ON trajectories(satellite_id, start_time, end_time);

CREATE TABLE opportunities (
    id TEXT PRIMARY KEY,
    aoi_id TEXT NOT NULL REFERENCES aois(id) ON DELETE CASCADE,
    satellite_id TEXT NOT NULL REFERENCES satellites(id),
    entry_time TEXT NOT NULL,
    closest_time TEXT NOT NULL,
    exit_time TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('descending', 'ascending')),
    satellite_sunlit INTEGER NOT NULL CHECK (satellite_sunlit IN (0, 1)),
    aoi_sun_elevation_deg REAL NOT NULL,
    illumination TEXT NOT NULL CHECK (illumination IN ('daylight', 'low_sun')),
    element_age_seconds REAL NOT NULL,
    swath_width_km REAL NOT NULL CHECK (swath_width_km > 0),
    swath_footprint_geojson TEXT NOT NULL CHECK (json_valid(swath_footprint_geojson)),
    minimum_ground_track_distance_km REAL NOT NULL CHECK (minimum_ground_track_distance_km >= 0),
    closest_subpoint_json TEXT NOT NULL CHECK (json_valid(closest_subpoint_json)),
    acquisition_status TEXT NOT NULL CHECK (acquisition_status IN ('unknown', 'observed', 'not_observed')),
    matched_scene_id TEXT REFERENCES scenes(id),
    truncated INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0, 1)),
    algorithm_version TEXT NOT NULL,
    omm_record_id TEXT NOT NULL REFERENCES omm_records(id),
    derived_key_sha256 TEXT NOT NULL UNIQUE CHECK (length(derived_key_sha256) = 64),
    provenance_node_id TEXT NOT NULL REFERENCES provenance_nodes(id),
    created_at TEXT NOT NULL,
    CHECK (entry_time <= closest_time AND closest_time <= exit_time),
    UNIQUE (aoi_id, satellite_id, closest_time, algorithm_version)
) STRICT;

CREATE INDEX opportunities_aoi_time_idx ON opportunities(aoi_id, closest_time);
CREATE INDEX opportunities_satellite_time_idx ON opportunities(satellite_id, closest_time);

CREATE TABLE scenes (
    id TEXT PRIMARY KEY,
    collection TEXT NOT NULL DEFAULT 'sentinel-2-l2a',
    platform TEXT NOT NULL,
    acquisition_time TEXT NOT NULL,
    datatake_id TEXT,
    tile TEXT NOT NULL,
    footprint_geojson TEXT NOT NULL CHECK (json_valid(footprint_geojson)),
    stac_self_url TEXT NOT NULL,
    analysis_state TEXT NOT NULL CHECK (analysis_state IN ('queued', 'reading', 'analysing', 'ready', 'failed', 'not_recorded')),
    analysis_error_json TEXT CHECK (analysis_error_json IS NULL OR json_valid(analysis_error_json)),
    thumbnail_status TEXT NOT NULL CHECK (thumbnail_status IN ('ready', 'pending', 'not_bundled', 'failed')),
    tile_cloud_cover_percent REAL CHECK (tile_cloud_cover_percent BETWEEN 0 AND 100),
    stac_item_blob_sha256 TEXT NOT NULL REFERENCES raw_blobs(sha256),
    source_request_id TEXT NOT NULL REFERENCES source_requests(id),
    provenance_node_id TEXT NOT NULL REFERENCES provenance_nodes(id),
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX scenes_time_idx ON scenes(acquisition_time DESC);
CREATE INDEX scenes_platform_time_idx ON scenes(platform, acquisition_time DESC);

CREATE TABLE scene_assets (
    scene_id TEXT NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('scl', 'visual', 'thumbnail', 'other')),
    href TEXT NOT NULL,
    media_type TEXT,
    proj_epsg INTEGER,
    gsd_m REAL CHECK (gsd_m IS NULL OR gsd_m > 0),
    etag TEXT,
    content_length INTEGER CHECK (content_length IS NULL OR content_length >= 0),
    metadata_json TEXT CHECK (metadata_json IS NULL OR json_valid(metadata_json)),
    PRIMARY KEY (scene_id, role)
) STRICT, WITHOUT ROWID;

CREATE TABLE scene_statistics (
    id TEXT PRIMARY KEY,
    scene_id TEXT NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    aoi_id TEXT NOT NULL REFERENCES aois(id) ON DELETE CASCADE,
    aoi_coverage_percent REAL NOT NULL CHECK (aoi_coverage_percent BETWEEN 0 AND 100),
    inside_aoi_pixels INTEGER NOT NULL CHECK (inside_aoi_pixels >= 0),
    valid_pixels INTEGER NOT NULL CHECK (valid_pixels >= 0),
    clear_pixels INTEGER NOT NULL CHECK (clear_pixels >= 0),
    invalid_pixels INTEGER NOT NULL CHECK (invalid_pixels >= 0),
    valid_coverage_percent REAL CHECK (valid_coverage_percent BETWEEN 0 AND 100),
    clear_percent REAL CHECK (clear_percent BETWEEN 0 AND 100),
    class_counts_json TEXT NOT NULL CHECK (json_valid(class_counts_json)),
    source_resolution_m REAL NOT NULL CHECK (source_resolution_m > 0),
    overview_factor INTEGER NOT NULL CHECK (overview_factor >= 1),
    algorithm_version TEXT NOT NULL,
    derived_key_sha256 TEXT NOT NULL UNIQUE CHECK (length(derived_key_sha256) = 64),
    provenance_node_id TEXT NOT NULL REFERENCES provenance_nodes(id),
    computed_at TEXT NOT NULL,
    CHECK (clear_pixels <= valid_pixels AND valid_pixels + invalid_pixels = inside_aoi_pixels),
    UNIQUE (scene_id, aoi_id, algorithm_version)
) STRICT;

CREATE INDEX scene_statistics_aoi_idx ON scene_statistics(aoi_id, computed_at DESC);

CREATE TABLE thumbnails (
    id TEXT PRIMARY KEY,
    scene_id TEXT NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    aoi_id TEXT NOT NULL REFERENCES aois(id) ON DELETE CASCADE,
    png_blob_sha256 TEXT NOT NULL REFERENCES raw_blobs(sha256),
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    transparent_outside_aoi INTEGER NOT NULL CHECK (transparent_outside_aoi IN (0, 1)),
    algorithm_version TEXT NOT NULL,
    derived_key_sha256 TEXT NOT NULL UNIQUE CHECK (length(derived_key_sha256) = 64),
    provenance_node_id TEXT NOT NULL REFERENCES provenance_nodes(id),
    created_at TEXT NOT NULL,
    UNIQUE (scene_id, aoi_id, algorithm_version)
) STRICT;

CREATE TABLE likelihood_estimates (
    id TEXT PRIMARY KEY,
    aoi_id TEXT NOT NULL REFERENCES aois(id) ON DELETE CASCADE,
    as_of TEXT NOT NULL,
    horizon_days INTEGER NOT NULL CHECK (horizon_days IN (7, 14)),
    opportunity_days INTEGER NOT NULL CHECK (opportunity_days >= 0),
    opportunity_count INTEGER NOT NULL CHECK (opportunity_count >= 0),
    probability REAL CHECK (probability BETWEEN 0 AND 1),
    interval_level REAL CHECK (interval_level > 0 AND interval_level < 1),
    interval_lower REAL CHECK (interval_lower BETWEEN 0 AND 1),
    interval_upper REAL CHECK (interval_upper BETWEEN 0 AND 1),
    acquisition_posterior_json TEXT NOT NULL CHECK (json_valid(acquisition_posterior_json)),
    clear_posterior_json TEXT NOT NULL CHECK (json_valid(clear_posterior_json)),
    excluded_count INTEGER NOT NULL CHECK (excluded_count >= 0),
    history_start TEXT NOT NULL,
    history_end TEXT NOT NULL,
    season_json TEXT NOT NULL CHECK (json_valid(season_json)),
    quality TEXT NOT NULL CHECK (quality IN ('seasonal', 'all-season-fallback', 'tile-fallback', 'insufficient-data', 'demo-only-sparse')),
    model_version TEXT NOT NULL,
    derived_key_sha256 TEXT NOT NULL UNIQUE CHECK (length(derived_key_sha256) = 64),
    provenance_node_id TEXT NOT NULL REFERENCES provenance_nodes(id),
    computed_at TEXT NOT NULL,
    CHECK (
        probability IS NULL
        OR (interval_lower <= probability AND probability <= interval_upper)
    ),
    UNIQUE (aoi_id, as_of, horizon_days, model_version)
) STRICT;

CREATE INDEX likelihood_aoi_time_idx ON likelihood_estimates(aoi_id, as_of DESC);

CREATE TABLE analysis_jobs (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('full_analysis', 'orbit_only', 'archive_refresh', 'raster_scene', 'likelihood_only')),
    aoi_id TEXT REFERENCES aois(id) ON DELETE SET NULL,
    scene_id TEXT REFERENCES scenes(id) ON DELETE SET NULL,
    mode TEXT NOT NULL CHECK (mode IN ('live', 'replay')),
    request_fingerprint_sha256 TEXT NOT NULL CHECK (length(request_fingerprint_sha256) = 64),
    idempotency_key TEXT,
    state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    stage TEXT NOT NULL CHECK (stage IN ('catalogue', 'orbit', 'archive', 'raster', 'likelihood', 'finalise')),
    progress REAL NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
    request_json TEXT NOT NULL CHECK (json_valid(request_json)),
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    error_json TEXT CHECK (error_json IS NULL OR json_valid(error_json)),
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    cancel_requested_at TEXT,
    updated_at TEXT NOT NULL,
    CHECK (
        (state IN ('succeeded', 'failed', 'cancelled') AND finished_at IS NOT NULL)
        OR (state IN ('queued', 'running') AND finished_at IS NULL)
    )
) STRICT;

CREATE UNIQUE INDEX analysis_jobs_idempotency_idx ON analysis_jobs(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX analysis_jobs_state_idx ON analysis_jobs(state, created_at);
CREATE INDEX analysis_jobs_fingerprint_idx ON analysis_jobs(request_fingerprint_sha256, created_at DESC);

CREATE TABLE job_events (
    job_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    emitted_at TEXT NOT NULL,
    clock_time TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    PRIMARY KEY (job_id, sequence)
) STRICT, WITHOUT ROWID;

CREATE INDEX job_events_emitted_idx ON job_events(emitted_at);

CREATE TABLE live_events (
    sequence INTEGER PRIMARY KEY CHECK (sequence > 0),
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    emitted_at TEXT NOT NULL,
    clock_time TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    retain_until TEXT NOT NULL
) STRICT;

CREATE INDEX live_events_retention_idx ON live_events(retain_until);

CREATE TABLE cache_entries (
    derived_key_sha256 TEXT PRIMARY KEY CHECK (length(derived_key_sha256) = 64),
    artifact_type TEXT NOT NULL,
    provenance_node_id TEXT NOT NULL REFERENCES provenance_nodes(id),
    storage_blob_sha256 TEXT REFERENCES raw_blobs(sha256),
    row_table TEXT,
    row_id TEXT,
    byte_length INTEGER NOT NULL DEFAULT 0 CHECK (byte_length >= 0),
    pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
    created_at TEXT NOT NULL,
    last_accessed_at TEXT NOT NULL
) STRICT;

CREATE INDEX cache_entries_lru_idx ON cache_entries(pinned, last_accessed_at);

COMMIT;
