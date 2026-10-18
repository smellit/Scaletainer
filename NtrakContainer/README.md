# Ntrak Container — FreeCAD add-on

Generate a corrugated transport container (ISO box / tank-tainer style) at any
modelling scale from **1:1 dimensions**. Type the real size of the container and
the scale — `1:87` (HO), `1:160` (N), or anything else — and the add-on writes
FreeCAD, STEP, STL and 3MF files.

The generator is fully scripted: **no spreadsheet object is created in the
document**. All parameter maths runs in plain Python, and the output is plain
`Part` geometry, which keeps the files small and print-ready.

## Install

FreeCAD 1.x discovers add-ons in its user `Mod` directory. For the Flatpak
build:

```sh
make install            # copy into ~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod
make link               # or symlink, convenient while developing
```

For an AppImage / system package, install into its own Mod directory:

```sh
make install DESTDIR=~/.local/share/FreeCAD/Mod
```

Then restart FreeCAD and pick the **Ntrak Container** workbench from the
workbench selector. `make uninstall` removes the installed copy again,
`make test` runs the headless test suite and `make test-params` the parameter
tests that need no FreeCAD at all.

Alternatively use FreeCAD's Addon Manager and point it at this repository, or
drop the `NtrakContainer` folder into the `Mod` directory yourself — it needs
`Init.py`, `InitGui.py`, `package.json`, `ntrak_container/` and `resources/`
to stay together.

### Troubleshooting

* **Workbench not in the list** — FreeCAD scans `Mod` at startup, so a full
  restart is required after installing or updating. Check that
  `Mod/NtrakContainer/InitGui.py` exists and that the folder matches the name
  in `package.json`.
* **Verify the install from a terminal** — start FreeCAD from a shell and look
  for a line reading `During initialization the error ... occurred in
  .../NtrakContainer/InitGui.py`; FreeCAD prints it when an add-on fails to
  load. `make test` includes a regression test for the workbench registration.
* **Console check** — `freecadcmd` should accept
  `from ntrak_container import tasks` without errors; if it does not, the
  add-on folder is not on the FreeCAD `Mod` path.

## Using the GUI

**Ntrak Container → Generate container...** (shortcut `G` then `N`) opens a
panel with five tabs:

1. **Scale & options** — input unit (mm, cm, m, in, ft), the modelling scale
   (preset list or a free-text `1:87`, `1/120`, `220`), the two printability
   safety nets described below, and whether to build the mounting frame and the
   door end.
2. **Dimensions (1:1)** — a *Standard size* picker with the common ISO boxes
   (20 ft dry / high cube / reefer, 40 ft dry / high cube, 45 ft high cube, the
   48 ft reference container and a 53 ft domestic) plus the real full-size
   measurements: overall length, width, height, end-frame/corner-fitting width,
   door border width, roof and floor plate thickness, the mounting rib
   dimensions, and the far-door hardware (backing plate, locking rod width,
   centre seam, hinge/handle size).
   Choosing a standard size fills the length, width and height; editing any of
   those three by hand switches the picker back to `-- custom --`, while the
   other fields keep their values. Changing the input unit re-expresses these
   fields — and keeps the size selection — without changing the model.

   The dimension fields show **whole numbers with no up/down arrows**. They
   still store the exact value behind the scenes, so the 48 ft reference size
   reads `14630 mm` on screen but remains `14630.4 mm` for the generator; the
   reference model is therefore still reproduced bit-for-bit.
3. **Corrugation** — for each of the four rib sets (side wall, roof, floor,
   door end): rib count, slope width, relief depth, and the share of the flat
   span that becomes the crest.
4. **Preview** — the derived scale-space numbers (model size, wall depth, rib
   pitch, mount rib size) plus a log of every adjustment applied.
5. **Generate** — output folder, formats, and the button.

Defaults reproduce the 48 ft ISO container of `../Container.FCStd` at 1:160.

## Using the console

```python
# freecadcmd
>>> from ntrak_container import tasks
>>> result = tasks.generate(
...     {"length": 14630.4, "width": 2590.8, "height": 2895.6,
...      "scale_divider": 87, "min_feature_mm": 0.25},
...     "~/Ntrak", formats=("stl", "3mf"))
>>> print(result.text())
```

