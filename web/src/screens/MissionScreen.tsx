import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import type { AnalysisProgress } from "../analysis/job-progress";
import { AOIDrawPanel } from "../components/AOIDrawing";
import { GlobeStage } from "../components/GlobeStage";
import { Icon } from "../components/Icon";
import { Badge, Eyebrow } from "../components/Primitives";
import { platformLabel, toAoiView } from "../data/dashboard-data";
import type { DashboardData, DashboardScene } from "../data/dashboard-data";
import type { AoiVertex } from "../drawing/validation";
import type { DrawingState } from "../hooks/useAoiDrawing";
import { useAppStore } from "../state/app-store";
import { formatCountdown } from "../time/display-clock";
import {
  formatElapsed,
  formatElementEpochOffset,
  formatLikelihoodPercent,
  formatUtc,
  opportunityForTime,
} from "../utils/presentation";

function GlobeLayerControl() {
  const layers = useAppStore((state) => state.layers);
  const toggleLayer = useAppStore((state) => state.toggleLayer);
  return (
    <details className="layer-popover">
      <summary aria-label="Open globe layers">
        <Icon name="layers" />
        Layers
      </summary>
      <section className="layer-control">
        <Eyebrow>Globe layers</Eyebrow>
        {(
          [
            ["tracks", "Ground tracks"],
            ["swath", "Nominal swath"],
            ["aoi", "AOI outline"],
            ["dayNight", "Day and night"],
            ["sceneDrape", "Selected scene"],
          ] as const
        ).map(([key, label]) => (
          <label key={key}>
            <input type="checkbox" checked={layers[key]} onChange={() => toggleLayer(key)} />
            <span>{label}</span>
          </label>
        ))}
      </section>
    </details>
  );
}

