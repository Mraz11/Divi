# The tree inventory: what it does, what it assumes, what it cannot do

After the maps are made, Dīvi checks the canopy height model, outlines the crowns, and estimates
each tree's biomass and carbon with a range. It also scores visible crown symptoms and writes
colour indices. Everything is in `results/analysis/`:

| File | What is in it |
| --- | --- |
| `trees.csv` | every tree: position, height as modelled and corrected, crown diameter, biomass and CO2 with 95 % ranges, colour score, symptom flag |
| `inventory_summary.json` | the quality grade and findings, the ground model used, the doming check, the height correction, the stand's totals, every assumption |
| `ground_sigma.tif` | how uncertain the ground is at each place (m) |
| `indices/` | colour indices (relative within this flight) and the vegetation mask |

Run it again with other inputs: `divi analyse results/ --field-heights trees.csv --reference glo30.tif`
(see `divi analyse --help`), or fill in "Trees: heights, biomass and carbon" on Make maps.

## 1. The canopy height model, checked

**Ground models, best first.** Photogrammetry cannot see the ground under a closed canopy, so
there it guesses the ground too high, and the trees come out too short. In tropical forest
Swinfield et al. (2019) found a mean bias of about 5 m. So the ground source matters most:

1. LiDAR ground model
2. ground from a leaf-off (or after-harvest) flight
3. ground surveyed on site and interpolated
4. the engine's ground from this flight (good where the ground was seen: open land, towns)
5. a global model, e.g. Copernicus GLO-30 (30 m, but not fooled by the canopy)
6. Dīvi's own estimate from the lowest points

Where the flight saw the ground on less than 10 % of the area (a closed canopy), a global model
is ranked above this flight's own ground.

An outside model is moved up or down to meet this flight where the ground was seen. Drone photo
heights are above the ellipsoid, while most elevation models are above the geoid; in Bangladesh
the two are tens of metres apart. The move is recorded.

**Uncertainty of the ground.** This is an assumption taken from the literature, not a
measurement:
- Base error (1 sigma): LiDAR 0.15 m; leaf-off, survey or engine 0.3 m; global 2 m; estimated
  0.5 m.
- For ground guessed from this flight, the error grows by 0.03 m for each metre away from the
  nearest place where the ground was seen, up to 6 m.

**Doming check.** If all photos look straight down and there are no ground control points, a
small lens-model error can bend the whole model into a dome or a bowl (James & Robson 2014).
Give an independent ground model and Dīvi will compare it with this flight where the ground was
seen. Any curvature left after removing the offset is the dome. It is reported if it is larger
than 0.5 m and larger than twice the noise. Without a reference model the check is reported as
"not checked".

**Other checks.** These cover holes, a ground model lying above the surface, spikes above 70 m,
hidden ground, and the ground's uncertainty under the trees. Together they give one grade: good,
use with care, or poor.

**Field-calibrated height correction.** Measure a few trees on the ground with a rangefinder or
clinometer and save them as a CSV:

    id,lat,lon,height_m
    T1,23.8101,90.4122,14.2

