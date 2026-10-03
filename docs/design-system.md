# Next Clear Look — design system

Status: develop-phase visual and interaction contract  
Companion token source: `tokens.css`  
Primary targets: 1440 × 900 and 390 × 844

## 1. Direction: orbital aperture

Next Clear Look belongs to the world of optical Earth observation, mission timelines, and evidence review—not generic enterprise analytics.

- **World:** a quiet optical payload console looking down through an orbital window.
- **Materials:** dark anodized instrument panels, smoked optical glass, etched coordinate rules, phosphor-like trajectories, and the warm edge of sunlight.
- **Palette:** indigo-black instrument glass, chalk-white type, cyan observed evidence, amber geometric opportunity, orchid obscuration, and cold slate unknowns.
- **Signature:** the **aperture scan**—a thin vertical light sheet and bracket pair that crosses an AOI exactly at geometric intersection. It appears in the globe, selected-row treatment, loading choreography, and the wordmark. It never resembles a camera shutter or claims acquisition.

The aesthetic risk is concentrated in the globe and aperture scan. Everything around it is restrained: hairline spectral rules, low-radius panels, dense readable telemetry, and precise hierarchy. No glassmorphic card pile, decorative star particles, neon-green “space” cliché, or gratuitous gradient headline.

## 2. Design principles

1. **Truth before theatre.** The first persistent badge says Recorded replay or Live data. The next-pass card says geometric opportunity before the countdown becomes the focal point.
2. **One continuous instrument.** Panels share rules and coordinate alignment; they do not float as unrelated rounded cards.
3. **Evidence has a different color from opportunity.** Amber means future geometry. Cyan means recorded observation/evidence. They are never interchangeable.
4. **Uncertainty is drawn.** Intervals, sample counts, stale states, unknown pixels, and missing previews have stable visual forms.
5. **The Earth is the hero, not decoration.** The globe carries the primary story; surrounding UI explains it and makes it usable.
6. **Compact, never cramped.** Dense analyst information uses a 4 px base rhythm, tabular numerals, strong labels, and generous interactive targets.
7. **Offline is a mode, not an error.** Recorded replay looks first-class and calm.

## 3. Palette

All values are defined in `tokens.css`. Hex values below are source colors; UI should use semantic variables.

### Foundations

| Token | Hex | Role |
|---|---:|---|
| Night 950 | `#050B14` | Page surround, loading field |
| Orbit 900 | `#07111F` | Main canvas |
| Orbit 850 | `#091727` | Globe-adjacent chrome |
| Orbit 800 | `#0D1C2E` | Panel surface |
| Orbit 750 | `#12243A` | Raised controls, selected inset |
| Rule 600 | `#294159` | Strong structural rule |
| Rule 700 | `#1C3147` | Default structural rule |
| Frost 050 | `#EDF6F8` | Primary text |
| Frost 200 | `#B7CBD4` | Secondary text |
| Frost 400 | `#829AA8` | Muted metadata; never body copy below 14 px |

The darks carry blue and green, echoing coastal imagery without becoming pure navy. Pure black is reserved for translucent overlays and imagery contrast.

### Semantic and data colors

| Token | Hex | Meaning | Required reinforcement |
|---|---:|---|---|
| Opportunity | `#FFB45B` | Future geometric opportunity, active AOI | Bracket/diamond shape + word label |
| Opportunity strong | `#FFD39A` | Opportunity emphasis and focus-on-dark | Same |
| Evidence | `#48D8E8` | Recorded scene, selected evidence, ready stream | Underline/solid circle + label |
| Evidence strong | `#A5F3F7` | Critical evidence text and focus | Same |
| Clear | `#56D4C5` | Clear-surface class | Forward diagonal hatch + percentage |
| Mixed | `#F3B966` | Mixed/partial usability | Dot texture + percentage |
| Obscured | `#D28AC7` | Cloud/cirrus-obscured | Crosshatch + percentage |
| Unknown | `#778D9E` | No data/unclassified/pending | Dashed outline + label |
| Error | `#FF8A82` | Unavailable/failed | Octagon/alert icon + explicit error text |
| Stale | `#C8A6FF` | Stale but retained input | Clock icon + “Stale input” |
| Focus | `#C4F5FF` | Keyboard focus ring only | 2 px ring + 2 px offset |

