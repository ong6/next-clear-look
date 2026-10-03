import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createAnalysisJob,
  createAoi,
  createAoiRecord,
  loadDashboardData,
  loadDashboardShell,
  NclApiError,
  reloadAoiDashboard,
  switchEngineMode,
} from "./api/client";
import { SseClient } from "./api/sse-client";
import { INITIAL_PROGRESS_ROWS, mergeJobEvent, reduceAnalysisProgress } from "./analysis/job-progress";
import type { AnalysisProgress } from "./analysis/job-progress";
import { AOIPicker } from "./components/AOIDrawing";
import { AppHeader } from "./components/AppHeader";
import { AttributionPanel, EvidenceDrawer, LoadingScreen, PerformanceOverlay } from "./components/Overlays";
import { Eyebrow } from "./components/Primitives";
import { emptyOpportunityMeta, emptySceneMeta, toAoiView } from "./data/dashboard-data";
import type { DashboardData, Schemas } from "./data/dashboard-data";
import { readSavedAois, replaceSavedAoiId, saveAoiLocally } from "./drawing/saved-aois";
import { useAoiDrawing } from "./hooks/useAoiDrawing";
import { AOIDetail } from "./screens/AOIDetail";
import { MissionScreen } from "./screens/MissionScreen";
import { useAppStore } from "./state/app-store";
import { createDisplayClock } from "./time/display-clock";
import { passProgressForTime, passTimeForProgress } from "./utils/presentation";
import "./styles/app.css";

const PASS_DURATION_MS = 12_000;
const TERMINAL_JOB_EVENTS = new Set(["job.completed", "job.failed", "job.cancelled"]);

async function restoreSavedAreas(data: DashboardData): Promise<DashboardData> {
  const aois = [...data.aois];
  for (const saved of readSavedAois()) {
    const existing = aois.find(
      (aoi) => aoi.id === saved.id || JSON.stringify(aoi.geometry) === JSON.stringify(saved.geometry),
    );
    if (existing) {
      if (existing.id !== saved.id) replaceSavedAoiId(saved.id, existing);
      continue;
    }
    try {
      const restored = await createAoiRecord(saved.name, saved.geometry, saved.timezone);
      aois.push(restored);
      replaceSavedAoiId(saved.id, restored);
    } catch {
      // A saved boundary remains available locally even if this engine cannot restore it yet.
    }
  }
  return { ...data, aois };
}