function NextOpportunity({
  data,
  displayTime,
  reducedMotion,
}: {
  data: DashboardData;
  displayTime: Date;
  reducedMotion: boolean;
}) {
  const selectedId = useAppStore((state) => state.selectedOpportunityId);
  const opportunity = opportunityForTime(data, selectedId, displayTime);
  const isPlaying = useAppStore((state) => state.isPlaying);
  const progress = useAppStore((state) => state.playbackProgress);
  const setPlaying = useAppStore((state) => state.setPlaying);
  const setProgress = useAppStore((state) => state.setPlaybackProgress);
  const openEvidence = useAppStore((state) => state.openEvidence);
  const steps = ["Approach", "Nearing AOI", "Intersection", "Leaving", "Complete"];
  const currentStep = Math.min(4, Math.round(progress * 4));
  if (!opportunity) {
    const live = data.mode.mode === "live";
    const windowComplete =
      data.opportunities.length > 0 &&
      displayTime.getTime() > Math.max(...data.opportunities.map((item) => Date.parse(item.exit_time)));
    return (
      <section
        className="next-opportunity next-opportunity--pending"
        id="opportunity-summary"
        data-testid="next-opportunity-card"
      >
        <div className="section-heading">
          <div>
            <Eyebrow>Decision window</Eyebrow>
            <h2>Next geometric opportunity</h2>
          </div>
          <Badge tone="replay">{windowComplete ? "Window complete" : "Analysing"}</Badge>
        </div>
        <div className="pending-orbit">
          <Icon name="satellite" />
          <div>
            <b>
              {windowComplete
                ? "No later opportunity in this window"
                : live
                  ? "Computing live geometry"
                  : "Computing recorded geometry"}
            </b>
            <p>
              {windowComplete
                ? "The displayed clock is beyond the last returned opportunity. Choose another pass or reset playback."
                : `The engine is deriving opportunities from the ${live ? "live" : "recorded"} Sentinel-2 elements.`}
            </p>
          </div>
        </div>
        <p className="honesty-note">
          <Icon name="info" />
          An overpass is a geometric opportunity, not a promised acquisition.
        </p>
      </section>
    );
  }
  const inSwath =
    displayTime.getTime() >= Date.parse(opportunity.entry_time) &&
    displayTime.getTime() <= Date.parse(opportunity.exit_time);
  const countdownValue = inSwath
    ? `00:${formatElapsed(opportunity.entry_time, displayTime)}`
    : formatCountdown(displayTime, opportunity.closest_time);
  const [countdownHours, countdownMinutes, countdownSeconds] = countdownValue.split(":");

  return (
    <section className="next-opportunity" id="opportunity-summary" data-testid="next-opportunity-card">
      <div className="section-heading">
        <div>
          <Eyebrow>Decision window</Eyebrow>
          <h2>Next geometric opportunity</h2>
        </div>
        <Badge tone="replay">{data.mode.mode === "live" ? "Live geometry" : "Recorded geometry"}</Badge>
      </div>
      <div className="satellite-line">
        <span className="satellite-icon">
          <Icon name="satellite" />
        </span>
        <span>
          <b>{platformLabel(opportunity.platform)}</b>
          <small>
            {opportunity.direction} · {opportunity.illumination.replace("_", " ")}
          </small>
        </span>
        <em>{formatElementEpochOffset(opportunity.element_age_seconds)}</em>
      </div>
      <p className={`countdown-state ${inSwath ? "is-active" : ""}`} data-testid="opportunity-phase">
        {inSwath
          ? `In swath · ${formatElapsed(opportunity.entry_time, displayTime)} since entry`
          : "Time to closest approach"}
      </p>
      <div
        className="countdown"
        aria-label={
          inSwath
            ? `Inside the swath for ${formatElapsed(opportunity.entry_time, displayTime)} since entry`
            : `Time until next geometric opportunity: ${formatCountdown(displayTime, opportunity.closest_time)}`
        }
      >
        <span>{countdownHours}</span>
        <i>:</i>
        <span>{countdownMinutes}</span>
        <i>:</i>
        <span>{countdownSeconds}</span>
      </div>
      <div className="countdown-units">
        <span>HOURS</span>
        <span>MINUTES</span>
        <span>SECONDS</span>
      </div>
      <div className="opportunity-time">
        <time dateTime={opportunity.closest_time}>{formatUtc(opportunity.closest_time)}</time>
        <span>
          {new Intl.DateTimeFormat("en-SG", {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: "Asia/Singapore",
            hour12: false,
          }).format(new Date(opportunity.closest_time))}{" "}
          SGT
        </span>
      </div>
      <div className="playback-control">
        <button
          className="button button--primary"
          type="button"
          aria-label={isPlaying ? "Pause pass" : progress >= 1 ? "Replay pass" : "Play pass"}
          data-testid="pass-playback-button"
          onClick={() =>
            reducedMotion ? setProgress(Math.min(1, (currentStep + 1) / 4)) : setPlaying(!isPlaying)
          }
        >
          <Icon name={isPlaying ? "pause" : "play"} />
          {isPlaying ? "Pause pass" : progress >= 1 ? "Replay pass" : "Play pass"}
          <small>{reducedMotion ? steps[currentStep] : "12 s"}</small>
        </button>
      </div>
      <p className="honesty-note">
        <Icon name="info" />
        An overpass is a geometric opportunity, not a promised acquisition.
      </p>
      <button className="evidence-link" type="button" onClick={() => openEvidence("opportunity")}>
        Open evidence
      </button>
    </section>
  );
}