All values are 1:1 millimetres unless `unit=` says otherwise. Anything you leave
out keeps the reference value. `tasks.preview(values)` returns the derived
numbers without building geometry.

## Printability at small scales

At 1:160 a 48 ft container is only 91 mm long, so many 1:1 features become
thinner than a nozzle. Two optional knobs (both `0` = off by default, so the
reference model is reproduced exactly):

* **Minimum feature size** — every scaled length below it is raised to it.
* **Minimum rib pitch** — ribs are dropped until the pitch reaches it.

When a raised profile no longer fits the corrugated span, the rib count is
reduced instead of letting the corrugation run past the wall; each change is
reported in the Preview tab and recorded in the `.json` sidecar.

## Output

For scale `1:87` you get `Ntrak-168x30x33-1-87.*`:

| File | Contents |
| --- | --- |
| `.FCStd` | one `Part::Feature` per component inside a group, no spreadsheets |
| `.step` | the same components as solids |
| `.stl`, `.3mf` | meshed assembly |
| `.json` | inputs, derived values, adjustments, per-part volume and size |
| `...-parts/` | one STL/3MF/STEP per component for multi-part prints |

Components: `SideWallRight`, `SideWallLeft`, `Roof`, `Floor`, `MountFrame`
(the ribs that hold the container), `DoorSide` (the ribbed end) and `FarDoor`
(the realistic double-door end). The model sits in the first octant with the
floor ribs at `Z = 0`, so it can be sliced without moving it.

## The far door end

The template only modelled one (ribbed) end, leaving the other side open. The
`FarDoor` part closes it with a realistic ISO box door: two leaves meeting at a
recessed centre seam, each framed by raised stiles and rails, with two vertical
locking rods and cam-keeper blocks per leaf, hinge blocks down the outer edges
and corner castings at the four corners.

Two design rules make it safe:

* **It never exceeds the overall length.** The door fills exactly the band
  between the corrugated shell (`overall_length`) and the nominal 1:1 `length`,
  so its outer face is flush with the container's real end and the model's
  bounding box is always `length` — never more.
* **It is raised relief on a solid backing plate**, not thin protrusions, so it
  survives a fine nozzle. At 1:160 the backing plate is ~0.30 mm and the raised
  detail ~0.58 mm. The `min_feature_mm` safety net raises anything too thin for
  a coarser nozzle; the door detail then simply reads as a flat panel.

Toggle it off with **Build realistic double-door end** on the Scale & options
tab, or `include_far_door=False` in the console.

The reference model's `FrameMiddle` / `FrameBack` are PartDesign clones of
`FrameFront`; here the three mounting ribs are one compound part, which is
simpler and print-ready.

## How the geometry is derived

The generator reproduces the reference model's construction:

* `inner_length = length - 2 * frame_size` — the corrugated span.
* Side wall depth `= 2 * frame_size`, plate `= depth - rib height`, so the
  corrugation is flush with the end frames.
* `pitch = span / count / scale`, `flat = pitch - 2 * slope`, split into crest
  (`flat * ratio`) and valley (`flat * (1 - ratio)`).
* Mounting ribs span `width - 2 * wall_depth` and are spread evenly over the
  corrugated span.

Coordinate system: `X` = length (door end at `X = 0`), `Y` = width crest plane
to crest plane, `Z` = height with the floor crest plane at `Z = 0`.

## Tests

```sh
make test-params    # parameter maths only, plain Python, no FreeCAD needed
make test           # all 67 tests: parameters, geometry, export, GUI, workbench
```

`make test` runs `tests/run_tests.py` headless (`freecadcmd`) with an offscreen
Qt platform, so it needs a display-free environment. The workbench test stubs
the `FreeCADGui` workbench API, which only exists in a GUI session.

`tests/test_geometry.py` compares the 1:160 build against volumes and bounding
boxes measured from `Container.FCStd`: side walls 2189.6384 mm³, roof
1334.8501 mm³, floor 1242.9017 mm³, three mounting ribs 3 × 773.28 mm³, door
end 163.4849 mm³.

Known difference: the reference `BackSide` body's border sketch has
self-overlapping wires, which inflate its volume slightly. The generated door
end is modelled cleanly (border ring plus ribbed slab) and matches the same
total volume.