Opportunity and evidence are color-blind-safe as a pair and use different geometry. Success does not default to green; Evidence cyan plus “Ready” is the ready state. Error is never shown by salmon color alone.

### Clear-percentage encoding

Never encode usability with a red-to-green ramp. The standard display is:

- **Numeral:** exact AOI clear percentage or named unavailable state.
- **Bar length:** 0–100% clear share.
- **Band:** Clear `#56D4C5`, Mixed `#F3B966`, Obscured `#D28AC7`, Unknown `#778D9E`.
- **Texture:** 45° hatch, dots, crosshatch, dashed/no fill respectively.
- **Text:** explicit category and percentage adjacent to each mark.

For a single AOI clear score, the fill stays cyan across the scale. Threshold grouping is conveyed by a separate word/shape (“Clear enough,” “Mixed,” “Obscured”), not by changing the score from green to red.

### Overlays

- Scrim: `rgba(2, 8, 16, 0.76)`.
- Panel glass: `rgba(9, 23, 39, 0.92)`; backdrop blur is optional enhancement, never needed for contrast.
- Globe vignette: radial/linear darkening up to 42%, leaving the AOI unobscured.
- Selection bloom: semantic color at 18% opacity; no large blurred neon fields.

## 4. Typography

### Families

- **Interface/display:** IBM Plex Sans, 400/500/600. Its technical but human shapes fit an analyst tool and the owner’s usual family.
- **Telemetry/data:** IBM Plex Mono, 400/500. Use for timestamps, coordinates, countdowns, IDs, percentages, pixel counts, and keyboard shortcuts.
- **Fallbacks:** `"Helvetica Neue", "Segoe UI", sans-serif` and `ui-monospace, "SFMono-Regular", Consolas, monospace`.
- Production should self-host WOFF2. The static prototype may use the approved font mirror and must remain legible on fallbacks.

### Type scale

| Style | Size / line | Weight | Tracking | Use |
|---|---:|---:|---:|---|
| Display orbit | 42 / 44 px | 500 | −0.035 em | Desktop countdown and hero datum |
| Display mobile | 34 / 38 px | 500 | −0.03 em | Mobile countdown |
| Title | 24 / 30 px | 500 | −0.02 em | Detail title, major result |
| Section | 16 / 22 px | 600 | −0.01 em | Panel heading |
| Body | 14 / 20 px | 400 | 0 | Standard prose/control text |
| Compact | 12 / 16 px | 500 | 0.01 em | Dense rows, not long prose |
| Eyebrow | 10 / 14 px | 600 | 0.11 em | Uppercase telemetry label |
| Mono datum | 13 / 18 px | 500 | 0 | UTC, coordinates, IDs |
| Mono micro | 10 / 14 px | 500 | 0.06 em | Globe readout and axis labels |

Rules:

- Use sentence case except short telemetry eyebrows.
- Use `font-variant-numeric: tabular-nums slashed-zero` for timers and tables.
- Use a true minus and en dash where appropriate.
- Prefer semantic line breaks in hero text; body line length is 45–72 characters.
- Never use font weight below 400 on dark backgrounds.
- No visible interface text is set below 10 px at either target viewport.

## 5. Grid, spacing, and density

Base unit: 4 px.

| Token | Value | Typical use |
|---|---:|---|
| `space-1` | 4 px | Icon optical adjustment, micro gap |
| `space-2` | 8 px | Label-to-value, compact controls |
| `space-3` | 12 px | Dense row padding |
| `space-4` | 16 px | Mobile inset, standard group gap |
| `space-5` | 20 px | Panel inset |
| `space-6` | 24 px | Desktop grid gutter |
| `space-8` | 32 px | Section separation |
| `space-10` | 40 px | Major detail separation |
| `space-12` | 48 px | Large page rhythm only |

Desktop:

- 12-column detail grid; 24 px outer margin and gutter.
- Mission screen uses a flexible 1,096 px globe/evidence column at the 1440 target and a fixed
  344 px, full-height outlook rail. AOI presets live in the command-bar picker, not a persistent rail.
