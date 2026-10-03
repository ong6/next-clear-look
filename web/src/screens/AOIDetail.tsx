import { useState } from "react";
import { Icon } from "../components/Icon";
import { Badge, Eyebrow } from "../components/Primitives";
import { platformLabel, toAoiView } from "../data/dashboard-data";
import type { AoiView, DashboardData, DashboardScene, Schemas } from "../data/dashboard-data";
import { useAppStore } from "../state/app-store";
import { formatUtc } from "../utils/presentation";
import { LikelihoodPanel, NotRecordedArchive, ScenePreview } from "./MissionScreen";

const classGroups = [
  { label: "Clear surface", keys: ["4", "5", "6"], className: "clear" },
  { label: "Unclassified", keys: ["7"], className: "unclassified" },
  { label: "Dark area", keys: ["2"], className: "dark" },
  { label: "Cloud", keys: ["8", "9"], className: "cloud" },
  { label: "Thin cirrus", keys: ["10"], className: "cirrus" },
  { label: "Cloud shadow", keys: ["3"], className: "shadow" },
  { label: "Snow or ice", keys: ["11"], className: "snow" },
  { label: "No data", keys: ["0", "1"], className: "nodata" },
];

function AOIAccounting({
  scene,
  statistics,
}: {
  scene: DashboardScene;
  statistics: Schemas["RasterStatistics"] | undefined;
}) {
  const [definition, setDefinition] = useState(false);
  const openEvidence = useAppStore((state) => state.openEvidence);
  const surfaceClasses = new Set(statistics?.surface_class_policy.surface_scl_classes ?? []);
  const groups = classGroups.map((group) => ({
    ...group,
    pixels: group.keys.reduce((total, key) => total + (statistics?.class_counts[key]?.pixels ?? 0), 0),
    countedSurface: group.keys.some((key) => surfaceClasses.has(Number(key))),
  }));
  if (!statistics)
    return (
      <section className="detail-panel accounting-panel accounting-panel--pending">
        <div className="section-heading">
          <div>
            <Eyebrow>Pixel evidence</Eyebrow>
            <h2>AOI clear accounting</h2>
          </div>
          <Badge tone="replay">{scene.analysis_state.replace("_", " ")}</Badge>
        </div>
        <div className="likelihood-pending">
          <b>
            {scene.analysis_state === "not_recorded"
              ? "AOI pixels were not recorded"
              : "Analysing AOI pixels"}
          </b>
          <span>Tile catalogue context remains separate while the engine produces clipped SCL counts.</span>
        </div>
      </section>
    );
  return (
    <section className="detail-panel accounting-panel">
      <div className="section-heading">
        <div>
          <Eyebrow>Pixel evidence</Eyebrow>
          <h2>AOI clear accounting</h2>
        </div>
        <Badge tone="ready">Ready</Badge>
      </div>
      <button className="clear-score" type="button" onClick={() => openEvidence("accounting")}>
        <strong>
          {statistics.clear_percent === null ? (
            <span className="clear-score-unavailable">Not reported</span>
          ) : (
            <>
              {statistics.clear_percent.toFixed(1)}
              <i>%</i>
            </>
          )}
        </strong>
        <span>
          AOI clear
          <small>
            {statistics.valid_pixels.toLocaleString()} valid / {statistics.inside_aoi_pixels.toLocaleString()}{" "}
            inside AOI
          </small>
        </span>
      </button>
      <div
        className="class-distribution"
        data-testid="class-distribution"
        aria-label="Scene classification pixel distribution"
      >
        {groups.map((group) => (
          <i
            key={group.label}
            className={`class-${group.className}`}
            style={{ flexGrow: group.pixels }}
            title={`${group.label}: ${group.pixels.toLocaleString()} pixels`}
          />
        ))}
      </div>
      <div className="class-table">
        {groups.map((group) => (
          <div key={group.label} className={group.countedSurface ? "inside-clear-bracket" : ""}>
            <i className={`class-${group.className}`} />
            <span>
              {group.label}
              {group.countedSurface && group.className !== "clear" && <small>counted as surface</small>}
            </span>
            <b>{group.pixels.toLocaleString()}</b>
          </div>
        ))}
      </div>
      <button
        className="definition-toggle"
        type="button"
        onClick={() => setDefinition((open) => !open)}
        aria-expanded={definition}
      >
        {definition ? "Hide definition" : "Show definition"}
        <Icon name="chevron" width={14} />
      </button>
      {definition && (
        <p className="definition-copy">
          This area counts SCL {statistics.surface_class_policy.surface_scl_classes.join(", ")} as surface.{" "}
          {statistics.surface_class_policy.snow_ice_counted_as_surface
            ? "Snow/ice is counted because it is the subject of this area."
            : "Snow/ice is not counted as clear surface."}{" "}
          No data is excluded from the valid denominator.
        </p>
      )}
      <section className="catalogue-context">
        <h3>Catalogue context</h3>
        <h4>Tile cloud cover</h4>
        <strong>
          {scene.tile_cloud_cover_percent === null
            ? "Not reported"
            : `${scene.tile_cloud_cover_percent.toFixed(1)}%`}
        </strong>
        <p>Tile cloud cover describes the full Sentinel-2 tile, not this AOI.</p>
      </section>
    </section>
  );
}

