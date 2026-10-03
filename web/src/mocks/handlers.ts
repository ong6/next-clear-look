import { delay, http, HttpResponse } from "msw";
import analysisJob from "../../../contracts/examples/analysis-job.json";
import aoi from "../../../contracts/examples/aoi.json";
import attributions from "../../../contracts/examples/attributions.json";
import health from "../../../contracts/examples/health.json";
import likelihood from "../../../contracts/examples/likelihood.json";
import mode from "../../../contracts/examples/mode.json";
import opportunities from "../../../contracts/examples/opportunities.json";
import provenance from "../../../contracts/examples/provenance.json";
import satellites from "../../../contracts/examples/satellites.json";
import scene from "../../../contracts/examples/scene.json";
import scenes from "../../../contracts/examples/scenes.json";
import statistics from "../../../contracts/examples/scene-statistics.json";
import thumbnailMetadata from "../../../contracts/examples/thumbnail-metadata.json";
import trajectory from "../../../contracts/examples/trajectory.json";

const json = (value: unknown, status = 200) => HttpResponse.json(value as never, { status });

const presetDefinitions = [
  [
    "aoi_sg_tuas_coast",
    "Tuas reclamation edge",
    "singapore-coast",
    "Tuas, Singapore",
    [103.695, 1.3],
    [103.62, 1.24, 103.77, 1.36],
  ],
  [
    "aoi_nl_maasvlakte",
    "Maasvlakte port",
    "rotterdam-port",
    "Rotterdam, Netherlands",
    [4.04, 51.935],
    [3.88, 51.84, 4.2, 52.03],
  ],
  [
    "aoi_cl_atacama",
    "Salar de Atacama works",
    "atacama-works",
    "Antofagasta, Chile",
    [-68.235, -23.52],
    [-68.42, -23.72, -68.05, -23.32],
  ],
  [
    "aoi_bd_sundarbans",
    "Sundarbans western delta",
    "sundarbans-delta",
    "India / Bangladesh",
    [89.425, 21.85],
    [89.1, 21.6, 89.75, 22.1],
  ],
  [
    "aoi_gl_jakobshavn",
    "Jakobshavn ice front",
    "jakobshavn-front",
    "Greenland",
    [-50.675, 69.2],
    [-51.55, 68.95, -49.8, 69.45],
  ],
] as const;

const mockAois = presetDefinitions.map(([id, name, slug, locality, centroid, bbox], index) => ({
  ...aoi,
  id,
  name,
  centroid: { type: "Point", coordinates: centroid },
  bbox,
  preset: {
    slug,
    locality,
    story: `${name} recorded fixture`,
    climate_tags: [index === 0 ? "equatorial" : "recorded"],
  },
  provenance_id: `prv_${id}`,
}));

const mockScenes = [0, 1, 2].map((index) => ({
  ...scenes.data[0],
  id: `${scenes.data[0].id}_R${index + 1}`,
  acquisition_time: new Date(
    Date.parse(scenes.data[0].acquisition_time) - index * 5 * 24 * 60 * 60 * 1_000,
  ).toISOString(),
  aoi_clear_percent: [69.9007, 84.2, 31.6][index],
  tile_cloud_cover_percent: [37.938815, 11.4, 68.7][index],
  thumbnail_url: "/scenes/sentinel-2-preview.jpg",
  statistics_url: `/v1/scenes/${scenes.data[0].id}_R${index + 1}/statistics/aoi_sg_tuas_coast`,
  provenance_id: `prv_scene_mock_${index + 1}`,
}));