export function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [modeMessage, setModeMessage] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisProgress | null>(null);
  const [globeReady, setGlobeReady] = useState(false);
  const [displayTime, setDisplayTime] = useState(() => new Date("2026-10-03T00:00:00Z"));
  const [reducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const clockRef = useRef<ReturnType<typeof createDisplayClock> | null>(null);
  const frameRef = useRef<number | null>(null);
  const playStartRef = useRef(0);
  const playProgressRef = useRef(0);
  const dataRef = useRef<DashboardData | null>(null);
  const analysisClientsRef = useRef(new Map<string, SseClient>());
  const refreshSequenceRef = useRef(0);
  const scrubbedProgressRef = useRef<number | null>(null);
  const scrubbedOpportunityRef = useRef("");
  const route = useAppStore((state) => state.route);
  const isPlaying = useAppStore((state) => state.isPlaying);
  const playbackProgress = useAppStore((state) => state.playbackProgress);
  const setPlaying = useAppStore((state) => state.setPlaying);
  const setProgress = useAppStore((state) => state.setPlaybackProgress);
  const evidenceOpen = useAppStore((state) => state.evidenceOpen);
  const aoiPickerOpen = useAppStore((state) => state.aoiPickerOpen);
  const attributionOpen = useAppStore((state) => state.attributionOpen);
  const openEvidence = useAppStore((state) => state.openEvidence);
  const selectedAoiId = useAppStore((state) => state.selectedAoiId);
  const selectedOpportunityId = useAppStore((state) => state.selectedOpportunityId);
  const setAoiPickerOpen = useAppStore((state) => state.setAoiPickerOpen);
  const selectAoi = useAppStore((state) => state.selectAoi);
  const screenState = useMemo(
    () =>
      import.meta.env.VITE_NCL_TEST === "1" ? new URLSearchParams(window.location.search).get("state") : null,
    [],
  );
  const performanceMode = useMemo(() => new URLSearchParams(window.location.search).has("perf"), []);

  const installDashboard = useCallback((loaded: DashboardData, resetClock = false) => {
    dataRef.current = loaded;
    setData(loaded);
    const store = useAppStore.getState();
    const selectedOpportunity =
      loaded.opportunities.find((item) => item.id === store.selectedOpportunityId) ?? loaded.opportunities[0];
    useAppStore.setState({
      selectedAoiId: loaded.aoi.id,
      selectedOpportunityId: selectedOpportunity?.id ?? "",
      selectedSceneId: loaded.scenes.some((item) => item.id === store.selectedSceneId)
        ? store.selectedSceneId
        : (loaded.scenes[0]?.id ?? ""),
      route: loaded.scenes.length === 0 && store.route === "detail" ? "mission" : store.route,
      isPlaying: false,
      playbackProgress: selectedOpportunity
        ? passProgressForTime(selectedOpportunity, new Date(loaded.mode.clock))
        : 0,
    });
    scrubbedProgressRef.current = selectedOpportunity
      ? passProgressForTime(selectedOpportunity, new Date(loaded.mode.clock))
      : null;
    scrubbedOpportunityRef.current = selectedOpportunity?.id ?? "";
    if (resetClock || !clockRef.current) {
      const clock = createDisplayClock({ clockTime: loaded.mode.clock, playbackRate: 1 });
      clockRef.current = clock;
      setDisplayTime(clock.now());
    }
  }, []);

  const refreshAoi = useCallback(
    async (aoiId: string) => {
      const current = dataRef.current;
      if (!current) return;
      const sequence = ++refreshSequenceRef.current;
      const loaded = await reloadAoiDashboard(current, aoiId);
      if (sequence === refreshSequenceRef.current && useAppStore.getState().selectedAoiId === aoiId)
        installDashboard(loaded);
    },
    [installDashboard],
  );

  const subscribeToJob = useCallback(
    (job: Schemas["AnalysisJob"], aoiId: string) => {
      if (analysisClientsRef.current.has(job.id)) return;
      const initial: AnalysisProgress = {
        jobId: job.id,
        state: "connecting",
        message: "Connecting to the engine's durable event stream…",
        rows: { ...INITIAL_PROGRESS_ROWS },
      };
      setAnalysis((value) => value ?? initial);
      const client = new SseClient({
        url: job.events_url,
        onStatus: (status) => {
          if (status === "retrying")
            setAnalysis((value) =>
              value
                ? { ...value, message: "The progress stream is reconnecting; completed results remain safe." }
                : value,
            );
        },
        onEvent: (event) => {
          setAnalysis((value) => reduceAnalysisProgress(value ?? initial, event));
          setData((current) => {
            if (!current) return current;
            const next = mergeJobEvent(current, event);
            dataRef.current = next;
            return next;
          });
          if (event.type === "job.result") {
            const result = event.data as {
              result_type?: string;
              resource?: { id?: string; scene_id?: string };
            };
            if (
              result.result_type === "opportunity" &&
              result.resource?.id &&
              !useAppStore.getState().selectedOpportunityId
            )
              useAppStore.setState({ selectedOpportunityId: result.resource.id });
            if (
              result.result_type === "scene" &&
              result.resource?.id &&
              !useAppStore.getState().selectedSceneId
            )
              useAppStore.setState({ selectedSceneId: result.resource.id });
          }
          if (TERMINAL_JOB_EVENTS.has(event.type)) {
            client.stop();
            analysisClientsRef.current.delete(job.id);
            window.setTimeout(() => void refreshAoi(aoiId).catch(() => undefined), 250);
          }
        },
      });
      analysisClientsRef.current.set(job.id, client);
      client.start();
    },
    [refreshAoi],
  );

  useEffect(() => {
    let active = true;
    void loadDashboardData()
      .then((loaded) => {
        if (!active) return;
        installDashboard(loaded, true);
        void restoreSavedAreas(loaded).then((restored) => {
          if (!active) return;
          setData((current) => {
            if (!current) return current;
            const next = { ...current, aois: restored.aois };
            dataRef.current = next;
            return next;
          });
        });
      })
      .catch((error: unknown) => {
        if (active)
          setLoadError(error instanceof Error ? error.message : "Recorded replay could not be loaded.");
      });
    return () => {
      active = false;
    };
  }, [installDashboard]);

  useEffect(
    () => () => {
      analysisClientsRef.current.forEach((client) => client.stop());
      analysisClientsRef.current.clear();
    },
    [],
  );

  useEffect(() => {
    if (!data) return;
    data.pendingJobs.forEach((job) => subscribeToJob(job, data.aoi.id));
  }, [data, subscribeToJob]);

  useEffect(() => {
    if (import.meta.env.MODE !== "test") window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [route]);

  useEffect(() => {
    if (!data || !selectedAoiId || selectedAoiId === data.aoi.id) return;
    const target = data.aois.find((item) => item.id === selectedAoiId);
    if (!target) return;
    const shell: DashboardData = {
      ...data,
      aoi: target,
      trajectories: [],
      opportunities: [],
      opportunityMeta: emptyOpportunityMeta(data.mode.clock),
      scenes: [],
      sceneMeta: emptySceneMeta(
        data.mode.clock,
        target.replay_coverage.archive ? "searching" : "not_recorded",
      ),
      likelihood: null,
      statistics: {},
      provenance: {},
      pendingJobs: [],
    };
    dataRef.current = shell;
    setData(shell);
    useAppStore.setState({ selectedOpportunityId: "", selectedSceneId: "", route: "mission" });
    void refreshAoi(selectedAoiId).catch((error: unknown) =>
      setLoadError(error instanceof Error ? error.message : "The AOI could not be loaded."),
    );
  }, [data, refreshAoi, selectedAoiId]);

  const handleSwitchMode = useCallback(
    async (mode: "live" | "replay") => {
      setModeMessage(null);
      try {
        const currentAoi = dataRef.current?.aoi;
        await switchEngineMode(mode);
        const preferredAoi = currentAoi?.origin === "preset" ? currentAoi.id : undefined;
        let loaded: DashboardData;
        try {
          loaded =
            mode === "live" ? await loadDashboardShell(preferredAoi) : await loadDashboardData(preferredAoi);
        } catch (error) {
          if (!(error instanceof NclApiError) || error.code !== "NO_AOIS" || !currentAoi) throw error;
          const carried = await createAoiRecord(currentAoi.name, currentAoi.geometry, currentAoi.timezone);
          loaded =
            mode === "live" ? await loadDashboardShell(carried.id) : await loadDashboardData(carried.id);
        }
        setAnalysis(null);
        installDashboard(loaded, true);
      } catch (error) {
        if (error instanceof NclApiError && error.code === "LIVE_DISABLED") {
          setModeMessage(
            "Live analysis is disabled by the engine. Restart it with NCL_ALLOW_LIVE=1; recorded replay is still ready.",
          );
        } else {
          setModeMessage(error instanceof Error ? error.message : "The engine could not switch modes.");
        }
        throw error;
      }
    },
    [installDashboard],
  );

  const handleUseArea = useCallback(
    async (vertices: [number, number][]) => {
      const current = dataRef.current;
      if (!current) throw new Error("The engine is still loading.");
      const aoi = await createAoi(`Drawn area · ${new Date().toISOString().slice(11, 16)} UTC`, vertices);
      const shell: DashboardData = {
        ...current,
        aois: [...current.aois.filter((item) => item.id !== aoi.id), aoi],
        aoi,
        trajectories: [],
        opportunities: [],
        opportunityMeta: emptyOpportunityMeta(current.mode.clock),
        scenes: [],
        sceneMeta: emptySceneMeta(
          current.mode.clock,
          current.mode.mode === "live" ? "searching" : "not_recorded",
        ),
        likelihood: null,
        statistics: {},
        provenance: {},
        pendingJobs: [],
      };
      saveAoiLocally(aoi);
      installDashboard(shell);
      useAppStore.setState({
        selectedAoiId: aoi.id,
        selectedOpportunityId: "",
        selectedSceneId: "",
        route: "mission",
      });
      const job = await createAnalysisJob(aoi.id, current.mode.mode);
      subscribeToJob(job, aoi.id);
    },
    [installDashboard, subscribeToJob],
  );

  const {
    drawing,
    startDrawing,
    addDrawPoint,
    closeDrawPolygon,
    undoDrawPoint,
    cancelDrawing,
    commitDrawnArea,
  } = useAoiDrawing(handleUseArea);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!isPlaying && clockRef.current) setDisplayTime(clockRef.current.now());
    }, 500);
    return () => window.clearInterval(timer);
  }, [isPlaying]);

  useEffect(() => {
    if (!reducedMotion || !data || !clockRef.current) return;
    clockRef.current.pause();
    setDisplayTime(clockRef.current.now());
  }, [data, reducedMotion]);

  useEffect(() => {
    if (!data || isPlaying) return;
    const opportunity =
      data.opportunities.find((item) => item.id === selectedOpportunityId) ?? data.opportunities[0];
    if (!opportunity) return;
    if (
      scrubbedOpportunityRef.current === opportunity.id &&
      scrubbedProgressRef.current !== null &&
      Math.abs(scrubbedProgressRef.current - playbackProgress) < 0.0001
    )
      return;
    scrubbedOpportunityRef.current = opportunity.id;
    scrubbedProgressRef.current = playbackProgress;
    const time = passTimeForProgress(opportunity, playbackProgress);
    clockRef.current?.setTime(time.toISOString());
    clockRef.current?.pause();
    setDisplayTime(time);
  }, [data, isPlaying, playbackProgress, selectedOpportunityId]);

  useEffect(() => {
    if (!isPlaying || !data || reducedMotion) return;
    const opportunity =
      data.opportunities.find((item) => item.id === useAppStore.getState().selectedOpportunityId) ??
      data.opportunities[0];
    if (!opportunity) {
      setPlaying(false);
      return;
    }
    playStartRef.current = performance.now();
    const currentProgress = useAppStore.getState().playbackProgress;
    playProgressRef.current = currentProgress >= 1 ? 0 : currentProgress;
    scrubbedProgressRef.current = playProgressRef.current;
    clockRef.current?.setTime(passTimeForProgress(opportunity, playProgressRef.current).toISOString());
    clockRef.current?.setRate(60);
    clockRef.current?.play();
    const tick = (now: number) => {
      const next = Math.min(1, playProgressRef.current + (now - playStartRef.current) / PASS_DURATION_MS);
      scrubbedProgressRef.current = next;
      setProgress(next);
      if (clockRef.current) setDisplayTime(clockRef.current.now());
      if (next >= 1) {
        setPlaying(false);
        clockRef.current?.pause();
        return;
      }
      frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [data, isPlaying, reducedMotion, setPlaying, setProgress]);

  const setTime = useCallback((isoTime: string) => {
    clockRef.current?.setTime(isoTime);
    clockRef.current?.pause();
    const time = new Date(isoTime);
    setDisplayTime(time);
    const current = dataRef.current;
    const opportunity =
      current?.opportunities.find((item) => item.id === useAppStore.getState().selectedOpportunityId) ??
      current?.opportunities[0];
    if (opportunity) {
      const progress = passProgressForTime(opportunity, time);
      scrubbedProgressRef.current = progress;
      useAppStore.getState().setPlaybackProgress(progress);
    }
  }, []);

  useEffect(() => {
    if (import.meta.env.VITE_NCL_TEST !== "1") return;
    window.__ncl = {
      setTime,
      pause: () => {
        setPlaying(false);
        clockRef.current?.pause();
      },
    };
    return () => {
      delete window.__ncl;
    };
  }, [setPlaying, setTime]);

  useEffect(() => {
    if (!data || !globeReady) return;
    document.documentElement.dataset.nclReady = "true";
    window.dispatchEvent(new CustomEvent("ncl:ready"));
    return () => {
      delete document.documentElement.dataset.nclReady;
    };
  }, [data, globeReady]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName ?? "")) return;
      const key = event.key.toLowerCase();
      if (key === "p" && !reducedMotion) setPlaying(!useAppStore.getState().isPlaying);
      if (key === "f")
        document.querySelector<HTMLButtonElement>('[aria-label="Focus globe on AOI"]')?.click();
      if (key === "n") document.querySelector<HTMLButtonElement>('[aria-label="Set north up"]')?.click();
      if (key === "e") openEvidence("opportunity");
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [evidenceOpen, openEvidence, reducedMotion, setPlaying]);

  if (loadError)
    return (
      <div className="fatal-error" role="alert">
        <Eyebrow>Recorded replay</Eyebrow>
        <h1>Replay could not initialise</h1>
        <p>{loadError}</p>
        <button type="button" onClick={() => window.location.reload()}>
          Try again
        </button>
      </div>
    );
  if (!data) return <LoadingScreen />;
  const selectedAoi = toAoiView(data.aoi);

  return (
    <div className={`app-shell route-${route}`}>
      <a className="skip-link" href="#opportunity-summary">
        Skip to opportunity summary
      </a>
      <AppHeader
        data={data}
        displayTime={displayTime}
        onSwitchMode={handleSwitchMode}
        modeMessage={modeMessage}
      />
      {route === "mission" ? (
        <MissionScreen
          data={data}
          displayTime={displayTime}
          globeReady={globeReady}
          setGlobeReady={() => setGlobeReady(true)}
          reducedMotion={reducedMotion}
          screenState={screenState}
          analysis={analysis}
          onReplay={() => void handleSwitchMode("replay").catch(() => undefined)}
          drawing={drawing}
          onDrawPoint={addDrawPoint}
          onDrawClose={closeDrawPolygon}
          onDrawUndo={undoDrawPoint}
          onDrawCancel={cancelDrawing}
          onDrawCommit={() => void commitDrawnArea()}
        />
      ) : (
        <AOIDetail data={data} />
      )}
      {aoiPickerOpen && (
        <AOIPicker
          selectedAoi={selectedAoi}
          aois={data.aois.map(toAoiView)}
          onClose={() => setAoiPickerOpen(false)}
          onSelect={selectAoi}
          onStartDrawing={startDrawing}
        />
      )}
      {evidenceOpen && <EvidenceDrawer data={data} />}
      {attributionOpen && <AttributionPanel data={data} />}
      <PerformanceOverlay enabled={performanceMode} />
      <div className="sr-only" aria-live="polite">
        {(() => {
          const opportunity =
            data.opportunities.find((item) => item.id === selectedOpportunityId) ?? data.opportunities[0];
          return opportunity &&
            displayTime.getTime() >= Date.parse(opportunity.entry_time) &&
            displayTime.getTime() <= Date.parse(opportunity.exit_time)
            ? `Nominal swath intersects ${selectedAoi.name} at ${displayTime.toISOString()}. This is a geometric opportunity, not a confirmed acquisition.`
            : "";
        })()}
      </div>
    </div>
  );
}
