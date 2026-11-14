# HANDOFF - 2026-11-08 - patches 0039 and 0040

Read the short hand-off brief first. Patches 0001-0038 are on GitHub; 0039 and 0040 are new.

## Patch 0045: the Dīvi name, logo and colours
- The project is now presented as **Dīvi** (दीवि; "Fly. Analyze. Decide."): header, tab title,
  footer, welcome, CLI help, README, phone page and manifest. The package, the `avispria`
  command, the settings folder, the theme storage key and the repository keep the old name until
  a full rename (a separate decision: it changes the command and the GitHub URL).
- Logo: `branding/logo-source.png` (founder's, transparent, stored at 2048 px);
  `scripts/make_branding.py` rewritten (dark variant lifts the slate drone, 256-colour screen
  copies, home-screen icons). Old jpg source and drone-redraw code removed.
- Colours (`theme.py`) measured from the logo: vegetation `#669762` = primary, agriculture
  `#DBB241` = highlight, urban `#7A96AA` = secondary, drone slate `#47545E`; errors have their
  own brick red (`danger*` fields, new). Light: mist page; dark: a near-black telemetry console
  with glowing text shades and cobalt/green data overlays. All 70 contrast pairs pass.
- **Bug found in a real browser (it predates this patch):** NiceGUI writes its own blue
  `--q-primary` onto `<body>` and loads Quasar's `!important` rules in a CSS layer that beats
  unlayered `!important`, so buttons, badges and links had always been NiceGUI blue, and white
  labels sat on coloured buttons. Fixed: Quasar variables set `!important` on `body`, and the
  whole theme injected inside NiceGUI's `overrides` layer (`layout.themed_css`). Verified with
  Playwright: button `#669762` with `#10181C` label, links `#3D6B3A` (light) / `#8FD18A` (dark).

## Patch 0043: one analysis engine for forest, farm and town (urban mapping)
- `core/profiles.py` (forest, farm, urban thresholds), `core/shade.py` (shadow from DSM + sun,
  array-shift ray walk), `core/landcover.py` (11 classes + confidence; buildings = smooth,
  not-green, raised cells closed/filled, kept whole if they have a core, grown 1 m into the rough
  rim), `core/buildings.py` (height, floors, roof slope = median of face slopes, rooftop green),
  `core/roads.py` (distance-transform width, elongation >= 3, street trees within 8 m, gaps >
  1.5x spacing), `core/surface.py` (the engine and the town numbers incl. 30/300 rules and street
  shade at 14:00 on the flight day).
- `app/surface_workflow.py` + `avispria analyse --profile`: runs canopy (without its own crowns),
  the engine, writes results/analysis/* and the single crowns file (with on_street). `process`
  runs it after processing with the profile chosen on Make maps ("What did you map?") or
  `--profile`; provenance records the profile and the sun's day and UTC offset.
- Synthetic town (tests/cityscene.py), 3 seeds: 98-99% of all cells right, footprints exact,
  gable slope 18.4 deg, rooftop garden 36 m2 within 7%, road width 8.0 m, 5 street trees and the
  missing one found. Real first flight: 0.3 s, canopy 70% (agrees with canopy.py), the building
  outlined, LC001 low confidence (sunset).
- Bugs found and fixed while building it: grey noise read as green (majority vote, not blur: blur
  moved edges), building corners lost to the opening (keep whole pieces with a core), a
  one-cell rim missing from footprints (grow into raised cells), gable read as flat (one plane
  averages the faces), one missing tree = exactly 2x spacing (gap rule 1.5x), numpy types in JSON.

## Patch 0040: the sun, and single tree crowns
- **The first flight was flown at sunset**: photo times 16:56-17:07 local, sun 3.4 to 1.0
  degrees up (shadows 17-57x the tree height). This, not only the camera settings, explains the
  slow shutters, the 23% ground visibility and the poor matching. Good window at 24 N in November:
  sun >= 35 degrees from about 09:10 to 14:10.
- `core/sun.py`: USNO low-precision solar position; `good_window` (sun >= 35 degrees) shown on
  the plan result ("light-window" card, this computer's clock); `photo_light` gives the sun during
  the photos. DJI clocks are local with no zone: the computer's UTC offset is used when within 2 h
  of the longitude's solar zone, else longitude/15 (recorded as `time_basis`). QA021 below 25
  degrees. Provenance gets `sun`; the canopy summary `sun_elevation_deg`.
- **New dependency: scipy** (decided with the founder: scipy only, not scikit-image; +36 MB
  download, ~115 MB installed). Used by `core/crowns.py` only.
- `core/crowns.py`: tree tops in a height-scaled window (1.5-4 m), marker watershed
  (`ndimage.watershed_ift`), per-crown height/area/diameter, CIE L*a*b* colour, share not green,
  structure flag (pixels flat within 1.5 m (sd < 0.15 m) and not green; or a planar crown),
  dieback candidate (>= half the crown's leaf pixels not green). CH003 when the sun is below 25.
  Written as `canopy/crowns.geojson` (WGS84) and `crowns.csv`; "Your forest" shows trees,
  dieback candidates and the sun. On the first flight: 248 crowns, 6 structures (the building),
  1 candidate (a small brown roof inside a tree crown: a false positive), all unreliable (sun 3).
- Prototype findings: dieback by colour works mechanically; its main confounder is buildings
  (now masked) and low sun. Shadow-height checking needs sun 25-55 degrees: not possible on this
  flight; to do after a midday flight.
- tests/photorecords.py: PhotoRecord builder shared by sequence and sun tests (tests/photobuild.py
  is a different, older helper for JPEG files: do not overwrite it).


## Patch 0039: findings of the first real Lito X1 flight, and the fixes
Flight: 73-waypoint mission, flown twice (two passes), 79 JPEGs of 48 MP, processed with Standard.
Results (orthophoto, DSM, textured model) completed: 67/79 photos placed, reprojection 0.82 px.
- **Last waypoint kept shooting**: DJI Fly photo size was 48 MP; the camera then needs ~6.5 s per
  photo (measured 5-7 s) while the plan asked for one every ~1.9 s. Triggers queued; photos fell
  between waypoints (up to 16 m off), ~19 per pass were never taken, and the queue emptied while
  the drone hovered at the last waypoint (5 + 3 photos at speed 0). The mission file is not at
  fault (last waypoint has no action). drones.toml: 48 MP min_interval_s 5.0 -> 6.5 (verified).
- **Blur**: DJI Fly Auto exposure chose 1/20-1/80 s at ISO 100 (plan assumed 1/1000 s): 6-25 cm
  of motion per photo at 4-6 m/s. Fly screen now has a camera-settings card (12 MP, Pro (M),
  1/1000 s, ISO Auto).
- New `core/sequence.py` (photos only, no plan needed): QA017 hovering repeats, QA018 repeated
  pass over the same ground (keeps the sharper pass), QA019 camera slower than 4 s per photo,
  QA020 exposure longer than 1/400 s. Check photos shows them; `process` leaves hover repeats and
  the repeated pass out (ProcessRequest.keep_repeats / "Use every photo" switch) and records
  `photos_left_out` in provenance.
- **"8-minute flight in 2 missions"**: the split came from the 99-waypoint limit (a photo at every
  waypoint uses one per ~11 m), not the battery. New PL004 says so and that the missions can be
  flown back to back on one battery. New Advanced field "Waypoints per mission" (10-200, default
  99); the Lito profile's cap is raised to 200 (users report 200; only 99 is verified).
- **Pages lost their contents** when moving between steps (NiceGUI rebuilds a page on every
  visit). New `ui/drafts.py`: in-memory only (coordinates never go to disk) store of every value
  widget of Plan, Check and Make maps, the drawn shapes and take-off pin, and the last plan result.
  "Start a new plan" clears it.
- Map: satellite background (Esri World Imagery, attributed; default when the background is
  switched on, Streets still offered); "Click to set take-off" button.
- Plan screen: "Show the missions on my phone" lists DJI Fly's missions with map picture, made and
  changed time (date AND time now), and "Use as my sample mission" (shared `pages/slot_list.py`).
- **Canopy** (the scientific goal, open item 3): `core/canopy.py` (progressive morphological
  ground filter, canopy height, cover, gaps, p50/p95, tree tops by local maxima, excess-green
  mask for roofs/vehicles), `app/canopy_workflow.py` (`avispria canopy <results>`, runs
  automatically after processing; writes results/canopy/chm.tif, chm_preview.png,
  canopy_summary.json; summary in provenance), "Your forest" section on Make maps. Standard preset
  now asks for the DTM. Guide: docs/field/canopy.md. On the first flight (about 3.4 ha mapped): cover 70%,
  gaps 25%, median canopy height 14.2 m, p95 24.6 m, 248 tree tops (~74/ha), ground seen in 23%,
  4% tall-not-green (a roof), ground estimated (no DTM was asked for then). NOT validated against
  field-measured trees.
- Processing warns when 48 MP photos are processed at 12 MP (the maps lose ~2x resolution).
- GPS agreement: shown as horizontal (1.9 m on the flight) and vertical (20 m: DJI altitude,
  normal) instead of ODX's 19 m average, which is almost all vertical.
- explain.py split (explain_base.py, explain_more.py) to stay under the soft line limit.

## Next
1. Re-fly the same area: 12 MP, Pro (M) 1/1000 s, one pass. Expect photos at the waypoints, no
   hover burst, sharp photos. Process Standard (now with DTM) and compare the canopy numbers.
2. Measure 5-10 trees in the field (height, crown width) to validate the canopy model.
3. Try 150-200 waypoints in one mission once; if DJI Fly accepts it, raise the default.
4. Still open: DJI Fly showed 1:09 vs planned 1:34 (the flight itself took ~4 min per pass:
   the slow camera likely held the drone back); the 3D preset in Make maps; resume-from-waypoint
   missions for interrupted flights; does DJI Fly offer to continue an interrupted mission?

---

# Earlier sessions
## Session #4, 2026-10-30 (doctor, engine, processing, terrain-aware QA, planner, window interface)
## Done this session
- `doctor`: RAM/swap/CPU/disk + verdict with real alternatives (ODM RAM table);
  finds the native WebODM app by its processes/ports; `--details`.
- `engine`: finds WebODM's NodeODX, reads its token from the running command line
  (memory only), connects via PyODX (BSD-3), lists 80 supported options.
- `process`: photos -> QA -> engine -> feasibility -> presets (only supported options;
  rolling-shutter for electronic shutters) -> 12 MP resize keeping EXIF+XMP -> upload ->
  progress -> all.zip + extracted results -> provenance JSON with SHA-256s.
- CLI split into modules (cli.py had hit the 400-line limit).
- Planner over terrain (core/predict.py, plan_model.py, plan_path.py): predicts the plan's real
  resolution/overlap/coverage from the actual height above the surface at each planned photo
  (same analyse_capture as QA, over the AOI). Terrain following used to lift the drone far above
  the requested height (margin 10 m + dilation + slope limits): 40 m hill target 2.0 cm/px gave
  2.73. Now a calibration loop (<=4 passes, keeps the most consistent) moves the route's
  reference height until the MEDIAN height above surface = target, never below
  min_surface_clearance - margin, and computes spacing for the 10th-percentile height.
  Warnings PL001 (typical GSD off by >15%), PL002 (coarsest tenth >30% worse), PL003.
  `--surface-height` = canopy allowance; `--no-calibrate` keeps the old behaviour.
  QA now reports front/side overlap separately (QA014: side < 50%).
- Look and feel: ONE palette in src/avispria/app/ui/theme.py (LIGHT/DARK dataclasses, tokens_css(),
  contrast_ratio(); tests/ui/test_theme.py measures 61 pairings). Brand colours are used as FILLS; where
  small text is needed a derived shade is used (link green #1B766B, dark text #74C69D, etc.). NiceGUI:
  assets/avispria.css (variables only) + ThemeState (theme_state.py) + header logo/toggle in layout.py;
  charts take a Palette and redraw on toggle (widgets.echart(builder)); the browser announces its theme
  via the `avispria_theme` event, the server never awaits JS replies (they hang under the simulated user).
  Phone page: css/theme.css and js/theme.js are GENERATED from theme.py by scripts/field_page.py.
  Logo: designed by the founder, coloured with an AI tool; branding/ + scripts/make_branding.py
  (cut-out, the navy X REDRAWN AS A DRONE - rings variant A chosen by the founder because the original X
  read as a windmill; test counts 4 rotor openings + camera hole; dark variant, icons). LOGO LICENCE
  UNDECIDED (branding/README.md). NOT verified: how either interface looks in a real browser (previews of the phone
  page were rendered with WeasyPrint, approximate). Test pitfalls: never `from main import ...` in a
  NiceGUI test (it runs ui.run); patch objects, not dotted paths, after page tests; type() appends.
- Phone field page (field-page/, PWA, no build step, no dependencies): checklists, calculators
  (js/calc.js = port of camera.py/speed.py/sorties.py, tested against tests/field_page/golden.json
  produced by the REAL planner), flight log with geolocation + CSV, offline via sw.js. Published by
  .github/workflows/pages.yml (Pages Source must be "GitHub Actions"; actions pinned: configure-pages
  v6.0.0, upload-pages-artifact v5.0.0, deploy-pages v5.0.1). `python scripts/field_page.py` regenerates
  js/generated.js (from drones.toml), golden.json and the sw.js asset list + BUILD id; pytest fails if stale.
  Strict CSP (no inline script/style, no outside hosts) is tested. Node tests: tests/field_page/*.test.mjs
  (pytest runs them if node exists; GitHub runners have it). tests/field_page/dom_check.mjs is a manual
  developer tool (needs a scratch jsdom install; see its header). NOT verified: a real phone/browser.
- Window interface (NiceGUI 3, local only: 127.0.0.1): `divi ui` / Start-Divi.bat.
  app/ui/: explain.py (plain-language text for all 49 issue codes; a test fails if a code
  lacks one), views.py + views_results.py (pure view models), charts.py (ECharts options),
  plan_job.py / process_job.py (forms as plain data + validation + execution, tested without a
  browser), jobs.py (background threads, QueueReporter, friendly errors), widgets.py (folder
  browser, banners, tiles), pages/ (home, check, plan, process). Screens: Start, Check my
  photos, Plan a flight, Make maps (progress, Cancel, results).
  Cancel: engine.wait(should_cancel) + ProcessRequest.cancel (tested with a fake engine whose
  task never ends). Photo size for processing is a real choice (12/8/6/4/3 MP, full).
  Survey rectangle from numbers: core.geometry.rectangle_polygon.
  TESTING: NiceGUI's simulated `user` runs on the AnyIO plugin (no pytest-asyncio needed);
  main file tests/ui/ui_main.py via the nicegui_main_file marker. NiceGUI quirks: simulated
  type() APPENDS (use clear() first: uihelpers.set_text); it cannot click ui.toggle options
  (use ui.radio); background handlers need `eventually(...)`. tests/ui/test_server.py starts
  the REAL server in a child process (env without PYTEST_*/NICEGUI_*, or NiceGUI enters its
  own test mode), requests every screen and checks it listens on 127.0.0.1 only.
  NOT verified: how it looks in a real browser, the Windows-only parts (drive buttons in the
  folder browser, "Open the folder"), no persistent settings, prepare-copy not in the UI.
