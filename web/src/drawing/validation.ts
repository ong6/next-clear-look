import { NclApiError } from "../api/client";

export type AoiVertex = [longitude: number, latitude: number];

export function validateVertices(vertices: AoiVertex[]): string | null {
  const finite = vertices.every(
    ([longitude, latitude]) =>
      Number.isFinite(longitude) &&
      Number.isFinite(latitude) &&
      longitude >= -180 &&
      longitude <= 180 &&
      latitude >= -90 &&
      latitude <= 90,
  );
  if (!finite) return "Every coordinate needs a longitude from −180 to 180 and a latitude from −90 to 90.";

  const distinct = new Set(
    vertices.map(([longitude, latitude]) => `${longitude.toFixed(9)},${latitude.toFixed(9)}`),
  );
  if (distinct.size < 3) return "Add at least three distinct points.";
  if (vertices.length > 9_999) return "This polygon has too many points. Use fewer than 10,000 vertices.";
  return null;
}

export function drawingErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : "The engine could not create this area.";
  if (/self[- ]?intersection|self[- ]?intersect|ring self/i.test(message)) {
    return "The polygon crosses itself. Undo a point and redraw the boundary without crossing lines.";
  }
  if (/outside the supported range|250.?000|area .* supported/i.test(message)) {
    return "This polygon is outside the supported size range. Draw an area no larger than 250,000 km².";
  }
  if (/at least three|too few|linear ring/i.test(message)) return "Add at least three distinct points.";
  if (/vertices|coordinate/i.test(message)) return message;
  if (error instanceof NclApiError && error.code === "VALIDATION_ERROR") {
    return `The engine rejected this boundary: ${message}`;
  }
  return message;
}
