# Next Clear Look SSE contract

Version: `1.0`. This document is the readable guide for `/v1/analysis-jobs/{job_id}/events` and `/v1/events`. `contracts/openapi.yaml` defines how streams are opened. The machine-readable contract is `contracts/events/envelope.schema.json` plus one `<event-type>.schema.json` file for every event below.

## Wire format

Responses use `Content-Type: text/event-stream`, `Cache-Control: no-cache`, disabled proxy buffering and UTF-8. One event is:

```text
id: job_2f3c:7
event: job.progress
data: {"id":"job_2f3c:7","sequence":7,"type":"job.progress","stream":"job","job_id":"job_2f3c","emitted_at":"2026-10-02T17:44:01.742472Z","mode":"replay","clock_time":"2026-10-02T17:43:54Z","schema_version":"1.0","data":{"stage":"raster","stage_progress":0.3333,"overall_progress":0.72,"message":"Computed AOI statistics for 1 of 3 scenes.","completed_units":1,"total_units":3}}

```

The `event:` line equals the envelope `type`. The `data:` line is one compact JSON object with no literal newlines. Servers send `: heartbeat <UTC timestamp>\n\n` at least every 15 seconds while otherwise idle; heartbeat comments have no ID and are not persisted.

## Base envelope schema

Every event validates against `events/envelope.schema.json` and its event-specific schema. `emitted_at` is wall time for diagnostics in live mode. In replay it **equals `clock_time`**, comes from the frozen engine clock, and the event ID derives from the request fingerprint plus sequence, making a replay stream byte-stable. Consumers must always use `clock_time` for the product timeline.

## Job stream events

All job event `data` objects use `additionalProperties=false`. Nullable IDs below mean a JSON string or `null`.

| Event type | Required `data` fields | Meaning |
|---|---|---|
| `job.accepted` | `job_type` (JobType), `aoi_id` (string/null), `scene_id` (string/null), `queue_position` (integer ≥0) | Durable acknowledgement; always the first event. |
| `job.started` | `job_type`, `aoi_id`, `scene_id` | Worker acquired the job. |
| `job.cancellation_requested` | `requested_at` (date-time) | Cancellation flag is durable; work may still be leaving an atomic operation. |
| `job.stage.started` | `stage` (JobStage), `total_units` (integer/null), `message` (string) | Stage boundary. |
| `job.progress` | `stage`, `stage_progress` (0..1), `overall_progress` (0..1), `message`, `completed_units` (integer ≥0), `total_units` (integer/null) | Monotonic progress; may repeat a value but never decrease. |
| `job.result` | `result_type` (enum below), `resource_url` (URI-reference), `resource` (typed object/null), `provenance_id` (string) | One complete partial result is already queryable. |
| `job.warning` | `code` (upper snake case), `message`, `retryable` (boolean), `details` (object) | Degradation such as stale OMM or failed scene; job can continue. |
| `job.stage.completed` | `stage`, `duration_seconds` (number ≥0), `completed_units`, `total_units` | Stage transaction committed. |
| `job.completed` | `opportunity_count`, `scene_count`, `likelihood_url` (string/null), `partial_failure_count` (integer ≥0) | Successful terminal event. |
| `job.failed` | `error` (ErrorObject from OpenAPI), `partial_result_urls` (array of URI-references) | Failed terminal event. Completed partial evidence remains available. |
| `job.cancelled` | `reason` (string), `partial_result_urls` (array), `cancelled_at` (date-time) | Cancelled terminal event. |

`result_type` is one of `trajectory`, `opportunity`, `scene`, `scene_statistics`, `thumbnail_metadata`, `likelihood`, `provenance`. `resource` follows the corresponding OpenAPI schema. A server may omit a large inline resource by sending `null`; `resource_url` is always authoritative.

`JobStage` is the closed enum `catalogue | orbit | archive | raster | likelihood | finalise`. All payloads use `additionalProperties=false`; the per-event schema files are normative if this table and a schema ever diverge.

## Live/replay stream events

