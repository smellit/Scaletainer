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

## Using the GUI

**Ntrak Container → Generate container...** (shortcut `G` then `N`) opens a
panel with five tabs:

1. **Scale & options** — input unit (mm, cm, m, in, ft), the modelling scale
   (preset list or a free-text `1:87`, `1/120`, `220`), the two printability
   safety nets described below, and whether to build the mounting frame and the
   door end.
2. **Dimensions (1:1)** — the real full-size measurements: overall length,
   width, height, end-frame/corner-fitting width, door border width, roof and
   floor plate thickness, and the mounting rib dimensions. Changing the input
   unit re-expresses these fields without changing the model.
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
(the ribs that hold the container), `DoorSide`. The model sits in the first
octant with the floor ribs at `Z = 0`, so it can be sliced without moving it.

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
make test           # all 46 tests: parameters, geometry, export, GUI, workbench
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