- Top bar 60 px; recent-looks strip 136 px with fixed 344 px cards inside the globe column.
- Dense control row 36 px visual height with a 44 px hit target.

Mobile:

- 14 px edge inset, four logical columns, 12 px gutters.
- Header 56 px; globe y=56–436 (380 px); bottom sheet with 16 px top radius. During pass playback
  the portrait globe extends to y=700 and the sheet collapses below it.
- Touch targets at least 44 × 44 px; primary action 48 px high.

## 6. Shape, radii, and rules

The product uses cut/bracket geometry more than soft cards.

- Radius 2 px: data chips and tiny swatches.
- Radius 6 px: buttons, inputs, tooltips, menu items.
- Radius 10 px: drawers and desktop overlays.
- Radius 16 px: mobile bottom sheet top corners only.
- Pill radius: status badges only; no content container uses a pill silhouette.
- Active AOI and selected opportunity use opposing corner brackets rather than a rounded background.
- Panel boundaries are 1 px rules. Strong group breaks use a double rule: 1 px + 3 px gap + 1 px at reduced opacity.

## 7. Elevation and surface treatment

Elevation is rare on the desktop continuous instrument. It primarily indicates transient layering.

| Level | Treatment | Use |
|---|---|---|
| 0 | No shadow, rule boundary | Permanent rails/panels |
| 1 | `0 6px 18px rgba(0,0,0,.22)` | Menus, compact popovers |
| 2 | `0 18px 56px rgba(0,0,0,.42)` | Evidence drawer, mobile sheet |
| 3 | Scrim + `0 24px 80px rgba(0,0,0,.55)` | Confirmation dialog only |

Raised controls use a subtle top inner highlight. Avoid stacked translucent cards or blur-dependent text contrast.

## 8. Iconography and marks

- 20 px default viewBox, 1.6 px strokes, square caps with slightly rounded joins.
- Hand-authored SVG only in the prototype; no emoji and no mixed icon libraries.
- Satellite: diamond aperture with two short solar-wing strokes.
- AOI: four open corner brackets.
- Evidence: solid central dot inside a broken square.
- Opportunity: hollow diamond crossing a line.
- Offline: database cylinder with a check, not a disconnected cloud icon.
- Unknown: dashed circle; stale: clock wedge; error: octagon with short bar.
- Icons used without visible labels require accessible names and tooltips; frequent primary actions keep text labels.

## 9. Data visualization

### Opportunity rail

- Horizontal time baseline uses Rule 700.
- Opportunity is a diamond sized 10 px; selected is 14 px with an amber inner dot.
- Daylight is a short solid cap; low sun is half-filled; night is outline only.
- Spacecraft identity uses A/B/C letter inside or adjacent to the mark, never color alone.
- The current replay time is a 1 px cyan vertical scan with a mono UTC label.

### Likelihood interval

- 2 px interval whisker, 8 px end caps, 8 px point estimate dot.
- Cyan fill/whisker for historical likelihood; a hatched ghost band shows uncertainty when space permits.
- Text always includes point estimate, numeric interval, and `n`.
- Insufficient sample replaces the chart with a dashed line and exact sample statement; never plot 0%.

### AOI accounting

- Segmented bar is at least 16 px high and not the sole representation.
- Adjacent table repeats name, count, and percentage.
- Stripes/dots/crosshatch use 1 px lines at ≥4 px pitch so they survive 1× mobile rendering.

### Sparklines

- SVG only, no hidden axes when absolute interpretation matters.
- Selected dot and first/last time labels are mandatory.
- Small history sparklines use no gradient fill; one semantic stroke plus a faint baseline.

## 10. Imagery treatment

- True-colour imagery is never covered by a color wash. UI labels sit in an external strip or on an 80% opaque local backing plate.
- AOI detail displays recorded true-colour thumbnails at no more than 768 CSS px unless the engine
  supplies a 1,536 px source; a thumbnail is never scaled beyond 2× at a 2× device pixel ratio.
