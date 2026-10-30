# Scaletainer — FreeCAD add-on

Generate a corrugated transport container (ISO box / tank-tainer style) at any
modelling scale from **1:1 dimensions**. Type the real size of the container,
pick the scale — `1:87` (HO), `1:160` (N) or any other preset (the console
accepts any divider) — and the add-on writes
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

Then restart FreeCAD and pick the **Scaletainer** workbench from the
workbench selector. `make uninstall` removes the installed copy again,
`make test` runs the headless test suite and `make test-params` the parameter
tests that need no FreeCAD at all.

Alternatively use FreeCAD's Addon Manager and point it at this repository, or
clone it straight into the `Mod` directory under the add-on name:

```sh
git clone https://github.com/smellit/Ntrak.git \
  ~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/Scaletainer
```

Whichever way you install it, `Init.py`, `InitGui.py`, `package.json`,
`scaletainer/` and `resources/` need to stay together, and the folder in
`Mod` must be named `Scaletainer`.

### Troubleshooting

* **Workbench not in the list** — FreeCAD scans `Mod` at startup, so a full
  restart is required after installing or updating. Check that
  `Mod/Scaletainer/InitGui.py` exists and that the folder matches the name
  in `package.json`.
* **Verify the install from a terminal** — start FreeCAD from a shell and look
  for a line reading `During initialization the error ... occurred in
  .../Scaletainer/InitGui.py`; FreeCAD prints it when an add-on fails to
  load. `make test` includes a regression test for the workbench registration.
* **Console check** — `freecadcmd` should accept
  `from scaletainer import tasks` without errors; if it does not, the
  add-on folder is not on the FreeCAD `Mod` path.

## Using the GUI

**Scaletainer → Generate container...** (shortcut `G` then `N`) opens a
panel with five tabs:

1. **Dimensions (1:1)** — a *Standard size* picker with the common ISO boxes
   (20 ft dry / high cube / reefer, 40 ft dry / high cube, 45 ft high cube, the
   48 ft reference container and a 53 ft domestic) plus the real full-size
   measurements: overall length, width, height, end-frame/corner-fitting width,
   door border width, roof and floor plate thickness, the mounting rib
   dimensions, and the far-door hardware (backing plate, locking rod width,
   centre seam, hinge/handle size).
   Choosing a standard size fills the length, width and height; editing any of
   those three by hand switches the picker back to `-- custom --`, while the
   other fields keep their values. The panel opens with the 48 ft reference
   size already selected. Changing the input unit re-expresses these
   fields — and keeps the size selection — without changing the model.

   The dimension fields show **whole numbers with no up/down arrows**. They
   still store the exact value behind the scenes, so the 48 ft reference size
   reads `14630 mm` on screen but remains `14630.4 mm` for the generator; the
   reference model is therefore still reproduced bit-for-bit.
2. **Corrugation** — for each of the four rib sets (side wall, roof, floor,
   door end): rib count, slope width, relief depth, and the share of the flat
   span that becomes the crest.
3. **Scale & options** — input unit (mm, cm, m, in, ft), the modelling scale
   (preset list; a scale outside the presets such as `1:96` can be stored in a
   configuration file and is then added to the list, or passed as
   `scale_divider` in the console), the two printability safety nets described
   below, and whether to build the mounting frame ribs.  Both door ends are
   always built.
4. **Preview** — the derived scale-space numbers (model size, wall depth, rib
   pitch, mount rib size) plus a log of every adjustment applied.
5. **Generate** — output folder, formats, and the button.

Defaults reproduce the 48 ft ISO reference container at 1:160 — the size the
generator ships as `ContainerParams.reference()`.

## Saving and loading configurations

Above the tabs, **Save config...** / **Load config...** write and read a plain
JSON file holding everything in the panel: the 1:1 dimensions, the corrugation
patterns, the scale, the safety nets, the option toggles and the input unit.
An optional *name* goes in the file too, and the path of the loaded file is
shown under the buttons.

