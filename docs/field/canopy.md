# Canopy height, cover and tree tops

After "Make maps" (Standard or Detailed), Dīvi turns the surface model into canopy numbers.
`avispria canopy <results folder>` does the same for any earlier result.

## What it makes (in `results/canopy/`)

| File | What it is |
|---|---|
| `chm.tif` | Canopy height model: height above the ground in metres, 0.5 m cells, same coordinates as the DSM. Opens in QGIS. |
| `chm_preview.png` | A quick look: brown = open ground and gaps, greens = low to tall canopy. |
| `crowns.geojson` | One outline per tree crown (longitude/latitude), with its height, area, width, colour and flags. Opens in QGIS. |
| `crowns.csv` | The same per crown as a table: id, position, height, area, diameter, share not green, CIE L\*a\*b\* colour, structure, dieback. |
| `canopy_summary.json` | The numbers below, with the settings used. Also copied into `avispria_provenance.json`. |

The numbers: canopy cover (share of the area with trees 2 m and taller), gaps and open ground,
canopy height (median and 95th percentile), tree tops found (local height maxima: a rough crown
count), and how much of the area the ground was seen in.

## How it works, and its limits

- **Canopy height = surface (DSM) minus ground (DTM).** Photos see the ground only where the canopy
  is open; under a closed canopy the ground is interpolated from the nearest open ground. The summary
  says in what share of the area the ground was seen (warning CH001 below 10%).
- **The ground model** comes from the engine (the Standard preset now asks for it). Without one, it is
  estimated from the surface itself with a progressive morphological filter; heights are then
  approximate (warning CH002). For dense forest, fly in leaf-off season, include open ground in the
  area, or use a LiDAR ground model.
- **Tall but not green.** Roofs, vehicles and dry or leafless crowns are tall but not green. An
  excess-green index from the orthophoto's colours keeps them out of the canopy figures. This is an
  RGB proxy, not a plant-health or species measure: it cannot tell a green roof from a crown.
- **The rim of the map** (5 m) is left out: few photos see it. Smeared, stretched patches at the edge
  of the orthophoto mean the surface there is unreliable too; check the preview against it.
- **Validate.** Measure a few trees in the field (height, crown width) before using the numbers in a
  study.

## Crowns and dieback candidates

- **Crowns**: tree tops are the highest points of the canopy height model within a window that
  grows with tree height; each crown is then grown down from its top to its edge (a marker
  watershed). Neighbouring crowns of the same height can merge, and big crowns with several
  leaders can split: check a sample against the orthophoto.
- **Dieback candidate**: more than half of the crown is not green. Dead, leafless or yellow-brown
  crowns show up; so do flowering or naturally reddish crowns. These are *candidates* for a ground
  visit, not a diagnosis. RGB sees only visible symptoms, never stress before symptoms.
- **Structures**: roofs, tanks and vehicles are tall and not green too. Surfaces that are flat
  and not green are marked as structures and left out.
- **Sun**: crown colour is only comparable in good light. Below 25 degrees of sun the summary
  warns (CH003). The Plan screen shows the day's good-light window (sun 35 degrees or higher).

## Change over time

Fly the same plan again (same height, same overlap, similar light and season) and compare the two
`chm.tif` files: height growth, new gaps, crown loss.
