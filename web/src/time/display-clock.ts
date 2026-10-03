export interface DisplayClockOptions {
  clockTime: string;
  playbackRate: number;
  monotonicNow?: () => number;
}

export interface DisplayClock {
  now: () => Date;
  pause: () => void;
  play: () => void;
  setTime: (isoTime: string) => void;
  setRate: (rate: number) => void;
  isPaused: () => boolean;
}

export function createDisplayClock({
  clockTime,
  playbackRate,
  monotonicNow = () => performance.now(),
}: DisplayClockOptions): DisplayClock {
  let anchorWall = Date.parse(clockTime);
  let anchorMonotonic = monotonicNow();
  let rate = playbackRate;
  let paused = false;

  const currentMilliseconds = () =>
    paused ? anchorWall : anchorWall + (monotonicNow() - anchorMonotonic) * rate;

  const reanchor = (milliseconds: number) => {
    anchorWall = milliseconds;
    anchorMonotonic = monotonicNow();
  };

  return {
    now: () => new Date(currentMilliseconds()),
    pause: () => {
      if (!paused) {
        reanchor(currentMilliseconds());
        paused = true;
      }
    },
    play: () => {
      if (paused) {
        anchorMonotonic = monotonicNow();
        paused = false;
      }
    },
    setTime: (isoTime) => reanchor(Date.parse(isoTime)),
    setRate: (nextRate) => {
      reanchor(currentMilliseconds());
      rate = Math.max(0, nextRate);
    },
    isPaused: () => paused,
  };
}

export function formatDisplayClock(date: Date): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  })
    .format(date)
    .replace(",", " ·")
    .toUpperCase()
    .concat(" UTC");
}

export function formatCountdown(from: Date, to: string): string {
  const seconds = Math.max(0, Math.floor((Date.parse(to) - from.getTime()) / 1_000));
  const hours = Math.floor(seconds / 3_600)
    .toString()
    .padStart(2, "0");
  const minutes = Math.floor((seconds % 3_600) / 60)
    .toString()
    .padStart(2, "0");
  const remainder = (seconds % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}:${remainder}`;
}

export function formatMissionOffset(from: Date, to: string): string {
  const delta = Date.parse(to) - from.getTime();
  if (delta >= 0) return `T−${formatCountdown(from, to)}`;
  const seconds = Math.floor(Math.abs(delta) / 1_000);
  const hours = Math.floor(seconds / 3_600)
    .toString()
    .padStart(2, "0");
  const minutes = Math.floor((seconds % 3_600) / 60)
    .toString()
    .padStart(2, "0");
  const remainder = (seconds % 60).toString().padStart(2, "0");
  return `T+${hours}:${minutes}:${remainder}`;
}
