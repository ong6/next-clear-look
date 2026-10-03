# Next Clear Look — product specification

Status: develop-phase product contract  
Viewport targets: 1440 × 900 and 390 × 844  
Binding source: `ncl-brief.md` and the product decision log.
Prototype clock: 2026-10-03 04:00 UTC, recorded replay

## 1. Product promise and product boundary

Next Clear Look answers one operational question for one place:

> When will Sentinel-2 next have a geometric opportunity to look here, and what did the last clear looks actually show?

It joins two things analysts currently reconcile by hand: future orbit geometry and recent AOI-level optical evidence. It does not promise an acquisition, forecast weather, recommend a response, or turn a tile-wide cloud property into an AOI claim.

The default experience is a deterministic offline replay. Live mode is opt-in and never required for the demo. Each estimate exposes its sample size and interval; each observation exposes the source scene, the AOI mask result, and provenance.

### Non-negotiable language

- Say **geometric opportunity**, never “capture,” “scheduled image,” or “guaranteed pass.”
- Say **historical clear-look likelihood**, never “weather forecast” or “chance of clear weather.”
- Say **AOI clear percentage** only when calculated over valid SCL pixels clipped to the selected polygon.
- Keep tile-wide catalogue cloud cover available as context, visibly labelled **tile cloud cover**.
- Mark prototype-only values as **illustrative replay result**. Do not let them resemble verified measurements without that label.

## 2. Personas and their weekly job

### Maya Tan — coastal evidence analyst

Maya works at a small environmental consultancy in Singapore. Every Monday she reviews Tuas and two mangrove-edge sites, decides whether the newest optical scene is usable over her actual study polygon, and plans field checks around likely fresh evidence. Before a monthly client brief she needs to show the exact pixels, clear/valid denominator, acquisition time, and source—not just a “cloudy” badge copied from a 100 km tile.

Her successful week:

1. Open saved AOIs and see what changed since the last review.
2. Verify whether recent imagery is clear over the AOI.
3. Identify the next few geometric opportunities.
4. Decide when to check again or schedule a field visit.
5. Export or cite the source scene and analysis provenance in her evidence note.

### Rafael Ortiz — rapid assessment analyst

Rafael supports an insurer’s disaster-response desk. After a flood, fire, or coastal event, he repeatedly checks when a usable post-event optical observation might appear. He needs an honest waiting picture: geometry now, historical likelihood over 7/14 days, and explicit uncertainty. He must distinguish “the satellite can pass here” from “an image will be acquired and cloud-free.”

His successful week:

1. Draw the incident footprint or choose a prepared AOI.
2. See the next opportunity and the complete 14-day likelihood window without reading orbital jargon.
3. Inspect the latest archive scene and its AOI-level usability.
4. Share a defensible status: what is known, what is only likely, and what inputs are stale.
5. Reopen the recorded analysis offline during a coordination call.

## 3. Core loop

1. **Choose the place.** Pick a preset, search a saved AOI, use the current view, or draw a polygon.
2. **Orient.** The globe focuses the AOI while the next Sentinel-2 ground track and swath settle into view.
3. **Read the wait.** See the next geometric opportunity, the 14-day opportunity rail, and the 7/14-day historical clear-look likelihood with interval and sample size.
4. **Inspect the evidence.** Scrub recent scenes; the globe, filmstrip, AOI clear percentage, SCL summary, and acquisition metadata stay synchronized.
5. **Verify the claim.** Open Evidence to see valid/clear pixel counts, tile-versus-AOI labels, source asset identity, OMM epoch, analysis clock, and replay/live status.
6. **Repeat.** Switch AOI or return when new recorded/live inputs exist. The selected AOI and filmstrip position persist locally.

The shortest useful loop is choose → read wait → inspect latest clear evidence. Provenance is one click away, never a separate expert mode.

## 4. V1 scope

### Must

- Default to the Tuas, Singapore AOI and a deterministic recorded replay.
- Render a CesiumJS globe without a Cesium ion token, with bundled NASA imagery as the offline base.
- Show Sentinel-2A, 2B, and 2C as distinct labelled spacecraft on sampled trajectories.
- Show luminous ground tracks and a translucent 290 km nominal swath representation.
- Show a countdown to the next **geometric opportunity** plus time, spacecraft, direction, daylight state, and freshness.
- Show every opportunity in the same 14-day window counted by the likelihood summary.
- Support preset AOIs and drawing a polygon; preserve a user-drawn AOI locally.
- Show every recent Sentinel-2 L2A scene for the AOI time window, including processing/empty/error states.
- Show AOI clear percentage from valid clipped SCL pixels, valid-pixel count, exclusions, and tile cloud cover as separate context.
- Show the real true-colour AOI image when available and a clearly labelled unavailable placeholder when not bundled.
- Show 7-day and 14-day historical clear-look likelihoods, honest intervals, and sample sizes.
- Keep raw evidence and provenance one click away.
- Work at 1440 × 900 and 390 × 844 with keyboard and screen-reader paths.
- Preserve all core reading and replay interactions offline.