export function LikelihoodPanel({
  data,
  analysis = null,
}: {
  data: DashboardData;
  analysis?: AnalysisProgress | null;
}) {
  const [explain, setExplain] = useState(false);
  const openEvidence = useAppStore((state) => state.openEvidence);
  const pendingCopy = analysis
    ? data.scenes.length > 0 && analysis.rows.raster.progress < 1
      ? `${data.scenes.length} scenes found · computing pixels`
      : analysis.rows.archive.progress < 1
        ? "Searching for archive scenes"
        : analysis.rows.raster.progress < 1
          ? "Waiting for AOI pixels"
          : "Computing likelihood"
    : data.sceneMeta?.archive_state === "not_recorded"
      ? "Likelihood not recorded for this area"
      : "Waiting for AOI pixels";
  return (
    <section className="likelihood-panel" data-testid="likelihood-interval">
      <div className="section-heading">
        <div>
          <Eyebrow>Historical record</Eyebrow>
          <h2>Historical clear-look likelihood</h2>
        </div>
      </div>
      {!data.likelihood && (
        <div className="likelihood-pending">
          <b>{pendingCopy}</b>
          <span>
            {analysis
              ? "The engine will publish the likelihood after AOI pixel accounting."
              : "The engine has not published a likelihood for this area."}
          </span>
        </div>
      )}
      {data.likelihood?.horizons.map((horizon) => (
        <button
          className="likelihood-row"
          type="button"
          key={horizon.days}
          onClick={() => openEvidence("likelihood")}
        >
          <span className="likelihood-label">
            Within {horizon.days} days <b>{formatLikelihoodPercent(horizon.probability)}</b>
          </span>
          {horizon.credible_interval ? (
            <span
              className="whisker"
              style={
                {
                  "--low": `${horizon.credible_interval.lower * 100}%`,
                  "--value": `${(horizon.probability ?? 0) * 100}%`,
                  "--high": `${horizon.credible_interval.upper * 100}%`,
                } as CSSProperties
              }
            >
              <i />
              <em />
            </span>
          ) : (
            <span className="whisker whisker--empty" />
          )}
          <span className="whisker-scale" aria-hidden="true">
            {[0, 50, 100].map((tick) => (
              <i
                key={tick}
                className={Math.abs(tick - (horizon.probability ?? -1) * 100) <= 4 ? "is-hidden" : ""}
              >
                {tick}
              </i>
            ))}
          </span>
          <span className="likelihood-meta">
            {horizon.credible_interval
              ? `${Math.round(horizon.credible_interval.lower * 100)}–${Math.round(horizon.credible_interval.upper * 100)}% interval`
              : "Not enough AOI observations"}
            <b>
              {horizon.opportunity_count} opportunities across {horizon.opportunity_days} days ·{" "}
              {data.likelihood?.clear_posterior.sample_size ?? 0} past looks
            </b>
          </span>
        </button>
      ))}
      {data.likelihood?.surface_class_policy.snow_ice_counted_as_surface && (
        <p className="surface-policy-note">Snow/ice counted as surface for this area.</p>
      )}
      <button
        className="text-button likelihood-explain"
        type="button"
        onClick={() => setExplain((open) => !open)}
        aria-expanded={explain}
      >
        How this is labelled
      </button>
      {explain && (
        <p className="expanded-note">
          This is a historical likelihood for this AOI and horizon. It does not use a weather forecast and
          does not guarantee an acquisition.
        </p>
      )}
      <p className="honesty-note honesty-note--evidence">
        <Icon name="info" />
        Based on past AOI observations. Not a weather forecast.
      </p>
    </section>
  );
}

function OpportunityRail({ data, selectedId }: { data: DashboardData; selectedId: string }) {
  const selectOpportunity = useAppStore((state) => state.selectOpportunity);
  const setProgress = useAppStore((state) => state.setPlaybackProgress);
  const windowStart = data.likelihood?.window_start ?? data.opportunityMeta.window_start;
  const windowEnd = data.likelihood?.window_end ?? data.opportunityMeta.window_end;
  const counted = data.opportunities.filter((opportunity) => {
    const time = Date.parse(opportunity.closest_time);
    return time >= Date.parse(windowStart) && time < Date.parse(windowEnd);
  });
  const expected = data.likelihood?.horizons.find((horizon) => horizon.days === 14)?.opportunity_count;
  return (
    <section className="upcoming-panel">
      <div className="section-heading">
        <Eyebrow>Upcoming · 14 days</Eyebrow>
        <span>{counted.length === 0 ? "COMPUTING" : `${counted.length} OPPORTUNITIES`}</span>
      </div>
      {expected !== undefined && expected !== counted.length && (
        <p className="window-mismatch">
          Engine window currently lists {counted.length} of {expected} counted opportunities.
        </p>
      )}
      <div className="opportunity-list">
        {counted.map((opportunity, index) => (
          <button
            type="button"
            key={opportunity.id}
            data-testid="opportunity-row"
            className={opportunity.id === selectedId ? "is-selected" : ""}
            onClick={() => {
              selectOpportunity(opportunity.id);
              setProgress(0);
            }}
            aria-pressed={opportunity.id === selectedId}
          >
            <i>{platformLabel(opportunity.platform).slice(-2)}</i>
            <span>
              <b>{index === 0 ? "Next pass" : `Pass ${index + 1}`}</b>
              <small>
                {formatUtc(opportunity.closest_time)} · {opportunity.illumination}
              </small>
            </span>
            <em>
              <b>{Math.round(opportunity.aoi_sun_elevation_deg)}° sun</b>
              <small>{Math.round(opportunity.minimum_ground_track_distance_km)} km from track</small>
            </em>
          </button>
        ))}
        {counted.length === 0 && <p className="opportunity-empty">Opportunity geometry is being computed.</p>}
      </div>
    </section>
  );
}

