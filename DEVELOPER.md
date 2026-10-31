# Scaletainer — developer and scripting notes

Companion to the [user guide](README.md). Everything here assumes you are
comfortable with a terminal, FreeCAD's Python console or the source tree.

## Architecture

```
Init.py                 puts the add-on folder on sys.path (GUI + console)
InitGui.py              registers the Scaletainer workbench (GUI only)
package.json            Addon Manager metadata
scaletainer/
  units.py              input units, scale presets, scale parsing
  params.py             1:1 parameter model + scale-space derivation
  profiles.py           2D rib / frame cross-sections
  builder.py            FreeCAD Part shapes and document assembly
  exporter.py           FCStd / STEP / STL / 3MF writers + JSON sidecar
  config.py             JSON save/load of panel values and options
  tasks.py              one-call headless entry point
  commands.py           workbench command, CLI helpers, output defaults
  gui.py                PySide panel
resources/container.svg workbench icon
tests/                  unittest suite, runs headless under freecadcmd
```

The generator is fully scripted: **no spreadsheet object is created in the
document**. All parameter maths runs in plain Python and the output is plain
`Part` geometry, which keeps the files small and print-ready.

`Init.py` and `InitGui.py` are executed by FreeCAD with *separate* globals and
locals dictionaries, may receive a relative `__file__`, and omit `__file__`
entirely in console mode. Both locate the add-on folder by testing candidate
paths rather than trusting the process working directory. A `class` body only
sees module globals, which is why the workbench is built inside the factory
function in `InitGui.py`. `freecadcmd` provides a stub `FreeCADGui` without the
workbench API, so registration is guarded by `hasattr`.

## Headless use

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

Configuration files work headless too:

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

The default output folder is `~/Scaletainer`; override it with the
`SCALETAINTER_OUTPUT` environment variable.

## Configuration file format

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

`values` holds the plain dict `scaletainer.tasks` expects, so a file can also be
fed straight to `tasks.generate`. Two other shapes are accepted on load:

* a **bare values dict** (top-level `length`/`width`/`height`), treated as a
  configuration with the default unit and no export settings;
* the **sidecar** the generator writes next to the models (`input_1to1` plus
  `build_config`), converted back into a configuration.

`config.FORMAT` is the current marker; `config.LEGACY_FORMATS` additionally
accepts `"NtrakContainer/config"`, written before the add-on was renamed, so old
saved designs still load. A foreign marker is rejected. Only `config.py` and the
panel touch files — nothing there imports Qt or FreeCAD, so the format is
testable in plain Python.

## Output files

For scale `1:87` you get `Scaletainer-168x30x33-1-87.*`:

| File | Contents |
| --- | --- |
| `.FCStd` | one `Part::Feature` per component inside a group, no spreadsheets |
| `.step` | the same components as solids |
| `.stl`, `.3mf` | meshed assembly |
| `.json` | inputs, derived values, adjustments, per-part volume and size |
| `...-parts/` | one STL/3MF/STEP per component, oriented flat, for multi-part prints |
| `...-parts.3mf` | every component as a 3MF object, laid out flat on the plate for printing together |

In the parts layout each sheet is tipped so its ribbed face points up, the door
ends lie on their outer face, and the mounting ribs lie on their annular face in
a single row, so no part needs support.

Components: `SideWallRight`, `SideWallLeft`, `Roof`, `Floor`, `MountFrame`,
`DoorSide` (the ribbed end) and `FarDoor` (the double-door end). The model sits
in the first octant with the floor ribs at `Z = 0`, so it slices without moving.

## How the geometry is derived

The generator reproduces the reference design's construction:

* `inner_length = length - 2 * frame_size` — the corrugated span.
* Side wall depth `= 2 * frame_size`, plate `= depth - rib height`, so the
  corrugation is flush with the end frames.
* `pitch = span / count / scale`, `flat = pitch - 2 * slope`, split into crest
  (`flat * ratio`) and valley (`flat * (1 - ratio)`).
* Mounting ribs span `width - 2 * wall_depth` and are spread evenly over the
  corrugated span.
* `floor_depth = bottom.height + bottom_skin` is the total floor thickness. With
  `include_floor_corrugation` off, `build_floor` extrudes a flat plate of exactly
  that depth (`profiles.flat_floor`), so the interior height, `mount_height` and
  the overall container height are unchanged.

Coordinate system: `X` = length (door end at `X = 0`), `Y` = width crest plane
to crest plane, `Z` = height with the floor crest plane at `Z = 0`.

### Printability clamps

Both `min_feature_mm` and `min_rib_pitch_mm` default to `0` (off), so the
reference model is reproduced exactly. When a raised profile no longer fits the
corrugated span, the rib count is reduced instead of letting the corrugation run
past the wall; each change is reported in the Preview tab and recorded in the
`.json` sidecar.

### The far door end

The original hand-modelled container only had one (ribbed) end. `FarDoor` closes
the other with two leaves meeting at a recessed centre seam, raised stiles and
rails, two vertical locking rods and cam-keeper blocks per leaf, hinge blocks on
the outer edges and corner castings. Two design rules keep it safe:

* **It never exceeds the overall length.** The door fills exactly the band
  between the corrugated shell (`overall_length`) and the nominal 1:1 `length`,
  so its outer face is flush and the bounding box is always `length`.
* **It is raised relief on a solid backing plate**, not thin protrusions. At
  1:160 the backing plate is ~0.30 mm and the raised detail ~0.58 mm;
  `min_feature_mm` raises anything too thin for a coarser nozzle and the detail
  then reads as a flat panel.

Toggle it with `include_far_door=False` (the panel always builds both ends). The
reference used separate PartDesign clones per mounting rib; here the three ribs
are one compound part.

## Development

The repository root *is* the add-on folder: `Init.py`, `InitGui.py`,
`package.json`, `scaletainer/` and `resources/` must stay together, and the
installed folder in `Mod` must be named `Scaletainer`.

```sh
make link    DESTDIR=~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod
make install DESTDIR=...          # copy instead of symlink
make uninstall
make lint                         # every .py file parses
make test-params                  # parameter maths, plain Python, no FreeCAD
make test-config                  # config format, plain Python, no FreeCAD
make test                         # full suite via freecadcmd
```

`make test` runs `tests/run_tests.py` headless with `QT_QPA_PLATFORM=offscreen`
and defaults to the Flatpak `freecadcmd`; point `FREECAD=` at another binary,
e.g. `make test FREECAD=freecadcmd` for an AppImage on PATH. The Makefile
installs an explicit `PAYLOAD` list so `.git` and repository metadata stay out
of the `Mod` folder.

`tests/test_workbench.py` stubs the `FreeCADGui` workbench API, which only
exists in a GUI session, and covers the relative-`__file__` and missing-`__file__`
cases. `tests/test_geometry.py` pins the 1:160 build against volumes and
bounding boxes measured from the original hand-modelled reference container —
side walls 2189.6384 mm³, roof 1334.8501 mm³, floor 1242.9017 mm³, three
mounting ribs 3 × 773.28 mm³, door end 163.4849 mm³.

Known difference: the reference door-end sketch had self-overlapping wires, which
inflate its volume slightly. The generated door end is modelled cleanly (border
ring plus ribbed slab) and matches the same total volume.

## Release checklist

* Bump `version` (and `date`, format `YYYY-MM-DD`) in `package.json` — the
  Addon Manager compares these.
* Keep `name` in `package.json` equal to the repository folder name used in
  `Mod`.
* `make lint && make test` before tagging.
* Changing the add-on name also means updating `config.LEGACY_FORMATS` so files
  written by the previous name keep loading.