### Should

- Compare two archive dates with a draggable split view.
- Offer an SCL overlay toggle and an inspectable legend.
- Save up to eight AOIs in local storage without accounts.
- Let the user copy a plain-language status summary with its uncertainty wording.
- Show source age warnings when OMM, catalogue, or AOI analysis inputs are stale.
- Offer a compact globe “camera reset” and a north-up option.
- Remember the replay position and reduced-motion preference.

### Won’t in V1

- Accounts, teams, shared workspaces, alerts, or notifications.
- Weather forecasts or numerical weather data.
- Claims about guaranteed acquisition, tasking, delivery time, or usable imagery.
- Sentinel-1, Landsat, commercial constellations, or global bulk indexing.
- Automated event attribution, change detection, legal shoreline delineation, or response recommendations.
- A 2D GIS editing suite, advanced layer catalogue, arbitrary CRS editing, or print-layout builder.
- Engine algorithms or a browser-side orbit/raster implementation.

## 5. Information architecture

There are two primary screens and two contextual surfaces:

1. **Mission screen** — globe, AOI control, next opportunity, likelihood, opportunity rail, recent looks.
2. **AOI detail** — large evidence comparison, SCL accounting, observation history, provenance.
3. **AOI picker/draw surface** — contextual panel over the mission screen.
4. **Evidence drawer** — contextual drawer available from both screens.

The app never opens on a marketing or onboarding page. The product itself is the first frame.

## 6. Screen-by-screen specification

### 6.1 Mission screen — 1440 px

#### Frame and grid

- Minimum canvas: 1440 × 900; page does not scroll.
- Top command bar: 60 px high.
- Work area: 840 px high, composed of a 1,096 px globe/evidence column and a fixed 344 px outlook rail.
- The recent-looks deck is a 136 px strip inside the bottom of the globe column. It uses fixed
  344 px scene cards; the outlook rail remains full height and never sits behind the deck.
- The two vertical regions are separated by a 1 px spectral rule, not floating rounded cards.
- Safe padding is 18 px at panel edges; core controls use a 44 px minimum target.

#### Top command bar

Left to right:

- Wordmark and aperture mark: “NEXT / CLEAR LOOK”. Clicking resets to the Mission screen without losing the AOI.
- Current AOI name: “Tuas reclamation edge”; opens AOI picker.
- Mode badge: “RECORDED REPLAY”; opens a two-option menu for Recorded replay and Live data. Choosing Live always asks for explicit confirmation because the demo guarantee changes.
- Deterministic clock: “03 OCT 2026 · 04:00 UTC”.
- Source health: three small labelled ticks for Orbit, Archive, Analysis. Color is reinforced by icon/word.
- Help button and keyboard shortcut button.

#### AOI access and layers

- The persistent left AOI rail is removed. The current AOI in the command bar opens the five-preset
  picker and Draw surface; rows retain name, locality, story tag, bounds glyph, and explicit
  Selected state.
- Globe layers live in a toolbar popover: Ground tracks, Nominal swath, AOI outline, Day/night,
  and Selected scene.
- Focus, north-up, and reset remain direct globe controls. Drawn geometry remains local to the
  browser and says so in the picker.

#### Globe stage

- Cesium fills the stage edge to edge behind quiet instrument overlays.
- The Earth is darkened and desaturated; atmosphere is a thin cobalt/cyan rim.
- The active AOI is a double-stroke polygon: solid amber core plus faint outer bloom.
- Every trajectory returned by the engine for the one shared time window is visible; the selected
  next-pass track is amber while other tracks are 1 px Frost at 22% opacity. Missing spacecraft
  are absent rather than browser-positioned.
- Spacecraft are 18 × 12 px diamond/wing apertures with fixed HTML labels driven by post-render
  projection and engine-sampled velocity alignment.
- The selected swath is a time-attribute strip: swept ground is Frost with diagonal hatch, future
  geometry is amber edges only, and an additive Frost aperture sheet ends at the push-broom line.
- One three-key legend sits bottom-left and identifies Opportunity, AOI, and Swept swath.
- The legend plate also carries `AOI` coordinates, integer `CAM` altitude, mission time/T offset,
  and the plain-language `Blue Marble Oct 2004` source label.
- A top-right camera cluster offers focus, north-up, and reset. Cesium’s default base-layer picker, timeline, and ion-backed search are absent.
- A hidden live region narrates camera, AOI, selected spacecraft, and intersection state.

#### Outlook rail

“Next geometric opportunity” is visually dominant:

- Spacecraft: Sentinel-2C.
- Countdown in tabular mono numerals.
- Absolute UTC and AOI-local time.
- Ascending/descending, daylight/twilight, and geometry freshness.
- Mandatory note: “An overpass is a geometric opportunity, not a promised acquisition.”
- “Play pass” starts a 12-second normalized playback; button becomes “Pause pass”.

“Historical clear-look likelihood”:

