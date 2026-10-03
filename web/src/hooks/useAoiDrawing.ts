import { useCallback, useState } from "react";
import type { AoiVertex } from "../drawing/validation";
import { drawingErrorMessage, validateVertices } from "../drawing/validation";
import { useAppStore } from "../state/app-store";

export interface DrawingState {
  active: boolean;
  closed: boolean;
  vertices: AoiVertex[];
  committing: boolean;
  error: string;
}

const EMPTY_DRAWING: DrawingState = {
  active: false,
  closed: false,
  vertices: [],
  committing: false,
  error: "",
};

export function useAoiDrawing(onCommit: (vertices: AoiVertex[]) => Promise<void>) {
  const [drawing, setDrawing] = useState<DrawingState>(EMPTY_DRAWING);
  const setAoiPickerOpen = useAppStore((state) => state.setAoiPickerOpen);

  const startDrawing = useCallback(() => {
    setAoiPickerOpen(false);
    useAppStore.getState().setRoute("mission");
    setDrawing({ ...EMPTY_DRAWING, active: true });
  }, [setAoiPickerOpen]);

  const addDrawPoint = useCallback((vertex: AoiVertex) => {
    setDrawing((current) => {
      if (!current.active || current.closed) return current;
      const duplicate = current.vertices.some(
        ([longitude, latitude]) =>
          Math.abs(longitude - vertex[0]) < 1e-9 && Math.abs(latitude - vertex[1]) < 1e-9,
      );
      return duplicate ? current : { ...current, vertices: [...current.vertices, vertex], error: "" };
    });
  }, []);

  const closeDrawPolygon = useCallback(() => {
    setDrawing((current) => {
      const error = validateVertices(current.vertices);
      return error ? { ...current, error } : { ...current, closed: true, error: "" };
    });
  }, []);

  const undoDrawPoint = useCallback(() => {
    setDrawing((current) => ({
      ...current,
      closed: false,
      vertices: current.vertices.slice(0, -1),
      error: "",
    }));
  }, []);

  const cancelDrawing = useCallback(() => setDrawing(EMPTY_DRAWING), []);

  const commitDrawnArea = useCallback(async () => {
    const error = validateVertices(drawing.vertices);
    if (error) {
      setDrawing((current) => ({ ...current, error }));
      return;
    }
    setDrawing((current) => ({ ...current, closed: true, committing: true, error: "" }));
    try {
      await onCommit(drawing.vertices);
      setDrawing(EMPTY_DRAWING);
    } catch (caught) {
      setDrawing((current) => ({
        ...current,
        committing: false,
        error: drawingErrorMessage(caught),
      }));
    }
  }, [drawing.vertices, onCommit]);

  return {
    drawing,
    startDrawing,
    addDrawPoint,
    closeDrawPolygon,
    undoDrawPoint,
    cancelDrawing,
    commitDrawnArea,
  };
}