- Make maps engine discovery: system_probe.find_engine() = the Windows app's nodeodx PROCESS, else NodeODX at
  its standard address http://localhost:3000 without a token (Docker; `docker run -p 3000:3000
  opendronemap/nodeodm`); the screen has optional Engine address/token (Advanced). ONLY the Windows app
  route has been tested with real WebODM; macOS/Linux/Docker is untested (and Apple Silicon needs an ARM
  image). Launchers: Start-Divi.bat (Windows), start-divi.sh + Start-Divi.command (Linux/macOS;
  keep the executable bit and LF endings; tested). README rewritten with install steps per OS;
  tests/test_docs.py keeps it in step with the CLI.
- Forest dataset (docs/datasets.md): ODM's helenenschacht (Autel EVO II Pro RTK, 176 photos, 2.4 GB, RAW
  PHOTOS ONLY, no DSM/DTM). The sandbox (7 GB disk, 3 GB RAM, 1 thread) cannot run photogrammetry, so only
  the 46 MB of photo HEADERS (range requests) + 6 full photos were fetched. It exposed that QA needed a
  relative altitude (DJI-only): now a photo has a height if it records one above takeoff OR one was
  worked out (elevation model, or `qa --ground-elev M` / the Check screen field); QA015 (no height above
  ground) and QA016 (camera angle not recorded, assumed nadir) added. Finding for later: `process` does not
  upload ODM's gcp_list.txt (GCP support missing); camera-from-photo labels 19.96 MP as "19mp".
- PHONE BRIDGE (built, docs/field/phone-bridge.md): `avispria phone status|slots|pull|send|pair|connect` and the
  Phone screen. RESEARCH behind it: DJI Fly has NO import/export of waypoint files; a mission folder DJI Fly did not
  create is NOT listed even with image/ShotSnap.json and map_preview/<ID>/ added (founder tested, 2026-10-30), so
  the only route is to OVERWRITE a placeholder ("slot") mission's <ID>/<ID>.kmz in
  Android/data/dji.go.v5/files/waypoint/ (the founder's method). Since Android 13 no phone app can touch that
  folder, so the PC does it over adb (USB or Wireless debugging): no Dīvi phone app. Safety design in
  app/phone_workflow.py: lint first, back up the original to ~/Divi/phone-backups, push to <ID>.kmz.avispria-new,
  verify sha256 on the phone, mv into place, verify again, restore on failure; ids/paths/serials validated because
  adb shell hands arguments to the phone's shell. adb is NOT bundled (user downloads platform-tools; found on PATH,
  ~/Divi/platform-tools, ANDROID_HOME, or chosen on the screen). A real DJI Fly mission folder holds the .kmz +
  image/ShotSnap.json ({"POI_POINT":{},"WAY_POINT":{}}) + map_preview/<ID>/<ID>.jpg (480x360 Google map picture:
  never redistribute) and a capability/ folder (same as our fixture). VERIFIED on the founder's Redmi over USB:
  adb devices, ls of the waypoint folder, push + rm of a file there. NOT verified on a real phone: the full send,
  Wi-Fi pairing, DJI Fly opening a sent mission. Tested only against tests/fakes/fake_adb.py.
  First real-phone run (founder, 2026-10-30): adb found in the Android SDK folder by itself, Redmi connected over USB,
  2 missions listed; one (F6C1AB6D) read as 0 waypoints (probably a point-of-interest mission): a mission Dīvi
  cannot read is never offered as a slot. BUG found by the founder: the 'Sent / Next, on the phone' message
  vanished after a split second because the refresh after a send rebuilt the card holding it; tests passed because
  they read the message before the refresh finished. RULE: the outcome of an action lives OUTSIDE widgets that a
  refresh rebuilds, and a test must wait for the refresh and then check the message is still there.
  CI FINDING (founder's screenshot, 2026-10-30): ubuntu-latest failed tests/field_page (golden survey[2] total_minutes
  6.9086 vs 6.8819) while Windows/macOS passed. Cause: grid.auto_heading decided a SQUARE's strip direction with
  `height > width` (and by which hull edge came first), i.e. by floating-point noise: ~1/3 of square and
  near-square surveys changed by 0.1-1.6 s between machines (a 1e-12 relative nudge was enough to flip them).
  Also ceil(height/spacing) on whole-number ratios. Fixed with tolerances + a fixed rule for squares (heading in
  [0,90)). RULE: any comparison/ceil/round on a derived float needs a tolerance; tests/core/test_planner_determinism.py
  nudges inputs by 1e-12 and demands an identical plan. A 150-case hunt (squares, near-squares, rotations) found 49
  unstable cases before the fix and 0 after.
  REAL DJI FLY SAMPLES (founder, 2026-11-02): a POI mission and a mission with per-waypoint camera angles
  (tests/fixtures/dji_fly_poi/, shifted to Greenwich) settled the encoding of Take Photo at a waypoint, POI
  headings and gimbal tilts: see docs/field/dji-fly-mission-format.md. BUG FIXED: the writer put waypoint i's tilt
  on leg [i, i+1] (one waypoint late); DJI Fly stores waypoint k's tilt on leg [k-1, k]. The reader now derives
  `gimbal_pitch_deg` from the actions (arrival_tilts) and reports heading_mode/poi; Waypoint has `poi`; camera limits
  are the Lito's -90..+40. NEXT (decided with the founder): drawable map with shape roles (map inside / leave out /
  band around / corridor line / keep clear), then 3D patterns (oblique crosshatch first, then orbit/dome and wall
  scans), each needing a 3D processing preset. Map tiles: OSM tile policy forbids offline downloading and heavy
  use, requires attribution; default OSM street, bring-your-own tile URL, no satellite default.
  Third real sample (custom heading, hover 3 s, zoom 2x, own speed, tilt +20, first-waypoint camera set-up):
  heading Custom = smoothTransition + angle; hover = `hover` action; zoom = `zoom` action (group 4, seen only at
  waypoint 1); DJI Fly groups actions by KIND (group 1 = arrival actions incl. several in one group, 2 = evenly
  turning tilt, 4 = zoom). The writer now writes that structure, supports Waypoint.heading_deg and hover_s, and its
  default takePhoto has useGlobalPayloadLensIndex (it was missing). Zoom is read but not written.
  MAP SEARCH + LOCATION (2026-11-02, patch 0033; founder confirmed the map itself works in his browser: map,
  toolbar, OSM credit): adapters/geocode.py (Nominatim-compatible; at most 1 request/s for the whole application
  via a lock and 1.1 s pace, answers cached 1 h, User-Agent 'Dīvi/<ver> (+repo)', search only on a button
  press (policy forbids search-as-you-type), OSM credit shown unless another service is configured, error text for
  403/429/offline/bad JSON); the service address is a setting because the public service's policy counts ALL users of
  an application together. 'My location' = navigator.geolocation through ui.run_javascript (secure context needed:
  http://127.0.0.1 or localhost); AreaMap._browser_location is the only JS call so tests replace it (awaiting JS under
  the simulated user hangs). UNVERIFIED: live Nominatim answers (the sandbox cannot reach it), real browser location.
  EDITING + UNDO (same patch; founder asked: 'no option to edit after drawing; the edit icon in the toolbar does not
  work'): Leaflet.draw's own edit tool cannot work because hide_drawn_items=True keeps its feature group empty (and
  NiceGUI strips an `edit: False` option), so it is hidden with CSS (EDIT_CSS, :has() selector). NiceGUI forwards only
  MAP-level events (map-click with latlng, draw:*), NOT marker drag/dragend, so editing is by CLICKING: Edit button in a
  shape's row -> numbered circleMarker discs on its corners -> pick a corner -> click the map to move it (documented
  pattern: m.on('map-click', ...) with e.args['latlng']). Add corner = midpoint of the longest side; remove picked
  corner (area >= 3, line >= 2); circle = centre by click + typed radius; a rectangle becomes a polygon when a corner
  moves; a move that makes the outline cross itself is refused (core/shapes.move_corner validates). Undo (history of 50,
  consecutive changes to one field = one step, restores shapes AND the takeoff pin/box). Pure operations are in
  core/shapes.py (move_corner, insert_corner, delete_corner, with_radius). The Start page promise is now exact: nothing
  is sent unless the map background or place search is used.
  FILE LAYOUT (the gate has a HARD 400-line limit per file; plan_map.py hit 591 and was split): pages/plan_map.py
  (AreaMap: build, shapes list, result; 399 lines: NO headroom, split further before adding to it), plan_map_edit.py
  (EditingMixin: undo + corner editing), plan_map_places.py (PlacesMixin: search, coordinates, location),
  plan_map_text.py (labels, colours, help texts). Tests patch plan_map_places.search_places and read LOCATION_JS there.
  UNVERIFIED in a real browser: the numbered tooltips (bindTooltip on circleMarker), the corner discs, clicks while a
  draw tool is active (draw:drawstart ends editing), live Nominatim answers, real browser location.
  FOUNDER'S FIRST REAL USE (2026-11-02): planned a map on the PC, sent it, it opened in DJI Fly (no flight yet).
  Three complaints: (1) waypoints only at line ends, wanted one at every photo point; (2) no separate 3D vs flat
  scanning with their own settings; (3) steps not in order / no direction. DONE: (1) PhotoMode.WAYPOINT was already
  implemented; the UI/CLI defaulted to interval. Now the default everywhere; AVI001 only for aircraft whose profile lacks
  photo_action_verified (Lito X1 has it); waypoint mode = more missions (200x300 m @2 cm: 3 x 84 waypoints, not 1 x 18):
  results say how many slots are needed. (2) ENGINE: core/camera.oblique_view (verified against independent ray casting in
  tests/raycast.py), planner tilt (spacing from the tilted footprint, overrun = near_ahead + 2 photo spacings, shutter limit
  from the finest along-track GSD, resolution asked = at the picture centre), PlanOptions/CLI --tilt, results tiles;
  core/scan_types.py (flat / area_3d / object_3d with recommended settings); app/ui/scan_job.py (object scan from the
  form). A coverage simulation (every photo footprint cast onto flat ground) shows every point seen by >= 9 photos in a
  30-degree crosshatch plan. TODO: (2) the SCREEN (scan-type chooser on Plan a flight, per-type fields, object card with a
  THEN BUILT (patches 0036, 0037): (3) the guided order: ui/journey.py defines STEPS once (1 Plan a flight, 2 Send to DJI
  Fly [was 'Phone'], 3 Fly [new screen], 4 Check my photos, 5 Make maps); the top bar, the Start page, a 'Step n of 5' bar
  and a Next-step card on every step screen use it. (2) the SCREEN: Plan a flight starts with 'What do you want to capture?'
  (flat / area_3d / object_3d; pages/plan_type.py), applies each kind's recommended settings, shows only that kind's
  cards (visibility bound to the radio); area_3d adds the tilt field; object_3d has its own where/rings cards
  (pages/plan_object.py), a PinMap (pages/plan_pin_map.py: ONE pin, same finder as the area map, shared via
  PlacesMixin._build_finder) and its own results (pages/scan_results.py; the missions table, notes and buttons are
  shared via plan_results.missions_section). The ground controls moved INTO the settings card (5 numbered cards).
  Missing explanations for the object scan's codes (SC001..SC006) were added and tests/ui/test_explain.py now looks for
  the SC prefix. NOT VERIFIED IN A REAL BROWSER: the whole new Plan layout (chooser, per-kind cards, pin map), the Fly
  screen. NOT FLOWN: tilted 3D missions, waypoint-per-photo missions, rings. Next ideas: a 3D preset in Make maps; a
  route chart for object plans; plan_map.py is 346 lines (hard limit 400).
  SECOND ROUND OF FEEDBACK (2026-11-03, patch 0038): founder sent a Plan screenshot ('go to step 2, come back, go again')
  and a DJI Fly screenshot (44 waypoints, 567 m, 1:09, black fan-shaped bands). ANALYSIS: the mission is a CIRCLE ~100 m
  across (R 49.7 m, 2 cm/px, a photo at every waypoint): reproduced exactly (44 waypoints, 566 m, leg lengths 10/12/11/25/41 =
  the 'D' labels), so the file is right; the short first/last rows and diagonal links are what a circle gives. OPEN: DJI Fly
  shows 1:09 = 8.2 m/s but the file says 6.0 m/s everywhere (autoFlightSpeed, globalTransitionalSpeed, waypointSpeed) and
  the planned time is 1:34; unexplained, asked the founder for DJI Fly's Global Speed. The black bands are probably DJI
  Fly's 3D altitude display (UNVERIFIED). WORKFLOW FIXES: state persists in ~/Divi/settings.json (paths only; STATE.load()
  at start-up; tests set AVISPRIA_SETTINGS); the sample mission is fetched on the Plan screen and Start page
  (pages/sample_panel.py, phone_job.fetch_sample: the mission with fewest waypoints); Send screen has a readiness
  checklist (ui/readiness.py: how many placeholder missions are missing); ui/progress.py = what is done and the next action,
  shown on Start and as chips on every step; a new plan clears last_sent_files; missions table has 'DJI Fly should show'
  (core/route.py: leg length, time per waypoint speed, clock); `avispria inspect` prints the three speeds, route, time and a
  NOTE when speeds disagree. docs/field/workflow.md is the pipeline in one page.
  OBJECT SCAN (built 2026-11-02, patch 0032; no flight yet): `avispria scan` (core/scan.py, app/scan_workflow.py,
  docs/field/object-scan.md). Object = upright cylinder; rings at radius+standoff; ring HEIGHTS follow from the heights on
  the surface each ring must be centred on (even, overlapping, base..top) and the tilt schedule (+10 up at the bottom,
  -20 down at the top): camera height = centre - tan(pitch)*standoff (aiming all rings at one point squeezes coverage by
  r/R); photos per ring = max(360/max_step 10 deg, footprint rule); top cap = nadir lattice 8 m above; spiral route (same
  direction, same start bearing: two consecutive waypoints in the same place are refused by lint WPML011); every waypoint
  faces the POI, stops, hovers, takes a photo, explicit tilt; whole rings per mission (99 waypoints, battery).
  Geometry is in UTM metres (grid north differs from true north by ~2 deg here; haversine is ~0.3% short of true metres).
  STILL TO BUILD: a Scan screen (map pin + fields) and a 3D processing preset (mesh/point cloud, not orthophoto/DSM),
  dome pattern, wall scans (custom heading + vertical columns), oblique crosshatch, route over the map.
  MAP (built 2026-11-02, patch 0031; NOT yet seen in a real browser): Plan a flight has a third way to choose the area,
  'Draw it on a map' (ui.leaflet with the Leaflet.draw toolbar, hide_drawn_items=True). The SERVER owns the shapes
  (pages/plan_map.py AreaMap): every drawn layer is parsed (map_events.parse_layer, tolerant of the payload formats)
  into core/shapes.py DrawnShape with a ROLE: inside (map it), leave_out (a hole), band (a ring of N m OUTSIDE the
  shape = 'map the outside of the polygon'), corridor (a line made a strip N m wide); build_area() combines them in a
  local UTM frame (union of mapped minus union of left-out, simplified 0.25 m, pieces under 100 m2 dropped) into
  polygons the planner already accepts (ONE polygon at a time, holes allowed; separate pieces are planned one by one
  via a chooser). Editing is in the list under the map, not Leaflet's own edit tools (the edit toolbar is empty
  because drawn items are hidden). The widget's default OSM layer is REMOVED at creation; the background is an opt-in
  switch (OSM tile policy: attribution, no offline use) or the person's own tile URL. 'Leave out' only means not
  planned for coverage: the planner still overruns strip ends into the hole and may fly across it (6 waypoints
  inside a 50 m hole in the test); a real 'keep clear' needs routing and is NOT built. Takeoff = the pin (also written
  into the takeoff box, and cleared with it). Tests hand the map what the toolbar would send (AreaMap.add_drawn); the
  browser-side drawing, tile loading and the exact draw:created payload are UNVERIFIED (founder to test with
  screenshots). STILL TO BUILD: route over the map after planning; vertex editing; 'keep clear'; GCP upload;
  canopy height model; 3D patterns (oblique crosshatch, orbit/dome, wall).
- Engine detection: doctor/Start screen now tell apart not running / WebODM programs running but not
  answering (starting, or started as administrator so Windows hides their ports) / running; Check again
  button on Start. The founder's Windows PC reported 'No WebODM-related programs are listening'.
- Terrain-aware capture QA: `core/ground.py` (height above the surface per photo; modes
  `takeoff` = DEM differences only, for any external DEM; `absolute` = photo altitude minus
  DEM, only when the DEM shares the photos' height reference, e.g. the engine's own DSM, with a
  plausibility check -> QA011). `qa --dem [--takeoff]`; `process` re-checks its resolution
  estimate against the engine's DSM. DEM reader can decimate (5 cm DSMs).
## Current state (command proof)
- (at session #4) 184 tests passed; founder's Windows run of `engine` connected to
  ODX 3.8.4 (API 2.4.0), 12 cores, 16 GB, 80 options.
- `process` verified on the founder's PC with ODM's public Brighton Beach set (18 photos,
  Phantom 3): fast 2 min, standard 8 min; 18/18 photos placed, reprojection 0.83 px,
  GPS agreement 0.66 m, 1.41 M points. Output now at the photos' GSD (1.9 cm/px), not 5.
- Brighton Beach: ODX measured GSD 1.59 cm/px; flat-ground estimate 1.89; terrain-aware 1.68
  (ground ~4-8 m above takeoff, camera ~35.6 m above surface). The remaining ~6% is the
  camera-size convention for the 16:9-cropped FC300S (ODX: f35/36 of image width; ours:
  diagonal-based). Lito X1 (full 4:3) uses our 9.692 mm width; ODX's convention would give
  10.08 mm (4% apart): UNVERIFIED until a Lito X1 set is processed. `process` records
  gsd_ratio (measured/estimate) in provenance for this.
## Open problems / suspicions
- Founder grounded ~1 month; test `process` with a public sample dataset.
- Non-DJI photos: EXIF GPS fallback not implemented (QA warns, processing works).
- PyODX uses deprecated datetime.utcfromtimestamp (narrowly ignored; report upstream).
## Next single task (ready-to-paste)
Founder to choose: (a) polish the window interface after real use (look, wording, prepare-copy
for the phone, remembered folders); (b) canopy height/change, which needs a terrain model (leaf-off flight,
external LiDAR DTM or open ground) and a public forest dataset to develop against (ODM lists
helenenschacht, 176 photos, 2.5 GB). Whenever Lito X1 data is processed: calibrate the camera
size (gsd_ratio in provenance) and measure the route-curve dip with the probe flight.
## Decisions made
- Process through NodeODX directly (not WebODM's API): no login, no WebODM settings
  touched; results importable into WebODM via its Import button.
- Default processing resolution 12.2 MP (JPEG only; DNG sent at full size).
- Terrain in QA uses the nadir surface point per photo (first order on steep slopes).
- Calibration targets the typical (median) height; spacing the 10th percentile. The 10 m curve
  margin is still unverified: when the probe flight measures the real dip, lowering it makes
  plans fly lower/tighter automatically.
## Do-not-touch notes
- tests/fixtures/* stay byte-exact; never print or persist engine tokens.

## Patch 0047: technical look (2026-11-09)
Dense console style everywhere: JetBrains Mono for all text (bundled, OFL, offline), 1px borders on
every block, square corners, no shadows/gradients/blur, instant inverted hovers, uppercase tracked
labels, tabular numbers. Desktop: `assets/avispria.css` (inside NiceGUI's overrides layer),
`install_look()` in layout.py sets flat/square/dense Quasar defaults, `icons.py` maps Material icon
names to Lucide outlines (stroke 1.5) via Quasar's iconMapFn; shapes in `assets/icons.css` are made
by `scripts/make_icons.py` (needs lucide-static 1.60.0 unpacked). A new icon name must be added to
ICONS (tests/ui/test_icons.py fails otherwise). Field page: same look, but tap targets stay >= 40px.

## Patch 0048: map editing by dragging, full screen, a real type scale (2026-11-09)
Drawing map: 520px to 72vh tall; Full screen button (Esc leaves) in a bar on the map with Undo,
Done and a hint. Outlines are edited by dragging Leaflet.draw's own handles (plan_map_layers.MAP_JS
turns them on; each finished drag comes back as `divi_shape_edit` and core.shapes.reshape keeps or
refuses it). Clicking an outline picks the shape. Layers are redrawn only when their shape changes.
The click-a-numbered-corner editor and move/insert/delete_corner are gone. Leaflet keeps its zoom
animation (the no-transition rule skips leaflet classes). Type scale 12/13.5/15/18/22/26 px.

## Patch 0049: readable forms, map files, speed limits, continuing a stopped job (2026-11-13)
- Type 16px body (13.5/15/16/19/23/27 scale); field labels full size at the top of 54px boxes
  (Quasar's 75% scaling and the extra container padding are switched off); `plan_form_parts.fit`
  sizes a field from its label and longest value (mono letters are 0.6 em), selects via
  `select_fit`; cards 14x16px padding, 16px between cards. Phone widths: fields full width.
- Speed: the wind reserve is now top speed minus wind (was half the top speed minus wind, which
  capped a 12 m/s Lito X1 at 6 m/s). New advanced fields: fastest flying speed (`cap_ms`, binding
  "your speed limit") and the camera's shortest time between photos (overrides the profile's
  `min_interval_s`, which for the Lito X1 12 MP is still an assumed 2.0 s). The field page mirrors
  the wind rule; golden.json regenerated (one survey case now has several missions).
- Waypoints per mission are no longer capped by the profile's `waypoint_limit`; above it the plan
  warns (AVI004). Battery up to 120 min.
- Map files: `adapters/area_file.py` reads KML, KMZ, .shp (finds .shx/.dbf/.prj/.cpg beside it,
  reprojects with the .prj; no .prj only if the numbers are lon/lat), a .zip with a shapefile, and
  GeoJSON (Polygon/MultiPolygon/features). Optional buffer in metres (UTM, mitred corners). Several
  separate areas: refused in file mode, or "Show it on the map" puts them on the drawing map
  (holes become leave-out shapes; outlines thinned to <=300 corners).
- Maps: right-drag pans every drawing map; while a drawing tool is on, left-drag no longer pans
  (mouse only), so a slightly moving click still places a point. The object (pin) map got the
  same box, height and Full screen (`plan_map_full.FullScreenMixin`).
- Processing can be continued: `app/process_work.py` keeps `divi_work.json` in the results folder
  (folder, settings, engine task id, step: started/uploaded/processed/downloaded/extracted/done),
  written after each long step. `divi resume <results>` and "Continue a job that stopped" on the
  Make maps screen run the same `run_process` with `resume=True`: prepared photos are reused,
  a task the engine still has is followed (restarted if stopped or failed), downloads are not
  repeated. `divi maps` (and Start-Divi-Maps.*) opens only the after-flight part.

## Patch 0053: only the native waypoint drones (2026-11-13)
The list is now exactly the drones with native waypoint flight (founder's list, from DJI's
support page and waypointmap.com): Mavic 4 Pro, Mavic 3 Pro/Cine, Mavic 3/Cine, Mavic 3 Classic,
Air 3S, Air 3, Mini 5 Pro, Mini 4 Pro, Inspire 3, Lito X1. mission_app is "dji-fly" or
"waypoint-pro" (Inspire 3: Waypoint Pro on the DJI RC Plus; Dīvi cannot write those yet, AVI005).
Inspire 3 assumes the X9-8K Air with the DL 24 mm lens (leaf shutter).

## Patch 0051: the DJI camera drones (2026-11-13)
20 profiles in drones.toml (no FPV, Neo, thermal or multispectral). New profile keys
`mission_app` ("dji-fly", "dji-pilot-2", "none") and `mechanical_shutter`. Only "dji-fly" drones get
missions (AVI005 otherwise; the form says so and the list puts them last, marked "photos and maps
only"). New profiles are `verified = false`; where DJI does not publish the focal length the
geometry is 35 mm-equivalent (same GSD and footprint). DJI Fly waypoint drones per DroneDJ
(Jan 2026): Mavic 4 Pro, Mavic 3 series, Air 3S, Air 3, Mini 5 Pro, Mini 4 Pro (+ Lito X1).

## Patch 0052: the tree inventory (2026-11-13)
See docs/field/tree-inventory.md. core: ground_sources (6 ranked kinds, closed-canopy rule,
datum alignment by median at seen-ground cells, ground sigma growing with distance to seen ground),
doming (quadratic fit of flight-minus-reference at seen ground; dome = middle minus corners),
height_calibration (line >= 5 trees, offset 2-4, LOO error), biomass (Jucker Eq. 7 checked against
the paper; Chave Eq. 4 with Jucker Eq. 6 D; chunked Monte Carlo, shared vs per-tree errors),
indices (relative only; rank_change for flights), symptoms (robust z of crown GCC + dieback),
chm_quality (grade). app: ground_choice (used by run_canopy), inventory_workflow (run after the
analysis engine; trees.csv, inventory_summary.json, ground_sigma.tif, indices/), `divi analyse`
options, `divi compare-flights`, TreeInputs carried through process and resume, Make maps inputs,
results tiles. Assumed sigmas are written into every summary.

## Patch 0054: cut by mask, DeepForest, goal helper, map icons (2026-11-13)
- Inspire 3 removed (the waypoint-pro mission_app stays, tested with a custom profile).
- app/clip_workflow.py: extract by mask right after stitching (process --clip, divi clip,
  Make maps "Cut the maps to your area"); ortho, DSM, DTM cut; originals kept as *.full.tif and
  every recut starts from them; --undo restores; unreadable products are skipped with a note;
  survives resume (clip_file/clip_buffer_m in the work record).
- DeepForest: optional extra `trees` (pyproject + uv.lock; default sync unchanged).
  adapters/tree_detector.py (resample to 10 cm, load_model or use_release, predict_tile with
  path/raster_path), app/crown_boxes.py, core/crowns.refine_tops (add a top in an empty box,
  merge tops in a box's middle half). Recorded as surface_summary "crown_detector".
- core/goals.py + `divi advise` + Settings card "What will you measure?": GSD rules per goal,
  overlap, height from the camera, capped at 120 m, unreachable below 15 m clearance (lesions).
- Leaflet.draw buttons drawn as Lucide outlines (icons.LEAFLET_ICONS -> icons.css), action
  buttons styled; readable in dark mode.

## Patch 0055: "General mapping" goal (2026-11-13)
First and default goal: 2 cm, 85/75 % overlap, keeps crowns, heights, cover, crown symptoms and
buildings open; what to measure is chosen at processing time.

## Patch 0056: sending keeps the planned waypoint count (2026-11-13)
send_mission and prepare_copy re-linted with the default LintLimits (99 waypoints), refusing a
mission planned with more waypoints per mission. They now use NO_WAYPOINT_CAP (the cap was
enforced at planning time, with the AVI004 warning above the drone's known limit).

## Patch 0057: DJI Fly's 200-waypoint limit (2026-11-13)
DJI Fly warned on a 508-waypoint mission (founder, 2026-11-13), so every DJI Fly profile has
waypoint_limit = 200 and the planners cap to it (workflow.capped: AVI004 says the plan was split).
Default waypoints per mission 200; the field's max is 200.

## Patch 0058: one pipeline of seven engines, projects, Back/Next, dual licence (2026-11-14)

**Decisions (founder, 2026-11-14).** Licence: AGPL-3.0-or-later plus a separate commercial licence
(`COMMERCIAL.md`): free of charge for organisations in Bangladesh and in World Bank low-income
countries, paid or by collaboration for others. Citation requested (`CITATION.cff`, `divi cite`, the
Report screen, the project record). There is no licence check in the program: local Python cannot
enforce one. `CITATION.cff` still needs the author's name before the first tagged release.
Architecture: one pipeline, seven engines, one project folder with a record. Order of work:
architecture and navigation (this patch), then the Report engine proper, then the look.

**The pipeline** is defined once in `core/pipeline.py`: Plan, Mission, Photo check, Reconstruct, Map
(optional), Analyse, Report, each with what it needs and makes. `app/engines.py` holds the two things
every engine shares: `runner(key)`, the one function that does its work (the existing workflows,
unchanged), and `inspect(Links)`, its state read from disk (done / started, not finished / ready /
needs an earlier step). Nothing about state is stored: a maps folder copied from another computer
shows the right state. Not done yet: the engines do not share one request/result type; each runner
keeps its own arguments. Unify those only when the Report engine needs it.

**Projects** (`app/project.py`, `ui/projects.py`): a folder with `divi_project.json`: name, dates,
version, the four links (plan files, sent files, photo folder, maps folder) and, per engine, when it
last finished and with which version. Never coordinates. Paths inside the folder are stored relative
to it. `STATE` writes its four links through to the open project (`state.py: LINKS, to_project`);
with no project open everything works as before (an unnamed project kept in the settings). Opening
a project swaps the links; `projects._set_links` does it with the project closed so one project's
links are never written into another. New projects go to `~/Divi/projects/<name>`.

**Navigation** (`ui/journey.py`): eight screens for seven engines (Mission has two: send, fly).
Top bar: Start plus the seven engines, the current one filled, a line under the finished ones.
Every screen: "Step n of 7", the engine's state, Back and Next at the top (`back-button`,
`forward-button`) and bottom (`back-step-button`, `next-step-button`). Dīvi Maps walks only the four
after-flight screens. The Start page lists the eight screens and the projects
(`pages/project_panel.py`).

**New screens**: `/map` Cut the maps and `/analyse` Measure (`pages/after.py`, rules in
`ui/after_job.py`) run those engines alone on maps already made; "Make maps" still cuts and measures
by itself. `/report` (`pages/report.py`) shows the engine table and saves the project record
(`app/report_workflow.py` -> `divi_record.md` in the maps folder). The record is deliberately plain:
states, file locations, limits, citation. The printable report with methods and numbers is the next
stage and should replace `record_lines`, keeping `RECORD_FILE` as what marks the engine done.

**Commands**: `divi pipeline`, `divi status <folder>`, `divi record <folder>`, `divi cite`.

**Changed behaviour to know**: a processing job that stopped is now linked to the project too (the
Reconstruct engine shows "Started, not finished"); the next action after maps is Measure, then
Report, then finished. The study plan for the validation paper is a separate document (not in the
repository).

## Patch 0059: the Report engine makes one HTML report (2026-11-14)

The Report engine now writes `divi_report.html` in the maps folder (replacing 0058's
`divi_record.md`): key numbers with 95% ranges, pictures of the orthophoto, canopy height model and
land cover (with a legend), methods written from the records, every quality warning, provenance
(engine table, map engine and options, checksums in `divi_provenance.json`), where the files are,
limits, citation and references. One file: font and pictures embedded, nothing fetched; "Print, or
save as PDF" in the browser makes an A4 PDF. Words in `core/report_text.py` (pure, tested), files
and pictures in `app/report_data.py` (an unreadable file is named in the report, never fatal),
HTML in `app/report_html.py`. The command is `divi report <folder>` (was `record`).

**Direction (founder, 2026-11-14):** keep Dīvi lean. After the flight it should produce files made
to be analysed elsewhere (QGIS, other platforms, the founder's Xylo Forest app), with bands as
separate files where possible, editable GIS exports and high-resolution publication-ready map
images. Keep only analyses that fill a genuine gap, plus conversions (for example a thermal band
estimated from RGB). Review the Analyse engine against this before adding to it.

## Patch 0060: a switch for every analysis (2026-11-14)

`core/analyses.py` lists the analyses that can be switched off (land cover, buildings, roads,
street shade, 3-30-300 checks, biomass, colour indices, symptom flags); the canopy height model
with its quality checks and the tree tops/crowns always run. The switches travel in
`TreeInputs.off` (so they reach the work record and `divi resume`), are remembered in the
settings (`STATE.analyses_off`), appear as "What to measure" on Make maps and Measure, and as
`divi analyse --off <name>`. Switched off means not computed where it can be skipped, not saved,
and left out of the summaries, the results screen and the report. Buildings are still classified
(so they never count as trees); the switch only skips describing and saving them.

## Patch 0061: the Export engine, files for QGIS (2026-11-14)

New engine 7 Export (Report is now 8): `app/export_workflow.py`, screen `/export`, command
`divi export <maps folder>`. Output in `<maps>/export`, rebuilt each time: `bands/` (red, green,
blue as single-band files with the alpha as mask, plus the full-colour orthophoto), `surfaces/`
(dsm, dtm, chm, ground_sigma), `analysis/` (landcover with its colour table, confidence,
`indices/*.tif`), `divi_layers.gpkg` (tree_tops, crowns, buildings, roads in the map CRS), README,
`export_manifest.json` (its presence marks the engine done). Rasters are Cloud-Optimised GeoTIFFs
written by streaming a one-band VRT through GDAL's COG driver (`app/export_rasters.py`), with band
description and unit, and a `.qml` beside each (QGIS loads it as the default style; ranges from
percentiles of a small sample). The GeoPackage is written with stdlib sqlite3
(`adapters/gpkg.py`, checked against GDAL/pyogrio during development) and carries QGIS styles in
`layer_styles`. The QML files have not been opened in a real QGIS yet: check that once.
Xylo Forest: a disabled option on the screen until the founder sends its format.

## Patch 0062: map images for publication (2026-11-14)

Second screen of the Export engine, `/figure` ("Map images"). `core/figure_spec.py` describes an
image (layer, width/height in mm, dpi, format, title, caption, legend, north arrow, scale bar,
grid, crown outlines, colour ramp and range, text size) and checks it (20-600 mm, 72-1200 dpi, at
most 250 million pixels). `app/figure.py` draws with matplotlib on its own canvas (no pyplot),
reading the raster only at the needed resolution; the preview is the same layout at 90 dpi. The
automatic height fits the map's shape plus the legend, labels, title and caption. Images go to
`export/figures/<title>.<fmt>`, never overwriting (`-2`, `-3`). New dependency: matplotlib
(PSF-based licence, permissive). The north arrow assumes grid north is up (true in UTM within a
degree or so); a map in another projection far from its central meridian would need a rotated
arrow.

## Patch 0063: relative heat exposure from RGB and the surface model (2026-11-14)

The founder asked for "a thermal band from RGB" after Diykh et al. 2026 (Expert Systems with
Applications 318: 132061). That paper translates RGB to thermal images with a trained network on
potato fields in Canada (one drone, one crop, image-similarity metrics, no error in °C, no code or
weights released), so it cannot be used or reproduced here. Agreed instead (2026-11-14): a
physically based, relative index that never claims °C. `core/heat.py`: sun hours (shadows cast by
the DSM at 09:00-16:00 local on the flight day, on a 0.5 m grid), assumed broadband albedo (0.18
for green vegetation; 0.05-0.45 from relative brightness otherwise, because green leaves look dark
in RGB but reflect strongly in near-infrared; the first version used brightness for everything and
ranked canopy hottest, which is wrong), vegetation cooling factor 0.6, product ranked 0-1 within
the flight; sky view factor (Dozier & Frew 1990, cos² of the horizon angle, 16 directions, 40 m,
1 m grid) as a separate band for night cooling. Written by `app/heat_workflow.py` to
`analysis/heat/*.tif`; switch "heat"; exported, drawable in Map images, described in the report
with the warning to validate against a thermal camera. The weights (0.18, 0.05-0.45, 0.6) are
assumptions to test in the study: fly a thermal drone with the RGB one and compare. Real thermal
import (DJI radiometric JPEG to °C) is not built yet; it waits for access to a thermal drone.

## Patch 0064: the look (2026-11-14)

Agreed direction: keep the dense technical style but make it distinctive and pleasant. Concept: a
survey instrument whose one bold element is the top bar, the pipeline drawn as a flight line
(transect) with a waypoint per step: diamond for Start (take-off), filled green when done,
half-filled when started, a gold ring for the screen in hand, and the line green up to the last
finished step (`layout.transect`, `last_reached`, CSS `.av-nav*`). Everything else is quiet:
Archivo (OFL, variable width and weight, bundled in `assets/fonts`) for all text, wider and
heavier for headings; JetBrains Mono only for data (tiles, table cells, paths, number fields);
sentence case everywhere (the uppercase tracked labels and buttons are gone); 8px corners on
panels, 6px on controls, no shadows; screen titles unboxed at 32px; hovers fill faintly instead of
inverting. Neutrals retuned (light page #EDF1EE pale lichen, text #17221E; dark page #0E1714 forest
night); the logo's green, gold and blue-grey are unchanged and the contrast tests still pass. The
HTML report uses the same type and flight line. The phone field page only took the new neutrals
(regenerated); its own type was not changed.

## Patch 0065: security hardening (2026-11-14)

"Should not be hackable": a licence check in local Python cannot be enforced, so none was added
(SECURITY.md says so); the real attack surfaces were closed instead. (1) `app/ui/guard.py`, called
in `run_app`: Starlette TrustedHostMiddleware (only 127.0.0.1/localhost, against DNS rebinding)
and socket.io allowed origins limited to Dīvi's own address (NiceGUI ships `*`); the real-server
test checks both. (2) `adapters/safe_files.py`: XML without DOCTYPE/entities/network/huge trees,
ZIP reading with limits on entries, size, total and expansion ratio (zip bombs), refusing
climbing names, and a 400 MB cap on area files; used for KML/KMZ/shapefile ZIP areas, the phone's
mission times and the sample's photo settings (KMZ missions already had their own checks). (3)
README: NodeODM published on 127.0.0.1 only (`-p 127.0.0.1:3000:3000`; it has no login), and the
Make maps screen warns that a remote engine receives the photos. (4) `opentelemetry-api` 1.45.1
(GHSA-mf5v-w3w3-f6cg, via fastapi) upgraded to 1.45.2; `.github/workflows/security.yml` runs
pip-audit on the locked dependencies (all extras) on lock changes and weekly; Dependabot for uv
and GitHub Actions. The phone already used paired, encrypted wireless debugging only.

## Patch 0066: Windows fix for the GeoPackage writer (2026-11-14)

On Windows the gate failed in `test_the_geopackage_holds_typed_columns_and_refuses_bad_names`
(WinError 32): `with sqlite3.connect(...)` commits but does not close the file, and Windows cannot
delete an open file. `write_gpkg` now closes the connection on every path (tested by counting
closes); the tests close theirs with `contextlib.closing`. Also: re-exporting while an earlier
export's files are open in QGIS (locked on Windows) gives a clear message instead of a crash.
Lesson: anything that deletes or replaces files must be checked for open handles; Linux CI does not
catch it, the Windows CI runner does.

## Patch 0067: the repository is Mraz11/Divi (2026-11-14)

The GitHub repository was renamed to `Mraz11/Divi`, and is being republished there with a single
"first public release" commit (the full development history is kept privately by the founder).
Every link now points to `github.com/Mraz11/Divi` and the phone page to `mraz11.github.io/Divi/`
(CITATION.cff, COMMERCIAL.md, README, citation.py, the geocoder's user agent, the field page and the
Fly screen). The README's install steps said `cd Dīvi` after cloning; the folder a clone makes is
`Divi`, so they now say that.
