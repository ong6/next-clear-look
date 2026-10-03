import { useState } from "react";
import type { DashboardData } from "../data/dashboard-data";
import { toAoiView } from "../data/dashboard-data";
import { useAppStore } from "../state/app-store";
import { formatDisplayClock, formatMissionOffset } from "../time/display-clock";
import { opportunityForTime } from "../utils/presentation";
import { Icon } from "./Icon";
import { Eyebrow } from "./Primitives";

export function AppHeader({
  data,
  displayTime,
  onSwitchMode,
  modeMessage,
}: {
  data: DashboardData;
  displayTime: Date;
  onSwitchMode: (mode: "live" | "replay") => Promise<void>;
  modeMessage: string | null;
}) {
  const setRoute = useAppStore((state) => state.setRoute);
  const setAoiPickerOpen = useAppStore((state) => state.setAoiPickerOpen);
  const setAttributionOpen = useAppStore((state) => state.setAttributionOpen);
  const selectedAoiId = useAppStore((state) => state.selectedAoiId);
  const selectedOpportunityId = useAppStore((state) => state.selectedOpportunityId);
  const [menuOpen, setMenuOpen] = useState(false);
  const [liveConfirm, setLiveConfirm] = useState(false);
  const [switching, setSwitching] = useState(false);
  const selectedAoi = data.aois.find((item) => item.id === selectedAoiId) ?? data.aoi;
  const aoi = toAoiView(selectedAoi);
  const isLive = data.mode.mode === "live";
  const selectedOpportunity = opportunityForTime(data, selectedOpportunityId, displayTime);

  const switchMode = async (mode: "live" | "replay") => {
    setSwitching(true);
    try {
      await onSwitchMode(mode);
      setLiveConfirm(false);
    } catch {
      // Parent keeps the engine's explicit error visible inside this dialog.
    } finally {
      setSwitching(false);
    }
  };

  return (
    <>
      <header className="app-header" data-testid="app-header">
        <button
          className="wordmark"
          type="button"
          onClick={() => setRoute("mission")}
          aria-label="Next Clear Look — return to Mission"
        >
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
          <span className="wordmark-short">NCL</span>
        </button>
        <button
          className="header-aoi"
          type="button"
          onClick={() => setAoiPickerOpen(true)}
          data-testid="aoi-switcher"
        >
          <span>{aoi.name}</span>
          <Icon name="chevron" width={14} />
        </button>
        <div className="header-spacer" />
        <button
          className={`mode-badge ${isLive ? "mode-badge--live" : ""}`}
          type="button"
          onClick={() => setLiveConfirm(true)}
          aria-label={`${isLive ? "Live data" : "Recorded replay"} mode. Open mode menu.`}
          data-testid="mode-badge"
        >
          <i />
          <span>{isLive ? "LIVE DATA" : "RECORDED REPLAY · OFFLINE READY"}</span>
          <Icon name="chevron" width={13} />
        </button>
        <time className="header-clock" data-testid="replay-clock" dateTime={displayTime.toISOString()}>
          <span>{formatDisplayClock(displayTime)}</span>
          {selectedOpportunity && <b>{formatMissionOffset(displayTime, selectedOpportunity.closest_time)}</b>}
        </time>
        <div className="source-health" aria-label="Replay ready" data-testid="source-health">
          {Object.entries(data.health.upstreams)
            .slice(0, 3)
            .map(([source, value]) => (
              <span key={source}>
                <i />
                {source === "celestrak" ? "Orbit" : source === "earth-search" ? "Archive" : "Analysis"}
                <b>{value.status}</b>
              </span>
            ))}
        </div>
        <button
          className="header-icon desktop-only"
          type="button"
          onClick={() => setAttributionOpen(true)}
          aria-label="Open attribution"
        >
          <Icon name="info" />
        </button>
        <button
          className="header-icon"
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-label="Open application menu"
          aria-expanded={menuOpen}
        >
          <Icon name="menu" />
        </button>
        {menuOpen && (
          <div className="app-menu" role="menu">
            <strong>{isLive ? "Live source status" : "Replay ready"}</strong>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setAttributionOpen(true);
                setMenuOpen(false);
              }}
            >
              Attribution and sources
            </button>
            <button type="button" role="menuitem" onClick={() => setMenuOpen(false)}>
              Keyboard shortcuts
            </button>
            <p>P play/pause · F focus · N north · E evidence</p>
          </div>
        )}
      </header>
      {liveConfirm && (
        <div className="modal-layer" role="presentation">
          <section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="live-title">
            <Eyebrow>Mode change</Eyebrow>
            <h2 id="live-title">{isLive ? "Return to recorded replay?" : "Switch to live data?"}</h2>
            <p>
              {isLive
                ? "The deterministic recorded fixture remains available offline."
                : "Live sources can be delayed or unavailable. Recorded replay remains available."}
            </p>
            {!isLive && !data.mode.live_available && (
              <p className="inline-status inline-status--warning">
                Live data is disabled by this engine. Start it with NCL_ALLOW_LIVE=1 to enable live analysis.
              </p>
            )}
            {modeMessage && (
              <p className="inline-status inline-status--warning" role="alert" data-testid="mode-error">
                {modeMessage}
              </p>
            )}
            <div className="dialog-actions">
              <button type="button" className="button button--quiet" onClick={() => setLiveConfirm(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="button button--primary"
                disabled={switching}
                onClick={() => void switchMode(isLive ? "replay" : "live")}
              >
                {switching ? "Switching…" : isLive ? "Use recorded replay" : "Use live data"}
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