- Two rows: 7 days and 14 days.
- Each row uses a labelled probability, a confidence/credible interval whisker, and a sample count.
- Encoding is blue/cyan fill plus shape/pattern and text, never red-versus-green.
- Mandatory note: “Based on past AOI observations. Not a weather forecast.”
- “How this is labelled” opens a concise explanation; it does not expose engine implementation.

“Upcoming opportunities”:

- Next four rows with spacecraft, UTC time, daylight state, and minimum ground-track distance
  (for example, `12 km off-nadir`).
- Selecting a row changes the highlighted trajectory and the globe clock but not the AOI.

#### Observation deck

- One 24 px header row says “Recent looks” and “AOI true colour” once, with count, date span, the
  “AOI clear” definition link, and “Open AOI detail” on the same baseline.
- A horizontal filmstrip of scenes. Each card includes acquisition UTC, spacecraft,
  preview/placeholder, AOI clear percentage or analysis state, and tile cloud cover rounded to one
  decimal in secondary text. The repeated preview chip and identical valid-pixel count are omitted.
- The selected card has a cyan lower rail and an explicit “Selected” label.
- Scrubbing or using arrow keys updates the large evidence peek, globe acquisition time, and source readout.
- The first prototype card uses the real 2026-10-01 Sentinel-2C preview. Supplied-sample tile cloud cover is 37.94%; any prototype AOI result is labelled “illustrative replay result.”

### 6.2 Mission screen — 390 px

#### Frame and grid

- Viewport target: 390 × 844; body does not horizontally scroll.
- Compact header: 56 px. It shows the aperture mark, abbreviated AOI name, replay badge, and menu.
- Globe stage: 380 px high beneath the header (y=56–436).
- Bottom sheet begins at y=436, has a 16 px top radius and occupies the remaining height. During
  pass playback it collapses below a portrait globe that extends to y=700.
- Minimum touch target: 44 × 44 px. Edge insets: 14 px.

#### Mobile header and globe

- Tapping the AOI name opens a full-height AOI picker sheet.
- Health ticks collapse to one labelled “Replay ready” status in the menu.
- Camera actions collapse to one “Globe view” menu; double tap is never required.
- Track labels hide except for the selected spacecraft. The legend collapses to two inline keys: Opportunity and AOI.
- The globe screen-reader summary remains complete even when visual labels hide.

#### Mobile bottom sheet

Order is optimized for the decision:

1. Next geometric opportunity and countdown.
2. Play/Pause pass button plus exact UTC.
3. Fourteen-day opportunity rail, horizontally scrollable with snap points.
4. 7/14-day historical likelihood.
5. Recent-look filmstrip, horizontally scrollable.
6. Honesty notes and “Open AOI detail”.

The sheet has collapsed and expanded snap positions. Focus never moves merely because the sheet snaps. When the software keyboard opens, the AOI search field and results remain visible.

### 6.3 AOI detail — 1440 px

#### Layout

- Same 60 px command bar for orientation.
- Main canvas uses a 12-column grid with 24 px gutters and 24 px outer padding.
- Left eight columns: Evidence stage and observation timeline.
- Right four columns: AOI clear accounting, likelihood context, and provenance summary.
- The page may scroll; sticky right rail stops 24 px below the command bar.

#### Evidence stage

- Title: AOI name, selected scene date, spacecraft, and explicit data-state badge.
- Large 16:10 true-colour image clipped to the AOI bounds, capped at 768 CSS px unless a 1,536 px
  source is available. The prototype uses the real supplied Sentinel-2 preview and states that it
  is a scene preview, not an AOI crop.
- View toggle: True colour / SCL classes / Split compare.
- In Split compare, the handle is keyboard movable in 5% increments; the labels always include both acquisition dates.
- Image controls: fit AOI, 1:1 pixels when available, copy scene ID.
- A resolution caption names the imagery/SCL resolutions provided by analysis data and says when the shown preview is downsampled.

#### AOI clear accounting

- Large AOI clear percentage in sans tabular figures with 4 px before `%`, interval only if the
  analysis data provides one, valid/total pixel counts, and analysis timestamp. A null statistic
  says `Not reported`, never `–%`.
- Segmented distribution for Clear surface, Cloud, Cirrus, Shadow, Snow/ice, Unclassified, and No data. Each segment has distinct texture/icon plus color and an adjacent text table.
- Tile cloud cover appears in a separate muted row titled “Catalogue context”; it is never subtracted to infer AOI clear.
- “Show definition” expands the clear/valid labels and exclusions in product language.

#### Observation history

- Chronological rail with all returned scenes. Filters: All, Clear enough, Obscured, Processing.
- Threshold control is labelled “Working threshold” and affects only the user’s visual grouping. It never changes recorded pixel statistics.
- Selecting a scene updates the evidence stage and right rail, preserving the current viewing mode.
- Empty date ranges offer “Broaden date range”; no scene is silently omitted.

#### Provenance summary and drawer

