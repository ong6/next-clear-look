import type { components } from "../api/generated/schema";

export type Schemas = components["schemas"];
export type DashboardAoi = Schemas["Aoi"];
export type DashboardTrajectory = Schemas["Trajectory"];

export type DashboardScene = Schemas["SceneSummary"] & {
  displayName: string;
  thumbnail: string | null;
};

export interface DashboardData {
  mode: Schemas["Mode"];
  health: Schemas["Health"];
  aois: DashboardAoi[];
  aoi: DashboardAoi;
  satellites: Schemas["Satellite"][];
  trajectories: DashboardTrajectory[];
  opportunities: Schemas["Opportunity"][];
  opportunityMeta: Schemas["OpportunityPageMeta"];
  scenes: DashboardScene[];
  sceneMeta: Schemas["ScenePageMeta"] | null;
  likelihood: Schemas["Likelihood"] | null;
  attributions: Schemas["Attribution"][];
  statistics: Record<string, Schemas["RasterStatistics"]>;
  provenance: Record<string, Schemas["ProvenanceGraph"]>;
  pendingJobs: Schemas["AnalysisJob"][];
}

export interface AoiView {
  id: string;
  slug: string;
  name: string;
  locality: string;
  tag: string;
  story: string;
  centroid: [number, number];
  bounds: [number, number, number, number];
  area: string;
  origin: "preset" | "user";
  coverage: Schemas["ReplayCoverage"];
  geometry: Schemas["GeoJsonGeometry"];
}

export function toAoiView(aoi: DashboardAoi): AoiView {
  const [longitude, latitude] = aoi.centroid.coordinates;
  return {
    id: aoi.id,
    slug: aoi.preset?.slug ?? "drawn-area",
    name: aoi.name,
    locality: aoi.preset?.locality ?? "Local geometry",
    tag: aoi.preset?.climate_tags[0]?.replaceAll("-", " ") ?? "User drawn",
    story: aoi.preset?.story ?? "User-drawn monitoring boundary",
    centroid: [longitude, latitude],
    bounds: aoi.bbox,
    area: `${aoi.area_km2.toLocaleString(undefined, { maximumFractionDigits: aoi.area_km2 < 100 ? 1 : 0 })} km²`,
    origin: aoi.origin,
    coverage: aoi.replay_coverage,
    geometry: aoi.geometry,
  };
}

export function toDashboardScene(scene: Schemas["SceneSummary"]): DashboardScene {
  return {
    ...scene,
    displayName: platformLabel(scene.platform),
    thumbnail: scene.thumbnail_status === "ready" ? scene.thumbnail_url : null,
  };
}

export function platformLabel(platform: string): string {
  return platform.replace("sentinel-", "Sentinel-").replace(/([abc])$/i, (letter) => letter.toUpperCase());
}

export function emptySceneMeta(
  clock: string,
  archiveState: Schemas["ArchiveState"],
): Schemas["ScenePageMeta"] {
  const end = new Date(clock);
  const start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1_000);
  return {
    count: 0,
    next_cursor: null,
    as_of: clock,
    archive_state: archiveState,
    window_start: start.toISOString(),
    window_end: end.toISOString(),
  };
}

export function emptyOpportunityMeta(clock: string): Schemas["OpportunityPageMeta"] {
  const start = new Date(clock);
  const end = new Date(start.getTime() + 14 * 24 * 60 * 60 * 1_000);
  return {
    count: 0,
    next_cursor: null,
    as_of: clock,
    window_start: start.toISOString(),
    window_end: end.toISOString(),
  };
}