function EvidenceStage({
  scene,
  aoi,
  statistics,
}: {
  scene: DashboardScene;
  aoi: AoiView;
  statistics: Schemas["RasterStatistics"] | undefined;
}) {
  const [view, setView] = useState<"true" | "scl" | "split">("true");
  const [split, setSplit] = useState(52);
  return (
    <section className="evidence-stage">
      <div className="detail-title">
        <div>
          <Eyebrow>
            {scene.analysis_state === "ready" ? "Recorded observation" : "Archive observation"}
          </Eyebrow>
          <h1>{aoi.name}</h1>
          <p>
            {formatUtc(scene.acquisition_time)} · {platformLabel(scene.platform)}
          </p>
        </div>
      </div>
      <div className="view-tabs" role="tablist" aria-label="Evidence view" data-testid="view-mode-tabs">
        {[
          ["true", "True colour"],
          ["scl", "SCL classes"],
          ["split", "Split compare"],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={view === key}
            onClick={() => setView(key as typeof view)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className={`evidence-image evidence-image--${view}`}>
        <ScenePreview scene={scene} aoiName={aoi.name} large />
        {view !== "true" && (
          <div
            className="scl-visual"
            style={view === "split" ? { clipPath: `inset(0 0 0 ${split}%)` } : undefined}
            aria-hidden="true"
          >
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
        )}
        {view === "split" && (
          <label className="split-control" style={{ left: `${split}%` }}>
            <span className="sr-only">Split position</span>
            <input
              type="range"
              min="10"
              max="90"
              step="5"
              value={split}
              onChange={(event) => setSplit(Number(event.currentTarget.value))}
            />
            <i />
          </label>
        )}
        {view !== "true" && (
          <div className="scl-legend">
            <span>
              <i className="class-clear" />
              Clear
            </span>
            <span>
              <i className="class-cloud" />
              Cloud
            </span>
            <span>
              <i className="class-cirrus" />
              Cirrus
            </span>
            <span>
              <i className="class-shadow" />
              Shadow
            </span>
            <span>
              <i className="class-nodata" />
              No data
            </span>
          </div>
        )}
      </div>
      <div className="image-toolbar">
        <Badge tone={scene.thumbnail ? "ready" : "replay"}>
          {scene.thumbnail ? "AOI crop ready" : scene.thumbnail_status.replace("_", " ")}
        </Badge>
        <button type="button">
          <Icon name="target" />
          Fit AOI
        </button>
        <button type="button">
          <Icon name="evidence" />
          View 1:1 pixels
        </button>
        <button type="button" onClick={() => void navigator.clipboard?.writeText(scene.id)}>
          <Icon name="copy" />
          Copy scene ID
        </button>
      </div>
      <p className="resolution-note">
        <Icon name="info" />
        AOI-clipped true colour is downsampled for display. Pixel accounting uses the{" "}
        {statistics?.source_resolution_m ?? 20} m SCL analysis source
        {statistics ? ` at overview factor ${statistics.overview_factor}` : ""}.
      </p>
    </section>
  );
}

function ObservationHistory({ data }: { data: DashboardData }) {
  const selectedSceneId = useAppStore((state) => state.selectedSceneId);
  const selectScene = useAppStore((state) => state.selectScene);
  const [filterOpen, setFilterOpen] = useState(false);
  return (
    <section className="history-panel">
      <div className="history-heading">
        <div>
          <Eyebrow>Observation history</Eyebrow>
          <h2>All returned scenes</h2>
        </div>
        <button type="button" onClick={() => setFilterOpen((open) => !open)}>
          Filter
        </button>
      </div>
      {filterOpen && (
        <div className="filter-row">
          <button type="button" className="is-selected">
            All
          </button>
          <button type="button">Clear enough</button>
          <button type="button">Obscured</button>
          <button type="button">Processing</button>
        </div>
      )}
      <div className="threshold">
        <label>
          Working threshold <input type="range" min="30" max="90" defaultValue="70" />
          <b>70%</b>
        </label>
        <p>Used only to group observations in this view. Recorded pixel statistics do not change.</p>
      </div>
      <div className="history-list" role="listbox" aria-label="Observation history">
        {data.scenes.map((scene) => (
          <button
            type="button"
            role="option"
            aria-selected={scene.id === selectedSceneId}
            key={scene.id}
            onClick={() => selectScene(scene.id)}
          >
            <time>{formatUtc(scene.acquisition_time)}</time>
            <span>
              {scene.id}
              <small>
                {platformLabel(scene.platform)} · {scene.analysis_state}
              </small>
            </span>
            <strong>
              {scene.aoi_clear_percent === null ? "Not reported" : `${scene.aoi_clear_percent.toFixed(1)}%`}
              <small>AOI clear</small>
            </strong>
            <em>→</em>
          </button>
        ))}
      </div>
    </section>
  );
}

export function AOIDetail({ data }: { data: DashboardData }) {
  const setRoute = useAppStore((state) => state.setRoute);
  const openEvidence = useAppStore((state) => state.openEvidence);
  const selectedSceneId = useAppStore((state) => state.selectedSceneId);
  const scene = data.scenes.find((item) => item.id === selectedSceneId) ?? data.scenes[0];
  const aoi = toAoiView(data.aoi);
  if (!scene)
    return (
      <main className="detail-main" data-testid="aoi-detail">
        <div className="mobile-detail-bar">
          <button type="button" onClick={() => setRoute("mission")}>
            <Icon name="arrow" />
            Back
          </button>
          <strong>{aoi.name}</strong>
        </div>
        <nav className="breadcrumb" aria-label="Breadcrumb">
          <button type="button" onClick={() => setRoute("mission")}>
            <Icon name="arrow" />
            Mission
          </button>
          <span>/</span>
          <span>{aoi.name}</span>
        </nav>
        <div className="detail-empty">
          <NotRecordedArchive />
          <button type="button" className="button button--secondary" onClick={() => setRoute("mission")}>
            Review opportunities
          </button>
        </div>
      </main>
    );
  const statistics = data.statistics[scene.id];
  return (
    <main className="detail-main" data-testid="aoi-detail">
      <div className="mobile-detail-bar">
        <button type="button" onClick={() => setRoute("mission")}>
          <Icon name="arrow" />
          Back
        </button>
        <strong>{aoi.name}</strong>
        <button type="button" aria-label="Open evidence" onClick={() => openEvidence("scene")}>
          Evidence
        </button>
      </div>
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <button type="button" onClick={() => setRoute("mission")}>
          <Icon name="arrow" />
          Mission
        </button>
        <span>/</span>
        <span>{aoi.name}</span>
      </nav>
      <div className="detail-grid">
        <div className="detail-primary">
          <EvidenceStage scene={scene} aoi={aoi} statistics={statistics} />
          <ObservationHistory data={data} />
        </div>
        <aside className="detail-sidebar">
          <AOIAccounting scene={scene} statistics={statistics} />
          <LikelihoodPanel data={data} />
          <section className="detail-panel provenance-summary">
            <div className="section-heading">
              <div>
                <Eyebrow>Evidence trail</Eyebrow>
                <h2>Provenance</h2>
              </div>
              <Badge tone="ready">{data.mode.mode}</Badge>
            </div>
            <dl>
              <div>
                <dt>Scene ID</dt>
                <dd>{scene.id}</dd>
              </div>
              <div>
                <dt>Collection</dt>
                <dd>{scene.collection}</dd>
              </div>
              <div>
                <dt>Grid tile</dt>
                <dd>{scene.tile}</dd>
              </div>
              <div>
                <dt>Analysis</dt>
                <dd>{statistics ? formatUtc(statistics.computed_at) : "Pending"}</dd>
              </div>
            </dl>
            <button
              className="button button--evidence button--wide"
              type="button"
              onClick={() => openEvidence("scene")}
            >
              <Icon name="evidence" />
              Open evidence
            </button>
          </section>
        </aside>
      </div>
    </main>
  );
}
