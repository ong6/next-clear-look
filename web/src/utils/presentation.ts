import type { DashboardData, Schemas } from "../data/dashboard-data";
import { formatCountdown } from "../time/display-clock";

export function formatUtc(isoTime: string, includeYear = false): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    ...(includeYear ? { year: "numeric" as const } : {}),
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    hour12: false,
  })
    .format(new Date(isoTime))
    .replace(",", " ·")
    .concat(" UTC");
}

export function passTimeForProgress(opportunity: Schemas["Opportunity"], progress: number): Date {
  const centre = Date.parse(opportunity.closest_time);
  return new Date(centre + (Math.min(1, Math.max(0, progress)) - 0.5) * 12 * 60_000);
}

export function passProgressForTime(opportunity: Schemas["Opportunity"], time: Date): number {
  return Math.min(
    1,
    Math.max(0, 0.5 + (time.getTime() - Date.parse(opportunity.closest_time)) / (12 * 60_000)),
  );
}

export function formatElementEpochOffset(seconds: number): string {
  const hours = Math.round(Math.abs(seconds) / 3_600);
  return seconds >= 0 ? `${hours} h old elements` : `Elements published ${hours} h after pass (hindcast)`;
}

export function formatLikelihoodPercent(probability: number | null): string {
  return probability === null ? "—" : `${Math.round(probability * 100)}%`;
}

export function opportunityForTime(
  data: DashboardData,
  selectedId: string,
  displayTime: Date,
): Schemas["Opportunity"] | null {
  const selected = data.opportunities.find((item) => item.id === selectedId);
  if (selected && displayTime.getTime() <= Date.parse(selected.exit_time)) return selected;
  return data.opportunities.find((item) => displayTime.getTime() <= Date.parse(item.exit_time)) ?? null;
}

export function formatElapsed(from: string, to: Date): string {
  const seconds = Math.max(0, Math.floor((to.getTime() - Date.parse(from)) / 1_000));
  const minutes = Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0");
  return `${minutes}:${(seconds % 60).toString().padStart(2, "0")}`;
}

export function countdownParts(displayTime: Date, opportunity: Schemas["Opportunity"]): string[] {
  const inSwath =
    displayTime.getTime() >= Date.parse(opportunity.entry_time) &&
    displayTime.getTime() <= Date.parse(opportunity.exit_time);
  return (
    inSwath
      ? `00:${formatElapsed(opportunity.entry_time, displayTime)}`
      : formatCountdown(displayTime, opportunity.closest_time)
  ).split(":");
}
