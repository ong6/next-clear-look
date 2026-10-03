import type { DashboardAoi, Schemas } from "../data/dashboard-data";

const STORAGE_KEY = "next-clear-look.saved-areas.v1";
const MAX_SAVED_AREAS = 8;

export interface SavedAoiRecord {
  id: string;
  name: string;
  geometry: Schemas["GeoJsonGeometry"];
  timezone: string;
  savedAt: string;
}

function isSavedAoiRecord(value: unknown): value is SavedAoiRecord {
  if (!value || typeof value !== "object") return false;
  const record = value as Partial<SavedAoiRecord>;
  return (
    typeof record.id === "string" &&
    typeof record.name === "string" &&
    typeof record.timezone === "string" &&
    typeof record.savedAt === "string" &&
    typeof record.geometry === "object" &&
    record.geometry !== null &&
    (record.geometry.type === "Polygon" || record.geometry.type === "MultiPolygon")
  );
}

export function readSavedAois(storage: Storage = window.localStorage): SavedAoiRecord[] {
  try {
    const value: unknown = JSON.parse(storage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter(isSavedAoiRecord).slice(0, MAX_SAVED_AREAS) : [];
  } catch {
    return [];
  }
}

export function writeSavedAois(records: SavedAoiRecord[], storage: Storage = window.localStorage): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(records.slice(0, MAX_SAVED_AREAS)));
}

export function saveAoiLocally(aoi: DashboardAoi, storage: Storage = window.localStorage): SavedAoiRecord[] {
  const saved: SavedAoiRecord = {
    id: aoi.id,
    name: aoi.name,
    geometry: aoi.geometry,
    timezone: aoi.timezone,
    savedAt: aoi.updated_at,
  };
  const next = [
    saved,
    ...readSavedAois(storage).filter(
      (record) => record.id !== aoi.id && JSON.stringify(record.geometry) !== JSON.stringify(aoi.geometry),
    ),
  ].slice(0, MAX_SAVED_AREAS);
  writeSavedAois(next, storage);
  return next;
}

export function replaceSavedAoiId(
  previousId: string,
  aoi: DashboardAoi,
  storage: Storage = window.localStorage,
): void {
  const records = readSavedAois(storage).map((record) =>
    record.id === previousId
      ? {
          ...record,
          id: aoi.id,
          name: aoi.name,
          geometry: aoi.geometry,
          timezone: aoi.timezone,
          savedAt: aoi.updated_at,
        }
      : record,
  );
  writeSavedAois(records, storage);
}

export const savedAoiStorageKey = STORAGE_KEY;