- Summary rows: scene ID, acquisition UTC, platform, collection, grid tile, analysis fixture/live, source updated time.
- “Open evidence” opens the full drawer with source assets, checksums/identifiers when supplied, OMM epochs used for the geometry view, AOI geometry version, and recorded clock.
- Each item has a copy action. External source actions are disabled offline with the label “Available when online”; local recorded identifiers remain readable.

### 6.4 AOI detail — 390 px

- Compact sticky header with Back, short AOI name, and Evidence action.
- Evidence image is full width at 1:1 aspect ratio to respect the supplied preview; controls form a horizontal scroll row.
- AOI clear accounting sits directly below the image. The numeric label and category table remain visible without relying on the segmented bar.
- History is a horizontal date rail; filters open from one 44 px “Filter” button.
- Provenance is a normal accordion at the end of the page rather than a side drawer.
- Split handle remains at least 44 px wide, has visible focus, and supports left/right keys.

### 6.5 AOI picker and draw surface

Desktop and mobile begin from the AOI picker, then expose drawing controls over the real globe while leaving its point-entry surface visible.

- Tabs: Presets / Saved / Draw.
- Presets show exactly the five stories in section 10.
- Draw gives three actions: Start polygon, Undo point, Use this area. Escape cancels. Enter closes a valid polygon. A polygon needs at least three distinct points.
- Validation copy names the problem: self-intersection, too few points, or unsupported size. It does not say “Invalid input.”
- Committing an AOI immediately focuses the globe, then starts archive/orbit analysis states independently.

### 6.6 Evidence drawer

- Desktop: 464 px drawer from the right, over the globe or detail page.
- Mobile: full-height route-like sheet with Back.
- Sections: What this claim says; AOI and clock; Orbit inputs; Archive scene; AOI analysis; Attribution.
- The drawer is reachable from every derived number using the same Evidence action.
- Escape closes it and returns focus to its opener. Content remains selectable and copyable offline.

## 7. Globe camera choreography

### 7.1 Opening fly-in

Normal motion, first visit:

| Time | Camera and scene | Interface response |
|---:|---|---|
| 0.0–0.5 s | Start on a plain Night-950 field while Cesium draws; no placeholder Earth or spacecraft art is shown. The real globe starts at 17,000 km, centred on 92° E. | Wordmark and “Recorded replay” appear; controls are already keyboard reachable. |
| 0.5–3.8 s | Cubic ease to `lookAt(AOI, HPR(incomingBearing−18°, −64°, 9,000 km))`; phone uses −15° and a practical 7,200 km range so the disc runs off the 390 px frame. | The real October Blue Marble, atmosphere, AOI and returned engine tracks resolve together. |
| Pass engagement | A Play or scrub action moves to `HPR(incomingBearing−7°, −40.5°, 1,810 km)`, releases the look-at transform, then looks up 7°. | The mission clock, every sampled spacecraft, the aperture apex, push-broom line and swath progress update from the same timestamp. |
| At the closest approach | The descending Sentinel-2 pass arrives from the north-northeast on its south-southwest track. The push-broom line crosses the AOI and its outer bracket strengthens once. | The card reads `In swath · T+MM:SS`; copy continues to say geometric opportunity, never acquisition. |

The fly-in is interruptible by any pointer, wheel, touch, or keyboard camera input. The user wins immediately; no snap-back.

### 7.2 AOI focus

- A preset selection first shows the whole region at a height where the AOI occupies 16–22% of globe width.
- After 800 ms, the camera aligns the selected opportunity ground track within 15° of vertical and settles with the AOI below center.
- If no opportunity is available, the camera uses north-up, pitch −78°, and shows only the AOI; it never invents a track.
- “Focus globe” repeats only the second settle, not the global fly-in.
- Switching AOIs cross-fades track visibility after the camera starts moving to avoid a misleading track teleport.

### 7.3 Pass playback

- Total normalized playback: 12 seconds, labelled as a time-compressed replay.
- 0–3 s: T−6 min to T−90 s; the pass camera starts at a 1,810 km range and the engine-sampled spacecraft and swath approach.
- 3–8 s: T−90 s to T+90 s; the camera dollies toward a 1,600 km range and tracks the AOI, not the spacecraft. On entry the card changes to `In swath · T+MM:SS` and counts elapsed swath time.
- At the closest approach: AOI bloom pulses once, a vertical aperture scan crosses the polygon, and the screen-reader live region announces the geometric intersection. There is no shutter sound or “captured” animation.
- 8–12 s: T+90 s to T+6 min; the 1,600 km pass frame holds. The next-opportunity rail advances only after playback ends.
- Scrubbing updates camera, swath, satellite, and absolute time together. Releasing the scrubber does not auto-play.

## 8. Product states

### First load

- Recorded replay initializes without a network check.
- Wordmark, globe base, AOI, and honesty label render first; other panels may skeleton independently.
- First-use hint appears once: “Drag the globe. Press `P` to play the pass.” It dismisses after interaction or 8 seconds and remains available in Help.
- If WebGL is unavailable, replace the globe with a labelled static orthographic fallback and keep all decision panels usable.