```json
{
  "generator": "Scaletainer/config",
  "config_version": 1,
  "name": "20 footer",
  "unit": "in",
  "values": {
    "length": 238.5, "width": 96.0, "height": 102.0,
    "side_ribs": {"count": 24, "slope": 1.97, "ratio": 0.2, "height": 1.42},
    "scale_divider": 87.0, "min_feature_mm": 0.25, "include_mount_frame": true
  },
  "export": {"directory": "~/Scaletainer", "formats": ["stl", "3mf"],
             "separate_parts": false}
}
```

* Dimensions are stored in the file's own `unit`, so loading a file written in
  inches switches the panel to inches instead of rescaling the numbers.
* **Save output folder, formats and parts option in config files** on the
  Generate tab decides whether the `export` block is written. With it off, a
  file carries only the design, and loading it leaves your current output
  settings alone.
* Files are validated on load: unknown keys, non-integer rib counts, unknown
  formats or a file from a newer add-on version are reported in the status line
  and the panel is left untouched.
* The `.json` sidecar the generator writes next to each model is accepted too,
  so a finished container can be opened again and tweaked.
* A scale that is not one of the presets is kept: it is added to the *Modelling
  scale* list when the file is loaded.

The same format is available without the GUI through
:mod:`scaletainer.config` (`save` / `load` / `build` / `to_json`).

## Using the console

```python
# freecadcmd
>>> from scaletainer import tasks
>>> result = tasks.generate(
...     {"length": 14630.4, "width": 2590.8, "height": 2895.6,
...      "scale_divider": 87, "min_feature_mm": 0.25},
...     "~/Scaletainer", formats=("stl", "3mf"))
>>> print(result.text())
```

All values are 1:1 millimetres unless `unit=` says otherwise. Anything you leave
out keeps the reference value. `tasks.preview(values)` returns the derived
numbers without building geometry.

Configuration files work headless too — write one, then build straight from it:

```python
# freecadcmd
>>> from scaletainer import commands, config
>>> config.save("~/Scaletainer/box.json",
...             {"length": 14630.4, "width": 2590.8, "height": 2895.6,
...              "scale_divider": 87}, "mm",
...             {"directory": "~/Scaletainer", "formats": ["stl"],
...              "separate_parts": False}, name="48 ft at HO")
'/home/you/Scaletainer/box.json'
>>> print(commands.generate_from_config("~/Scaletainer/box.json").text())
```

`generate_from_config(path)` uses the file's folder, formats and parts option;
pass a second argument to send the output somewhere else. `config.load(path)`
returns the validated `values` dict if you would rather call `tasks.generate`
yourself.

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

For scale `1:87` you get `Scaletainer-168x30x33-1-87.*`:

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

The original hand-modelled container only had one (ribbed) end, leaving the
other side open. The
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

Toggle it off with `include_far_door=False` in the console (the panel always
builds both door ends).

The hand-modelled reference used separate PartDesign clones for each mounting
rib; here the three mounting ribs are one compound part, which is simpler and
print-ready.

## How the geometry is derived

The generator reproduces the reference design's construction:

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
make test           # all 124 tests: parameters, geometry, export, GUI, workbench
```

`make test` runs `tests/run_tests.py` headless (`freecadcmd`) with an offscreen
Qt platform, so it needs a display-free environment. The workbench test stubs
the `FreeCADGui` workbench API, which only exists in a GUI session.

`tests/test_geometry.py` pins the 1:160 build against the volumes and bounding
boxes measured from the original hand-modelled reference container — side walls
2189.6384 mm³, roof 1334.8501 mm³, floor 1242.9017 mm³, three mounting ribs
3 × 773.28 mm³, door end 163.4849 mm³.

Known difference: the reference door-end sketch had self-overlapping wires,
which inflate its volume slightly. The generated door
end is modelled cleanly (border ring plus ribbed slab) and matches the same
total volume.
