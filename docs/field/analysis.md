# What Dīvi measures: one engine for forest, farm and town

After "Make maps", Dīvi analyses the results for what you mapped. Choose it on the Make maps
screen ("What did you map?"), or with `avispria analyse <results> --profile forest|farm|urban`.

## How it works

Every profile uses the same five layers, computed on a 0.5 m grid:

| Layer | From | Tells apart |
|---|---|---|
| Height above ground | surface model minus ground model | ground, low objects, raised (trees, roofs) |
| Roughness (height spread within 1.5 m) | surface model | roofs and paving (smooth) from leaves (rough) |
| Greenness (excess green) | orthophoto | plants from everything else |
| Colour (CIE L\*a\*b\*) | orthophoto | grey paving, brown soil, dark bluish water |
| Shadow, predicted | 3D model and the sun at photo time | dark because of shade, not because of what it is |

The shadow layer is computed, not guessed: the sun's position at the time of the photos is known,
so every cell that something taller blocks from the sun is marked before colours are judged.

## Land cover classes (`analysis/landcover.tif`)

| Code | Class | Rule |
|---|---|---|
| 1 | paved (roads, yards) | ground level, grey |
| 2 | bare soil | ground level, warm brown |
| 3 | grass, crops, low plants | ground level, green |
| 4 | water | ground level, dark, smooth, bluish, not in shadow |
| 5 | low objects (cars, walls) | 0.5-2.5 m, not green |
| 6 | shrubs | 0.5-2.5 m, green |
| 7 | tree canopy | raised, green |
| 8 | buildings (roofs) | raised, smooth, not green, closed into blocks of at least 12 m2 |
| 9 | rooftop vegetation | green on a roof, away from its rim |
| 10 | other tall (dead crowns, masts) | raised, not green, not a building |
| 11 | ground (colour unknown) | without an orthophoto |

Limits (0.5 and 2.5 m in town) differ per profile: see `src/avispria/core/profiles.py`.
`analysis/confidence.tif` (0-100) shows how sure each cell is: lower in shadow, in low sun, where
the ground was estimated, close to a height limit, and for green lying flat on a roof.

## Objects and numbers

- **Buildings** (`buildings.geojson`): footprint, height (median over the roof), floors (height /
  3 m), roof slope (median of the roof faces: works for gables), flat or pitched, rooftop
  vegetation, and how much of it lies flat (lawn, but possibly paint or shade cloth).
- **Roads** (`roads.geojson`, town and farm): paved pieces at least 3 times longer than wide,
  2-40 m wide; width from the distance to the edge, length = area / width. Wide paved areas are
  yards and car parks.
- **Street trees**: crowns within 8 m of a road (`on_street` in `canopy/crowns.csv`), their spacing
  along the road and the planting gaps (a spacing over 1.5 times the usual one).
- **Green numbers**: tree canopy, all green, sealed surfaces, rooftop green; the "30" of the
  3-30-300 rule (30% canopy) and the "300" (buildings within 300 m of a green space of at least
  0.5 ha, inside the map); street shade from trees at 14:00 on the flight day.

## Checking it

Before using the numbers in a study, check a sample:

- 50-100 random points against the orthophoto, giving an error matrix per class;
- building heights against counted floors;
- street trees counted along two or three streets.

The synthetic test town in `tests/cityscene.py` gets 98-99% of cells right. A real town is
harder: shadows, glass, tin roofs and trees over roads all lower the accuracy.

## Known limits

- Glass, shiny metal roofs and water break the 3D model: heights there are unreliable.
- Moving cars leave ghosts.
- Trees over a road hide it; the road may then be split in two.
- Power lines are invisible.
- A green-painted roof and a lawn on a roof look alike from above.
- In low sun almost everything is in shadow and orange: fly between mid-morning and early
  afternoon (the Plan screen shows the window).