### Loading and streaming analysis

- Separate progress rows for Orbit geometry, Archive search, AOI pixels, and Likelihood summary.
- The live progress card is opaque Orbit-850, anchored inside the desktop outlook rail and a normal
  in-flow section on phone; it never overlays the globe or bottom-sheet content.
- States are queued, reading sources, analysing AOI, ready. Show completed sections as soon as they are available.
- Filmstrip cards may enter individually. A card says “Analysing AOI pixels” until the clipped statistic is ready; tile cloud cover may appear earlier but remains labelled as tile context.
- The globe can animate recorded trajectories while archive analysis streams.
- Never use an indeterminate full-screen spinner after the first globe frame.

### Empty archive

- Headline: “No Sentinel-2 scenes in this window.”
- Body: “The AOI and opportunity geometry are still available. Broaden the archive dates to look for earlier observations.”
- Actions: “Broaden to 90 days” and “Review opportunities”.
- Likelihood shows “Not enough AOI observations” with sample size, not 0%.

### Upstream error

- The failed source is named: Orbit elements, Earth Search catalogue, or scene asset.
- Recorded replay remains selectable and is the primary recovery action.
- Example: “Live archive is unavailable. Recorded evidence is still ready.” Actions: “Use recorded replay” and “Try live again”.
- Derived values from stale cached inputs retain their last-updated time and a “Stale input” badge; they are not silently removed or presented as current.

### Offline replay

- Persistent badge: “Recorded replay · offline ready”.
- Deterministic clock and fixture timestamp remain visible.
- External-source buttons become “Available when online”; local source identifiers, thumbnails, analysis summaries, and provenance remain readable.
- No error toast appears merely because the browser is offline.

### Reduced motion

- Honor `prefers-reduced-motion` on first visit and offer an app override.
- Replace fly-in with two 120 ms cross-fades: world view → settled AOI view.
- Freeze atmosphere drift, aperture scan, path dashes, number rolling, and idle camera parallax.
- Pass playback becomes a five-step manual sequence: Approach, Nearing AOI, Intersection, Leaving, Complete. Previous/Next buttons and the scrubber remain.
- The T0 AOI state changes using stroke weight plus a persistent label, not a pulse.

## 9. Sixty-second demo script

The first 24 seconds require no clicks. The remaining 36 seconds demonstrate deliberate analyst actions. If nobody interacts, the app remains on the decision frame and loops the opportunity rail without changing AOI.

| Time | Viewer action | What happens | What the product says |
|---:|---|---|---|
| 0–4 s | None | Earth limb appears; camera flies toward Southeast Asia. | “Recorded replay” and the deterministic UTC clock establish truth before spectacle. |
| 4–9 s | None | Tuas AOI resolves; Sentinel-2C and its swath approach. | “Next geometric opportunity” appears with countdown. |
| 9–13 s | None | Swath intersects the AOI; the aperture scan crosses once. | “Geometric opportunity—not a promised acquisition.” |
| 13–18 s | None | Camera rests; 7/14-day likelihood whiskers draw and sample sizes appear. | “Historical likelihood. Not a weather forecast.” |
| 18–24 s | None | Recent-look filmstrip advances to the real 2026-10-01 scene preview. | Scene ID, acquisition time, and “tile cloud cover 37.94%” appear; prototype AOI values are labelled illustrative. |
| 24–30 s | Click **Play pass** | The normalized pass replay starts and the button becomes Pause pass. | Exact replay UTC updates; T0 is described as intersection, never capture. |
| 30–36 s | Click the 2026-10-01 scene | The globe clock jumps to acquisition time and the evidence peek selects the real preview. | “Scene preview · Sentinel-2C · 01 Oct 2026 03:37 UTC.” |
| 36–43 s | Click **Open AOI detail** | AOI detail view opens with the real preview and accounting rail. | Tile context and AOI result are visually separated. |
| 43–49 s | Choose **SCL classes** | Evidence image changes to the class legend treatment. | Clear/Cloud/Cirrus/Shadow/No data labels remain textual and patterned. |
| 49–55 s | Click **Open evidence** | Provenance drawer opens. | It shows recorded clock, real STAC scene ID, CelesTrak OMM epochs, and attribution. |
| 55–60 s | Press Escape, then keyboard-focus the timeline | Drawer closes to its opener; arrow key changes selected scene. | Screen-reader live text announces the scene and AOI analysis state. |

## 10. Preset AOIs

Coordinates are WGS84 rectangles in `[longitude, latitude]` order. They are product presets, not claims that a particular change has already been measured. Singapore is backed by the supplied verified sample; the other four need archive verification during implementation.

