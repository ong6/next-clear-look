import { describe, expect, it } from "vitest";
import { createDisplayClock, formatCountdown, formatMissionOffset } from "../../src/time/display-clock";

describe("display clock", () => {
  it("advances the mode clock from monotonic elapsed time at playback rate", () => {
    let monotonic = 1_000;
    const clock = createDisplayClock({
      clockTime: "2026-10-03T04:00:00.000Z",
      playbackRate: 4,
      monotonicNow: () => monotonic,
    });

    monotonic += 2_500;
    expect(clock.now().toISOString()).toBe("2026-10-03T04:00:10.000Z");
  });

  it("pauses, scrubs, and resumes without changing while paused", () => {
    let monotonic = 5_000;
    const clock = createDisplayClock({
      clockTime: "2026-10-03T04:00:00.000Z",
      playbackRate: 1,
      monotonicNow: () => monotonic,
    });

    clock.pause();
    monotonic += 8_000;
    expect(clock.now().toISOString()).toBe("2026-10-03T04:00:00.000Z");
    clock.setTime("2026-10-03T06:18:00.000Z");
    clock.play();
    monotonic += 2_000;
    expect(clock.now().toISOString()).toBe("2026-10-03T06:18:02.000Z");
  });

  it("uses one floor-based HH:MM:SS value for countdown and mission offset", () => {
    const from = new Date("2026-10-03T01:20:09.900Z");
    const closest = "2026-10-03T03:20:05.500Z";

    expect(formatCountdown(from, closest)).toBe("01:59:55");
    expect(formatMissionOffset(from, closest)).toBe("T−01:59:55");
    expect(formatMissionOffset(new Date("2026-10-03T00:00:00.250Z"), "2026-10-03T11:11:50.900Z")).toBe(
      "T−11:11:50",
    );
    expect(formatMissionOffset(new Date("2026-10-03T03:21:06.900Z"), closest)).toBe("T+00:01:01");
  });
});
