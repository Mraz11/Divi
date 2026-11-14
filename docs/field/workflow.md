# The workflow: from an idea to a map, in order

A project is **one set-up (once)** and **eight steps**, one for each engine of Dīvi's pipeline:
Plan, Mission, Photo check, Reconstruct, Map, Analyse, Export, Report. The top bar shows them in this order and
marks what is done. Every screen says "Step n of 8" and has Back and Next buttons at the top and at the
bottom. The Start page says the one thing to do next and lists your projects.

```
 ONCE            1 Plan         2 Mission: send   2 Mission: fly   3 Photo check   4 Reconstruct
 sample mission  on the PC      PC + phone        phone, outside   PC              PC (WebODM)
 from the phone  (what, where,  (placeholder      (compare, fly)   (copy photos,   (map or 3D
                 drone, set-    missions, then                    check overlap)  model)
                 tings, save)   send)
```

## Once: the sample mission

Dīvi copies the exact file format of your DJI Fly from one mission that DJI Fly made. In DJI Fly make a
Waypoint Flight with two points and save it (do not fly it), plug the phone in (USB debugging on), and press
**Get it from my phone** (on the Start page or in step 1). It is remembered between runs, in
`~/Divi/settings.json` (paths only, never coordinates).

## 1. Plan a flight (on the computer)

1. **What do you want to capture?** A flat map, a 3D model of an area, or a 3D model of one object.
2. **Where:** the area (numbers, a map file, or drawn on a map) or the object (a pin).
3. **Your drone** and its sample mission.
4. **Settings** for that kind (resolution, overlaps, tilt, the rings).
5. **Where to save**, then **Plan the flight**.

The results say how many missions the plan has, and what **DJI Fly should show** for each (waypoints, route
length, time).

## 2. Mission: send to DJI Fly (computer and phone)

DJI Fly cannot import missions, so a plan is put into a *placeholder mission* that DJI Fly made. A plan of N
missions needs N placeholders. The screen's checklist says how many DJI Fly has and how many more to make
(Waypoint Flight, any two points, Save). Then press Send. Originals are copied to the computer first.

## 2. Mission: fly (outside)

Open each mission in DJI Fly and compare its map with the plan's **DJI Fly should show** column. If they
differ, do not fly it (see the Fly screen: Global Speed, and `avispria phone pull` then `avispria inspect`).

## 3. Check my photos / 4. Make maps (on the computer)

Copy the photos to one folder, check that they overlap enough, then turn them into a map or a model.

## 5. Cut the maps / 6. Measure / 7. Export / 8. Report (on the computer)

"Make maps" cuts and measures by itself when you ask it to. These three screens do each part on its own,
on maps that are already made, without stitching the photos again:

- **Cut the maps** to your study area (optional), so every number is about that area only. The uncut maps
  are kept and the cut can be undone.
- **Measure** again after a cut, or when you have a better ground model or trees measured on the ground.
- **Export** saves everything for QGIS and other programs: one GeoTIFF per band with its
  name, unit and style, and a GeoPackage of editable layers (see `export/README.txt`).
- **Map images** makes figures for papers and posters: choose the layer, the size in millimetres,
  the resolution and the format, add a title, legend, north arrow, scale bar and grid, look at the
  preview, then save (to `export/figures/`).
- **Report** makes one report of the project (`divi_report.html` in the maps folder; print it to PDF
  from the browser): results with ranges, pictures, methods, quality checks, where the files are, the limits
  to state with your results, and how to cite Dīvi.

## Projects

Give a project a name on the Start page ("New project") and it gets a folder of its own in
`Divi/projects` in your home folder, with a small record (`divi_project.json`) of where its missions,
photos and maps are. Named projects stay in the list on the Start page: open one to continue it. The
record holds file paths and dates, never coordinates. Paths inside the project folder are stored relative
to it, so the folder can be copied to another computer ("Open a project folder").

Without a name, Dīvi still remembers the steps of the flight in hand, as before.

## Why a step can seem to go backwards

The only trip back is making the placeholder missions: how many are needed is only known once the plan
exists. The Send screen says it before anything is sent.