| Preset | Polygon corners | Why it tells a story | Cloud/climate contrast |
|---|---|---|---|
| **Tuas reclamation edge, Singapore** | `[103.600,1.200] [103.790,1.200] [103.790,1.365] [103.600,1.365]` | Rapidly evolving port/reclamation geometry makes “what did the last clear looks show?” tangible. It is first because the verified STAC/preview sample covers Singapore. | Equatorial humidity, haze, convection, frequent partial cloud. |
| **Maasvlakte port, Rotterdam** | `[3.880,51.840] [4.200,51.840] [4.200,52.030] [3.880,52.030]` | Large artificial coastline and port logistics create legible infrastructure change at Sentinel-2 scale. | Temperate maritime cloud and low winter sun. |
| **Salar de Atacama works, Chile** | `[-68.420,-23.720] [-68.050,-23.720] [-68.050,-23.320] [-68.420,-23.320]` | Evaporation ponds and mine infrastructure create strong colour/geometry patterns for archive comparison. | Arid, usually clearer; high-altitude brightness tests haze/snow-class honesty. |
| **Sundarbans western delta** | `[89.100,21.600] [89.750,21.600] [89.750,22.100] [89.100,22.100]` | Tidal channels, mangrove edges, and storm impacts make evidence timing operationally meaningful without implying automated attribution. | Monsoon seasonality and persistent tropical cloud. |
| **Jakobshavn ice front, Greenland** | `[-51.550,68.950] [-49.800,68.950] [-49.800,69.450] [-51.550,69.450]` | A large, recognizable ice-front/sea-ice boundary makes the archive filmstrip visually distinct. | Polar cloud, snow/ice classes, low sun, and seasonal darkness. |

## 11. Copy deck

Sentence case is used throughout. Numerals use UTC first; AOI local time is secondary. Angle-bracketed values are data substitutions, not literal strings. Prototype-only substituted values carry the visible phrase “Illustrative replay result.”

### Global and navigation

| Surface | String |
|---|---|
| Product mark | `Next Clear Look` |
| Main route | `Mission` |
| Detail route | `AOI detail` |
| Mode, default | `Recorded replay` |
| Mode, offline | `Recorded replay · offline ready` |
| Mode, live | `Live data` |
| Live confirmation title | `Switch to live data?` |
| Live confirmation body | `Live sources can be delayed or unavailable. Recorded replay remains available.` |
| Primary live action | `Use live data` |
| Cancel | `Keep recorded replay` |
| Health ready | `Replay ready` |
| Help | `Help` |
| Shortcuts | `Keyboard shortcuts` |
| Evidence | `Open evidence` |
| Back | `Back` |

### AOI controls

| Surface | String |
|---|---|
| Panel title | `Area of interest` |
| Search label | `Find an area` |
| Search placeholder | `Search saved areas` |
| Tabs | `Presets`, `Saved`, `Draw` |
| Selected marker | `Selected` |
| Draw action | `Draw area` |
| Draw instruction | `Choose at least three points. Press Enter to close the area.` |
| Draw actions | `Undo point`, `Clear`, `Use this area`, `Cancel` |
| Too few points | `Add at least three distinct points.` |
| Self-intersection | `The boundary crosses itself. Move or remove a point.` |
| Too large | `This area is larger than the replay supports. Draw a smaller area.` |
| Local-only note | `Geometry is stored in this browser.` |
| Selected section | `Selected area` |
| Metadata labels | `Centre`, `Area`, `Last analysed` |
| Actions | `Focus globe`, `Edit area`, `More actions` |
| Layers | `Layers` |
| Layer labels | `Ground tracks`, `Nominal swath`, `AOI outline`, `Day and night` |
| Camera labels | `North up`, `Reset view`, `Globe view` |

### Opportunity and likelihood

| Surface | String |
|---|---|
| Card heading | `Next geometric opportunity` |
| Countdown accessible label | `Time until next geometric opportunity: <duration>` |
| Direction values | `Ascending`, `Descending` |
| Illumination values | `Daylight`, `Low sun`, `Night` |
| Mandatory note | `An overpass is a geometric opportunity, not a promised acquisition.` |
| Playback actions | `Play pass`, `Pause pass`, `Replay pass` |
| Playback badge | `Time-compressed replay` |
| T0 label | `Swath intersects AOI` |
| Likelihood heading | `Historical clear-look likelihood` |
| Horizon labels | `Within 7 days`, `Within 14 days` |
| Interval label | `<low>–<high>% interval` |
| Sample label | `Based on <n> past AOI observations` |
| Likelihood note | `Based on past AOI observations. Not a weather forecast.` |
| Explanation action | `How this is labelled` |
| Explanation | `This is a historical likelihood for this AOI and horizon. It does not use a weather forecast and does not guarantee an acquisition.` |
| Opportunity list | `Upcoming opportunities` |
| No next opportunity | `No geometric opportunity in this replay window` |

### Archive and AOI detail