export function ScenePreview({
  scene,
  aoiName,
  large = false,
}: {
  scene: DashboardScene;
  aoiName: string;
  large?: boolean;
}) {
  const [safeSize, setSafeSize] = useState<{ width: number; height: number } | null>(null);
  const alt = `${scene.thumbnail ? "AOI-clipped true-colour image" : "Preview unavailable"} for ${aoiName} from ${scene.id}, acquired ${formatUtc(scene.acquisition_time)} by ${platformLabel(scene.platform)}.`;
  return scene.thumbnail ? (
    <div className={`scene-preview ${large ? "scene-preview--large" : ""}`}>
      <img
        src={scene.thumbnail}
        alt={alt}
        style={
          large && safeSize
            ? ({
                "--source-safe-width": `${safeSize.width}px`,
                "--source-safe-height": `${safeSize.height}px`,
              } as CSSProperties)
            : undefined
        }
        onLoad={
          large
            ? (event) => {
                const scale = 1.5 / Math.max(1, window.devicePixelRatio);
                setSafeSize({
                  width: Math.floor(event.currentTarget.naturalWidth * scale),
                  height: Math.floor(event.currentTarget.naturalHeight * scale),
                });
              }
            : undefined
        }
      />
      {large && <span>AOI TRUE COLOUR</span>}
    </div>
  ) : (
    <div className={`missing-preview ${large ? "missing-preview--large" : ""}`} role="img" aria-label={alt}>
      <Icon name="evidence" />
      <b>Preview not bundled</b>
      <span>Metadata remains available</span>
    </div>
  );
}

function RecentLooksDeck({
  data,
  state,
  analysis,
}: {
  data: DashboardData;
  state: string | null;
  analysis: AnalysisProgress | null;
}) {
  const selectedId = useAppStore((store) => store.selectedSceneId);
  const selectScene = useAppStore((store) => store.selectScene);
  const setRoute = useAppStore((store) => store.setRoute);
  const scenes = state === "empty" ? [] : data.scenes;
  const archiveState = state === "empty" ? "empty" : data.sceneMeta?.archive_state;
  const pendingPixels = scenes.filter((scene) => scene.analysis_state !== "ready").length;
  const archiveSummary =
    archiveState === "not_recorded"
      ? "Archive not recorded"
      : analysis && scenes.length > 0 && (pendingPixels > 0 || analysis.rows.raster.progress < 1)
        ? `${scenes.length} scenes found · computing pixels`
        : archiveState === "searching" && scenes.length === 0
          ? "Searching archive"
          : `${scenes.length} scene${scenes.length === 1 ? "" : "s"} ready`;

  return (
    <section className="recent-deck" data-testid="recent-looks-deck">
      <div className="deck-heading">
        <div className="deck-title-line">
          <h2>Recent looks</h2>
          <span>AOI true colour · {archiveSummary} · 30-day window</span>
        </div>
        <div>
          <button
            type="button"
            onClick={() =>
              window.alert(
                "AOI clear is the share of valid scene-classification pixels inside this boundary that are labelled clear surface.",
              )
            }
          >
            What AOI clear means
          </button>
          <button
            type="button"
            aria-label="Open AOI detail"
            data-testid="open-aoi-detail"
            onClick={() => setRoute("detail")}
          >
            Open AOI detail →
          </button>
        </div>
      </div>
      {archiveState === "empty" ? (
        <EmptyArchive />
      ) : archiveState === "not_recorded" ? (
        <NotRecordedArchive />
      ) : (
        <div
          className="scene-filmstrip"
          role="listbox"
          aria-label="Recent Sentinel-2 scenes"
          tabIndex={0}
          onKeyDown={(event) => {
            if ((event.key === "Home" || event.key === "End") && data.scenes.length > 0)
              selectScene(data.scenes[event.key === "Home" ? 0 : data.scenes.length - 1].id);
          }}
        >
          {scenes.map((scene) => (
            <button
              type="button"
              role="option"
              aria-selected={scene.id === selectedId}
              className={`scene-card ${scene.id === selectedId ? "is-selected" : ""}`}
              key={scene.id}
              onClick={() => selectScene(scene.id)}
              data-testid="scene-card"
            >
              <ScenePreview scene={scene} aoiName={data.aoi.name} />
              <span className="scene-card-copy">
                <span>
                  <b>{formatUtc(scene.acquisition_time)}</b>
                  {scene.id === selectedId && <em>Selected</em>}
                </span>
                <strong>
                  {scene.aoi_clear_percent === null ? "—" : `${scene.aoi_clear_percent.toFixed(1)}%`}{" "}
                  <small>
                    {scene.analysis_state === "ready" ? "AOI clear" : scene.analysis_state.replace("_", " ")}
                  </small>
                </strong>
                <span>
                  {scene.tile_cloud_cover_percent === null
                    ? "Tile cloud not reported"
                    : `${scene.tile_cloud_cover_percent.toFixed(1)}% tile cloud`}
                </span>
              </span>
            </button>
          ))}
          {archiveState === "searching" && scenes.length === 0 && (
            <div className="scene-card scene-card--pending">
              <span className="scene-card-skeleton" />
              <span>
                <b>Searching the archive</b>
                <small>Scene cards enter as the engine returns them.</small>
              </span>
            </div>
          )}
        </div>
      )}
      {scenes.length > 3 && <span className="deck-overflow-count">+{scenes.length - 3}</span>}
    </section>
  );
}

