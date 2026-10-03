import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { AoiView } from "../data/dashboard-data";
import type { AoiVertex } from "../drawing/validation";
import { Icon } from "./Icon";

interface AoiPickerProps {
  selectedAoi: AoiView;
  aois: AoiView[];
  onClose: () => void;
  onSelect: (id: string) => void;
  onStartDrawing: () => void;
}

export function AOIPicker({ selectedAoi, aois, onClose, onSelect, onStartDrawing }: AoiPickerProps) {
  const [tab, setTab] = useState<"presets" | "saved" | "draw">("presets");
  const panelRef = useRef<HTMLElement>(null);
  const presets = aois.filter((aoi) => aoi.origin === "preset");
  const saved = aois.filter((aoi) => aoi.origin === "user").slice(0, 8);

  useEffect(() => {
    panelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const areaRows = (items: AoiView[]) => (
    <div className="picker-results">
      {items.map((aoi) => (
        <button
          type="button"
          data-testid={aoi.origin === "preset" ? "aoi-preset-row" : "aoi-saved-row"}
          key={aoi.id}
          className={aoi.id === selectedAoi.id ? "is-selected" : ""}
          onClick={() => {
            onSelect(aoi.id);
            onClose();
          }}
        >
          <span className="preset-map">
            <i />
          </span>
          <span>
            <b>{aoi.name}</b>
            <small>
              {aoi.locality} · {aoi.area}
            </small>
          </span>
          {aoi.id === selectedAoi.id ? (
            <span className="badge badge--opportunity">Selected</span>
          ) : (
            <em>→</em>
          )}
        </button>
      ))}
    </div>
  );

  return (
    <div className="modal-layer aoi-modal" role="presentation">
      <section
        ref={panelRef}
        tabIndex={-1}
        className="aoi-picker"
        role="dialog"
        aria-modal="true"
        aria-labelledby="aoi-picker-title"
        data-testid="aoi-picker"
      >
        <div className="drawer-heading">
          <div>
            <p className="eyebrow">Mission target</p>
            <h2 id="aoi-picker-title">Choose an area of interest</h2>
          </div>
          <button type="button" aria-label="Close AOI picker" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <div className="segmented-tabs" role="tablist">
          {(["presets", "saved", "draw"] as const).map((value) => (
            <button
              type="button"
              role="tab"
              aria-selected={tab === value}
              onClick={() => setTab(value)}
              key={value}
            >
              {value[0].toUpperCase() + value.slice(1)}
            </button>
          ))}
        </div>
        {tab === "presets" && areaRows(presets)}
        {tab === "saved" &&
          (saved.length > 0 ? (
            areaRows(saved)
          ) : (
            <div className="picker-empty">
              <Icon name="aperture" />
              <h3>No saved areas yet</h3>
              <p>Draw an area on the globe to keep up to eight boundaries in this browser.</p>
              <button type="button" onClick={() => setTab("draw")}>
                Draw area
              </button>
            </div>
          ))}
        {tab === "draw" && (
          <div className="picker-empty picker-draw-intro">
            <Icon name="aperture" />
            <h3>Draw directly on the globe</h3>
            <p>
              Place at least three points. Close the boundary with Enter, a double-click, or by choosing the
              first point.
            </p>
            <p>Coordinate entry remains available for keyboard users.</p>
            <button type="button" className="button button--primary" onClick={onStartDrawing}>
              Start polygon
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

interface AoiDrawPanelProps {
  vertices: AoiVertex[];
  closed: boolean;
  committing: boolean;
  error: string;
  onAddCoordinate: (vertex: AoiVertex) => void;
  onUndo: () => void;
  onClosePolygon: () => void;
  onCancel: () => void;
  onCommit: () => void;
}

export function AOIDrawPanel({
  vertices,
  closed,
  committing,
  error,
  onAddCoordinate,
  onUndo,
  onClosePolygon,
  onCancel,
  onCommit,
}: AoiDrawPanelProps) {
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [coordinateError, setCoordinateError] = useState("");

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
      if (event.key === "Enter" && !["INPUT", "BUTTON"].includes((event.target as HTMLElement).tagName)) {
        event.preventDefault();
        onClosePolygon();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onCancel, onClosePolygon]);

  const addCoordinate = (event: FormEvent) => {
    event.preventDefault();
    const nextLatitude = Number(latitude);
    const nextLongitude = Number(longitude);
    if (
      !Number.isFinite(nextLatitude) ||
      nextLatitude < -90 ||
      nextLatitude > 90 ||
      !Number.isFinite(nextLongitude) ||
      nextLongitude < -180 ||
      nextLongitude > 180
    ) {
      setCoordinateError("Enter a latitude from −90 to 90 and longitude from −180 to 180.");
      return;
    }
    onAddCoordinate([nextLongitude, nextLatitude]);
    setLatitude("");
    setLongitude("");
    setCoordinateError("");
  };

  return (
    <aside className="aoi-draw-controls" data-testid="aoi-draw-panel" aria-label="Draw an area of interest">
      <div className="aoi-draw-controls__heading">
        <div>
          <p className="eyebrow">Area boundary</p>
          <h2>Draw on the globe</h2>
        </div>
        <button type="button" aria-label="Cancel drawing" onClick={onCancel}>
          <Icon name="close" />
        </button>
      </div>
      <p className="draw-instruction">
        {closed
          ? "Boundary closed. Use this area to validate it with the engine."
          : "Click or tap the globe to place points. Double-click, press Enter, or choose the first point to close."}
      </p>
      <div className="draw-status" aria-live="polite">
        <b data-testid="draw-vertex-count">{vertices.length}</b>
        <span>{vertices.length === 1 ? "point" : "points"}</span>
        <em>{closed ? "Closed" : "Drawing"}</em>
      </div>
      <form className="coordinate-entry" onSubmit={addCoordinate}>
        <p className="eyebrow">Keyboard coordinate entry</p>
        <label>
          Latitude
          <input
            inputMode="decimal"
            value={latitude}
            onChange={(event) => setLatitude(event.currentTarget.value)}
            placeholder="1.3000"
          />
        </label>
        <label>
          Longitude
          <input
            inputMode="decimal"
            value={longitude}
            onChange={(event) => setLongitude(event.currentTarget.value)}
            placeholder="103.6950"
          />
        </label>
        <button type="submit" className="button button--secondary">
          Add coordinate
        </button>
      </form>
      {coordinateError && (
        <p className="validation-message" role="alert">
          {coordinateError}
        </p>
      )}
      <ol className="draw-vertex-list">
        {vertices.map(([vertexLongitude, vertexLatitude], index) => (
          <li key={`${vertexLongitude}-${vertexLatitude}-${index}`}>
            <span>{index + 1}</span>
            <code>
              {vertexLatitude.toFixed(5)}°, {vertexLongitude.toFixed(5)}°
            </code>
          </li>
        ))}
      </ol>
      {error && (
        <p className="validation-message" role="alert">
          {error}
        </p>
      )}
      <p className="local-note">
        Up to eight accepted boundaries are stored in this browser. Geometry validation and analysis run in
        the engine.
      </p>
      <div className="dialog-actions">
        <button
          type="button"
          className="button button--quiet"
          disabled={vertices.length === 0 || committing}
          onClick={onUndo}
        >
          Undo point
        </button>
        <button
          type="button"
          className="button button--secondary"
          disabled={vertices.length < 3 || closed || committing}
          onClick={onClosePolygon}
        >
          Close polygon
        </button>
        <button
          type="button"
          className="button button--primary"
          data-testid="use-drawn-aoi"
          disabled={vertices.length < 3 || committing}
          onClick={onCommit}
        >
          {committing ? "Validating area…" : "Use this area"}
        </button>
      </div>
    </aside>
  );
}