| Surface | String |
|---|---|
| Deck title | `Recent looks` |
| Definition action | `What AOI clear means` |
| Definition | `AOI clear is the share of valid scene-classification pixels inside this boundary that are labelled clear surface.` |
| Detail action | `Open AOI detail` |
| Analysis ready | `<percent>% AOI clear` |
| Prototype result | `Illustrative replay result` |
| Analysis pending | `Analysing AOI pixels` |
| Valid pixels | `<count> valid pixels` |
| Tile context | `<percent>% tile cloud cover` |
| Selected card | `Selected` |
| Preview source | `Scene preview` |
| Missing preview | `Preview not bundled` |
| View modes | `True colour`, `SCL classes`, `Split compare` |
| Image actions | `Fit AOI`, `View 1:1 pixels`, `Copy scene ID` |
| Downsample note | `Preview is downsampled. Pixel accounting uses the AOI analysis source.` |
| Accounting title | `AOI clear accounting` |
| Class labels | `Clear surface`, `Cloud`, `Thin cirrus`, `Cloud shadow`, `Snow or ice`, `Unclassified`, `No data` |
| Catalogue context | `Catalogue context` |
| Tile warning | `Tile cloud cover describes the full Sentinel-2 tile, not this AOI.` |
| Definition toggle | `Show definition`, `Hide definition` |
| History | `Observation history` |
| Filters | `All`, `Clear enough`, `Obscured`, `Processing` |
| Threshold | `Working threshold` |
| Threshold help | `Used only to group observations in this view. Recorded pixel statistics do not change.` |

### Loading, empty, error, and offline

| Surface | String |
|---|---|
| Focus status | `Focusing <AOI>` |
| Stream stages | `Orbit geometry`, `Archive search`, `AOI pixels`, `Likelihood summary` |
| Stage values | `Queued`, `Reading recorded source`, `Analysing AOI`, `Ready` |
| Empty title | `No Sentinel-2 scenes in this window` |
| Empty body | `The AOI and opportunity geometry are still available. Broaden the archive dates to look for earlier observations.` |
| Empty actions | `Broaden to 90 days`, `Review opportunities` |
| Low sample | `Not enough AOI observations` |
| Archive error | `Live archive is unavailable. Recorded evidence is still ready.` |
| Orbit error | `Live orbit elements are unavailable. Recorded geometry is still ready.` |
| Asset error | `This scene asset could not be read. Its catalogue record is still available.` |
| Recovery actions | `Use recorded replay`, `Try live again` |
| Stale | `Stale input · last updated <time>` |
| Offline external action | `Available when online` |
| WebGL title | `3D globe unavailable` |
| WebGL body | `Opportunity times and recorded evidence are still available below.` |

### Provenance and attribution

| Surface | String |
|---|---|
| Drawer title | `Evidence and provenance` |
| Sections | `What this claim says`, `AOI and clock`, `Orbit inputs`, `Archive scene`, `AOI analysis`, `Attribution` |
| Identifiers | `Scene ID`, `Acquired`, `Platform`, `Collection`, `Grid tile`, `OMM epoch`, `AOI geometry`, `Analysis time`, `Replay clock` |
| Copy feedback | `Copied` |
| Source action | `Open source record` |
| CelesTrak attribution | `Orbit elements: CelesTrak GP data. Cached and attributed under the CelesTrak usage policy.` |
| Earth Search attribution | `Catalogue: Element 84 Earth Search, Sentinel-2 L2A.` |
| Copernicus attribution | `Contains modified Copernicus Sentinel data.` |

### Help and accessibility strings

| Surface | String |
|---|---|
| First-use hint | `Drag the globe. Press P to play the pass.` |
| Globe label | `Interactive 3D globe showing the selected AOI and Sentinel-2 opportunities` |
| Globe state summary | `<AOI>. Camera at <altitude>. Next geometric opportunity is <spacecraft> at <UTC>. The selected nominal swath <does/does not> intersect the AOI at the replay time.` |
| Intersection announcement | `Nominal swath intersects <AOI> at <UTC>. This is a geometric opportunity, not a confirmed acquisition.` |
| Scene announcement | `Selected <scene ID>, acquired <UTC> by <platform>. AOI analysis is <state>.` |
| Reduced motion label | `Reduce motion` |
| Shortcuts list | `P: play or pause pass. F: focus AOI. N: north up. E: open evidence. Left and right arrows: change selected time or scene.` |

## 12. Accessibility specification

### Keyboard path

1. Skip link: `Skip to opportunity summary`.
2. Header: product mark → AOI picker → mode → health → Help → Shortcuts.
3. AOI rail: search → presets → draw → selected-area actions → layers.
4. Globe toolbar; the WebGL canvas itself is not a keyboard trap.
5. Next opportunity → pass playback → likelihood explanation → opportunity list.
6. Recent-look filmstrip → AOI detail.
7. Evidence drawer, when open, traps focus and returns it to the opener on close.

Additional behavior:

- `P` plays/pauses the pass except while typing.
- `F` focuses the AOI; `N` sets north up; `E` opens evidence.
- Arrow keys change a focused opportunity/scene. Home/End move to first/last.
- Escape cancels drawing, closes menus/drawers, or exits split-handle adjustment in that order.
- Polygon drawing has a parallel coordinate-entry/list path so precise input does not require a pointer.

### Focus and targets

