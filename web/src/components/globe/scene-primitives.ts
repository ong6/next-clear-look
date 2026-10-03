import type { Cartesian3, Entity, Primitive, SampledPositionProperty } from "cesium";
import type { AoiView, DashboardTrajectory } from "../../data/dashboard-data";
import type { AoiVertex } from "../../drawing/validation";

export const loadCesium = () => import("cesium");
export type CesiumModule = Awaited<ReturnType<typeof loadCesium>>;

export const EOX_TEMPLATE =
  "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg";
const EOX_PROBE_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/1/0/1.jpg";
let eoxReachability: Promise<boolean> | null = null;

export function probeEox(): Promise<boolean> {
  if (eoxReachability) return eoxReachability;
  eoxReachability = new Promise((resolve) => {
    if (!navigator.onLine) {
      resolve(false);
      return;
    }
    const image = new Image();
    const timeout = window.setTimeout(() => resolve(false), 5_000);
    const finish = (reachable: boolean) => {
      window.clearTimeout(timeout);
      image.onload = null;
      image.onerror = null;
      resolve(reachable);
    };
    image.onload = () => finish(true);
    image.onerror = () => finish(false);
    image.referrerPolicy = "no-referrer";
    image.src = EOX_PROBE_URL;
  });
  return eoxReachability;
}

export interface SpacecraftVisual {
  entity: Entity;
  position: SampledPositionProperty;
  satelliteId: string;
  selected: boolean;
}

export const SATELLITE_CODES: Record<string, string> = {
  "sentinel-2a": "2A",
  "sentinel-2b": "2B",
  "sentinel-2c": "2C",
};

export const PRESET_IMAGERY: Record<
  string,
  { url: string; rectangle: readonly [number, number, number, number] }
> = {
  "singapore-coast": {
    url: "/imagery/presets/singapore-coast-200410.jpg",
    rectangle: [93.695, -8.7, 113.695, 11.3],
  },
  "rotterdam-port": {
    url: "/imagery/presets/rotterdam-port-200410.jpg",
    rectangle: [-5.96, 41.935, 14.04, 61.935],
  },
  "atacama-works": {
    url: "/imagery/presets/atacama-works-200410.jpg",
    rectangle: [-78.235, -33.52, -58.235, -13.52],
  },
  "sundarbans-delta": {
    url: "/imagery/presets/sundarbans-delta-200410.jpg",
    rectangle: [79.425, 11.85, 99.425, 31.85],
  },
  "jakobshavn-front": {
    url: "/imagery/presets/jakobshavn-front-200410.jpg",
    rectangle: [-60.675, 59.2, -40.675, 79.2],
  },
  "jakobshavn-ice-front": {
    url: "/imagery/presets/jakobshavn-front-200410.jpg",
    rectangle: [-60.675, 59.2, -40.675, 79.2],
  },
};

