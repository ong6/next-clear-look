import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  Cartesian2,
  Cartesian3,
  Entity,
  ImageryLayer,
  Primitive,
  SampledPositionProperty,
  ScreenSpaceEventHandler,
  Viewer,
} from "cesium";
import type { AoiView, DashboardData } from "../data/dashboard-data";
import type { AoiVertex } from "../drawing/validation";
import { platformLabel } from "../data/dashboard-data";
import type { LayerKey } from "../state/app-store";
import { formatMissionOffset } from "../time/display-clock";
import { Icon } from "./Icon";
import {
  createAperturePrimitive,
  createOrbitPrimitive,
  createPositionProperty,
  createSwathPrimitive,
  EOX_TEMPLATE,
  geometryPolygons,
  incomingBearing,
  interpolateSample,
  loadCesium,
  PRESET_IMAGERY,
  probeEox,
  SATELLITE_CODES,
  satelliteSvg,
  setApertureMatrix,
} from "./globe/scene-primitives";
import type { CesiumModule, SpacecraftVisual } from "./globe/scene-primitives";

interface GlobeStageProps {
  data: DashboardData;
  aoi: AoiView;
  selectedOpportunityId: string;
  selectedSceneId: string;
  playbackProgress: number;
  clockTime: string;
  layers: Record<LayerKey, boolean>;
  reducedMotion: boolean;
  isPlaying: boolean;
  forceFallback?: boolean;
  onFirstFrame: () => void;
  onProgressChange: (progress: number) => void;
  drawing?: {
    active: boolean;
    closed: boolean;
    vertices: AoiVertex[];
  };
  onDrawPoint?: (vertex: AoiVertex) => void;
  onDrawClose?: () => void;
}