- Visible 2 px focus ring plus 2 px offset; focus color is `--focus-ring` and passes 3:1 against adjacent surfaces.
- Touch targets are at least 44 × 44 px; desktop compact rows may be 36 px high only when the internal button target remains 44 px.
- Hover never reveals information unavailable to focus or touch.

### Contrast and color

- Body text and critical labels meet WCAG 2.2 AA (4.5:1); large display text meets 3:1.
- UI boundaries and data marks meet 3:1 against adjacent colors.
- Clear percentages use label + number + bar length + texture. Clear is cyan with diagonal clear-space hatching; mixed is amber with dot texture; obscured is magenta with crosshatch; unknown is slate with dashed outline.
- Selected, error, stale, and ready states always include a word or icon shape, never color alone.

### Globe alternative and announcements

- The globe container has the accessible label in the copy deck and points via `aria-describedby` to a live textual summary.
- The summary updates only on settled AOI/camera changes, selected opportunity changes, and T0. It does not narrate every animation frame.
- A sibling “Globe data” disclosure lists spacecraft, selected track time range, AOI coordinates, and current intersection state in plain text.
- Decorative orbital glows and scan textures are hidden from assistive technology.
- If WebGL fails, the alternative summary and all opportunity/archive controls remain in normal document order.

### Motion and media

- All non-essential continuous motion stops under reduced motion.
- Playback always has Pause and a scrubber/manual-step alternative.
- No audio is used; no information depends on sound.
- Imagery alt text names place, source scene, acquisition date, platform, and whether the image is a scene preview or AOI crop. It does not invent visible change.

## 13. Data needs

This section defines screen inputs only. It intentionally does not specify APIs, engine algorithms, transport, or storage.

### App/replay context

- Mode: recorded replay or live.
- Deterministic/current UTC, playback range, playback rate, offline availability, bundle/version identifier.
- Per-source readiness, last-success time, staleness status, and human-readable failure reason.

### AOI

- Stable AOI ID, name, story/climate tags, source (preset/saved/drawn), GeoJSON polygon or multipolygon, centroid, bounds, area, timezone, created/updated time, and geometry version.
- Validation status and limitations supported by the current replay.

### Orbit display

- Spacecraft identity, display name, NORAD catalogue ID, color/shape key, OMM epoch and source identity.
- Compact time-stamped ECEF/geodetic trajectory samples suitable for browser interpolation.
- Ground-track positions, nominal swath polygons/corridors, validity interval, daylight/illumination label, and source freshness.
- No browser-computed propagation is required by the screen.

### Opportunities

- Opportunity ID, AOI ID/version, spacecraft, start/closest/end UTC, direction, intersection state, nominal swath geometry, playback sample window, illumination label, geometry freshness, and provenance reference.
- Explicit field saying the record is a geometric opportunity, never an acquisition promise.

### Archive scenes

- STAC item/scene ID, collection, platform, acquisition UTC, updated UTC, tile/grid ID, footprint, tile cloud cover, source link/identifier, and available asset roles.
- Preview/AOI-crop image reference, dimensions, pixel resolution, crop status, offline availability, and alt-text fields.
- Analysis state per scene: queued/reading/analysing/ready/failed plus safe reason.

### AOI clear accounting

- AOI and geometry version, scene ID, analysed UTC, valid/total/no-data pixel counts.
- Counts and percentages for clear surface, cloud, thin cirrus, cloud shadow, snow/ice, unclassified, and no data.
- AOI clear percentage, denominator definition, exclusions, source SCL identity/resolution, preview/crop relationship, fixture/live label, and provenance reference.
- Tile cloud cover remains a separately named catalogue input.

### Historical likelihood

- AOI/version, horizon (7/14 days), central estimate, lower/upper interval, sample size, observation window, last analysed UTC, fixture/live label, and a short approved method label.
- Flags for insufficient sample and exclusions. The screen needs no model internals.

### Evidence/provenance

- Human-readable claim, source names, identifiers/URLs when allowed, input timestamps/epochs, cache/fixture identity, checksums where available, attribution strings, licence/usage-policy link labels, and whether each source can open offline.

### Prototype data note

The prototype includes the supplied real CelesTrak Sentinel-2 OMM JSON, Earth Search Singapore STAC JSON, and the real `S2C_48NUG_20261001_0_L2A` preview. The three real scene timestamps and tile-cloud properties are used as supplied. AOI statistics, opportunity times, and likelihood values in the visual prototype are interaction fixtures and are visibly labelled “Illustrative replay result”; they are not presented as measurements from the partial binary samples.

## 14. Acceptance notes for implementation

- A first-time viewer can state the next geometric opportunity, the uncertainty boundary, and the latest evidence source within 30 seconds.
- A keyboard-only user can choose an AOI, play/step a pass, select a scene, and open/close evidence.
- The app remains coherent with network disabled after its recorded bundle and Cesium runtime are available.
- No screen calls a geometric opportunity a capture or historical likelihood a weather forecast.
- The AOI and tile statistics are never visually conflated.
- At both target sizes, the next opportunity, honesty note, and at least one recent look appear in the first viewport.
