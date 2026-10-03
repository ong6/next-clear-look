#!/usr/bin/env python3
"""Generate deterministic API examples and SSE schemas for the NCL contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "examples"
EVENTS = ROOT / "events"
NOW = "2026-10-03T00:00:00Z"
WINDOW_END = "2026-10-17T00:00:00Z"
CREATED = "2026-10-02T23:59:00Z"
AOI_ID = "aoi_sg_tuas_coast"
JOB_ID = "job_f5f0c6d7b318"
PROVENANCE_ID = "prv_9dfd692c81d0"
GEOMETRY_SHA = "6f6ee87d1aa324b073cc9513199a523d35a6a2f5a3252b00bf04a4fd1665126d"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def polygon(west: float, south: float, east: float, north: float) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }


AOI_GEOMETRY = polygon(103.62, 1.24, 103.77, 1.36)
AOI = {
    "id": AOI_ID,
    "name": "Tuas reclamation edge",
    "origin": "preset",
    "preset": {
        "slug": "singapore-coast",
        "locality": "Tuas, Singapore",
        "story": "Monitor the changing reclamation edge and near-shore water.",
        "climate_tags": ["equatorial", "coastal", "convective-cloud"],
    },
    "geometry": AOI_GEOMETRY,
    "centroid": {"type": "Point", "coordinates": [103.695, 1.3]},
    "bbox": [103.62, 1.24, 103.77, 1.36],
    "timezone": "Asia/Singapore",
    "area_km2": 222.7108,
    "geometry_sha256": GEOMETRY_SHA,
    "replay_coverage": {
        "opportunities": True,
        "archive": True,
        "likelihood": True,
        "thumbnails": True,
    },
    "created_at": CREATED,
    "updated_at": CREATED,
    "provenance_id": "prv_aoi_sg_tuas_coast",
}

SATELLITE = {
    "id": "sentinel-2c",
    "name": "Sentinel-2C",
    "norad_catalog_id": 60989,
    "platform": "sentinel-2c",
    "status": "operational-observed",
    "omm_epoch": "2026-10-02T16:31:57.583104Z",
    "omm_age_seconds": 26882.416896,
    "provenance_id": "prv_satellite_s2c",
}

SWATH = polygon(102.35, -0.25, 105.03, 2.85)
OPPORTUNITY = {
    "id": "opp_ef8b898f1dfb",
    "kind": "geometric_opportunity",
    "aoi_id": AOI_ID,
    "satellite_id": "sentinel-2c",
    "platform": "sentinel-2c",
    "entry_time": "2026-10-03T02:31:20.100000Z",
    "closest_time": "2026-10-03T02:32:07.250000Z",
    "exit_time": "2026-10-03T02:32:54.450000Z",
    "duration_seconds": 94.35,
    "direction": "descending",
    "satellite_sunlit": True,
    "aoi_sun_elevation_deg": 53.82,
    "illumination": "daylight",
    "element_age_seconds": 36009.666896,
    "swath_width_km": 290.0,
    "swath_footprint": SWATH,
    "minimum_ground_track_distance_km": 37.41,
    "closest_subpoint": {"latitude": 1.01, "longitude": 103.78, "altitude_m": 786122.4},
    "acquisition_status": "unknown",
    "matched_scene_id": None,
    "truncated": False,
    "caveat": "Geometric opportunity only; acquisition is not guaranteed.",
    "source": {
        "omm_epoch": "2026-10-02T16:31:57.583104Z",
        "omm_sha256": "7368f1805ce51fdd4acb5a1226ce40465d22a2589967c4e555ac243492abf844",
        "propagation_model": "SGP4",
        "coarse_step_seconds": 20,
        "crossing_tolerance_seconds": 0.05,
    },
    "provenance_id": "prv_opp_ef8b898f1dfb",
}

SCENE_ID = "S2C_48NUG_20261001_0_L2A"
SCENE = {
    "id": SCENE_ID,
    "collection": "sentinel-2-l2a",
    "platform": "sentinel-2c",
    "acquisition_time": "2026-10-01T03:19:11.406000Z",
    "tile": "48NUG",
    "footprint": polygon(103.078, 0.813, 104.066, 1.808),
    "stac_self_url": f"https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/{SCENE_ID}",
    "analysis_state": "ready",
    "analysis_error": None,
    "aoi_coverage_percent": 100.0,
    "tile_cloud_cover_percent": 37.938815,
    "aoi_clear_percent": 69.9007,
    "valid_pixels": 548603,
    "thumbnail_status": "ready",
    "thumbnail_url": f"/v1/scenes/{SCENE_ID}/thumbnails/{AOI_ID}",
    "statistics_url": f"/v1/scenes/{SCENE_ID}/statistics/{AOI_ID}",
    "provenance_id": "prv_scene_s2c_20261001",
}

SCL_LABELS = {
    0: "No data",
    1: "Saturated or defective",
    2: "Dark area",
    3: "Cloud shadow",
    4: "Vegetation",
    5: "Not vegetated",
    6: "Water",
    7: "Unclassified",
    8: "Cloud medium probability",
    9: "Cloud high probability",
    10: "Thin cirrus",
    11: "Snow or ice",
}
SCL_PIXELS = [3680, 0, 7402, 12788, 65438, 55304, 255894, 6912, 61245, 72423, 11197, 0]
SURFACE_CLASS_POLICY = {
    "surface_scl_classes": [4, 5, 6, 7],
    "snow_ice_counted_as_surface": False,
}

STATS = {
    "scene_id": SCENE_ID,
    "aoi_id": AOI_ID,
    "algorithm_version": "scl-aoi-v1",
    "clear_percent": 69.9007,
    "valid_coverage_percent": 99.3337,
    "clear_pixels": 383548,
    "valid_pixels": 548603,
    "inside_aoi_pixels": 552283,
    "invalid_pixels": 3680,
    "clear_scl_classes": [4, 5, 6, 7],
    "valid_scl_classes": list(range(2, 12)),
    "surface_class_policy": SURFACE_CLASS_POLICY,
    "class_counts": {
        str(index): {"label": SCL_LABELS[index], "pixels": pixels}
        for index, pixels in enumerate(SCL_PIXELS)
    },
    "source_resolution_m": 20.0,
    "overview_factor": 1,
    "computed_at": "2026-10-02T17:44:08Z",
    "provenance_id": "prv_stats_s2c_20261001_tuas",
}

THUMBNAIL = {
    "scene_id": SCENE_ID,
    "aoi_id": AOI_ID,
    "url": f"/v1/scenes/{SCENE_ID}/thumbnails/{AOI_ID}",
    "media_type": "image/png",
    "width": 640,
    "height": 512,
    "byte_length": 384121,
    "sha256": "9584ad9f08ae7e4cb028979078659c0d03ef27aa33f0c86fcc8be57d641e57c3",
    "transparent_outside_aoi": True,
    "provenance_id": "prv_thumb_s2c_20261001_tuas",
}

QUEUED_JOB = {
    "id": JOB_ID,
    "type": "full_analysis",
    "aoi_id": AOI_ID,
    "scene_id": None,
    "state": "queued",
    "progress": 0.0,
    "stage": "catalogue",
    "created_at": NOW,
    "started_at": None,
    "finished_at": None,
    "cancel_requested_at": None,
    "result": None,
    "error": None,
    "events_url": f"/v1/analysis-jobs/{JOB_ID}/events",
}


def beta_posterior(success: int, failure: int, excluded: int = 0) -> dict[str, Any]:
    return {
        "distribution": "Beta",
        "prior_alpha": 1.0,
        "prior_beta": 1.0,
        "alpha": float(1 + success),
        "beta": float(1 + failure),
        "sample_size": success + failure,
        "success_count": success,
        "failure_count": failure,
        "excluded_count": excluded,
    }


LIKELIHOOD = {
    "aoi_id": AOI_ID,
    "as_of": NOW,
    "computed_at": NOW,
    "window_start": NOW,
    "window_end": WINDOW_END,
    "history_start": "2023-10-03T00:00:00Z",
    "history_end": NOW,
    "interpretation": "Historical likelihood of at least one acquired, AOI-clear look; not a weather forecast or acquisition promise.",
    "usable_definition": {
        "minimum_aoi_clear_percent": 70.0,
        "minimum_valid_coverage_percent": 95.0,
        "unit": "past looks",
    },
    "surface_class_policy": SURFACE_CLASS_POLICY,
    "season": {"window_days": 45, "tier": "seasonal", "timezone": "Asia/Singapore"},
    "acquisition_posterior": beta_posterior(19, 7),
    "clear_posterior": beta_posterior(12, 7, 1),
    "horizons": [
        {
            "days": 7,
            "opportunity_days": 2,
            "opportunity_count": 3,
            "probability": 0.6852,
            "credible_interval": {"level": 0.9, "lower": 0.4521, "upper": 0.8568},
        },
        {
            "days": 14,
            "opportunity_days": 5,
            "opportunity_count": 7,
            "probability": 0.9231,
            "credible_interval": {"level": 0.9, "lower": 0.7612, "upper": 0.9877},
        },
    ],
    "monte_carlo": {
        "draws": 100000,
        "rng": "numpy-pcg64",
        "seed": 18006016087674619204,
        "model_version": "seasonal-beta-acquisition-clear-v1",
    },
    "quality": "seasonal",
    "trial_evidence": [
        {
            "opportunity_id": "opp_hist_01",
            "date": "2026-10-01",
            "usable": False,
            "reason": "Acquired; AOI clear percentage below threshold.",
            "scene_id": SCENE_ID,
            "clear_percent": 69.9007,
        }
    ],
    "excluded_evidence": [
        {"opportunity_id": "opp_hist_missing_scl", "reason": "SCL asset unavailable."}
    ],
    "provenance_id": "prv_likelihood_tuas_20261003",
}


def error(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": {},
            "request_id": "req_01d2e7d96cf4",
        }
    }


ERROR_OBJECT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code", "message", "retryable", "details", "request_id"],
    "properties": {
        "code": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]+$"},
        "message": {"type": "string"},
        "retryable": {"type": "boolean"},
        "details": {"type": "object"},
        "request_id": {"type": "string"},
    },
}

STAGES = ["catalogue", "orbit", "archive", "raster", "likelihood", "finalise"]
JOB_TYPES = ["full_analysis", "orbit_only", "archive_refresh", "raster_scene", "likelihood_only"]


def object_schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


nullable_string = {"type": ["string", "null"]}
nullable_integer = {"type": ["integer", "null"], "minimum": 0}
stage = {"type": "string", "enum": STAGES}

EVENT_PAYLOAD_SCHEMAS: dict[str, dict[str, Any]] = {
    "job.accepted": object_schema(
        ["job_type", "aoi_id", "scene_id", "queue_position"],
        {
            "job_type": {"type": "string", "enum": JOB_TYPES},
            "aoi_id": nullable_string,
            "scene_id": nullable_string,
            "queue_position": {"type": "integer", "minimum": 0},
        },
    ),
    "job.started": object_schema(
        ["job_type", "aoi_id", "scene_id"],
        {
            "job_type": {"type": "string", "enum": JOB_TYPES},
            "aoi_id": nullable_string,
            "scene_id": nullable_string,
        },
    ),
    "job.cancellation_requested": object_schema(
        ["requested_at"], {"requested_at": {"type": "string", "format": "date-time"}}
    ),
    "job.stage.started": object_schema(
        ["stage", "total_units", "message"],
        {"stage": stage, "total_units": nullable_integer, "message": {"type": "string"}},
    ),
    "job.progress": object_schema(
        ["stage", "stage_progress", "overall_progress", "message", "completed_units", "total_units"],
        {
            "stage": stage,
            "stage_progress": {"type": "number", "minimum": 0, "maximum": 1},
            "overall_progress": {"type": "number", "minimum": 0, "maximum": 1},
            "message": {"type": "string"},
            "completed_units": {"type": "integer", "minimum": 0},
            "total_units": nullable_integer,
        },
    ),
    "job.result": object_schema(
        ["result_type", "resource_url", "resource", "provenance_id"],
        {
            "result_type": {
                "type": "string",
                "enum": ["trajectory", "opportunity", "scene", "scene_statistics", "thumbnail_metadata", "likelihood", "provenance"],
            },
            "resource_url": {"type": "string"},
            "resource": {"type": ["object", "null"]},
            "provenance_id": {"type": "string"},
        },
    ),
    "job.warning": object_schema(
        ["code", "message", "retryable", "details"],
        {
            "code": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]+$"},
            "message": {"type": "string"},
            "retryable": {"type": "boolean"},
            "details": {"type": "object"},
        },
    ),
    "job.stage.completed": object_schema(
        ["stage", "duration_seconds", "completed_units", "total_units"],
        {
            "stage": stage,
            "duration_seconds": {"type": "number", "minimum": 0},
            "completed_units": {"type": "integer", "minimum": 0},
            "total_units": nullable_integer,
        },
    ),
    "job.completed": object_schema(
        ["opportunity_count", "scene_count", "likelihood_url", "partial_failure_count"],
        {
            "opportunity_count": {"type": "integer", "minimum": 0},
            "scene_count": {"type": "integer", "minimum": 0},
            "likelihood_url": nullable_string,
            "partial_failure_count": {"type": "integer", "minimum": 0},
        },
    ),
    "job.failed": object_schema(
        ["error", "partial_result_urls"],
        {
            "error": ERROR_OBJECT_SCHEMA,
            "partial_result_urls": {"type": "array", "items": {"type": "string"}},
        },
    ),
    "job.cancelled": object_schema(
        ["reason", "partial_result_urls", "cancelled_at"],
        {
            "reason": {"type": "string"},
            "partial_result_urls": {"type": "array", "items": {"type": "string"}},
            "cancelled_at": {"type": "string", "format": "date-time"},
        },
    ),
    "live.clock": object_schema(
        ["speed", "paused"],
        {"speed": {"type": "number", "minimum": 0}, "paused": {"type": "boolean"}},
    ),
    "live.satellite_positions": object_schema(
        ["positions"],
        {
            "positions": {
                "type": "array",
                "items": object_schema(
                    ["satellite_id", "time", "latitude", "longitude", "altitude_m", "swath_left", "swath_right"],
                    {
                        "satellite_id": {"type": "string"},
                        "time": {"type": "string", "format": "date-time"},
                        "latitude": {"type": "number", "minimum": -90, "maximum": 90},
                        "longitude": {"type": "number", "minimum": -180, "maximum": 180},
                        "altitude_m": {"type": "number", "minimum": 0},
                        "swath_left": {"type": "array", "prefixItems": [{"type": "number"}, {"type": "number"}], "items": False},
                        "swath_right": {"type": "array", "prefixItems": [{"type": "number"}, {"type": "number"}], "items": False},
                    },
                ),
            }
        },
    ),
    "live.opportunity.entered": object_schema(
        ["aoi_id", "opportunity_id", "satellite_id", "entry_time"],
        {"aoi_id": {"type": "string"}, "opportunity_id": {"type": "string"}, "satellite_id": {"type": "string"}, "entry_time": {"type": "string", "format": "date-time"}},
    ),
    "live.opportunity.closest": object_schema(
        ["aoi_id", "opportunity_id", "satellite_id", "closest_time", "minimum_ground_track_distance_km"],
        {"aoi_id": {"type": "string"}, "opportunity_id": {"type": "string"}, "satellite_id": {"type": "string"}, "closest_time": {"type": "string", "format": "date-time"}, "minimum_ground_track_distance_km": {"type": "number", "minimum": 0}},
    ),
    "live.opportunity.exited": object_schema(
        ["aoi_id", "opportunity_id", "satellite_id", "exit_time"],
        {"aoi_id": {"type": "string"}, "opportunity_id": {"type": "string"}, "satellite_id": {"type": "string"}, "exit_time": {"type": "string", "format": "date-time"}},
    ),
    "live.scene.available": object_schema(
        ["aoi_id", "scene_id", "acquisition_time", "scene_url"],
        {"aoi_id": {"type": "string"}, "scene_id": {"type": "string"}, "acquisition_time": {"type": "string", "format": "date-time"}, "scene_url": {"type": "string"}},
    ),
    "live.upstream.status": object_schema(
        ["source", "status", "checked_at", "age_seconds", "error"],
        {
            "source": {"type": "string", "enum": ["celestrak", "earth-search", "sentinel-cogs", "jpl-de421"]},
            "status": {"type": "string", "enum": ["ok", "stale", "unavailable", "fixture", "disabled"]},
            "checked_at": {"type": "string", "format": "date-time"},
            "age_seconds": {"type": ["number", "null"], "minimum": 0},
            "error": {"oneOf": [ERROR_OBJECT_SCHEMA, {"type": "null"}]},
        },
    ),
    "live.mode.changed": object_schema(
        ["previous_mode", "current_mode", "fixture_set", "effective_clock"],
        {
            "previous_mode": {"type": "string", "enum": ["live", "replay"]},
            "current_mode": {"type": "string", "enum": ["live", "replay"]},
            "fixture_set": nullable_string,
            "effective_clock": {"type": "string", "format": "date-time"},
        },
    ),
    "stream.reset_required": object_schema(
        ["reason", "oldest_available_id"],
        {"reason": {"type": "string"}, "oldest_available_id": nullable_string},
    ),
}


EVENT_EXAMPLE_DATA: dict[str, dict[str, Any]] = {
    "job.accepted": {"job_type": "full_analysis", "aoi_id": AOI_ID, "scene_id": None, "queue_position": 0},
    "job.started": {"job_type": "full_analysis", "aoi_id": AOI_ID, "scene_id": None},
    "job.cancellation_requested": {"requested_at": NOW},
    "job.stage.started": {"stage": "orbit", "total_units": 3, "message": "Predicting Sentinel-2 geometric opportunities."},
    "job.progress": {"stage": "raster", "stage_progress": 0.3333, "overall_progress": 0.55, "message": "Computed AOI statistics for 1 of 3 scenes.", "completed_units": 1, "total_units": 3},
    "job.result": {"result_type": "opportunity", "resource_url": f"/v1/aois/{AOI_ID}/opportunities", "resource": OPPORTUNITY, "provenance_id": OPPORTUNITY["provenance_id"]},
    "job.warning": {"code": "STALE_OMM", "message": "Using cached orbital elements beyond the preferred age.", "retryable": False, "details": {"age_seconds": 90000}},
    "job.stage.completed": {"stage": "raster", "duration_seconds": 6.42, "completed_units": 3, "total_units": 3},
    "job.completed": {"opportunity_count": 5, "scene_count": 3, "likelihood_url": f"/v1/aois/{AOI_ID}/likelihood", "partial_failure_count": 0},
    "job.failed": {"error": error("UPSTREAM_UNAVAILABLE", "Earth Search is unavailable.", True)["error"], "partial_result_urls": [f"/v1/aois/{AOI_ID}/opportunities"]},
    "job.cancelled": {"reason": "Cancelled by client.", "partial_result_urls": [], "cancelled_at": NOW},
    "live.clock": {"speed": 1.0, "paused": False},
    "live.satellite_positions": {"positions": [{"satellite_id": "sentinel-2c", "time": NOW, "latitude": 1.01, "longitude": 103.78, "altitude_m": 786122.4, "swath_left": [102.48, 1.01], "swath_right": [105.08, 1.01]}]},
    "live.opportunity.entered": {"aoi_id": AOI_ID, "opportunity_id": OPPORTUNITY["id"], "satellite_id": "sentinel-2c", "entry_time": OPPORTUNITY["entry_time"]},
    "live.opportunity.closest": {"aoi_id": AOI_ID, "opportunity_id": OPPORTUNITY["id"], "satellite_id": "sentinel-2c", "closest_time": OPPORTUNITY["closest_time"], "minimum_ground_track_distance_km": 37.41},
    "live.opportunity.exited": {"aoi_id": AOI_ID, "opportunity_id": OPPORTUNITY["id"], "satellite_id": "sentinel-2c", "exit_time": OPPORTUNITY["exit_time"]},
    "live.scene.available": {"aoi_id": AOI_ID, "scene_id": SCENE_ID, "acquisition_time": SCENE["acquisition_time"], "scene_url": f"/v1/scenes/{SCENE_ID}"},
    "live.upstream.status": {"source": "earth-search", "status": "fixture", "checked_at": NOW, "age_seconds": None, "error": None},
    "live.mode.changed": {"previous_mode": "replay", "current_mode": "live", "fixture_set": None, "effective_clock": NOW},
    "stream.reset_required": {"reason": "Requested event predates retained history.", "oldest_available_id": "live:42"},
}


def event_stream(event_type: str) -> str:
    return "job" if event_type.startswith("job.") else "live"


def event_example(event_type: str, sequence: int) -> dict[str, Any]:
    stream = event_stream(event_type)
    value: dict[str, Any] = {
        "id": f"{JOB_ID}:{sequence}" if stream == "job" else f"live:{sequence}",
        "sequence": sequence,
        "type": event_type,
        "stream": stream,
        "emitted_at": NOW,
        "mode": "replay",
        "clock_time": NOW,
        "schema_version": "1.0",
        "data": EVENT_EXAMPLE_DATA[event_type],
    }
    if stream == "job":
        value["job_id"] = JOB_ID
    return value


def write_event_schemas() -> list[dict[str, Any]]:
    event_types = list(EVENT_PAYLOAD_SCHEMAS)
    envelope = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://next-clear-look.local/schemas/events/envelope.schema.json",
        "title": "Next Clear Look SSE envelope",
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "sequence", "type", "stream", "emitted_at", "mode", "clock_time", "schema_version", "data"],
        "properties": {
            "id": {"type": "string", "minLength": 1, "maxLength": 200},
            "sequence": {"type": "integer", "minimum": 1},
            "type": {"type": "string", "enum": event_types},
            "stream": {"type": "string", "enum": ["job", "live"]},
            "job_id": {"type": "string", "pattern": "^job_[A-Za-z0-9_-]+$"},
            "emitted_at": {"type": "string", "format": "date-time"},
            "mode": {"type": "string", "enum": ["live", "replay"]},
            "clock_time": {"type": "string", "format": "date-time"},
            "schema_version": {"const": "1.0"},
            "data": {"type": "object"},
        },
        "allOf": [
            {"if": {"properties": {"stream": {"const": "job"}}, "required": ["stream"]}, "then": {"required": ["job_id"]}},
            {"if": {"properties": {"stream": {"const": "live"}}, "required": ["stream"]}, "then": {"not": {"required": ["job_id"]}}},
        ],
    }
    write_json(EVENTS / "envelope.schema.json", envelope)
    examples: list[dict[str, Any]] = []
    for sequence, (event_type, payload_schema) in enumerate(EVENT_PAYLOAD_SCHEMAS.items(), 1):
        stream = event_stream(event_type)
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://next-clear-look.local/schemas/events/{event_type}.schema.json",
            "title": f"Next Clear Look {event_type} event",
            "allOf": [
                {"$ref": "envelope.schema.json"},
                {
                    "type": "object",
                    "required": ["type", "stream", "data"],
                    "properties": {
                        "type": {"const": event_type},
                        "stream": {"const": stream},
                        "data": payload_schema,
                    },
                },
            ],
        }
        write_json(EVENTS / f"{event_type}.schema.json", schema)
        examples.append(event_example(event_type, sequence))
    return examples


def as_sse(events: list[dict[str, Any]]) -> str:
    blocks = []
    for event in events:
        data = json.dumps(event, sort_keys=True, separators=(",", ":"))
        blocks.append(f"id: {event['id']}\nevent: {event['type']}\ndata: {data}")
    return "\n\n".join(blocks) + "\n"


def main() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    EVENTS.mkdir(parents=True, exist_ok=True)

    mode_replay = {
        "mode": "replay",
        "clock": NOW,
        "network_enabled": False,
        "live_available": False,
        "fixture_set": "ncl-showcase",
        "fixture_recorded_at": "2026-10-03T00:06:32Z",
        "deterministic": True,
    }
    mode_live = {
        "mode": "live",
        "clock": "2026-10-03T08:00:00Z",
        "network_enabled": True,
        "live_available": True,
        "fixture_set": None,
        "fixture_recorded_at": None,
        "deterministic": False,
    }
    health = {
        "status": "ok",
        "version": "1.0.0",
        "mode": "replay",
        "clock": NOW,
        "database": "ok",
        "cache": "ok",
        "upstreams": {
            "celestrak": {"status": "fixture", "last_success_at": "2026-10-03T00:05:11Z", "reason": None},
            "earth-search": {"status": "fixture", "last_success_at": "2026-10-03T00:05:32Z", "reason": None},
            "sentinel-cogs": {"status": "fixture", "last_success_at": "2026-10-03T00:06:28Z", "reason": None},
            "jpl-de421": {"status": "fixture", "last_success_at": "2026-10-03T00:06:32Z", "reason": None},
        },
    }
    trajectory = {
        "satellite_id": "sentinel-2c",
        "frame": "ITRS/WGS84 geodetic",
        "sample_interval_seconds": 60,
        "start_time": "2026-10-03T02:31:00Z",
        "end_time": "2026-10-03T02:33:00Z",
        "samples": [
            {"time": "2026-10-03T02:31:00Z", "latitude": 5.13, "longitude": 102.98, "altitude_m": 786201.2, "swath_left": [101.67, 5.11], "swath_right": [104.29, 5.14]},
            {"time": "2026-10-03T02:32:00Z", "latitude": 1.55, "longitude": 103.69, "altitude_m": 786132.1, "swath_left": [102.39, 1.54], "swath_right": [104.99, 1.56]},
            {"time": "2026-10-03T02:33:00Z", "latitude": -2.04, "longitude": 104.39, "altitude_m": 786087.7, "swath_left": [103.09, -2.06], "swath_right": [105.69, -2.02]},
        ],
        "algorithm_version": "sgp4-swath-v1",
        "provenance_id": "prv_trajectory_s2c_20261003",
    }
    scene_detail = {
        **SCENE,
        "assets": {
            "scl": "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/48/N/UG/2026/10/S2C_48NUG_20261001_0_L2A/SCL.tif",
            "visual": "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/48/N/UG/2026/10/S2C_48NUG_20261001_0_L2A/TCI.tif",
        },
    }
    insufficient = {
        **LIKELIHOOD,
        "acquisition_posterior": beta_posterior(0, 0),
        "clear_posterior": beta_posterior(0, 0),
        "horizons": [
            {"days": 7, "opportunity_days": 2, "opportunity_count": 3, "probability": None, "credible_interval": None},
            {"days": 14, "opportunity_days": 5, "opportunity_count": 7, "probability": None, "credible_interval": None},
        ],
        "quality": "insufficient-data",
        "trial_evidence": [],
        "excluded_evidence": [],
        "provenance_id": "prv_likelihood_unrecorded_aoi",
    }
    provenance = {
        "id": PROVENANCE_ID,
        "root_artifact_id": OPPORTUNITY["id"],
        "created_at": NOW,
        "nodes": [
            {"id": "prv_node_omm", "kind": "raw_input", "label": "CelesTrak Sentinel OMM catalogue", "source_id": "celestrak", "request_key_sha256": "3b5be69e3eb0d97506c5a43bf14960d7656faf07defbd6b6e6e4cc11f1cf5b2b", "fixture_interaction_id": "int_celestrak_001", "available_offline": True, "origin": "fixture", "sha256": OPPORTUNITY["source"]["omm_sha256"], "source_url": "https://celestrak.org/NORAD/elements/gp.php?GROUP=sentinel&FORMAT=json", "fetched_at": "2026-10-03T00:05:11Z"},
            {"id": "prv_node_orbit", "kind": "algorithm", "label": "SGP4 nominal MSI swath", "source_id": None, "request_key_sha256": None, "fixture_interaction_id": None, "available_offline": True, "origin": None, "algorithm_version": "sgp4-swath-v1"},
            {"id": "prv_node_opp", "kind": "derived", "label": "Tuas geometric opportunity", "source_id": None, "request_key_sha256": None, "fixture_interaction_id": None, "available_offline": True, "origin": None, "sha256": "8f83a7f9c30b4428c877407262abc2b95d3a58d75177be74a722dbd8bc461a84"},
        ],
        "edges": [
            {"from": "prv_node_omm", "to": "prv_node_opp", "relation": "input_to"},
            {"from": "prv_node_opp", "to": "prv_node_orbit", "relation": "generated_by"},
        ],
    }
    completed_job = {
        **QUEUED_JOB,
        "state": "succeeded",
        "progress": 1.0,
        "stage": "finalise",
        "started_at": "2026-10-03T00:00:00.010000Z",
        "finished_at": "2026-10-03T00:00:01.210000Z",
        "result": {"opportunity_count": 5, "scene_count": 3, "likelihood_url": f"/v1/aois/{AOI_ID}/likelihood"},
    }
    cancelling_job = {**QUEUED_JOB, "state": "running", "progress": 0.55, "stage": "raster", "started_at": NOW, "cancel_requested_at": "2026-10-03T00:00:00.900000Z"}

    examples: dict[str, Any] = {
        "health.json": health,
        "mode.json": mode_replay,
        "mode-replay.json": mode_replay,
        "mode-live.json": mode_live,
        "mode-switch-live.json": {"mode": "live"},
        "attributions.json": {"data": [
            {"source": "celestrak", "display_text": "Orbital elements: CelesTrak (recorded 2026-10-03).", "source_url": "https://celestrak.org/", "terms_url": "https://celestrak.org/NORAD/documentation/gp-data-formats.php"},
            {"source": "earth-search", "display_text": "Catalogue: Earth Search by Element 84.", "source_url": "https://earth-search.aws.element84.com/v1", "terms_url": "https://github.com/Element84/earth-search"},
            {"source": "sentinel-cogs", "display_text": "Contains modified Copernicus Sentinel data 2026.", "source_url": "https://registry.opendata.aws/sentinel-2-l2a-cogs/", "terms_url": "https://dataspace.copernicus.eu/terms-and-conditions"},
            {"source": "jpl-de421", "display_text": "Solar geometry: JPL DE421 ephemeris excerpt.", "source_url": "https://ssd.jpl.nasa.gov/planets/eph_export.html", "terms_url": "https://www.jpl.nasa.gov/jpl-image-use-policy"},
        ]},
        "aoi-create.json": {"name": "Tuas reclamation edge", "geometry": AOI_GEOMETRY, "timezone": "Asia/Singapore"},
        "aoi-patch.json": {"name": "Tuas reclamation monitoring edge"},
        "aoi.json": AOI,
        "aoi-page.json": {"data": [AOI], "meta": {"count": 1, "next_cursor": None, "as_of": NOW}},
        "satellite.json": SATELLITE,
        "satellites.json": {"data": [SATELLITE], "meta": {"count": 1, "next_cursor": None, "as_of": NOW}},
        "trajectory.json": trajectory,
        "opportunities.json": {
            "data": [OPPORTUNITY],
            "meta": {
                "count": 1,
                "next_cursor": None,
                "as_of": NOW,
                "window_start": NOW,
                "window_end": WINDOW_END,
            },
        },
        "scene.json": scene_detail,
        "scenes.json": {"data": [SCENE], "meta": {"count": 1, "next_cursor": None, "as_of": NOW, "archive_state": "ready", "window_start": "2026-09-03T00:00:00Z", "window_end": NOW}},
        "scenes-empty.json": {"data": [], "meta": {"count": 0, "next_cursor": None, "as_of": NOW, "archive_state": "empty", "window_start": "2026-09-03T00:00:00Z", "window_end": NOW}},
        "scenes-not-recorded.json": {"data": [], "meta": {"count": 0, "next_cursor": None, "as_of": NOW, "archive_state": "not_recorded", "window_start": "2026-09-03T00:00:00Z", "window_end": NOW}},
        "scene-statistics.json": STATS,
        "thumbnail-metadata.json": THUMBNAIL,
        "likelihood.json": LIKELIHOOD,
        "likelihood-insufficient.json": insufficient,
        "provenance.json": provenance,
        "analysis-job-create.json": {"type": "full_analysis", "aoi_id": AOI_ID},
        "analysis-job.json": QUEUED_JOB,
        "analysis-job-cancelling.json": cancelling_job,
        "analysis-job-completed.json": completed_job,
        "analysis-jobs.json": {"data": [completed_job], "meta": {"count": 1, "next_cursor": None, "as_of": NOW}},
        "error.json": error("NOT_FOUND", "The requested resource does not exist."),
        "error-live-disabled.json": error("LIVE_DISABLED", "Set NCL_ALLOW_LIVE=1 before switching to live mode."),
    }

    event_examples = write_event_schemas()
    examples["sse-events.json"] = event_examples

    operation_examples = {
        "getHealth": {"responses": [{"status": 200, "file": "health.json"}, {"status": 503, "file": "error.json"}]},
        "getMode": {"responses": [{"status": 200, "file": "mode-replay.json"}, {"status": 200, "file": "mode-live.json"}]},
        "switchMode": {"request": "mode-switch-live.json", "responses": [{"status": 200, "file": "mode-live.json"}, {"status": 409, "file": "error-live-disabled.json"}]},
        "listAttributions": {"responses": [{"status": 200, "file": "attributions.json"}]},
        "listAois": {"responses": [{"status": 200, "file": "aoi-page.json"}]},
        "createAoi": {"request": "aoi-create.json", "responses": [{"status": 201, "file": "aoi.json"}]},
        "getAoi": {"responses": [{"status": 200, "file": "aoi.json"}]},
        "updateAoi": {"request": "aoi-patch.json", "responses": [{"status": 200, "file": "aoi.json"}]},
        "deleteAoi": {"responses": [{"status": 204, "file": None}]},
        "listSatellites": {"responses": [{"status": 200, "file": "satellites.json"}]},
        "getSatellite": {"responses": [{"status": 200, "file": "satellite.json"}]},
        "getTrajectory": {"responses": [{"status": 200, "file": "trajectory.json"}]},
        "listOpportunities": {"responses": [{"status": 200, "file": "opportunities.json"}, {"status": 202, "file": "analysis-job.json"}]},
        "listScenes": {"responses": [{"status": 200, "file": "scenes.json"}, {"status": 200, "file": "scenes-empty.json"}, {"status": 202, "file": "analysis-job.json"}]},
        "getScene": {"responses": [{"status": 200, "file": "scene.json"}]},
        "getSceneStatistics": {"responses": [{"status": 200, "file": "scene-statistics.json"}, {"status": 202, "file": "analysis-job.json"}]},
        "getSceneThumbnail": {"responses": [{"status": 200, "file": "thumbnail.png"}, {"status": 202, "file": "analysis-job.json"}]},
        "getSceneThumbnailMetadata": {"responses": [{"status": 200, "file": "thumbnail-metadata.json"}]},
        "getLikelihood": {"responses": [{"status": 200, "file": "likelihood.json"}, {"status": 200, "file": "likelihood-insufficient.json"}, {"status": 202, "file": "analysis-job.json"}]},
        "getProvenance": {"responses": [{"status": 200, "file": "provenance.json"}]},
        "listAnalysisJobs": {"responses": [{"status": 200, "file": "analysis-jobs.json"}]},
        "createAnalysisJob": {"request": "analysis-job-create.json", "responses": [{"status": 202, "file": "analysis-job.json"}]},
        "getAnalysisJob": {"responses": [{"status": 200, "file": "analysis-job-completed.json"}]},
        "cancelAnalysisJob": {"responses": [{"status": 202, "file": "analysis-job-cancelling.json"}]},
        "streamAnalysisJobEvents": {"responses": [{"status": 200, "file": "job-events.sse"}]},
        "streamLiveEvents": {"responses": [{"status": 200, "file": "live-events.sse"}]},
    }
    examples["operation-examples.json"] = operation_examples

    for filename, value in examples.items():
        write_json(EXAMPLES / filename, value)

    job_events = [event for event in event_examples if event["stream"] == "job"]
    live_events = [event for event in event_examples if event["stream"] == "live"]
    (EXAMPLES / "job-events.sse").write_text(as_sse(job_events), encoding="utf-8")
    (EXAMPLES / "live-events.sse").write_text(as_sse(live_events), encoding="utf-8")


if __name__ == "__main__":
    main()
