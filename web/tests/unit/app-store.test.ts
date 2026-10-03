import { beforeEach, describe, expect, it } from "vitest";
import { initialAppState, useAppStore } from "../../src/state/app-store";

describe("app store", () => {
  beforeEach(() => useAppStore.setState(initialAppState));

  it("coordinates AOI, scene, opportunity and evidence selections", () => {
    const state = useAppStore.getState();
    state.selectAoi("aoi_sg_tuas_coast");
    state.selectScene("S2C_48NUG_20261001_0_L2A");
    state.selectOpportunity("opp_s2c_tuas_1");
    state.openEvidence("likelihood");

    expect(useAppStore.getState()).toMatchObject({
      selectedAoiId: "aoi_sg_tuas_coast",
      selectedSceneId: "S2C_48NUG_20261001_0_L2A",
      selectedOpportunityId: "opp_s2c_tuas_1",
      evidenceOpen: true,
      evidenceClaim: "likelihood",
    });
  });

  it("keeps replay playback and layer state client-only", () => {
    const state = useAppStore.getState();
    state.setPlaying(true);
    state.setPlaybackProgress(0.5);
    state.toggleLayer("swath");

    expect(useAppStore.getState().isPlaying).toBe(true);
    expect(useAppStore.getState().playbackProgress).toBe(0.5);
    expect(useAppStore.getState().layers.swath).toBe(false);
  });
});