export function GlobeStage({
  data,
  aoi,
  selectedOpportunityId,
  selectedSceneId,
  playbackProgress,
  clockTime,
  layers,
  reducedMotion,
  isPlaying,
  forceFallback = false,
  onFirstFrame,
  onProgressChange,
  drawing,
  onDrawPoint,
  onDrawClose,
}: GlobeStageProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const creditRef = useRef<HTMLDivElement>(null);
  const labelLayerRef = useRef<HTMLDivElement>(null);
  const cameraAltitudeRef = useRef<HTMLSpanElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const cesiumRef = useRef<CesiumModule | null>(null);
  const spacecraftRef = useRef<SpacecraftVisual[]>([]);
  const apertureRef = useRef<Primitive | null>(null);
  const swathRef = useRef<Primitive | null>(null);
  const aoiBloomRef = useRef<Entity | null>(null);
  const sceneLayerRef = useRef<ImageryLayer | null>(null);
  const presetLayerRef = useRef<ImageryLayer | null>(null);
  const dayLayerRef = useRef<ImageryLayer | null>(null);
  const eoxLayerRef = useRef<ImageryLayer | null>(null);
  const orbitPrimitivesRef = useRef<Primitive[]>([]);
  const interactionHandlerRef = useRef<ScreenSpaceEventHandler | null>(null);
  const drawStateRef = useRef(drawing);
  const onDrawPointRef = useRef(onDrawPoint);
  const onDrawCloseRef = useRef(onDrawClose);
  const firstFrameSent = useRef(false);
  const initialClockTimeRef = useRef(clockTime);
  const onFirstFrameRef = useRef(onFirstFrame);
  const latestAoiRef = useRef(aoi);
  const latestBearingRef = useRef(12);
  const previousAoiIdRef = useRef(aoi.id);
  const previousProgressRef = useRef(playbackProgress);
  const previousPlayingRef = useRef(isPlaying);
  const manualCameraRef = useRef(false);
  const [status, setStatus] = useState<"loading" | "ready" | "fallback">("loading");
  const [eoxStatus, setEoxStatus] = useState<"probing" | "ready" | "unavailable">("probing");

  const selectedOpportunity =
    data.opportunities.find((item) => item.id === selectedOpportunityId) ?? data.opportunities[0];
  const selectedScene = data.scenes.find((item) => item.id === selectedSceneId) ?? data.scenes[0];
  const selectedTrajectory =
    data.trajectories.find((item) => item.satellite_id === selectedOpportunity?.satellite_id) ??
    data.trajectories[0];
  const bearing = useMemo(
    () => incomingBearing(selectedTrajectory, selectedOpportunity?.closest_time),
    [selectedOpportunity?.closest_time, selectedTrajectory],
  );
  const clockMilliseconds = Date.parse(clockTime);
  const intersects =
    Boolean(selectedOpportunity) &&
    clockMilliseconds >= Date.parse(selectedOpportunity.entry_time) &&
    clockMilliseconds <= Date.parse(selectedOpportunity.exit_time);

  latestAoiRef.current = aoi;
  latestBearingRef.current = bearing;
  drawStateRef.current = drawing;
  onDrawPointRef.current = onDrawPoint;
  onDrawCloseRef.current = onDrawClose;

  useEffect(() => {
    onFirstFrameRef.current = onFirstFrame;
  }, [onFirstFrame]);

  const signalFirstFrame = useCallback(() => {
    if (firstFrameSent.current) return;
    firstFrameSent.current = true;
    onFirstFrameRef.current();
  }, []);

  const applyCameraPose = useCallback((pass: boolean, duration: number, rangeOverride?: number) => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    if (!viewer || !Cesium) return;
    const currentAoi = latestAoiRef.current;
    const mobile = window.matchMedia("(max-width: 720px)").matches;
    const target = Cesium.Cartesian3.fromDegrees(currentAoi.centroid[0], currentAoi.centroid[1], 0);
    // The phone range keeps the Earth limb outside the compact frame while preserving orientation.
    const range = rangeOverride ?? (pass ? 1_810_000 : mobile ? 7_200_000 : 9_000_000);
    const headingOffset = pass ? -7 : mobile ? -15 : -18;
    const heading = Cesium.Math.toRadians(latestBearingRef.current + headingOffset);
    const pitch = Cesium.Math.toRadians(pass ? -40.5 : -64);
    const scratch = new Cesium.Camera(viewer.scene);
    scratch.lookAt(target, new Cesium.HeadingPitchRange(heading, pitch, range));
    scratch.lookAtTransform(Cesium.Matrix4.IDENTITY);
    if (pass) scratch.lookUp(Cesium.Math.toRadians(7));
    const destination = Cesium.Cartesian3.clone(scratch.positionWC);
    const direction = Cesium.Cartesian3.clone(scratch.directionWC);
    const up = Cesium.Cartesian3.clone(scratch.upWC);
    manualCameraRef.current = false;
    viewer.camera.cancelFlight();
    if (duration <= 0) viewer.camera.setView({ destination, orientation: { direction, up } });
    else
      viewer.camera.flyTo({
        destination,
        orientation: { direction, up },
        duration,
        easingFunction: Cesium.EasingFunction.CUBIC_OUT,
      });
  }, []);

  useEffect(() => {
    if (forceFallback || import.meta.env.MODE === "test") {
      setStatus("fallback");
      signalFirstFrame();
      return;
    }
    let disposed = false;
    let viewer: Viewer | undefined;
    void (async () => {
      try {
        const Cesium = await loadCesium();
        if (disposed || !containerRef.current || !creditRef.current) return;
        cesiumRef.current = Cesium;
        viewer = new Cesium.Viewer(containerRef.current, {
          baseLayer: false,
          terrainProvider: new Cesium.EllipsoidTerrainProvider(),
          animation: false,
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          infoBox: false,
          navigationHelpButton: false,
          sceneModePicker: false,
          selectionIndicator: false,
          timeline: false,
          scene3DOnly: true,
          shouldAnimate: false,
          skyBox: Cesium.SkyBox.createEarthSkyBox(),
          creditContainer: creditRef.current,
          requestRenderMode: true,
          maximumRenderTimeChange: Number.POSITIVE_INFINITY,
          msaaSamples: 4,
        });
        if (disposed) {
          viewer.destroy();
          return;
        }
        viewerRef.current = viewer;
        viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#020711");
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#06101c");
        viewer.scene.globe.enableLighting = true;
        viewer.scene.globe.lightingFadeOutDistance = 1;
        viewer.scene.globe.lightingFadeInDistance = 2;
        viewer.scene.globe.nightFadeOutDistance = 1;
        viewer.scene.globe.nightFadeInDistance = 2;
        viewer.scene.globe.dynamicAtmosphereLighting = true;
        viewer.scene.globe.dynamicAtmosphereLightingFromSun = true;
        viewer.scene.globe.atmosphereLightIntensity = 12;
        viewer.scene.globe.showGroundAtmosphere = true;
        if (viewer.scene.skyAtmosphere) {
          viewer.scene.skyAtmosphere.perFragmentAtmosphere = true;
          viewer.scene.skyAtmosphere.atmosphereLightIntensity = 12;
          viewer.scene.skyAtmosphere.hueShift = -0.08;
          viewer.scene.skyAtmosphere.saturationShift = -0.25;
          viewer.scene.skyAtmosphere.brightnessShift = -0.18;
        }
        viewer.scene.fog.enabled = false;
        if (viewer.scene.sun) viewer.scene.sun.show = true;
        if (viewer.scene.moon) viewer.scene.moon.show = false;
        viewer.scene.sunBloom = false;
        viewer.scene.postProcessStages.bloom.enabled = false;
        viewer.scene.highDynamicRange = false;
        if (new URLSearchParams(window.location.search).has("perf"))
          viewer.scene.debugShowFramesPerSecond = true;
        viewer.scene.screenSpaceCameraController.minimumZoomDistance = 180_000;
        viewer.scene.screenSpaceCameraController.maximumZoomDistance = 28_000_000;
        viewer.scene.screenSpaceCameraController.enableCollisionDetection = false;
        viewer.scene.screenSpaceCameraController.inertiaSpin = 0.78;
        viewer.scene.screenSpaceCameraController.inertiaZoom = 0.72;
        viewer.clock.currentTime = Cesium.JulianDate.fromIso8601(initialClockTimeRef.current);
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(92, 11, 17_000_000),
          orientation: { heading: 0, pitch: Cesium.Math.toRadians(-90), roll: 0 },
        });

        const dayProvider = await Cesium.SingleTileImageryProvider.fromUrl(
          "/imagery/world.topo.bathy.200410.3x5400x2700.jpg",
          { rectangle: Cesium.Rectangle.MAX_VALUE },
        );
        const dayLayer = viewer.imageryLayers.addImageryProvider(dayProvider);
        dayLayerRef.current = dayLayer;
        dayLayer.brightness = 0.82;
        dayLayer.contrast = 1.13;
        dayLayer.saturation = 0.82;
        dayLayer.gamma = 0.92;
        dayLayer.nightAlpha = 0.35;

        const nightProvider = await Cesium.SingleTileImageryProvider.fromUrl(
          "/imagery/dnb_land_ocean_ice.2012.3600x1800.jpg",
          { rectangle: Cesium.Rectangle.MAX_VALUE },
        );
        const nightLayer = viewer.imageryLayers.addImageryProvider(nightProvider);
        nightLayer.dayAlpha = 0;
        nightLayer.nightAlpha = 0.68;
        nightLayer.brightness = 0.88;
        nightLayer.contrast = 1.12;
        nightLayer.saturation = 0.35;

        void probeEox().then((reachable) => {
          if (disposed || !viewer || viewer.isDestroyed()) return;
          if (!reachable) {
            setEoxStatus("unavailable");
            return;
          }
          const provider = new Cesium.UrlTemplateImageryProvider({
            url: EOX_TEMPLATE,
            maximumLevel: 14,
            credit: new Cesium.Credit(
              "Sentinel-2 cloudless – https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2024)",
            ),
          });
          const layer = viewer.imageryLayers.addImageryProvider(provider, 2);
          layer.alpha = 0.72;
          layer.brightness = 0.92;
          layer.contrast = 1.08;
          layer.saturation = 0.82;
          layer.show = viewer.camera.positionCartographic.height < 2_500_000;
          eoxLayerRef.current = layer;
          setEoxStatus("ready");
          viewer.scene.requestRender();
        });

        const removePostRender = viewer.scene.postRender.addEventListener(() => {
          if (!viewer?.scene.globe.tilesLoaded) return;
          removePostRender();
          setStatus("ready");
          signalFirstFrame();
          window.setTimeout(() => applyCameraPose(false, reducedMotion ? 0 : 3.6), 0);
        });
        viewer.scene.postRender.addEventListener(() => {
          const altitude = viewer?.camera.positionCartographic.height ?? 0;
          if (cameraAltitudeRef.current)
            cameraAltitudeRef.current.textContent = `CAM ${Math.max(0, Math.round(altitude / 1_000)).toLocaleString("en-US")} km`;
          if (eoxLayerRef.current) eoxLayerRef.current.show = altitude < 2_500_000;
        });
      } catch {
        if (!disposed) {
          setStatus("fallback");
          signalFirstFrame();
        }
      }
    })();
    return () => {
      disposed = true;
      if (interactionHandlerRef.current && !interactionHandlerRef.current.isDestroyed())
        interactionHandlerRef.current.destroy();
      interactionHandlerRef.current = null;
      if (viewer && !viewer.isDestroyed()) viewer.destroy();
      viewerRef.current = null;
      dayLayerRef.current = null;
      eoxLayerRef.current = null;
    };
  }, [applyCameraPose, forceFallback, reducedMotion, signalFirstFrame]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    if (!viewer || !Cesium || status !== "ready") return;

    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    interactionHandlerRef.current = handler;
    const markManual = () => {
      if (drawStateRef.current?.active) return;
      manualCameraRef.current = true;
      viewer.camera.cancelFlight();
    };
    handler.setInputAction(markManual, Cesium.ScreenSpaceEventType.LEFT_DOWN);
    handler.setInputAction(markManual, Cesium.ScreenSpaceEventType.MIDDLE_DOWN);
    handler.setInputAction(markManual, Cesium.ScreenSpaceEventType.RIGHT_DOWN);
    handler.setInputAction(markManual, Cesium.ScreenSpaceEventType.WHEEL);
    handler.setInputAction((movement: { position: Cartesian2 }) => {
      const currentDrawing = drawStateRef.current;
      if (!currentDrawing?.active || currentDrawing.closed) return;
      const first = currentDrawing.vertices[0];
      if (first) {
        const firstWindow = Cesium.SceneTransforms.worldToWindowCoordinates(
          viewer.scene,
          Cesium.Cartesian3.fromDegrees(first[0], first[1]),
        );
        if (
          firstWindow &&
          Cesium.Cartesian2.distance(firstWindow, movement.position) <= 18 &&
          currentDrawing.vertices.length >= 3
        ) {
          onDrawCloseRef.current?.();
          viewer.scene.requestRender();
          return;
        }
      }
      const position = viewer.camera.pickEllipsoid(movement.position, viewer.scene.globe.ellipsoid);
      if (!position) return;
      const cartographic = Cesium.Cartographic.fromCartesian(position);
      onDrawPointRef.current?.([
        Cesium.Math.toDegrees(cartographic.longitude),
        Cesium.Math.toDegrees(cartographic.latitude),
      ]);
      viewer.scene.requestRender();
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    handler.setInputAction(() => {
      if (drawStateRef.current?.active && (drawStateRef.current.vertices.length ?? 0) >= 3)
        onDrawCloseRef.current?.();
      viewer.scene.requestRender();
    }, Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

    return () => {
      if (!handler.isDestroyed()) handler.destroy();
      if (interactionHandlerRef.current === handler) interactionHandlerRef.current = null;
    };
  }, [status]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    if (!viewer || !Cesium || status !== "ready") return;
    const labelLayer = labelLayerRef.current;
    viewer.scene.globe.enableLighting = layers.dayNight;
    viewer.entities.removeAll();
    spacecraftRef.current = [];
    if (apertureRef.current) viewer.scene.primitives.remove(apertureRef.current);
    if (swathRef.current) viewer.scene.primitives.remove(swathRef.current);
    orbitPrimitivesRef.current.forEach((primitive) => viewer.scene.primitives.remove(primitive));
    orbitPrimitivesRef.current = [];
    apertureRef.current = null;
    swathRef.current = null;
    labelLayer?.replaceChildren();

    const [west, south, east, north] = aoi.bounds;
    geometryPolygons(aoi).forEach((rings, polygonIndex) => {
      const exterior = rings[0];
      if (!exterior || exterior.length < 3) return;
      viewer.entities.add({
        id: `aoi-fill-${polygonIndex}`,
        show: layers.aoi,
        polygon: {
          hierarchy: new Cesium.PolygonHierarchy(
            Cesium.Cartesian3.fromDegreesArray(exterior.flat()),
            rings
              .slice(1)
              .map((ring) => new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(ring.flat()))),
          ),
          material: Cesium.Color.fromCssColorString("#ffb45b").withAlpha(0.06),
          height: 1_500,
        },
      });
      const closed =
        exterior[0][0] === exterior.at(-1)?.[0] && exterior[0][1] === exterior.at(-1)?.[1]
          ? exterior
          : [...exterior, exterior[0]];
      const outline = viewer.entities.add({
        id: `aoi-bloom-${polygonIndex}`,
        show: layers.aoi,
        polyline: {
          positions: Cesium.Cartesian3.fromDegreesArrayHeights(
            closed.flatMap(([longitude, latitude]) => [longitude, latitude, 8_000]),
          ),
          width: 3,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.12,
            color: Cesium.Color.fromCssColorString("#ffb45b").withAlpha(0.72),
          }),
        },
      });
      if (polygonIndex === 0) aoiBloomRef.current = outline;
    });

    const labels: {
      node: HTMLDivElement;
      position: SampledPositionProperty | Cartesian3;
      selected: boolean;
      aoi?: boolean;
      marker?: boolean;
    }[] = [];
    data.trajectories
      .filter((trajectory) => trajectory.samples.length >= 2)
      .forEach((trajectory) => {
        const satelliteId = trajectory.satellite_id;
        const selected = satelliteId === selectedOpportunity?.satellite_id;
        const position = createPositionProperty(Cesium, trajectory);
        const entity = viewer.entities.add({
          id: `spacecraft-${satelliteId}`,
          availability: new Cesium.TimeIntervalCollection([
            new Cesium.TimeInterval({
              start: Cesium.JulianDate.fromIso8601(trajectory.start_time),
              stop: Cesium.JulianDate.fromIso8601(trajectory.end_time),
            }),
          ]),
          position,
          orientation: new Cesium.VelocityOrientationProperty(position),
          billboard: {
            image: satelliteSvg(selected ? "#ffd39a" : "#edf6f8"),
            width: 18,
            height: 12,
            alignedAxis: new Cesium.VelocityVectorProperty(position, true),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            scaleByDistance: new Cesium.NearFarScalar(500_000, 1.15, 15_000_000, 0.8),
          },
        });
        const orbitPrimitive = createOrbitPrimitive(Cesium, trajectory, selected);
        orbitPrimitive.show = layers.tracks;
        viewer.scene.primitives.add(orbitPrimitive);
        orbitPrimitivesRef.current.push(orbitPrimitive);
        spacecraftRef.current.push({ entity, position, satelliteId, selected });
        if (labelLayer) {
          const node = document.createElement("div");
          node.className = `geo-label geo-label--spacecraft${selected ? " is-selected" : ""}`;
          const mark = document.createElement("i");
          const code = document.createElement("strong");
          const name = document.createElement("span");
          code.textContent = SATELLITE_CODES[satelliteId] ?? satelliteId;
          name.textContent = platformLabel(satelliteId);
          node.append(mark, code, name);
          labelLayer.append(node);
          labels.push({ node, position, selected });
        }
      });

    if (labelLayer) {
      const node = document.createElement("div");
      node.className = "geo-label geo-label--aoi";
      const labelName =
        aoi.slug === "singapore-coast"
          ? "TUAS"
          : aoi.origin === "user"
            ? "DRAWN AREA"
            : aoi.name.toUpperCase();
      const mark = document.createElement("i");
      const name = document.createElement("strong");
      const kind = document.createElement("span");
      name.textContent = labelName;
      kind.textContent = "AOI";
      node.append(mark, name, kind);
      labelLayer.append(node);
      labels.push({
        node,
        position: Cesium.Cartesian3.fromDegrees(east, south, 18_000),
        selected: true,
        aoi: true,
      });
      const brackets = document.createElement("div");
      brackets.className = "aoi-screen-brackets";
      brackets.setAttribute("aria-hidden", "true");
      labelLayer.append(brackets);
      labels.push({
        node: brackets,
        position: Cesium.Cartesian3.fromDegrees(aoi.centroid[0], aoi.centroid[1], 18_000),
        selected: true,
        marker: true,
      });
    }

    const selected = selectedTrajectory;
    if (selected && selected.samples.length >= 2 && selectedOpportunity) {
      const groundTrack = selected.samples.flatMap((sample) => [sample.longitude, sample.latitude]);
      viewer.entities.add({
        id: "selected-ground-track",
        show: layers.tracks,
        polyline: {
          positions: Cesium.Cartesian3.fromDegreesArray(groundTrack),
          width: 1,
          clampToGround: true,
          material: new Cesium.PolylineDashMaterialProperty({
            color: Cesium.Color.fromCssColorString("#ffb45b").withAlpha(0.45),
            dashLength: 12,
          }),
        },
      });
      swathRef.current = createSwathPrimitive(Cesium, selected);
      swathRef.current.show = layers.swath;
      viewer.scene.primitives.add(swathRef.current);
      apertureRef.current = createAperturePrimitive(Cesium);
      apertureRef.current.show = layers.swath;
      const initialSample = interpolateSample(
        selected,
        Cesium.JulianDate.toDate(viewer.clock.currentTime).getTime(),
      );
      const initialSpacecraft = spacecraftRef.current
        .find((visual) => visual.satelliteId === selected.satellite_id)
        ?.position.getValue(viewer.clock.currentTime);
      if (initialSample && initialSpacecraft) {
        setApertureMatrix(
          Cesium,
          apertureRef.current,
          initialSpacecraft,
          Cesium.Cartesian3.fromDegrees(initialSample.swath_left[0], initialSample.swath_left[1], 2_000),
          Cesium.Cartesian3.fromDegrees(initialSample.swath_right[0], initialSample.swath_right[1], 2_000),
        );
      } else {
        const first = selected.samples[0];
        setApertureMatrix(
          Cesium,
          apertureRef.current,
          Cesium.Cartesian3.fromDegrees(first.longitude, first.latitude, first.altitude_m),
          Cesium.Cartesian3.fromDegrees(first.swath_left[0], first.swath_left[1], 2_000),
          Cesium.Cartesian3.fromDegrees(first.swath_right[0], first.swath_right[1], 2_000),
        );
      }
      viewer.scene.primitives.add(apertureRef.current);
      for (const [id, sampleKey] of [
        ["left", "swath_left"],
        ["right", "swath_right"],
      ] as const) {
        const edgePositions = (swept: boolean) =>
          new Cesium.CallbackProperty(() => {
            const currentMilliseconds = Cesium.JulianDate.toDate(viewer.clock.currentTime).getTime();
            const current = interpolateSample(selected, currentMilliseconds);
            if (!current) return [];
            const samples = selected.samples
              .filter((sample) =>
                swept
                  ? Date.parse(sample.time) <= currentMilliseconds
                  : Date.parse(sample.time) >= currentMilliseconds,
              )
              .map((sample) => sample[sampleKey]);
            const points = swept ? [...samples, current[sampleKey]] : [current[sampleKey], ...samples];
            return Cesium.Cartesian3.fromDegreesArrayHeights(
              points.flatMap((point) => [point[0], point[1], 2_100]),
            );
          }, false);
        viewer.entities.add({
          id: `swath-${id}-swept-edge`,
          polyline: {
            show: new Cesium.CallbackProperty(() => {
              const time = Cesium.JulianDate.toDate(viewer.clock.currentTime).getTime();
              return (
                layers.swath &&
                time >= Date.parse(selected.start_time) &&
                time <= Date.parse(selected.end_time)
              );
            }, false),
            positions: edgePositions(true),
            width: 1,
            material: Cesium.Color.fromCssColorString("#edf6f8").withAlpha(0.7),
          },
        });
        viewer.entities.add({
          id: `swath-${id}-future-edge`,
          polyline: {
            show: new Cesium.CallbackProperty(() => {
              const time = Cesium.JulianDate.toDate(viewer.clock.currentTime).getTime();
              return (
                layers.swath &&
                time >= Date.parse(selected.start_time) &&
                time <= Date.parse(selected.end_time)
              );
            }, false),
            positions: edgePositions(false),
            width: 1,
            material: Cesium.Color.fromCssColorString("#ffb45b").withAlpha(0.62),
          },
        });
      }
      for (const [id, sampleKey] of [
        ["left", "swath_left"],
        ["right", "swath_right"],
      ] as const) {
        viewer.entities.add({
          id: `aperture-${id}-edge`,
          polyline: {
            show: new Cesium.CallbackProperty(() => {
              const time = Cesium.JulianDate.toDate(viewer.clock.currentTime).getTime();
              return (
                layers.swath &&
                time >= Date.parse(selected.start_time) &&
                time <= Date.parse(selected.end_time)
              );
            }, false),
            positions: new Cesium.CallbackProperty(() => {
              const currentTime = viewer.clock.currentTime;
              const sample = interpolateSample(selected, Cesium.JulianDate.toDate(currentTime).getTime());
              const spacecraft = spacecraftRef.current
                .find((visual) => visual.satelliteId === selected.satellite_id)
                ?.position.getValue(currentTime);
              return sample && spacecraft
                ? [
                    spacecraft,
                    Cesium.Cartesian3.fromDegrees(sample[sampleKey][0], sample[sampleKey][1], 2_000),
                  ]
                : [];
            }, false),
            width: 3,
            material: new Cesium.PolylineOutlineMaterialProperty({
              color: Cesium.Color.fromCssColorString("#edf6f8").withAlpha(0.85),
              outlineColor: Cesium.Color.fromCssColorString("#050b14").withAlpha(0.4),
              outlineWidth: 0.875,
            }),
          },
        });
      }
      viewer.entities.add({
        id: "pushbroom-line",
        polyline: {
          show: new Cesium.CallbackProperty(() => {
            const time = Cesium.JulianDate.toDate(viewer.clock.currentTime).getTime();
            return (
              layers.swath && time >= Date.parse(selected.start_time) && time <= Date.parse(selected.end_time)
            );
          }, false),
          positions: new Cesium.CallbackProperty(() => {
            const sample = interpolateSample(
              selected,
              Cesium.JulianDate.toDate(viewer.clock.currentTime).getTime(),
            );
            return sample
              ? Cesium.Cartesian3.fromDegreesArrayHeights([
                  sample.swath_left[0],
                  sample.swath_left[1],
                  2_500,
                  sample.swath_right[0],
                  sample.swath_right[1],
                  2_500,
                ])
              : [];
          }, false),
          width: 2,
          material: new Cesium.PolylineGlowMaterialProperty({
            color: Cesium.Color.fromCssColorString("#ffd39a"),
            glowPower: 0.25,
          }),
        },
      });
    }

    if (sceneLayerRef.current) viewer.imageryLayers.remove(sceneLayerRef.current, true);
    sceneLayerRef.current = null;
    if (layers.sceneDrape && selectedScene?.thumbnail) {
      void Cesium.SingleTileImageryProvider.fromUrl(selectedScene.thumbnail, {
        rectangle: Cesium.Rectangle.fromDegrees(west, south, east, north),
      }).then((provider) => {
        if (viewer.isDestroyed()) return;
        const layer = viewer.imageryLayers.addImageryProvider(provider);
        layer.alpha = 0.88;
        layer.brightness = 1.05;
        layer.contrast = 1.06;
        sceneLayerRef.current = layer;
      });
    }

    if (presetLayerRef.current) viewer.imageryLayers.remove(presetLayerRef.current, true);
    presetLayerRef.current = null;
    const presetImagery = PRESET_IMAGERY[aoi.slug];
    if (presetImagery) {
      void Cesium.SingleTileImageryProvider.fromUrl(presetImagery.url, {
        rectangle: Cesium.Rectangle.fromDegrees(...presetImagery.rectangle),
      }).then((provider) => {
        if (viewer.isDestroyed()) return;
        const layer = viewer.imageryLayers.addImageryProvider(provider, 1);
        layer.brightness = 0.88;
        layer.contrast = 1.12;
        layer.saturation = 0.86;
        layer.nightAlpha = 0.35;
        presetLayerRef.current = layer;
      });
    }

    const scratchWindow = new Cesium.Cartesian2();
    const removePostRender = viewer.scene.postRender.addEventListener(() => {
      const currentMilliseconds = Cesium.JulianDate.toDate(viewer.clock.currentTime).getTime();
      if (selected && apertureRef.current) {
        const active =
          layers.swath &&
          currentMilliseconds >= Date.parse(selected.start_time) &&
          currentMilliseconds <= Date.parse(selected.end_time);
        apertureRef.current.show = active;
        const sample = interpolateSample(selected, currentMilliseconds);
        const spacecraft = spacecraftRef.current
          .find((visual) => visual.satelliteId === selected.satellite_id)
          ?.position.getValue(viewer.clock.currentTime);
        if (sample && spacecraft) {
          const left = Cesium.Cartesian3.fromDegrees(sample.swath_left[0], sample.swath_left[1], 2_000);
          const right = Cesium.Cartesian3.fromDegrees(sample.swath_right[0], sample.swath_right[1], 2_000);
          setApertureMatrix(Cesium, apertureRef.current, spacecraft, left, right);
        }
      }
      if (selected && swathRef.current) {
        const active =
          layers.swath &&
          currentMilliseconds >= Date.parse(selected.start_time) &&
          currentMilliseconds <= Date.parse(selected.end_time);
        swathRef.current.show = active;
        const total = Date.parse(selected.end_time) - Date.parse(selected.start_time);
        const progress = Math.min(
          1,
          Math.max(0, (currentMilliseconds - Date.parse(selected.start_time)) / total),
        );
        const appearance = swathRef.current.appearance as InstanceType<typeof Cesium.MaterialAppearance>;
        const uniforms = appearance.material.uniforms as unknown as Record<string, number>;
        uniforms.progress = progress;
      }
      const occupied: { left: number; right: number; top: number; bottom: number }[] = [];
      labels
        .filter((label) => label.aoi)
        .concat(
          labels.filter((label) => !label.aoi && label.selected),
          labels.filter((label) => !label.aoi && !label.selected),
        )
        .forEach((label) => {
          const position =
            label.position instanceof Cesium.Cartesian3
              ? label.position
              : label.position.getValue(viewer.clock.currentTime);
          if (!position || (!label.selected && window.matchMedia("(max-width: 720px)").matches)) {
            label.node.hidden = true;
            return;
          }
          const screen = Cesium.SceneTransforms.worldToWindowCoordinates(
            viewer.scene,
            position,
            scratchWindow,
          );
          if (
            !screen ||
            screen.x < 0 ||
            screen.y < 0 ||
            screen.x > viewer.canvas.clientWidth ||
            screen.y > viewer.canvas.clientHeight
          ) {
            label.node.hidden = true;
            return;
          }
          if (label.marker) {
            label.node.hidden = false;
            label.node.style.left = `${screen.x}px`;
            label.node.style.top = `${screen.y}px`;
            return;
          }
          const width = label.node.offsetWidth || (label.aoi ? 68 : 80);
          const leader = label.aoi ? 24 : 18;
          const rightEdge = screen.x + leader + width;
          const fitsRight = rightEdge <= viewer.canvas.clientWidth - 12;
          const fitsLeft = screen.x - width - leader >= 12;
          const leftSide = !fitsRight && fitsLeft;
          label.node.style.maxWidth =
            !fitsRight && !fitsLeft
              ? `${Math.max(56, viewer.canvas.clientWidth - screen.x - leader - 12)}px`
              : "";
          const box = {
            left: leftSide ? screen.x - width - leader : screen.x + leader,
            right: leftSide ? screen.x - leader : rightEdge,
            top: screen.y - 14,
            bottom: screen.y + 16,
          };
          let verticalOffset = 0;
          if (
            occupied.some(
              (item) =>
                box.left < item.right &&
                box.right > item.left &&
                box.top < item.bottom &&
                box.bottom > item.top,
            )
          )
            verticalOffset = label.aoi ? 22 : -24;
          label.node.hidden = false;
          label.node.classList.toggle("is-left", leftSide);
          label.node.style.left = `${Math.min(viewer.canvas.clientWidth - 24, Math.max(24, screen.x))}px`;
          label.node.style.top = `${Math.min(viewer.canvas.clientHeight - 20, Math.max(20, screen.y + verticalOffset))}px`;
          occupied.push({ ...box, top: box.top + verticalOffset, bottom: box.bottom + verticalOffset });
        });
    });

    return () => {
      removePostRender();
      labelLayer?.replaceChildren();
    };
  }, [aoi, data.trajectories, layers, selectedOpportunity, selectedScene, selectedTrajectory, status]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    if (!viewer || !Cesium || status !== "ready") return;
    const fill = viewer.entities.getById("aoi-fill-0")?.polygon;
    if (fill)
      fill.material = new Cesium.ColorMaterialProperty(
        Cesium.Color.fromCssColorString("#ffb45b").withAlpha(intersects ? 0.12 : 0.06),
      );
    const outline = aoiBloomRef.current?.polyline;
    if (outline) {
      outline.width = new Cesium.ConstantProperty(intersects ? 8 : 3);
      outline.material = new Cesium.PolylineGlowMaterialProperty({
        glowPower: intersects ? 0.4 : 0.12,
        color: Cesium.Color.fromCssColorString("#ffb45b").withAlpha(intersects ? 1 : 0.72),
      });
    }
    viewer.scene.requestRender();
  }, [intersects, status]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    if (!viewer || !Cesium || status !== "ready") return;
    const ids = viewer.entities.values
      .map((entity) => entity.id)
      .filter((id) => id.startsWith("draw-preview-"));
    ids.forEach((id) => viewer.entities.removeById(id));
    const active = drawing?.active ?? false;
    const vertices = drawing?.vertices ?? [];
    viewer.scene.screenSpaceCameraController.enableRotate = !active;
    viewer.scene.screenSpaceCameraController.enableTilt = !active;
    viewer.scene.screenSpaceCameraController.enableTranslate = !active;
    viewer.canvas.style.cursor = active ? "crosshair" : "default";
    if (active && vertices.length > 0) {
      vertices.forEach(([longitude, latitude], index) => {
        viewer.entities.add({
          id: `draw-preview-point-${index}`,
          position: Cesium.Cartesian3.fromDegrees(longitude, latitude, 12_000),
          point: {
            pixelSize: index === 0 ? 12 : 9,
            color: Cesium.Color.fromCssColorString(index === 0 ? "#ffd39a" : "#48d8e8"),
            outlineColor: Cesium.Color.fromCssColorString("#06101c"),
            outlineWidth: 2,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
      });
      const lineVertices = drawing?.closed && vertices.length >= 3 ? [...vertices, vertices[0]] : vertices;
      if (lineVertices.length >= 2) {
        viewer.entities.add({
          id: "draw-preview-line",
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArrayHeights(
              lineVertices.flatMap(([longitude, latitude]) => [longitude, latitude, 10_000]),
            ),
            width: 3,
            material: new Cesium.PolylineGlowMaterialProperty({
              glowPower: 0.18,
              color: Cesium.Color.fromCssColorString("#48d8e8"),
            }),
          },
        });
      }
      if (vertices.length >= 3) {
        viewer.entities.add({
          id: "draw-preview-polygon",
          polygon: {
            hierarchy: Cesium.Cartesian3.fromDegreesArray(vertices.flat()),
            material: Cesium.Color.fromCssColorString(drawing?.closed ? "#48d8e8" : "#ffb45b").withAlpha(
              drawing?.closed ? 0.18 : 0.1,
            ),
            height: 2_000,
          },
        });
      }
    }
    viewer.scene.requestRender();
    return () => {
      if (viewer.isDestroyed()) return;
      viewer.scene.screenSpaceCameraController.enableRotate = true;
      viewer.scene.screenSpaceCameraController.enableTilt = true;
      viewer.scene.screenSpaceCameraController.enableTranslate = true;
      viewer.canvas.style.cursor = "default";
      viewer.scene.requestRender();
    };
  }, [drawing?.active, drawing?.closed, drawing?.vertices, status]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    if (viewer && Cesium) {
      viewer.clock.currentTime = Cesium.JulianDate.fromIso8601(clockTime);
      viewer.scene.requestRender();
    }
    if (dayLayerRef.current) {
      const duringPass =
        Boolean(selectedTrajectory) &&
        clockMilliseconds >= Date.parse(selectedTrajectory.start_time) &&
        clockMilliseconds <= Date.parse(selectedTrajectory.end_time);
      dayLayerRef.current.brightness = duringPass ? 0.72 : 0.82;
    }
  }, [clockMilliseconds, clockTime, selectedTrajectory]);

  useEffect(() => {
    if (previousAoiIdRef.current === aoi.id) return;
    previousAoiIdRef.current = aoi.id;
    window.setTimeout(() => applyCameraPose(false, reducedMotion ? 0 : 1.6), 0);
  }, [aoi, applyCameraPose, reducedMotion]);

  useEffect(() => {
    if (status !== "ready") return;
    const startedPlaying = isPlaying && !previousPlayingRef.current;
    previousPlayingRef.current = isPlaying;
    if (!startedPlaying) return;
    applyCameraPose(true, reducedMotion ? 0 : 0.7, 1_810_000);
    if (reducedMotion) return;
    const dolly = window.setTimeout(() => {
      if (!manualCameraRef.current) applyCameraPose(true, 11.3, 1_600_000);
    }, 700);
    return () => window.clearTimeout(dolly);
  }, [applyCameraPose, isPlaying, reducedMotion, status]);

  useEffect(() => {
    if (status !== "ready" || !drawing?.active) return;
    applyCameraPose(false, 0, 500_000);
  }, [applyCameraPose, drawing?.active, status]);

  useEffect(() => {
    const changed = Math.abs(previousProgressRef.current - playbackProgress) > 0.0001;
    previousProgressRef.current = playbackProgress;
    if (status !== "ready" || isPlaying || !changed) return;
    applyCameraPose(true, reducedMotion ? 0 : 0.7, 1_810_000);
  }, [applyCameraPose, isPlaying, playbackProgress, reducedMotion, status]);

  const focus = () => applyCameraPose(false, reducedMotion ? 0 : 1.6);
  const northUp = () => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    if (!viewer || !Cesium) return;
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(aoi.centroid[0], aoi.centroid[1], 2_500_000),
      orientation: { heading: 0, pitch: Cesium.Math.toRadians(-90), roll: 0 },
      duration: reducedMotion ? 0 : 1,
    });
  };
  const reset = () => applyCameraPose(false, reducedMotion ? 0 : 1.5);

  const offsetLabel = selectedOpportunity
    ? formatMissionOffset(new Date(clockMilliseconds), selectedOpportunity.closest_time)
    : "COMPUTING";
  const summary = selectedOpportunity
    ? `${aoi.name}. Next geometric opportunity is ${platformLabel(selectedOpportunity.platform)} at ${new Date(selectedOpportunity.closest_time).toISOString()}. The selected nominal swath ${intersects ? "intersects" : "does not intersect"} the AOI at ${new Date(clockTime).toISOString()}.`
    : `${aoi.name}. Opportunity geometry is being computed by the engine.`;

  return (
    <section
      className={`globe-stage ${intersects ? "is-intersecting" : ""} ${drawing?.active ? "is-drawing" : ""}`}
      data-testid={drawing?.active ? "aoi-draw-map" : "globe-stage"}
      aria-label={
        drawing?.active
          ? "Draw an area directly on the 3D globe"
          : "Interactive 3D globe showing the selected AOI and Sentinel-2 opportunities"
      }
      aria-describedby="globe-summary"
    >
      <div ref={containerRef} className="cesium-host" aria-hidden={status === "fallback"} />
      <div ref={creditRef} className="cesium-credit-sink" aria-hidden="true" />
      {status !== "ready" && (
        <div className={`globe-placeholder globe-placeholder--${status}`} aria-hidden={status === "loading"}>
          {status === "loading" ? (
            <>
              <span className="globe-loading-mark" />
              <p>Rendering globe imagery</p>
            </>
          ) : (
            <>
              <Icon name="globe" />
              <h2>3D globe unavailable</h2>
              <p>Opportunity times and recorded evidence are still available below.</p>
            </>
          )}
        </div>
      )}
      <div className="globe-vignette" aria-hidden="true" />
      <div ref={labelLayerRef} className="globe-label-layer" aria-hidden="true" />
      <div className="globe-legend" aria-label="Globe legend and readouts">
        <div className="legend-keys">
          <span>
            <i className="legend-line legend-line--opportunity" />
            Opportunity
          </span>
          <span>
            <i className="legend-aoi" />
            AOI
          </span>
          <span>
            <i className="legend-swath" />
            Swept swath
          </span>
          <span>
            <i className="legend-swath-ahead" />
            Swath ahead
          </span>
        </div>
        <div className="globe-readout">
          <span>
            AOI {Math.abs(aoi.centroid[1]).toFixed(2)}° {aoi.centroid[1] >= 0 ? "N" : "S"},{" "}
            {Math.abs(aoi.centroid[0]).toFixed(2)}° {aoi.centroid[0] >= 0 ? "E" : "W"}
          </span>
          <span ref={cameraAltitudeRef} />
          <span>Blue Marble Oct 2004</span>
          {eoxStatus === "ready" && <span>EOX close zoom</span>}
        </div>
      </div>
      <div className="globe-toolbar" aria-label="Globe view controls">
        <button type="button" onClick={focus} aria-label="Focus globe on AOI">
          <Icon name="target" />
        </button>
        <button type="button" onClick={northUp} aria-label="Set north up">
          <Icon name="north" />
        </button>
        <button type="button" onClick={reset} aria-label="Reset to whole Earth">
          <Icon name="reset" />
        </button>
      </div>
      <div className="globe-time">
        <span>MISSION CLOCK · {offsetLabel}</span>
        <strong>{new Date(clockTime).toISOString().slice(11, 19)} UTC</strong>
      </div>
      {isPlaying && (
        <label className="globe-scrubber">
          <span className="sr-only">Pass replay position</span>
          <i className="timeline-entry">ENTRY</i>
          <i className="timeline-t0">T0</i>
          <i className="timeline-exit">EXIT</i>
          <input
            type="range"
            min="0"
            max="100"
            value={Math.round(playbackProgress * 100)}
            data-testid="globe-playback-scrubber"
            onChange={(event) => onProgressChange(Number(event.currentTarget.value) / 100)}
          />
        </label>
      )}
      {!isPlaying && (
        <input
          className="sr-only"
          aria-label="Pass replay position"
          type="range"
          min="0"
          max="100"
          value={Math.round(playbackProgress * 100)}
          data-testid="globe-playback-scrubber"
          onChange={(event) => onProgressChange(Number(event.currentTarget.value) / 100)}
        />
      )}
      <p id="globe-summary" className="sr-only" aria-live="polite" data-testid="globe-text-alternative">
        {summary}
      </p>
    </section>
  );
}