- Scene preview, AOI crop, and SCL visualization are visibly distinguished by a top-left label.
- A preview that is not clipped to the AOI says “Scene preview,” never “AOI image.”
- Missing imagery uses a coordinate grid and the words “Preview not bundled”; it does not reuse another scene’s image.
- SCL classes follow the data encoding colors and textures, not the true ESA palette if that palette would make product states ambiguous. A legend is always present.
- Split compare handle: 2 px Evidence line, 44 px draggable zone, date tabs on both sides, visible keyboard focus.

## 11. Motion system

### Timing tokens

| Token | Duration | Use |
|---|---:|---|
| Instant | 90 ms | Press/active feedback |
| Fast | 160 ms | Hover, focus backing, small disclosure |
| Standard | 240 ms | Menu/drawer content transition |
| Deliberate | 420 ms | Sheet snap, panel reflow |
| Scene | 800 ms | AOI focus settle/cross-fade |
| Camera | 2.4–3.8 s | Major Cesium camera move only |

### Easing

- UI enter/exit: `cubic-bezier(0.2, 0.8, 0.2, 1)`.
- Camera settle: `cubic-bezier(0.16, 1, 0.3, 1)`.
- Linear: only clock/satellite interpolation and scan texture moving at constant time.
- No spring/bounce; an orbital instrument should feel controlled.

### What animates

- Opening fly-in, AOI focus, sampled satellite interpolation, nominal swath translation/alpha, current-time scan, one T0 aperture pass, drawer/sheet transitions, selection underline, and data streaming reveals.
- Countdown numerals cross-fade per changed group; they never roll continuously.
- Skeletons use a slow 1.6 s luminance pass only while data work is active.
- Hover movement is limited to color/rule changes; buttons do not lift.

### What does not animate

- Text reflow, error messages, provenance content, pattern fills, selected imagery, and user-entered AOI vertices.
- No ambient starfield, floating particles, or perpetual glowing cards.

### Reduced motion

- `prefers-reduced-motion: reduce` sets UI duration to 1 ms and scene cross-fade to 120 ms.
- Opening camera cuts to the settled view through two cross-fades.
- Satellite and scan animations stop; pass replay becomes five manual steps.
- Pulses become persistent changes in stroke width plus text.
- Skeleton shimmer becomes a static placeholder.
- Smooth scrolling is disabled.

## 12. Cesium styling

### Runtime and imagery

- CesiumJS via pinned CDN version in the prototype; no `Cesium.Ion.defaultAccessToken` is set.
- The day globe uses the bundled NASA October 2004 Blue Marble. A 4,800 × 4,800, 20° × 20°
  crop from the 500 m source tiles is layered over each preset; source URLs, geographic bounds,
  hashes, and public-domain status live in `web/public/imagery/README.md`.
- Bundled NASA Blue Marble remains the offline base and last-resort imagery source.
- Hide ion-dependent widgets and services: geocoder, base-layer picker, terrain selector, and Cesium ion assets.
- Keep required Cesium attribution/credit visible. Product source attribution also appears in Evidence.
- Globe base color is Orbit 900 so missing tiles fail dark, not white.

### Imagery look

- October BMNG brightness 0.82 (0.72 while the pass sample window is active), contrast 1.13,
  saturation 0.82, gamma 0.92. Preset crops use brightness 0.88, contrast 1.12, saturation 0.86;
  day and preset layers preserve 35% alpha on the night side.
- The keyless EOX Sentinel-2 cloudless layer is probed once and appears only below 2,500 km camera altitude when reachable. Its licence and attribution remain visible in the source panel, and replay never waits for it.
- Use a subtle globe-edge vignette in the HTML layer, not a destructive imagery filter.

### Atmosphere and lighting

- Enable globe lighting when replay time is trustworthy; otherwise label the day/night display unavailable.
- Dynamic atmosphere lighting follows the one mission clock. Globe lighting and night fade
  distances are forced to 1/2 m so Cesium does not flatten lighting at pass-camera altitude;
  `dynamicAtmosphereLightingFromSun` is enabled.
- Atmosphere is per-fragment with intensity 12, hue shift −0.08, saturation shift −0.25,
  brightness shift −0.18. Bloom and sun bloom are off.