function jobStream() {
  const jobId = analysisJob.id;
  const envelope = (sequence: number, type: string, data: Record<string, unknown>) => ({
    id: `${jobId}:${sequence}`,
    sequence,
    type,
    stream: "job",
    job_id: jobId,
    emitted_at: mode.clock,
    mode: "replay",
    clock_time: mode.clock,
    schema_version: "1.0",
    data,
  });
  const events = [
    envelope(1, "job.started", { job_type: "orbit_only", aoi_id: "aoi_drawn_mock", scene_id: null }),
    envelope(2, "job.stage.started", {
      stage: "orbit",
      total_units: 3,
      message: "Predicting geometric opportunities and swaths.",
    }),
    envelope(3, "job.progress", {
      stage: "orbit",
      stage_progress: 0.34,
      overall_progress: 0.2,
      message: "Predicted 1 of 3 satellite tracks.",
      completed_units: 1,
      total_units: 3,
    }),
    envelope(4, "job.result", {
      result_type: "opportunity",
      resource_url: "/v1/aois/aoi_drawn_mock/opportunities",
      resource: { ...opportunities.data[0], id: "opp_drawn_mock", aoi_id: "aoi_drawn_mock" },
      provenance_id: opportunities.data[0].provenance_id,
    }),
    envelope(5, "job.progress", {
      stage: "orbit",
      stage_progress: 1,
      overall_progress: 0.32,
      message: "Predicted 3 of 3 satellite tracks.",
      completed_units: 3,
      total_units: 3,
    }),
    envelope(6, "job.stage.completed", {
      stage: "orbit",
      duration_seconds: 0,
      completed_units: 3,
      total_units: 3,
    }),
    envelope(7, "job.completed", {
      opportunity_count: 1,
      scene_count: 0,
      likelihood_url: null,
      partial_failure_count: 0,
    }),
  ];
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      events.forEach((event, index) =>
        setTimeout(() => {
          controller.enqueue(
            encoder.encode(`id: ${event.id}\nevent: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`),
          );
          if (index === events.length - 1) controller.close();
        }, index * 160),
      );
    },
  });
}

export const handlers = [
  http.get("*/v1/health", () => json(health)),
  http.get("*/v1/mode", () => json(mode)),
  http.put("*/v1/mode", async ({ request }) => {
    const body = (await request.json()) as { mode?: string };
    if (body.mode === "live")
      return json(
        {
          error: {
            code: "LIVE_DISABLED",
            message: "Live mode is disabled for the recorded test server.",
            retryable: false,
            details: {},
            request_id: "req_mock_live_disabled",
          },
        },
        409,
      );
    return json(mode);
  }),
  http.get("*/v1/attributions", () => json(attributions)),
  http.get("*/v1/aois", () =>
    json({ data: mockAois, meta: { count: mockAois.length, next_cursor: null, as_of: mode.clock } }),
  ),
  http.get("*/v1/aois/:aoiId", ({ params }) =>
    json(mockAois.find((item) => item.id === params.aoiId) ?? aoi),
  ),
  http.post("*/v1/aois", async ({ request }) => {
    const body = (await request.json()) as { name: string; geometry: typeof aoi.geometry; timezone: string };
    return json(
      {
        ...aoi,
        id: "aoi_drawn_mock",
        name: body.name,
        origin: "user",
        preset: null,
        geometry: body.geometry,
        timezone: body.timezone,
        replay_coverage: { opportunities: true, archive: false, likelihood: false, thumbnails: false },
      },
      201,
    );
  }),
  http.get("*/v1/satellites", () => json(satellites)),
  http.get("*/v1/satellites/:satelliteId/trajectory", () => json(trajectory)),
  http.get("*/v1/aois/:aoiId/opportunities", () => json(opportunities)),
  http.get("*/v1/aois/:aoiId/scenes", async ({ params }) => {
    await delay(40);
    if (params.aoiId === "aoi_drawn_mock")
      return json({ data: [], meta: { ...scenes.meta, count: 0, archive_state: "not_recorded" } });
    return json({ data: mockScenes, meta: { ...scenes.meta, count: mockScenes.length } });
  }),
  http.get("*/v1/scenes/:sceneId", () => json(scene)),
  http.get("*/v1/scenes/:sceneId/statistics/:aoiId", ({ params }) =>
    json({ ...statistics, scene_id: params.sceneId, aoi_id: params.aoiId }),
  ),
  http.get("*/v1/scenes/:sceneId/thumbnails/:aoiId/metadata", () => json(thumbnailMetadata)),
  http.get("*/v1/aois/:aoiId/likelihood", () => json(likelihood)),
  http.get("*/v1/provenance/:provenanceId", () => json(provenance)),
  http.get("*/v1/analysis-jobs", () => json({ data: [analysisJob], meta: { count: 1, next_cursor: null } })),
  http.post("*/v1/analysis-jobs", () => json(analysisJob, 202)),
  http.get("*/v1/analysis-jobs/:jobId", () => json(analysisJob)),
  http.get(
    "*/v1/analysis-jobs/:jobId/events",
    () =>
      new HttpResponse(jobStream(), {
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
      }),
  ),
];
