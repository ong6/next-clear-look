import createClient from "openapi-fetch";
import type { paths } from "./generated/schema";
import type { DashboardData, Schemas } from "../data/dashboard-data";
import { emptyOpportunityMeta, emptySceneMeta, toDashboardScene } from "../data/dashboard-data";
const apiBase =
  typeof window === "undefined" ? "/v1" : new URL("/v1", window.location.href).toString().replace(/\/$/, "");

export const apiClient = createClient<paths>({ baseUrl: apiBase });

interface ApiResult<T> {
  data?: T;
  error?: Schemas["ErrorResponse"];
  response: Response;
}

export class NclApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;

  constructor(status: number, code: string, message: string, retryable = false) {
    super(message);
    this.name = "NclApiError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

function asResult<T>(value: unknown): ApiResult<T> {
  return value as ApiResult<T>;
}

function unwrap<T>(value: unknown, label: string): T {
  const result = asResult<T>(value);
  if (result.data !== undefined) return result.data;
  const error = result.error?.error;
  throw new NclApiError(
    result.response?.status ?? 500,
    error?.code ?? "REQUEST_FAILED",
    error?.message ?? `Unable to load ${label}.`,
    error?.retryable ?? false,
  );
}

function isJob(value: unknown): value is Schemas["AnalysisJob"] {
  return typeof value === "object" && value !== null && "events_url" in value && "state" in value;
}

interface BootstrapData {
  mode: Schemas["Mode"];
  health: Schemas["Health"];
  aois: Schemas["Aoi"][];
  satellites: Schemas["Satellite"][];
  attributions: Schemas["Attribution"][];
}

async function loadBootstrap(): Promise<BootstrapData> {
  const [modeResult, healthResult, aoisResult, satellitesResult, attributionsResult] = await Promise.all([
    apiClient.GET("/mode"),
    apiClient.GET("/health"),
    apiClient.GET("/aois", { params: { query: { limit: 50 } } }),
    apiClient.GET("/satellites"),
    apiClient.GET("/attributions"),
  ]);
  return {
    mode: unwrap<Schemas["Mode"]>(modeResult, "mode"),
    health: unwrap<Schemas["Health"]>(healthResult, "health"),
    aois: unwrap<Schemas["AoiPage"]>(aoisResult, "areas of interest").data,
    satellites: unwrap<Schemas["SatellitePage"]>(satellitesResult, "satellites").data,
    attributions: unwrap<Schemas["AttributionList"]>(attributionsResult, "attributions").data,
  };
}

async function loadProvenance(ids: string[]): Promise<Record<string, Schemas["ProvenanceGraph"]>> {
  const unique = [...new Set(ids.filter(Boolean))];
  const entries = await Promise.all(
    unique.map(async (id) => {
      try {
        const result = await apiClient.GET("/provenance/{provenance_id}", {
          params: { path: { provenance_id: id } },
        });
        return [id, unwrap<Schemas["ProvenanceGraph"]>(result, "provenance")] as const;
      } catch {
        return null;
      }
    }),
  );
  return Object.fromEntries(entries.filter((entry): entry is NonNullable<typeof entry> => entry !== null));
}

export async function loadAoiDashboard(bootstrap: BootstrapData, aoiId: string): Promise<DashboardData> {
  const aoi =
    bootstrap.aois.find((item) => item.id === aoiId) ??
    unwrap<Schemas["Aoi"]>(
      await apiClient.GET("/aois/{aoi_id}", { params: { path: { aoi_id: aoiId } } }),
      "AOI",
    );
  const replayArchiveRecorded = bootstrap.mode.mode !== "replay" || aoi.replay_coverage.archive;
  const replayLikelihoodRecorded = bootstrap.mode.mode !== "replay" || aoi.replay_coverage.likelihood;
  const [opportunitiesResult, scenesResult, likelihoodResult] = await Promise.all([
    apiClient.GET("/aois/{aoi_id}/opportunities", {
      params: { path: { aoi_id: aoi.id }, query: { limit: 200 } },
    }),
    replayArchiveRecorded
      ? apiClient.GET("/aois/{aoi_id}/scenes", {
          params: { path: { aoi_id: aoi.id }, query: { limit: 200 } },
        })
      : Promise.resolve(null),
    replayLikelihoodRecorded
      ? apiClient.GET("/aois/{aoi_id}/likelihood", { params: { path: { aoi_id: aoi.id }, query: {} } })
      : Promise.resolve(null),
  ]);

  const pendingJobs: Schemas["AnalysisJob"][] = [];
  const opportunitiesPayload = unwrap<Schemas["OpportunityPage"] | Schemas["AnalysisJob"]>(
    opportunitiesResult,
    "opportunities",
  );
  const scenesPayload =
    scenesResult === null
      ? null
      : unwrap<Schemas["ScenePage"] | Schemas["AnalysisJob"]>(scenesResult, "archive scenes");
  const likelihoodPayload =
    likelihoodResult === null
      ? null
      : unwrap<Schemas["Likelihood"] | Schemas["AnalysisJob"]>(likelihoodResult, "likelihood");
  if (isJob(opportunitiesPayload)) pendingJobs.push(opportunitiesPayload);
  if (scenesPayload && isJob(scenesPayload)) pendingJobs.push(scenesPayload);
  if (likelihoodPayload && isJob(likelihoodPayload)) pendingJobs.push(likelihoodPayload);

  const opportunityPage = isJob(opportunitiesPayload) ? null : opportunitiesPayload;
  const opportunities = opportunityPage?.data ?? [];
  const scenePage = !scenesPayload || isJob(scenesPayload) ? null : scenesPayload;
  const scenes = scenePage?.data.map(toDashboardScene) ?? [];
  const likelihood = !likelihoodPayload || isJob(likelihoodPayload) ? null : likelihoodPayload;

  // Every spacecraft is requested over the same engine-time window. The globe may interpolate
  // these samples, but it must never phase-shift one spacecraft from another in the browser.
  const selectedPass = opportunities[0];
  const visualCentre = Date.parse(selectedPass?.closest_time ?? bootstrap.mode.clock);
  const visualStart = new Date(visualCentre - 8 * 60_000).toISOString();
  const visualEnd = new Date(visualCentre + 8 * 60_000).toISOString();
  const trajectoryEntries = await Promise.all(
    bootstrap.satellites.map(async (satellite) => {
      try {
        const result = await apiClient.GET("/satellites/{satellite_id}/trajectory", {
          params: {
            path: { satellite_id: satellite.platform },
            query: {
              start: visualStart,
              end: visualEnd,
              step_seconds: 20,
            },
          },
        });
        return unwrap<Schemas["Trajectory"]>(result, `${satellite.name} trajectory`);
      } catch {
        return null;
      }
    }),
  );
  const trajectories = trajectoryEntries.filter((item): item is Schemas["Trajectory"] => item !== null);

  const statisticEntries = await Promise.all(
    scenes
      .filter((scene) => scene.analysis_state === "ready" && scene.statistics_url)
      .map(async (scene) => {
        try {
          const result = await apiClient.GET("/scenes/{scene_id}/statistics/{aoi_id}", {
            params: { path: { scene_id: scene.id, aoi_id: aoi.id } },
          });
          const payload = unwrap<Schemas["RasterStatistics"] | Schemas["AnalysisJob"]>(
            result,
            "scene statistics",
          );
          if (isJob(payload)) {
            pendingJobs.push(payload);
            return null;
          }
          return [scene.id, payload] as const;
        } catch {
          return null;
        }
      }),
  );
  const statistics = Object.fromEntries(
    statisticEntries.filter((entry): entry is NonNullable<typeof entry> => entry !== null),
  );

  const provenance = await loadProvenance([
    aoi.provenance_id,
    ...bootstrap.satellites.map((item) => item.provenance_id),
    ...trajectories.map((item) => item.provenance_id),
    ...opportunities.map((item) => item.provenance_id),
    ...scenes.map((item) => item.provenance_id),
    ...Object.values(statistics).map((item) => item.provenance_id),
    likelihood?.provenance_id ?? "",
  ]);

  return {
    ...bootstrap,
    aoi,
    trajectories,
    opportunities,
    opportunityMeta: opportunityPage?.meta ?? emptyOpportunityMeta(bootstrap.mode.clock),
    scenes,
    sceneMeta:
      scenePage?.meta ??
      emptySceneMeta(bootstrap.mode.clock, replayArchiveRecorded ? "searching" : "not_recorded"),
    likelihood,
    statistics,
    provenance,
    pendingJobs,
  };
}

async function loadTestDashboard(): Promise<DashboardData> {
  const [
    modeModule,
    healthModule,
    aoiModule,
    satellitesModule,
    trajectoryModule,
    opportunitiesModule,
    scenesModule,
    likelihoodModule,
    attributionsModule,
    statisticsModule,
    provenanceModule,
  ] = await Promise.all([
    import("../../../contracts/examples/mode.json"),
    import("../../../contracts/examples/health.json"),
    import("../../../contracts/examples/aoi.json"),
    import("../../../contracts/examples/satellites.json"),
    import("../../../contracts/examples/trajectory.json"),
    import("../../../contracts/examples/opportunities.json"),
    import("../../../contracts/examples/scenes.json"),
    import("../../../contracts/examples/likelihood.json"),
    import("../../../contracts/examples/attributions.json"),
    import("../../../contracts/examples/scene-statistics.json"),
    import("../../../contracts/examples/provenance.json"),
  ]);
  const baseAoi = aoiModule.default as Schemas["Aoi"];
  const presets = [
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
  const aois = presets.map(([id, name, slug, locality, centroid, bbox], index) => ({
    ...baseAoi,
    id,
    name,
    centroid: { type: "Point" as const, coordinates: [...centroid] as [number, number] },
    bbox: [...bbox] as [number, number, number, number],
    preset: {
      slug,
      locality,
      story: `${name} recorded fixture`,
      climate_tags: [index === 0 ? "equatorial" : "recorded"],
    },
    replay_coverage: { opportunities: true, archive: true, likelihood: true, thumbnails: true },
  }));
  const mode = modeModule.default as Schemas["Mode"];
  const satellites = (satellitesModule.default as Schemas["SatellitePage"]).data;
  const baseTrajectory = trajectoryModule.default as Schemas["Trajectory"];
  const scenes = (scenesModule.default as Schemas["ScenePage"]).data
    .map(toDashboardScene)
    .map((scene) => ({ ...scene, thumbnail: "/scenes/sentinel-2-preview.jpg" }));
  const statistics = statisticsModule.default as Schemas["RasterStatistics"];
  const provenance = provenanceModule.default as Schemas["ProvenanceGraph"];
  const opportunityPage = opportunitiesModule.default as Schemas["OpportunityPage"];
  const opportunityData = opportunityPage.data;
  const likelihoodData = likelihoodModule.default as Schemas["Likelihood"];
  return {
    mode,
    health: healthModule.default as Schemas["Health"],
    aois,
    aoi: aois[0],
    satellites,
    trajectories: satellites.map((satellite) => ({ ...baseTrajectory, satellite_id: satellite.id })),
    opportunities: opportunityData,
    opportunityMeta: opportunityPage.meta,
    scenes,
    sceneMeta: (scenesModule.default as Schemas["ScenePage"]).meta,
    likelihood: likelihoodData,
    attributions: attributionsModule.default.data,
    statistics: { [statistics.scene_id]: statistics },
    provenance: {
      [provenance.id]: provenance,
      [statistics.provenance_id]: provenance,
      [opportunityData[0].provenance_id]: provenance,
      [scenes[0].provenance_id]: provenance,
      [likelihoodData.provenance_id]: provenance,
    },
    pendingJobs: [],
  };
}

export async function loadDashboardData(preferredAoiId?: string): Promise<DashboardData> {
  if (import.meta.env.MODE === "test") return loadTestDashboard();
  const bootstrap = await loadBootstrap();
  const aoiId =
    preferredAoiId && bootstrap.aois.some((item) => item.id === preferredAoiId)
      ? preferredAoiId
      : (bootstrap.aois.find((item) => item.preset?.slug === "singapore-coast")?.id ?? bootstrap.aois[0]?.id);
  if (!aoiId) throw new NclApiError(404, "NO_AOIS", "The engine did not return an area of interest.");
  return loadAoiDashboard(bootstrap, aoiId);
}

export async function loadDashboardShell(preferredAoiId?: string): Promise<DashboardData> {
  const bootstrap = await loadBootstrap();
  const aoi = preferredAoiId
    ? bootstrap.aois.find((item) => item.id === preferredAoiId)
    : (bootstrap.aois.find((item) => item.preset?.slug === "singapore-coast") ?? bootstrap.aois[0]);
  if (!aoi) throw new NclApiError(404, "NO_AOIS", "The engine did not return an area of interest.");
  return {
    ...bootstrap,
    aoi,
    trajectories: [],
    opportunities: [],
    opportunityMeta: emptyOpportunityMeta(bootstrap.mode.clock),
    scenes: [],
    sceneMeta: emptySceneMeta(bootstrap.mode.clock, "searching"),
    likelihood: null,
    statistics: {},
    provenance: {},
    pendingJobs: [],
  };
}

export async function reloadAoiDashboard(current: DashboardData, aoiId: string): Promise<DashboardData> {
  const bootstrap: BootstrapData = {
    mode: current.mode,
    health: current.health,
    aois: current.aois,
    satellites: current.satellites,
    attributions: current.attributions,
  };
  return loadAoiDashboard(bootstrap, aoiId);
}

export async function switchEngineMode(mode: "live" | "replay"): Promise<Schemas["Mode"]> {
  const result = await apiClient.PUT("/mode", {
    body: { mode, ...(mode === "replay" ? { fixture_set: "ncl-showcase" } : {}) },
  });
  return unwrap<Schemas["Mode"]>(result, `${mode} mode`);
}

export async function createAoiRecord(
  name: string,
  geometry: Schemas["GeoJsonGeometry"],
  timezone = "UTC",
): Promise<Schemas["Aoi"]> {
  const result = await apiClient.POST("/aois", {
    params: { header: { "Idempotency-Key": crypto.randomUUID() } },
    body: { name, timezone, geometry },
  });
  return unwrap<Schemas["Aoi"]>(result, "drawn AOI");
}

export async function createAoi(name: string, coordinates: [number, number][]): Promise<Schemas["Aoi"]> {
  const closed =
    coordinates[0]?.[0] === coordinates.at(-1)?.[0] && coordinates[0]?.[1] === coordinates.at(-1)?.[1]
      ? coordinates
      : [...coordinates, coordinates[0]];
  return createAoiRecord(name, { type: "Polygon", coordinates: [closed] });
}

export async function createAnalysisJob(
  aoiId: string,
  mode: "live" | "replay",
): Promise<Schemas["AnalysisJob"]> {
  const result = await apiClient.POST("/analysis-jobs", {
    params: { header: { "Idempotency-Key": crypto.randomUUID() } },
    body: { type: mode === "live" ? "full_analysis" : "orbit_only", aoi_id: aoiId, force_refresh: false },
  });
  return unwrap<Schemas["AnalysisJob"]>(result, "analysis job");
}