- Fog density stays low enough that the AOI is sharp at the settled 650–1,150 km views.
- Space/sky background is Night 950; sun and moon can remain disabled in the compact prototype if they distract.

### AOI

- Polygon fill: Opportunity at 6% opacity (12% at intersection) with no ambient breathing animation.
- A screen-stable set of four 1.5 px Opportunity corner brackets is at least 18 px across and is
  anchored to the AOI centroid; the 24 px leader label anchors southeast of the AOI.
- Outer bloom: 6 px equivalent at 16% opacity, one pulse only at geometric intersection.
- Vertices appear only in Edit mode; otherwise the AOI is an evidence target, not a drawing artifact.

### Ground tracks

- Selected orbital path: one 1.5 px Opportunity-strong line whose first and last 12% fade to zero;
  ground track: 1 px dashed Opportunity at 45%. The spacecraft entity does not draw a duplicate path.
- Other tracks: 1 px Frost at 22%, no glow. They appear only when the engine returned samples for
  that spacecraft over the same selected-pass window.
- The sampled-position path carries an 8-minute trail and lead around the mission clock.
- Tracks are sampled data supplied by the engine; the browser only interpolates display positions.

### Spacecraft

- Screen-fixed diamond/wing SVG, 18 × 12 px, without a bloom halo.
- Selected spacecraft uses Opportunity; others use Evidence/Frost and include A/B/C.
- Labels are HTML projected in `postRender`: Orbit 900 at 82% opacity, IBM Plex Mono 500 11/14,
  +0.04 em, with 1 px leaders. They flip sides and offset vertically on overlap. Phone shows only
  the selected spacecraft and AOI labels.
- Every glyph uses one `SampledPositionProperty` built from the engine's timestamps (Lagrange
  degree 5 at six or more samples, linear otherwise). Velocity controls glyph alignment.

### Swath material

- Nominal swath is a ground corridor/polygon approximately 290 km wide from supplied geometry.
- Swept base fill: Frost at 16% with 24% diagonal hatch on an 8 km world-space period, using a
  per-vertex engine-time attribute. Swept edges are 1 px Frost at 70%.
- Unswept geometry: Opportunity edges at 62%, 1 px, beginning at the current sample; there is no
  cyan evidence fill and amber never runs along the swept section.
- Aperture: one local 24-segment fan primitive. Its per-frame model matrix maps the fan apex to
  the sampled spacecraft and its base to the interpolated engine swath edges lifted 2 km. The
  translucent Frost material is additive, double-sided, and does not write depth. Explicit FOV
  edges are 1.25 px Frost at 85% over a 3 px Night-950 40% under-stroke. The 2 px Opportunity-strong
  base line uses a 0.25 glow and is the brightest mark on Earth.
- At T0, only the AOI aperture scan brightens. The whole swath does not flash.
- Legend says “Nominal swath,” and the opportunity card carries the non-acquisition warning.

### Camera controls

- Disable default Cesium double-click fly-to; app actions own the focus behavior.
- Allow rotate, pan, pinch, and wheel with conservative inertia.
- Any manual interaction cancels an in-progress scripted camera move immediately.
- Minimum altitude prevents clipping; maximum view retains a whole-Earth orientation.

## 13. Components

### App shell

- `AppHeader`: wordmark, AOI switcher, mode, clock, health, help.
- `ResponsiveWorkspace`: desktop rails/globe/deck or mobile globe/sheet.
- `SkipLink`: first focusable item.

### AOI

- `AOISwitcher`, `AOIPresetRow`, `AOISummary`, command-bar picker, `LayerControl` popover.
- `AOIDrawPanel`, `VertexList`, `AOIValidationMessage`.
- `ApertureBracket`: signature selected-state primitive.

### Globe

- `GlobeStage`, `GlobeLegend`, `GlobeToolbar`, `GlobeReadout`, `GlobeTextAlternative`.
- Cesium primitives/entities: `AOIEntity`, `TrackEntity`, `SpacecraftEntity`, `SwathEntity`.
- `PlaybackScrubber` and `ReplayClock` remain HTML for accessibility.

### Opportunity

