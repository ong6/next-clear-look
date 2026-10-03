import { create } from "zustand";

export type LayerKey = "tracks" | "swath" | "aoi" | "dayNight" | "sceneDrape";
export type EvidenceClaim = "opportunity" | "likelihood" | "scene" | "accounting";
export type AppRoute = "mission" | "detail";

export interface AppState {
  route: AppRoute;
  selectedAoiId: string;
  selectedSceneId: string;
  selectedOpportunityId: string;
  isPlaying: boolean;
  playbackProgress: number;
  evidenceOpen: boolean;
  evidenceClaim: EvidenceClaim;
  evidenceReturnFocus: HTMLElement | null;
  aoiPickerOpen: boolean;
  attributionOpen: boolean;
  layers: Record<LayerKey, boolean>;
  setRoute: (route: AppRoute) => void;
  selectAoi: (id: string) => void;
  selectScene: (id: string) => void;
  selectOpportunity: (id: string) => void;
  setPlaying: (playing: boolean) => void;
  setPlaybackProgress: (progress: number) => void;
  openEvidence: (claim?: EvidenceClaim) => void;
  closeEvidence: () => void;
  setAoiPickerOpen: (open: boolean) => void;
  setAttributionOpen: (open: boolean) => void;
  toggleLayer: (layer: LayerKey) => void;
}

export const initialAppState = {
  route: "mission" as const,
  selectedAoiId: "",
  selectedSceneId: "",
  selectedOpportunityId: "",
  isPlaying: false,
  playbackProgress: 0.42,
  evidenceOpen: false,
  evidenceClaim: "opportunity" as const,
  evidenceReturnFocus: null,
  aoiPickerOpen: false,
  attributionOpen: false,
  layers: { tracks: true, swath: true, aoi: true, dayNight: true, sceneDrape: true },
};

export const useAppStore = create<AppState>((set) => ({
  ...initialAppState,
  setRoute: (route) => set({ route }),
  selectAoi: (selectedAoiId) => set({ selectedAoiId }),
  selectScene: (selectedSceneId) => set({ selectedSceneId }),
  selectOpportunity: (selectedOpportunityId) => set({ selectedOpportunityId }),
  setPlaying: (isPlaying) => set({ isPlaying }),
  setPlaybackProgress: (playbackProgress) =>
    set({ playbackProgress: Math.min(1, Math.max(0, playbackProgress)) }),
  openEvidence: (evidenceClaim = "opportunity") =>
    set({
      evidenceOpen: true,
      evidenceClaim,
      evidenceReturnFocus: document.activeElement instanceof HTMLElement ? document.activeElement : null,
    }),
  closeEvidence: () => set({ evidenceOpen: false }),
  setAoiPickerOpen: (aoiPickerOpen) => set({ aoiPickerOpen }),
  setAttributionOpen: (attributionOpen) => set({ attributionOpen }),
  toggleLayer: (layer) => set((state) => ({ layers: { ...state.layers, [layer]: !state.layers[layer] } })),
}));