export function satelliteSvg(color: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="12" viewBox="0 0 18 12"><g fill="none" stroke="${color}" stroke-width="1.25" stroke-linejoin="round"><path d="m6.5 6 2.5-3 2.5 3L9 9 6.5 6Z" fill="${color}" fill-opacity=".28"/><path d="M1 3.5 6.5 6 1 8.5v-5Zm16 0L11.5 6 17 8.5v-5Z"/></g></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function bearingDegrees(
  from: { latitude: number; longitude: number },
  to: { latitude: number; longitude: number },
): number {
  const phi1 = (from.latitude * Math.PI) / 180;
  const phi2 = (to.latitude * Math.PI) / 180;
  const deltaLongitude = ((to.longitude - from.longitude) * Math.PI) / 180;
  const y = Math.sin(deltaLongitude) * Math.cos(phi2);
  const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(deltaLongitude);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

export function incomingBearing(
  trajectory: DashboardTrajectory | undefined,
  closestTime: string | undefined,
): number {
  if (!trajectory || trajectory.samples.length < 2) return 12;
  const target = Date.parse(closestTime ?? trajectory.start_time);
  let upper = trajectory.samples.findIndex((sample) => Date.parse(sample.time) >= target);
  if (upper <= 0) upper = 1;
  if (upper >= trajectory.samples.length) upper = trajectory.samples.length - 1;
  const track = bearingDegrees(trajectory.samples[upper - 1], trajectory.samples[upper]);
  return (track + 180) % 360;
}

export function interpolateSample(trajectory: DashboardTrajectory, milliseconds: number) {
  const samples = trajectory.samples;
  if (samples.length === 0) return null;
  if (milliseconds <= Date.parse(samples[0].time)) return samples[0];
  if (milliseconds >= Date.parse(samples[samples.length - 1].time)) return samples[samples.length - 1];
  let upperIndex = samples.findIndex((sample) => Date.parse(sample.time) >= milliseconds);
  if (upperIndex <= 0) upperIndex = 1;
  const lower = samples[upperIndex - 1];
  const upper = samples[upperIndex];
  const lowerTime = Date.parse(lower.time);
  const fraction = (milliseconds - lowerTime) / (Date.parse(upper.time) - lowerTime);
  const mix = (start: number, end: number) => start + (end - start) * fraction;
  return {
    time: new Date(milliseconds).toISOString(),
    longitude: mix(lower.longitude, upper.longitude),
    latitude: mix(lower.latitude, upper.latitude),
    altitude_m: mix(lower.altitude_m, upper.altitude_m),
    swath_left: [
      mix(lower.swath_left[0], upper.swath_left[0]),
      mix(lower.swath_left[1], upper.swath_left[1]),
    ] as [number, number],
    swath_right: [
      mix(lower.swath_right[0], upper.swath_right[0]),
      mix(lower.swath_right[1], upper.swath_right[1]),
    ] as [number, number],
  };
}

export function createPositionProperty(
  Cesium: CesiumModule,
  trajectory: DashboardTrajectory,
): SampledPositionProperty {
  const property = new Cesium.SampledPositionProperty();
  trajectory.samples.forEach((sample) => {
    property.addSample(
      Cesium.JulianDate.fromIso8601(sample.time),
      Cesium.Cartesian3.fromDegrees(sample.longitude, sample.latitude, sample.altitude_m),
    );
  });
  property.setInterpolationOptions({
    interpolationDegree: trajectory.samples.length >= 6 ? 5 : 1,
    interpolationAlgorithm:
      trajectory.samples.length >= 6 ? Cesium.LagrangePolynomialApproximation : Cesium.LinearApproximation,
  });
  return property;
}

export function createAperturePrimitive(Cesium: CesiumModule): Primitive {
  const segments = 24;
  const positions = [0, 0, 1];
  const normals = [0, -1, 0];
  const textureCoordinates = [0.5, 0];
  for (let index = 0; index <= segments; index += 1) {
    positions.push(-1 + (index * 2) / segments, 0, 0);
    normals.push(0, -1, 0);
    textureCoordinates.push(index / segments, 1);
  }
  const indices: number[] = [];
  for (let index = 0; index < segments; index += 1) indices.push(0, index + 1, index + 2);
  const attributes = new Cesium.GeometryAttributes();
  attributes.position = new Cesium.GeometryAttribute({
    componentDatatype: Cesium.ComponentDatatype.DOUBLE,
    componentsPerAttribute: 3,
    values: new Float64Array(positions),
  });
  attributes.normal = new Cesium.GeometryAttribute({
    componentDatatype: Cesium.ComponentDatatype.FLOAT,
    componentsPerAttribute: 3,
    values: new Float32Array(normals),
  });
  attributes.st = new Cesium.GeometryAttribute({
    componentDatatype: Cesium.ComponentDatatype.FLOAT,
    componentsPerAttribute: 2,
    values: new Float32Array(textureCoordinates),
  });
  const geometry = new Cesium.Geometry({
    attributes,
    indices: new Uint16Array(indices),
    primitiveType: Cesium.PrimitiveType.TRIANGLES,
    boundingSphere: new Cesium.BoundingSphere(Cesium.Cartesian3.ZERO, 2),
  });
  const material = new Cesium.Material({
    fabric: {
      type: "NclApertureSheet",
      source: `
        czm_material czm_getMaterial(czm_materialInput materialInput) {
          czm_material material = czm_getDefaultMaterial(materialInput);
          float s = materialInput.st.s;
          float facing = abs(dot(normalize(materialInput.normalEC), normalize(materialInput.positionToEyeEC)));
          float edgeOn = clamp(1.0 / max(facing, 0.2), 1.0, 5.0);
          float outerFivePercent = smoothstep(0.9, 1.0, abs(2.0 * s - 1.0));
          float alpha = (0.12 + 0.38 * outerFivePercent) * edgeOn;
          material.diffuse = vec3(0.929, 0.965, 0.973);
          material.emission = material.diffuse * 0.62;
          material.alpha = clamp(alpha, 0.0, 0.9);
          return material;
        }
      `,
    },
    translucent: true,
  });
  const additiveBlending = Cesium.BlendingState.ADDITIVE_BLEND as unknown as { enabled: boolean };
  return new Cesium.Primitive({
    geometryInstances: new Cesium.GeometryInstance({ geometry }),
    appearance: new Cesium.MaterialAppearance({
      material,
      translucent: true,
      closed: false,
      faceForward: true,
      flat: false,
      renderState: {
        depthMask: false,
        blending: additiveBlending,
        cull: { enabled: false },
      },
    }),
    asynchronous: false,
    modelMatrix: Cesium.Matrix4.clone(Cesium.Matrix4.IDENTITY),
  });
}

export function createSwathPrimitive(Cesium: CesiumModule, trajectory: DashboardTrajectory): Primitive {
  const positions: number[] = [];
  const normals: number[] = [];
  const textureCoordinates: number[] = [];
  let alongTrackMeters = 0;
  let previousCentre: Cartesian3 | null = null;
  trajectory.samples.forEach((sample) => {
    const left = Cesium.Cartesian3.fromDegrees(sample.swath_left[0], sample.swath_left[1], 1_800);
    const right = Cesium.Cartesian3.fromDegrees(sample.swath_right[0], sample.swath_right[1], 1_800);
    const centre = Cesium.Cartesian3.midpoint(left, right, new Cesium.Cartesian3());
    if (previousCentre) alongTrackMeters += Cesium.Cartesian3.distance(previousCentre, centre);
    previousCentre = centre;
    const crossTrackPeriods = Cesium.Cartesian3.distance(left, right) / 8_000;
    const alongTrackPeriods = alongTrackMeters / 8_000;
    [sample.swath_left, sample.swath_right].forEach((point, side) => {
      const position = Cesium.Cartesian3.fromDegrees(point[0], point[1], 1_800);
      const normal = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal(position, new Cesium.Cartesian3());
      positions.push(position.x, position.y, position.z);
      normals.push(normal.x, normal.y, normal.z);
      textureCoordinates.push(side * crossTrackPeriods, alongTrackPeriods);
    });
  });
  const indices: number[] = [];
  for (let index = 0; index < trajectory.samples.length - 1; index += 1) {
    const left = index * 2;
    indices.push(left, left + 1, left + 2, left + 1, left + 3, left + 2);
  }
  const material = new Cesium.Material({
    fabric: {
      type: "NclSweptSwath",
      uniforms: { progress: 0, maxAlong: alongTrackMeters / 8_000 },
      source: `
        uniform float progress;
        uniform float maxAlong;
        czm_material czm_getMaterial(czm_materialInput materialInput) {
          czm_material material = czm_getDefaultMaterial(materialInput);
          float swept = 1.0 - step(progress * maxAlong + 0.002, materialInput.st.t);
          float hatchWave = sin((materialInput.st.s + materialInput.st.t) * 6.2831853);
          float hatch = smoothstep(0.72, 0.92, hatchWave);
          material.diffuse = vec3(0.929, 0.965, 0.973);
          material.alpha = swept * mix(0.16, 0.24, hatch);
          return material;
        }
      `,
    },
    translucent: true,
  });
  const attributes = new Cesium.GeometryAttributes();
  attributes.position = new Cesium.GeometryAttribute({
    componentDatatype: Cesium.ComponentDatatype.DOUBLE,
    componentsPerAttribute: 3,
    values: new Float64Array(positions),
  });
  attributes.normal = new Cesium.GeometryAttribute({
    componentDatatype: Cesium.ComponentDatatype.FLOAT,
    componentsPerAttribute: 3,
    values: new Float32Array(normals),
  });
  attributes.st = new Cesium.GeometryAttribute({
    componentDatatype: Cesium.ComponentDatatype.FLOAT,
    componentsPerAttribute: 2,
    values: new Float32Array(textureCoordinates),
  });
  const geometry = new Cesium.Geometry({
    attributes,
    indices: new Uint16Array(indices),
    primitiveType: Cesium.PrimitiveType.TRIANGLES,
    boundingSphere: Cesium.BoundingSphere.fromVertices(positions),
  });
  return new Cesium.Primitive({
    geometryInstances: new Cesium.GeometryInstance({ geometry }),
    appearance: new Cesium.MaterialAppearance({
      material,
      translucent: true,
      closed: false,
      faceForward: true,
    }),
    asynchronous: false,
  });
}

export function createOrbitPrimitive(
  Cesium: CesiumModule,
  trajectory: DashboardTrajectory,
  selected: boolean,
): Primitive {
  const positions = trajectory.samples.map((sample) =>
    Cesium.Cartesian3.fromDegrees(sample.longitude, sample.latitude, sample.altitude_m),
  );
  const color = Cesium.Color.fromCssColorString(selected ? "#ffd39a" : "#edf6f8");
  const last = Math.max(1, trajectory.samples.length - 1);
  const colors = trajectory.samples.map((_, index) => {
    const fraction = index / last;
    const edgeFade = Math.min(1, fraction / 0.12, (1 - fraction) / 0.12);
    return color.withAlpha((selected ? 0.88 : 0.22) * Math.max(0, edgeFade));
  });
  const geometry = new Cesium.PolylineGeometry({
    positions,
    width: selected ? 1.5 : 1,
    colors,
    colorsPerVertex: true,
    arcType: Cesium.ArcType.NONE,
    vertexFormat: Cesium.PolylineColorAppearance.VERTEX_FORMAT,
  });
  return new Cesium.Primitive({
    geometryInstances: new Cesium.GeometryInstance({ geometry }),
    appearance: new Cesium.PolylineColorAppearance({ translucent: true }),
    asynchronous: false,
  });
}

export function setApertureMatrix(
  Cesium: CesiumModule,
  primitive: Primitive,
  spacecraft: Cartesian3,
  left: Cartesian3,
  right: Cartesian3,
) {
  const baseCentre = Cesium.Cartesian3.midpoint(left, right, new Cesium.Cartesian3());
  const x = Cesium.Cartesian3.multiplyByScalar(
    Cesium.Cartesian3.subtract(right, left, new Cesium.Cartesian3()),
    0.5,
    new Cesium.Cartesian3(),
  );
  const z = Cesium.Cartesian3.subtract(spacecraft, baseCentre, new Cesium.Cartesian3());
  const y = Cesium.Cartesian3.normalize(
    Cesium.Cartesian3.cross(z, x, new Cesium.Cartesian3()),
    new Cesium.Cartesian3(),
  );
  const matrix = Cesium.Matrix4.clone(Cesium.Matrix4.IDENTITY);
  Cesium.Matrix4.setColumn(matrix, 0, new Cesium.Cartesian4(x.x, x.y, x.z, 0), matrix);
  Cesium.Matrix4.setColumn(matrix, 1, new Cesium.Cartesian4(y.x, y.y, y.z, 0), matrix);
  Cesium.Matrix4.setColumn(matrix, 2, new Cesium.Cartesian4(z.x, z.y, z.z, 0), matrix);
  Cesium.Matrix4.setColumn(
    matrix,
    3,
    new Cesium.Cartesian4(baseCentre.x, baseCentre.y, baseCentre.z, 1),
    matrix,
  );
  primitive.modelMatrix = matrix;
}

export function geometryPolygons(aoi: AoiView): AoiVertex[][][] {
  return aoi.geometry.type === "Polygon" ? [aoi.geometry.coordinates] : aoi.geometry.coordinates;
}