| Event type | Required `data` fields | Delivery |
|---|---|---|
| `live.clock` | `speed` (number ≥0), `paused` (boolean) | Coalescible; at least once per replay clock change and every 5 s while advancing. |
| `live.satellite_positions` | `positions` (array of Position) | Coalescible high-rate state; newest value wins under backpressure. |
| `live.opportunity.entered` | `aoi_id`, `opportunity_id`, `satellite_id`, `entry_time` | Durable for retention window. |
| `live.opportunity.closest` | `aoi_id`, `opportunity_id`, `satellite_id`, `closest_time`, `minimum_ground_track_distance_km` | Durable. |
| `live.opportunity.exited` | `aoi_id`, `opportunity_id`, `satellite_id`, `exit_time` | Durable. |
| `live.scene.available` | `aoi_id`, `scene_id`, `acquisition_time`, `scene_url` | Durable; means indexed evidence, not necessarily completed statistics. |
| `live.upstream.status` | `source`, `status`, `checked_at`, `age_seconds` (number/null), `error` (ErrorObject/null) | Durable only on change. |
| `live.mode.changed` | `previous_mode`, `current_mode`, `fixture_set` (string/null), `effective_clock` | Durable; server closes existing stream after sending it so clients reconnect to the new sequence. |
| `stream.reset_required` | `reason`, `oldest_available_id` (string/null) | Sent before close when recovery cannot continue in-band. |

A Position includes the satellite ID and the same WGS84 centre/swath-edge fields as an OpenAPI `TrajectorySample`:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["satellite_id", "time", "latitude", "longitude", "altitude_m", "swath_left", "swath_right"],
  "properties": {
    "satellite_id": {"type": "string"},
    "time": {"type": "string", "format": "date-time"},
    "latitude": {"type": "number", "minimum": -90, "maximum": 90},
    "longitude": {"type": "number", "minimum": -180, "maximum": 180},
    "altitude_m": {"type": "number", "minimum": 0},
    "swath_left": {"$ref": "../openapi.yaml#/components/schemas/Position"},
    "swath_right": {"$ref": "../openapi.yaml#/components/schemas/Position"}
  }
}
```

The three opportunity event schemas are references into the stored Opportunity: IDs plus their named phase timestamp. They deliberately do not duplicate the entire opportunity; clients resolve it by the ordinary resource API.

## Ordering, resume and retention

- Job sequence starts at 1, is gap-free per job and survives restart. In live mode the event ID is `<job_id>:<sequence>`; in replay the job ID itself derives from the canonical request fingerprint, so the complete event ID remains stable.
- Live sequence is global within a persisted engine database. Live event ID is `live:<sequence>`.
- State/result rows and the announcing event commit in the same SQLite transaction. Receiving `job.result` guarantees its URL is readable.
- Exactly one of `job.completed`, `job.failed`, `job.cancelled` is the final job event. No later job event is legal.
- `Last-Event-ID` header resumes strictly after the named event. Query `last_event_id` exists for browser clients that cannot set the header; the header wins if both exist.
- Unknown future event types must be ignored. A known type with a different `schema_version` must not be decoded as 1.0.
- Job events are retained at least seven days after terminal state. Durable live events are retained 24 hours in live mode and for the entire bundled replay. A resume older than retention returns HTTP `410`; if the gap is detected after connection, send `stream.reset_required` then close.
- A reconnect may receive an event it processed before if the client failed to persist its high-water mark. Consumers deduplicate by event ID.

## Backpressure and failures

Each connection has a 256-event outbound buffer. The server may replace queued `live.clock` or `live.satellite_positions` with their newest value. It may not drop job events, opportunity phase events, scene availability, upstream changes, mode changes or reset notices. A client that remains slow after coalescing is disconnected; durable events remain resumeable.

SSE transport failure does not cancel a job. Upstream failures appear as `job.warning`, `job.failed` or `live.upstream.status` and never as malformed SSE. A JSON serialisation failure fails the job before an event is committed.

## Examples

Run `python contracts/generate_examples.py` from the repository root to regenerate all API examples, `contracts/examples/sse-events.json`, the two wire-format `.sse` examples, and every schema under `contracts/events/`. The JSON event example contains one valid instance of every event type.
