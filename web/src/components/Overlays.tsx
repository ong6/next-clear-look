import { useCallback, useEffect, useRef, useState } from "react";
import type { DashboardData } from "../data/dashboard-data";
import { useAppStore } from "../state/app-store";
import { formatUtc } from "../utils/presentation";
import { Icon } from "./Icon";
import { Badge, Eyebrow } from "./Primitives";

export function EvidenceDrawer({ data }: { data: DashboardData }) {
  const closeEvidence = useAppStore((state) => state.closeEvidence);
  const claim = useAppStore((state) => state.evidenceClaim);
  const selectedSceneId = useAppStore((state) => state.selectedSceneId);
  const selectedOpportunityId = useAppStore((state) => state.selectedOpportunityId);
  const scene = data.scenes.find((item) => item.id === selectedSceneId) ?? data.scenes[0];
  const opportunity =
    data.opportunities.find((item) => item.id === selectedOpportunityId) ?? data.opportunities[0];
  const statistics = scene ? data.statistics[scene.id] : undefined;
  const provenanceId =
    claim === "likelihood"
      ? data.likelihood?.provenance_id
      : claim === "opportunity"
        ? opportunity?.provenance_id
        : claim === "accounting"
          ? statistics?.provenance_id
          : scene?.provenance_id;
  const graph = provenanceId ? data.provenance[provenanceId] : undefined;
  const dialogRef = useRef<HTMLElement>(null);
  const returnFocus = useAppStore((state) => state.evidenceReturnFocus);

  const closeAndRestoreFocus = useCallback(() => {
    closeEvidence();
    window.setTimeout(() => returnFocus?.focus());
  }, [closeEvidence, returnFocus]);

  useEffect(() => {
    dialogRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeAndRestoreFocus();
      if (event.key === "Tab" && dialogRef.current) {
        const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>("button, a[href]")];
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [closeAndRestoreFocus]);

  const copy = (text: string) => void navigator.clipboard?.writeText(text);
  return (
    <div className="drawer-layer" role="presentation">
      <section
        ref={dialogRef}
        tabIndex={-1}
        className="evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Evidence and provenance"
        data-testid="evidence-drawer"
      >
        <div className="drawer-heading">
          <div>
            <Eyebrow>Trace every claim</Eyebrow>
            <h2>Evidence and provenance</h2>
          </div>
          <button type="button" aria-label="Close evidence" onClick={closeAndRestoreFocus}>
            <Icon name="close" />
          </button>
        </div>
        <section>
          <Eyebrow>What this claim says</Eyebrow>
          <h3>
            {claim === "likelihood"
              ? "Historical clear-look likelihood"
              : claim === "accounting"
                ? "AOI clear accounting"
                : claim === "scene"
                  ? "Recorded archive scene"
                  : "Geometric opportunity"}
          </h3>
          <p>
            {claim === "likelihood"
              ? (data.likelihood?.interpretation ??
                "Likelihood is unavailable because the archive sample is insufficient or not recorded.")
              : claim === "opportunity"
                ? "The supplied orbital geometry intersects this AOI. It does not represent acquisition planning."
                : "Pixel accounting is clipped to the AOI. Catalogue tile cloud remains separate context."}
          </p>
        </section>
        <section>
          <h3>AOI and clock</h3>
          <dl>
            <CopyRow label="AOI geometry" value={data.aoi.geometry_sha256} onCopy={copy} />
            <CopyRow label="Replay clock" value={data.mode.clock} onCopy={copy} />
            <CopyRow label="Fixture" value={data.mode.fixture_set ?? "none"} onCopy={copy} />
          </dl>
        </section>
        <section>
          <h3>Orbit inputs</h3>
          <dl>
            {data.satellites.map((satellite) => (
              <CopyRow
                key={satellite.id}
                label={`${satellite.name} OMM`}
                value={satellite.omm_epoch}
                onCopy={copy}
              />
            ))}
          </dl>
        </section>
        <section>
          <h3>Archive scene</h3>
          {scene ? (
            <>
              <dl>
                <CopyRow label="Scene ID" value={scene.id} onCopy={copy} />
                <CopyRow label="Acquired" value={scene.acquisition_time} onCopy={copy} />
                <CopyRow label="Collection" value={scene.collection} onCopy={copy} />
                <CopyRow label="Grid tile" value={scene.tile} onCopy={copy} />
              </dl>
              <button type="button" className="offline-link" disabled={!navigator.onLine}>
                {navigator.onLine ? "Open source record" : "Available when online"}
              </button>
            </>
          ) : (
            <p>No archive scene was recorded for this AOI.</p>
          )}
        </section>
        <section>
          <h3>AOI analysis</h3>
          {statistics ? (
            <dl>
              <CopyRow label="Valid pixels" value={statistics.valid_pixels.toLocaleString()} onCopy={copy} />
              <CopyRow label="Algorithm" value={statistics.algorithm_version} onCopy={copy} />
              <CopyRow label="Provenance" value={statistics.provenance_id} onCopy={copy} />
            </dl>
          ) : (
            <p>AOI SCL accounting is pending or not recorded.</p>
          )}
        </section>
        <section className="provenance-graph" data-testid="provenance-graph">
          <h3>Provenance graph</h3>
          {graph ? (
            <>
              <p>
                {graph.nodes.length} nodes · {graph.edges.length} lineage links · created{" "}
                {formatUtc(graph.created_at, true)}
              </p>
              <ul>
                {graph.nodes.map((node) => (
                  <li key={node.id}>
                    <span>
                      <b>{node.label}</b>
                      <small>
                        {node.kind}
                        {node.source_id ? ` · ${node.source_id}` : ""}
                      </small>
                    </span>
                    <Badge tone={node.available_offline ? "ready" : "replay"}>
                      {node.available_offline ? "offline" : "online"}
                    </Badge>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p>The engine did not return a provenance graph for this resource.</p>
          )}
        </section>
        <AttributionList data={data} />
      </section>
    </div>
  );
}

function CopyRow({
  label,
  value,
  onCopy,
}: {
  label: string;
  value: string;
  onCopy: (value: string) => void;
}) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
      <dd className="copy-action">
        <button type="button" onClick={() => onCopy(value)} aria-label={`Copy ${label}`}>
          <Icon name="copy" width={15} />
          <span>Copy</span>
        </button>
      </dd>
    </>
  );
}

function AttributionList({ data }: { data: DashboardData }) {
  const productCredits = [
    "CesiumJS — Apache 2.0. Cesium ion services are not used.",
    "NASA Blue Marble: Next Generation, October 2004 — global image and 500 m preset crops.",
    "NASA Black Marble 2012 night lights.",
    "Sentinel-2 cloudless – https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2024) — online close-zoom enhancement, CC BY-NC-SA 4.0.",
  ];
  return (
    <section className="attribution-list" data-testid="attribution-list">
      <h3>Data attribution · verbatim from the engine</h3>
      <ul>
        {data.attributions.map((item) => (
          <li key={item.source} data-source={item.source}>
            {item.display_text}
          </li>
        ))}
      </ul>
      <h3>Map and runtime credits</h3>
      <ul>
        {productCredits.map((credit) => (
          <li key={credit}>{credit}</li>
        ))}
      </ul>
    </section>
  );
}

export function AttributionPanel({ data }: { data: DashboardData }) {
  const setOpen = useAppStore((state) => state.setAttributionOpen);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setOpen]);
  return (
    <div className="modal-layer" role="presentation">
      <section
        className="attribution-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Attribution and sources"
        data-testid="attribution-panel"
      >
        <div className="drawer-heading">
          <div>
            <Eyebrow>Source register</Eyebrow>
            <h2>Attribution and sources</h2>
          </div>
          <button type="button" aria-label="Close attribution" onClick={() => setOpen(false)}>
            <Icon name="close" />
          </button>
        </div>
        <AttributionList data={data} />
        <p>
          NASA day, night, and preset-context imagery is bundled locally. Recorded replay does not request a
          basemap service.
        </p>
      </section>
    </div>
  );
}

