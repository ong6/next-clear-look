import type { SseEnvelope } from "../api/sse-client";
import { toDashboardScene } from "../data/dashboard-data";
import type { DashboardData, Schemas } from "../data/dashboard-data";

export interface ProgressRowState {
  progress: number;
  label: string;
}

export interface AnalysisProgress {
  jobId: string;
  state: "connecting" | "running" | "succeeded" | "failed";
  message: string;
  rows: Record<"orbit" | "archive" | "raster" | "likelihood", ProgressRowState>;
}

export const INITIAL_PROGRESS_ROWS: AnalysisProgress["rows"] = {
  orbit: { progress: 0, label: "Queued" },
  archive: { progress: 0, label: "Queued" },
  raster: { progress: 0, label: "Queued" },
  likelihood: { progress: 0, label: "Queued" },
};

function progressRowForStage(stage: string): keyof AnalysisProgress["rows"] {
  if (stage === "orbit") return "orbit";
  if (stage === "catalogue" || stage === "archive") return "archive";
  if (stage === "raster") return "raster";
  return "likelihood";
}

export function mergeJobEvent(current: DashboardData, event: SseEnvelope): DashboardData {
  if (event.type !== "job.result") return current;
  const payload = event.data as { result_type?: string; resource?: Record<string, unknown> | null };
  if (!payload.resource || !payload.result_type) return current;
  if (payload.result_type === "opportunity") {
    const opportunity = payload.resource as Schemas["Opportunity"];
    const existed = current.opportunities.some((item) => item.id === opportunity.id);
    return {
      ...current,
      opportunities: [
        ...current.opportunities.filter((item) => item.id !== opportunity.id),
        opportunity,
      ].sort((a, b) => Date.parse(a.closest_time) - Date.parse(b.closest_time)),
      opportunityMeta: {
        ...current.opportunityMeta,
        count: existed ? current.opportunityMeta.count : current.opportunityMeta.count + 1,
      },
    };
  }
  if (payload.result_type === "trajectory") {
    const trajectory = payload.resource as Schemas["Trajectory"];
    return {
      ...current,
      trajectories: [
        ...current.trajectories.filter((item) => item.satellite_id !== trajectory.satellite_id),
        trajectory,
      ],
    };
  }
  if (payload.result_type === "scene") {
    const scene = toDashboardScene(payload.resource as Schemas["SceneSummary"]);
    return {
      ...current,
      scenes: [...current.scenes.filter((item) => item.id !== scene.id), scene].sort(
        (a, b) => Date.parse(b.acquisition_time) - Date.parse(a.acquisition_time),
      ),
      sceneMeta: current.sceneMeta
        ? {
            ...current.sceneMeta,
            archive_state: "searching",
            count: current.scenes.some((item) => item.id === scene.id)
              ? current.sceneMeta.count
              : current.sceneMeta.count + 1,
          }
        : current.sceneMeta,
    };
  }
  if (payload.result_type === "scene_statistics") {
    const statistics = payload.resource as Schemas["RasterStatistics"];
    return {
      ...current,
      statistics: { ...current.statistics, [statistics.scene_id]: statistics },
      scenes: current.scenes.map((scene) =>
        scene.id === statistics.scene_id
          ? {
              ...scene,
              analysis_state: "ready",
              aoi_clear_percent: statistics.clear_percent,
              valid_pixels: statistics.valid_pixels,
            }
          : scene,
      ),
    };
  }
  if (payload.result_type === "thumbnail_metadata") {
    const thumbnail = payload.resource as Schemas["ThumbnailMetadata"];
    return {
      ...current,
      scenes: current.scenes.map((scene) =>
        scene.id === thumbnail.scene_id
          ? {
              ...scene,
              thumbnail: thumbnail.url,
              thumbnail_url: thumbnail.url,
              thumbnail_status: "ready",
            }
          : scene,
      ),
    };
  }
  if (payload.result_type === "likelihood") {
    return { ...current, likelihood: payload.resource as Schemas["Likelihood"] };
  }
  if (payload.result_type === "provenance") {
    const graph = payload.resource as Schemas["ProvenanceGraph"];
    return { ...current, provenance: { ...current.provenance, [graph.id]: graph } };
  }
  return current;
}

export function reduceAnalysisProgress(previous: AnalysisProgress, event: SseEnvelope): AnalysisProgress {
  if (event.type === "job.started") {
    return {
      ...previous,
      state: "running",
      message: "The engine accepted the AOI and started bounded analysis.",
    };
  }
  if (event.type === "job.stage.started") {
    const data = event.data as { stage: string; message: string };
    const row = progressRowForStage(data.stage);
    const progress = Math.max(0.03, previous.rows[row].progress);
    return {
      ...previous,
      state: "running",
      message: data.message,
      rows: {
        ...previous.rows,
        [row]: { progress, label: `Running · ${Math.round(progress * 100)}%` },
      },
    };
  }
  if (event.type === "job.progress") {
    const data = event.data as { stage: string; stage_progress: number; message: string };
    const row = progressRowForStage(data.stage);
    return {
      ...previous,
      state: "running",
      message: data.message,
      rows: {
        ...previous.rows,
        [row]: {
          progress: data.stage_progress,
          label: `Running · ${Math.round(data.stage_progress * 100)}%`,
        },
      },
    };
  }
  if (event.type === "job.stage.completed") {
    const data = event.data as { stage: string };
    const row = progressRowForStage(data.stage);
    return { ...previous, rows: { ...previous.rows, [row]: { progress: 1, label: "Ready" } } };
  }
  if (event.type === "job.result") {
    const data = event.data as { result_type?: string };
    return {
      ...previous,
      message:
        data.result_type === "scene_statistics"
          ? "A scene card just received measured AOI pixel statistics."
          : "A completed result is now visible in the workspace.",
    };
  }
  if (event.type === "job.completed") {
    return {
      ...previous,
      state: "succeeded",
      message: "All available results are committed and queryable.",
      rows: {
        orbit: { progress: 1, label: "Ready" },
        archive: { progress: 1, label: "Ready" },
        raster: { progress: 1, label: "Ready" },
        likelihood: { progress: 1, label: "Ready" },
      },
    };
  }
  if (event.type === "job.failed") {
    const data = event.data as { error?: { message?: string } };
    return {
      ...previous,
      state: "failed",
      message: data.error?.message ?? "The engine could not finish this analysis.",
    };
  }
  if (event.type === "job.cancelled") {
    return {
      ...previous,
      state: "failed",
      message: "Analysis was cancelled. Completed partial results remain visible.",
    };
  }
  return previous;
}