function StreamProgress({ analysis }: { analysis: AnalysisProgress }) {
  const rows = [
    ["orbit", "Orbit geometry"],
    ["archive", "Archive search"],
    ["raster", "AOI pixels"],
    ["likelihood", "Likelihood summary"],
  ] as const;
  return (
    <section
      className={`stream-progress stream-progress--${analysis.state}`}
      data-testid="stream-progress"
      aria-label="Live analysis progress"
    >
      <div className="stream-progress__heading">
        <div>
          <Eyebrow>Engine stream</Eyebrow>
          <h2>
            {analysis.state === "succeeded"
              ? "Analysis ready"
              : analysis.state === "failed"
                ? "Analysis stopped"
                : "Analysing drawn area"}
          </h2>
        </div>
        <Badge tone={analysis.state === "failed" ? "opportunity" : "ready"}>
          {analysis.state === "connecting" ? "Connecting" : analysis.state}
        </Badge>
      </div>
      <p>{analysis.message}</p>
      {rows.map(([key, label]) => (
        <div key={key} data-testid={`progress-${key}`}>
          <span>{label}</span>
          <i>
            <em style={{ width: `${Math.round(analysis.rows[key].progress * 100)}%` }} />
          </i>
          <b>{analysis.rows[key].label}</b>
        </div>
      ))}
    </section>
  );
}

function EmptyArchive() {
  return (
    <div className="empty-archive" data-testid="empty-archive">
      <Icon name="evidence" />
      <div>
        <h3>No Sentinel-2 scenes in this window</h3>
        <p>
          The AOI and opportunity geometry are still available. Broaden the archive dates to look for earlier
          observations.
        </p>
      </div>
      <button type="button">Review opportunities</button>
    </div>
  );
}

export function NotRecordedArchive() {
  return (
    <div className="empty-archive empty-archive--not-recorded" data-testid="not-recorded-archive">
      <Icon name="evidence" />
      <div>
        <h3>Archive scenes are not recorded for this drawn area</h3>
        <p>
          Replay can compute geometric opportunities from its recorded orbital elements, but it will not
          invent imagery or AOI statistics.
        </p>
      </div>
    </div>
  );
}

function UpstreamError({ data, onReplay }: { data: DashboardData; onReplay: () => void }) {
  const entry = Object.entries(data.health.upstreams).find(
    ([, value]) => value.status === "unavailable" || value.status === "stale",
  );
  if (!entry) return null;
  const [source, health] = entry;
  const label =
    source === "celestrak"
      ? "Orbit elements"
      : source === "earth-search"
        ? "Earth Search catalogue"
        : source === "sentinel-cogs"
          ? "Scene asset"
          : source;
  return (
    <div className="upstream-error" role="alert" data-testid="upstream-error">
      <Eyebrow>
        {label} · {health.status}
      </Eyebrow>
      <h3>
        {source === "celestrak"
          ? "Live orbit elements are unavailable. Recorded geometry is still ready."
          : "Live archive is unavailable. Recorded evidence is still ready."}
      </h3>
      <p>
        {health.reason ?? "The engine reported a degraded source."}
        {health.last_success_at
          ? ` Stale input · last updated ${formatUtc(health.last_success_at, true)}.`
          : ""}
      </p>
      <div>
        <button className="button button--primary" type="button" onClick={onReplay}>
          Use recorded replay
        </button>
      </div>
    </div>
  );
}