(`x`,`y` in the map's coordinates also work.) Each tree is matched to the nearest tree top
within 3 m.
- 5 or more trees: a straight line, field = a + b × model (Swinfield et al. 2019).
- 2 to 4 trees: an offset only.

The error before and after is reported, along with a leave-one-out error for trees not used in
the fit. Both raw and corrected heights are always written.

**DeepForest crown pass (optional).** DeepForest (Weinstein et al. 2020, MIT licence) is a
pretrained tree-crown detector. When it is installed (`uv sync --extra trees`, about 1 to 2 GB
because of PyTorch) and switched on, its boxes correct the height model's tree tops:
- a box with no tree top inside gets one (a crown the height model merged into a neighbour);
- two tops in the middle of one box become one tree (a crown it split in two).

The orthophoto is resampled to 10 cm, the resolution the model was trained on. If DeepForest is
not installed or fails, the crowns come from the height model alone and the reason is recorded.

## 2. Biomass and carbon with honest ranges

**Main route: Jucker et al. 2017, Eq. 7** (checked against the paper):
`AGB [kg] = (0.016 + aG) (H × CD)^(2.013 + bG) × exp(0.204² / 2)`, where aG = 0.093 and
bG = −0.223 for conifers, and 0 for broadleaf trees. The validation scatter is 0.69 on the log
scale. Jucker's data did not include plantation or agroforestry trees.

**Second opinion: Chave et al. 2014, Eq. 4**, `AGB = 0.0673 (ρ D² H)^0.976`, with
D = 0.557 (H × CD)^0.809 × exp(0.056²/2) (Jucker Eq. 6). Jucker et al. found this route about
30 % biased against field biomass.

**Carbon** = 0.47 × AGB (IPCC 2006 default); **CO2e** = 44/12 × carbon.

**Monte Carlo** (1000 runs). Errors shared by all trees: the height bias left over (0.7 m without
field trees), the wood density, and the carbon fraction. Errors of each tree alone: its ground
and height, its crown outline (15 %), and the equation's scatter. One tree's 95 % range is about
4 times either way of its middle value. A stand total is much tighter, but never tighter than its
shared errors allow.

This is a remote-sensing-assisted estimate built on IPCC Tier 1 defaults, not a carbon credit.
Urban, open-grown trees differ from the forest trees the equations were made from. Local
allometry and field plots are needed for anything more.

## 3. Colour indices: relative tools only

ExG, ExR, ExGR, GLI, NGRDI, MGRVI, RGBVI, VARI, TGI (generic band centres), GCC and RCC are
computed on the orthophoto's colours as they are. A drone JPEG's colours have been through the
camera's tone curve, white balance and processing, and cannot be turned back into reflectance
(Burggraaff et al. 2019). So the values are compared only within one flight. They are used for
segmentation (vegetation mask: ExGR > 0, or Otsu on ExG for dull photos) and for change.

`divi compare-flights before.tif after.tif` compares two flights by each place's rank within its
own flight. It shows what changed against the rest of the flight, but not a change of the whole
area.

Left out on purpose: "visible NDWI", SAVI with green instead of near-infrared, ad-hoc shadow
indices, and the visible "NDVI" (vNDVI), which was fitted on two cameras and three crops.

## 4. Disease and stress: visible symptoms only

Each tree crown's mean GCC is compared with the other crowns of the same flight using a robust
z-score (median and MAD). A crown is a candidate if:
- its z is −2.5 or lower, or
- half or more of it is not green.

The plot-scale severity is the share of crown area flagged.

- RGB cannot detect latent infection or stress before symptoms (Bock et al. 2020). That needs
  near-infrared, thermal or hyperspectral sensors.
- Single leaf lesions need about 0.5 mm per pixel; a mapping flight gives 1 to 3 cm.
- Check every candidate on the ground with a standard rating scale, by someone who does not know
  which crowns were flagged. Validate on other sites, not only the one used to set things up.
- At a low sun (below 25 degrees) the colours are unreliable, and this is said in the results.

## Corrections to the general RGB guide this was checked against

| Claim in the guide | Verdict |
| --- | --- |
| RGB gives "80 to 95 % of multispectral utility" | no source; removed |
| sRGB linearisation of JPEGs before indices | not valid for camera tone curves; not done |
| MicaSense radiance equation with row terms | for factory-calibrated multispectral cameras, not consumer RGB |
| Jucker biomass with a wood-density term | wrong form: Eq. 7 has no density term |
| COM2 credited to Guijarro 2011 | it is Guerrero et al. 2012 |
| TGI = G − 0.39R − 0.61B | a generic-camera approximation; labelled as such |
| oblique GSD = GSD / cos² θ | only along the tilt; across it is GSD / cos θ |
| LAI = −ln(1 − cover) / k from nadir cover | ignores clumping and within-crown gaps; not given |
| benchmark ranges (tree height R² 0.85 to 0.95 etc.) | optimistic; independent tropical results are lower (e.g. detectree2 F1 above 0.56) |