export function LoadingScreen() {
  return (
    <div className="loading-shell">
      <header className="app-header">
        <div className="wordmark">
          <span className="aperture-mark">
            <i />
            <i />
            <i />
            <i />
          </span>
          <span className="wordmark-long">
            <b>NEXT</b>
            <em>CLEAR LOOK</em>
          </span>
        </div>
        <div className="header-spacer" />
        <Badge tone="replay">RECORDED REPLAY</Badge>
      </header>
      <main>
        <section>
          <Eyebrow>Initialising recorded mission</Eyebrow>
          <h1>Focusing Tuas</h1>
          <p>An overpass is a geometric opportunity, not a promised acquisition.</p>
          <div className="skeleton-lines">
            <i />
            <i />
            <i />
          </div>
        </section>
      </main>
    </div>
  );
}

export function PerformanceOverlay({ enabled }: { enabled: boolean }) {
  const [sample, setSample] = useState({ fps: 0, p10Fps: 0, longestTaskMs: 0 });
  useEffect(() => {
    if (!enabled) return;
    const frameTimes: number[] = [];
    const longTasks: number[] = [];
    let frame = 0;
    let previous = performance.now();
    let lastReport = previous;
    const observer =
      "PerformanceObserver" in window
        ? new PerformanceObserver((list) => {
            longTasks.push(...list.getEntries().map((entry) => entry.duration));
          })
        : null;
    observer?.observe({ type: "longtask", buffered: true });
    const tick = (now: number) => {
      frameTimes.push(now - previous);
      previous = now;
      if (now - lastReport >= 1_000 && frameTimes.length > 4) {
        const recent = frameTimes.slice(-120);
        const rates = recent.map((duration) => 1_000 / duration).sort((a, b) => a - b);
        const next = {
          fps: Math.round((recent.length * 1_000) / recent.reduce((total, duration) => total + duration, 0)),
          p10Fps: Math.round(rates[Math.floor(rates.length * 0.1)] ?? 0),
          longestTaskMs: Math.round(Math.max(0, ...longTasks)),
        };
        setSample(next);
        window.__nclPerf = next;
        lastReport = now;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      delete window.__nclPerf;
    };
  }, [enabled]);
  if (!enabled) return null;
  return (
    <output className="performance-overlay" data-testid="performance-overlay">
      <span>LOCAL PERFORMANCE</span>
      <b>{sample.fps} FPS</b>
      <em>
        P10 {sample.p10Fps} · LONG {sample.longestTaskMs} MS
      </em>
    </output>
  );
}