interface MissionScreenProps {
  data: DashboardData;
  displayTime: Date;
  globeReady: boolean;
  setGlobeReady: () => void;
  reducedMotion: boolean;
  screenState: string | null;
  analysis: AnalysisProgress | null;
  onReplay: () => void;
  drawing: DrawingState;
  onDrawPoint: (vertex: AoiVertex) => void;
  onDrawClose: () => void;
  onDrawUndo: () => void;
  onDrawCancel: () => void;
  onDrawCommit: () => void;
}

export function MissionScreen({
  data,
  displayTime,
  globeReady,
  setGlobeReady,
  reducedMotion,
  screenState,
  analysis,
  onReplay,
  drawing,
  onDrawPoint,
  onDrawClose,
  onDrawUndo,
  onDrawCancel,
  onDrawCommit,
}: MissionScreenProps) {
  const selectedAoiId = useAppStore((state) => state.selectedAoiId);
  const selectedAoi = data.aois.find((item) => item.id === selectedAoiId) ?? data.aoi;
  const aoi = useMemo(() => toAoiView(selectedAoi), [selectedAoi]);
  const selectedOpportunityId = useAppStore((state) => state.selectedOpportunityId);
  const selectedSceneId = useAppStore((state) => state.selectedSceneId);
  const playbackProgress = useAppStore((state) => state.playbackProgress);
  const isPlaying = useAppStore((state) => state.isPlaying);
  const layers = useAppStore((state) => state.layers);
  const setProgress = useAppStore((state) => state.setPlaybackProgress);
  const displayOpportunity = opportunityForTime(data, selectedOpportunityId, displayTime);
  const displayOpportunityId = displayOpportunity?.id ?? selectedOpportunityId;
  const visibleAnalysis =
    analysis ??
    (screenState === "streaming"
      ? {
          jobId: "preview",
          state: "running" as const,
          message: "Streaming engine results as they become queryable.",
          rows: {
            orbit: { progress: 1, label: "Ready" },
            archive: { progress: 1, label: "Ready" },
            raster: { progress: 0.58, label: "Analysing AOI" },
            likelihood: { progress: 0, label: "Queued" },
          },
        }
      : null);

  return (
    <main className={`mission-workspace ${isPlaying ? "is-playing" : ""}`} data-testid="mission-screen">
      <div className="globe-cell">
        <GlobeStage
          data={data}
          aoi={aoi}
          selectedOpportunityId={displayOpportunityId}
          selectedSceneId={selectedSceneId}
          playbackProgress={playbackProgress}
          clockTime={displayTime.toISOString()}
          layers={layers}
          reducedMotion={reducedMotion}
          isPlaying={isPlaying}
          forceFallback={screenState === "webgl"}
          onFirstFrame={() => {
            if (!globeReady) setGlobeReady();
          }}
          onProgressChange={setProgress}
          drawing={drawing}
          onDrawPoint={onDrawPoint}
          onDrawClose={onDrawClose}
        />
        {!drawing.active && <GlobeLayerControl />}
        {drawing.active && (
          <AOIDrawPanel
            vertices={drawing.vertices}
            closed={drawing.closed}
            committing={drawing.committing}
            error={drawing.error}
            onAddCoordinate={onDrawPoint}
            onUndo={onDrawUndo}
            onClosePolygon={onDrawClose}
            onCancel={onDrawCancel}
            onCommit={onDrawCommit}
          />
        )}
      </div>
      <aside className="outlook-rail">
        <div className="mobile-sheet-handle" aria-hidden="true" />
        {!aoi.coverage.archive && data.mode.mode === "replay" && (
          <div className="fixture-note">
            <Icon name="info" />
            This area has recorded orbital geometry. Archive evidence is not recorded in replay.
          </div>
        )}
        {(screenState === "error" ||
          data.health.status !== "ok" ||
          Object.values(data.health.upstreams).some(
            (item) => item.status === "stale" || item.status === "unavailable",
          )) && <UpstreamError data={data} onReplay={onReplay} />}
        <NextOpportunity data={data} displayTime={displayTime} reducedMotion={reducedMotion} />
        <OpportunityRail data={data} selectedId={displayOpportunityId} />
        <LikelihoodPanel data={data} analysis={visibleAnalysis} />
        {visibleAnalysis && <StreamProgress analysis={visibleAnalysis} />}
      </aside>
      <RecentLooksDeck data={data} state={screenState} analysis={visibleAnalysis} />
    </main>
  );
}
