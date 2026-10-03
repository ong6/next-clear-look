import { beforeEach, describe, expect, it } from "vitest";
import exampleAoi from "../../../contracts/examples/aoi.json";
import type { DashboardAoi } from "../../src/data/dashboard-data";
import { readSavedAois, saveAoiLocally } from "../../src/drawing/saved-aois";

describe("saved drawn areas", () => {
  beforeEach(() => window.localStorage.clear());

  it("keeps the eight most recently accepted boundaries", () => {
    for (let index = 0; index < 9; index += 1) {
      saveAoiLocally({
        ...(exampleAoi as DashboardAoi),
        id: `drawn-${index}`,
        name: `Drawn area ${index}`,
        origin: "user",
        preset: null,
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [103.6 + index / 100, 1.2],
              [103.7 + index / 100, 1.2],
              [103.7 + index / 100, 1.3],
              [103.6 + index / 100, 1.2],
            ],
          ],
        },
      });
    }

    const saved = readSavedAois();
    expect(saved).toHaveLength(8);
    expect(saved[0].id).toBe("drawn-8");
    expect(saved.some((record) => record.id === "drawn-0")).toBe(false);
  });
});