- `NextOpportunityCard`, `Countdown`, `HonestyNote`, `PassPlaybackButton`.
- `OpportunityRail`, `OpportunityRow`, `IlluminationGlyph`.
- `LikelihoodInterval`, `LikelihoodRow`, `SampleStatement`.

### Archive/evidence

- `RecentLooksDeck`, `SceneCard`, `ScenePreview`, `MissingPreview`.
- `EvidenceStage`, `ViewModeTabs`, `SplitCompare`, `ResolutionCaption`.
- `AOIAccounting`, `ClassDistribution`, `ClassTable`, `TileContextRow`.
- `ObservationHistory`, `WorkingThreshold`, `HistoryFilter`.
- `EvidenceDrawer`, `ProvenanceSection`, `CopyField`, `AttributionList`.

### Feedback and system state

- `SourceHealth`, `StreamProgress`, `SkeletonBlock`, `InlineStatus`.
- `EmptyArchive`, `UpstreamError`, `OfflineReady`, `StaleInput`.
- `Toast` only for brief confirmation such as Copied; persistent problems remain inline.
- `Dialog` only for switching to Live data or discarding an edited AOI.

### Primitives

- Buttons: Primary, Secondary, Quiet, Icon, Destructive.
- `TextField`, `SearchField`, `Checkbox`, `Toggle`, `SegmentedTabs`, `Menu`.
- `Badge` variants: Replay, Live, Ready, Pending, Stale, Error, Illustrative.
- `Tooltip`, `Disclosure`, `Divider`, `DataLabel`, `MonoValue`.

## 14. Component behavior requirements

- Every visible control has hover, focus, active, disabled, loading where relevant, and a real interaction in the prototype.
- Primary buttons use Opportunity only for future-geometry actions and Evidence for evidence actions. Neutral actions use raised Orbit surfaces.
- Disabled controls retain readable labels and an explanation via adjacent text or tooltip.
- Tooltips appear after 500 ms hover/focus and never hold essential information.
- Menus close on Escape/outside press and return focus.
- Drawers/dialogs trap focus; bottom sheets do not unless modal.
- Filmstrip and opportunity rail support pointer drag, wheel/trackpad, and keyboard selection without hijacking page scroll.
- Status changes announce through a polite live region; errors use assertive announcement only when they block the requested action.

## 15. Voice and formatting

- Calm, exact, and operational. No “magic,” “AI-powered,” “perfect,” “guaranteed,” or “real-time” unless the data actually is.
- UTC format: `03 Oct 2026 · 06:18 UTC`; local secondary: `14:18 SGT`.
- Countdown: `02:18:14`; accessible expansion includes units.
- Coordinates: `1.27° N, 103.68° E`; full precision is available in Evidence, not the main rail.
- Percentages: whole number in hero, one decimal in accounting, two decimals only for supplied catalogue metadata.
- Large counts use locale grouping; scene IDs and hashes never truncate without a copy/full-value path.
- Use “scene,” “observation,” “geometric opportunity,” “recorded replay,” and “AOI.” Avoid “shot,” “capture,” “prediction,” or “forecast” for unsupported claims.

## 16. Responsive simplification

- Desktop keeps AOI selection, globe, opportunity decision, and recent looks simultaneously visible.
- Mobile keeps the globe, next opportunity, honesty note, and first recent look in the first viewport; secondary layers move into menus.
- Information is reordered, not removed. Evidence and the textual globe alternative remain complete.
- Long scene IDs wrap in Evidence and show abbreviated forms only in compact cards.
- On mobile, source health, layers, and attribution move to menu/accordion; next-opportunity and AOI state never do.

## 17. Prototype fidelity rules

- The real supplied scene preview appears only for its real scene ID/date.
- Missing scene previews use the designed placeholder; no duplicate image masquerades as another date.
- Real STAC tile-cloud values and OMM epochs use the supplied JSON.
- AOI clear values, opportunity times, and likelihoods are marked “Illustrative replay result.”
- The globe uses static sampled demo trajectories for visual interaction only; it does not suggest browser-side orbit propagation.
- Cesium credit remains visible, and the Evidence surface lists CelesTrak, Earth Search, and Copernicus attribution.
