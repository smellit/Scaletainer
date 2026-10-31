# Scaletainer — scaled transport containers for FreeCAD

Scaletainer builds a corrugated freight container (ISO box / tank-tainer style)
from its **real full-size dimensions**. You type the container's actual length,
width and height, choose a modelling scale such as `1:87` (HO) or `1:160` (N),
and the workbench produces print-ready files: FreeCAD, STEP, STL and 3MF.

You do not need to model anything, and you do not need any Python knowledge.
Everything happens in a panel with ordinary input fields.

* **Works with FreeCAD 1.0 or newer** (the add-on needs FreeCAD 1.x).
* **Windows, Linux and macOS** — the add-on is pure Python, nothing to compile.
* The result is a clean, solid model with one part per component, sitting on the
  build plate so it can be sliced straight away.

**See it in one minute** — type the 1:1 dimensions, pick `1:160 (N)` and press
*Generate container*:

https://github.com/user-attachments/assets/c88eb2c6-5cc4-41e6-b0c2-9a2cbd2dda46

---

## 1. Install

### Option A — the Addon Manager (recommended, all systems)

1. Start FreeCAD.
2. Open the **Addon Manager** from the **Tools** menu.
3. Select the **Workbenches** tab.
4. Find **Scaletainer** in the list and install it. If the add-on is not in the
   catalogue yet, install it manually with [option B](#option-b--copy-the-folder-yourself)
   instead.
5. **Close FreeCAD completely and start it again.** This is not optional —
   FreeCAD only looks for add-ons while it starts up.

### Option B — copy the folder yourself

Download the repository as a ZIP from
[github.com/smellit/scaletainer](https://github.com/smellit/scaletainer)
(**Code → Download ZIP**), unzip it, and copy the resulting folder into your
FreeCAD `Mod` folder, renaming it to **`Scaletainer`**. The folder name matters.

Where is the `Mod` folder?

| System | Path |
| --- | --- |
| **Windows** | `C:\Users\<you>\AppData\Roaming\FreeCAD\v1-1\Mod` |
| **macOS** | `~/Library/Application Support/FreeCAD/v1-1/Mod` |
| **Linux** (AppImage, deb, system package) | `~/.local/share/FreeCAD/v1-1/Mod` |
| **Linux** (Flatpak) | `~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod` |

`AppData` and `Library` are hidden by default. On Windows type `%APPDATA%` into
the Explorer address bar; on macOS use **Go → Go to Folder…** in the Finder.

The `v1-1` part is your FreeCAD version — FreeCAD 1.0 uses `v1-0`, so if the
path above does not exist, look for the similar folder next to it. To see the
exact folder for your installation, start FreeCAD, open **View → Panels →
Python console** and enter:

```python
import FreeCAD; FreeCAD.getUserAppDataDir()
```

The printed path is where the `Mod` folder belongs (create `Mod` if it is not
there yet).

After copying, **restart FreeCAD**.

### Check it worked

In the workbench selector dropdown (the list near the top of the window that
normally shows *Part*, *Sketcher*, *Assembly*, …) there should now be a
**Scaletainer** entry. Pick it: a **Scaletainer** menu and toolbar appear.

If it is missing, see [Troubleshooting](#6-troubleshooting).

---

## 2. Generate your first container

1. Choose the **Scaletainer** workbench.
2. Click **Scaletainer → Generate container…** (toolbar icon or the shortcut
   `G` then `N`).
3. The panel opens with a real 48 ft container already filled in. Pick your
   **Modelling scale** on the **Scale & options** tab — `1:160 (N)` or
   `1:87 (HO)`.
4. Go to the **Generate** tab, choose an **Output folder**, and press
   **Generate container**.
5. A message in the status line lists the written files. Open the folder and
   load the `.FCStd` into FreeCAD, or the `.stl` / `.3mf` into your slicer.

That is all there is to it. The rest of this page explains the settings.

---

## 3. The panel, tab by tab

The window is called **Scaletainer** and has five tabs. Above them sit
**Save config…**, **Load config…** and a name field (see
[section 4](#4-saving-and-loading-a-design)).

### Dimensions (1:1)

Everything here is the **real, full-size** measurement of the container — not
the scaled-down model size. Scaletainer divides it by your scale for you.

* **Standard size** — a dropdown of the common boxes: 20 ft dry, 20 ft high
  cube, 20 ft reefer, 40 ft dry, 40 ft high cube, 45 ft high cube, the 48 ft
  reference container and a 53 ft domestic box. Choosing one fills in length,
  width and height.
* **Overall length / width / height** — the outside dimensions. If you edit any
  of these three by hand, the dropdown switches to `-- custom / enter manually
  --` so you can see you left the standard sizes; the other fields keep their
  values.
* **End frame / corner fitting width** — the thickness of the corner posts and
  fittings at each end. This is what the corrugated wall panels sit between.
* **Door end border width** — the frame around the ribbed door end.
* **Roof plate / Floor plate thickness** — the sheet metal of roof and floor.
* **Mount rib depth / wall thickness / corner chamfer** — the three ribs on the
  underside that a truck chassis, spine or twist-lock actually grips.
* **Far door backing plate / locking rod width / centre seam width / hinge,
  handle & casting size** — the details of the realistic double-door end: the
  solid plate the door relief sits on, the two vertical locking rods per leaf,
  the recessed seam where the leaves meet, and the size of the hinge blocks,
  handles and corner castings.

The fields show **whole numbers** and have no up/down arrows, which keeps them
readable. The exact value is still used behind the scenes: the 48 ft reference
size shows `14630 mm` but stays `14630.4 mm` in the generator.

### Corrugation

Four groups — **Side wall corrugation**, **Roof corrugation**, **Floor
corrugation**, **Door end ribs**. Each has the same four settings, and they
describe the repeating wave profile of the sheet:

| Setting | Meaning |
| --- | --- |
| **Rib count** | How many corrugation waves fit along that surface. More ribs = finer, busier texture. |
| **Slope width** | How wide the slanted part of each wave is. Larger values make softer, rounder-looking waves; small values make crisp, sharply creased ribs. |
| **Relief depth** | How deep the wave sticks out — the thickness of the corrugation itself. |
| **Crest share of flat span** | Each wave has a flat top (crest) and a flat bottom (valley). This splits the leftover flat distance between them: `0.5` gives equal crest and valley, higher values give wider flat tops and narrower valleys. |

The side walls are the ones that decide the look of the model, so start there.

### Scale & options

* **Input unit** — mm, cm, m, in or ft. This only changes how you *type* the
  dimensions on the Dimensions tab. Switching unit rewrites the fields in the
  new unit **without changing the size of the model**, so you can go from
  millimetres to feet and back freely.
* **Modelling scale** — `1:22.5 (G / I)`, `1:32`, `1:43.5 (OO)`, `1:48 (O)`,
  `1:64 (S)`, `1:72`, `1:76 (EM)`, `1:87 (HO)`, `1:100`, `1:120 (TT)`, `1:150`,
  `1:160 (N)`, `1:180 (Z)` and `1:225 (Zm)`. A scale that is not in the list can
  be restored from a saved configuration file, which then adds it to the
  dropdown.
* **Minimum feature size** — a safety net for 3D printing. Any part of the model
  thinner than this is made thicker. Leave it at `0` for the exact proportions;
  set it to roughly your printer nozzle width (e.g. `0.2` or `0.25`) when
  printing very small. See [section 5](#5-printing-the-model).
* **Minimum rib pitch** — the second safety net: ribs are dropped one by one
  until the distance between them reaches this value, instead of leaving
  impossibly fine texture.

Both of those are measured in **millimetres of the finished model** and always
stay in millimetres, whatever input unit you picked above.
* **Build mounting frame ribs** — turn off to skip the underframe ribs (a
  lighter file if you only ever show the box from above).
* **Mounting ribs** — how many of those ribs to place.

Both door ends are always built.

### Preview

Read-only, and the most useful tab for checking a design: a table of the
**Derived value** and its **Scale space** result — the finished model length,
width and height, wall depth, rib pitch, mount rib size and so on. Below the
table, a log lists every automatic adjustment, for example
`side_ribs: 24 -> 20 ribs`.

If a field is impossible, the status line at the bottom says so and nothing is
generated.

### Generate

* **Output folder** — where the files go, with a **Browse…** button.
* **Formats** — tick any combination. FreeCAD document and STL are ticked by
  default; untick what you do not need to save time.
  * **FreeCAD document (.FCStd)** — one object per component, inside a group.
  * **STEP (.step)** — for CAD programs and CNC work.
  * **STL (.stl)** — for slicing.
  * **3MF (.3mf)** — modern slicer format, carries colours and units.
* **Also write one file per component** — adds a `...-parts` subfolder with a
  separate STL / 3MF / STEP for each piece, for printing parts individually, and
  a `...-parts.3mf` file holding every piece as its own object, laid out flat
  side by side on the build plate so they print together in one job. The
  mounting ribs lie on their annular face in one row, so each ring stays open.
* **Save output folder, formats and parts option in config files** — on, a saved
  configuration also stores these settings; off, a file carries only the design
  and loading it leaves your current output settings alone.
* **Generate container** — writes the files.

---

## 4. Saving and loading a design

**Save config…** writes a small `.json` file holding everything in the panel:
dimensions, corrugation, scale, safety nets, options, input unit, and an
optional **name**. **Load config…** refills the panel from such a file.

This is how you keep a fleet: save one file per container type, then load and
tweak it for a variant. A few things worth knowing:

* Dimensions are stored in the file's own unit, so loading a file written in
  inches switches the panel to inches rather than rescaling the numbers.
* A scale outside the preset list is kept and added to the dropdown.
* Files are checked when loaded. An unknown setting, a rib count with a decimal
  in it or a file from a newer version of the add-on is reported in the status
  line, and your panel is left untouched.
* The `.json` file Scaletainer writes **next to each model** can be loaded back
  into the panel too, so a finished container can be reopened and adjusted.

---

## 5. Printing the model

At `1:160` a 48 ft container is only about 91 mm long, so many real features
end up thinner than a printer nozzle. The two safety nets on the
**Scale & options** tab exist for this:

* **Minimum feature size** raises anything too thin.
* **Minimum rib pitch** removes ribs that would be too close together.

Both are `0` (off) by default, so the model matches reality exactly until you
ask otherwise. When raising a profile would make the corrugation run past the
wall, Scaletainer reduces the rib count instead — always reported in the
**Preview** tab and recorded in the `.json` file, so nothing is changed behind
your back.

The model sits in the first octant with the floor ribs at `Z = 0`: drop the STL
or 3MF into your slicer and it is already resting on the plate.

Components written: `SideWallRight`, `SideWallLeft`, `Roof`, `Floor`,
`MountFrame` (the gripping ribs), `DoorSide` (the ribbed end) and `FarDoor`
(the realistic double-door end with locking rods, hinges and corner castings).

**Each face is a separate part on purpose.** The generator writes the six faces
individually so you can lay each one flat on the printer bed instead of printing
a hollow box with bridged roofs and long overhangs. Flat parts print faster,
need little or no support, and come out cleaner — glue them together after the
print.

**Turn on ironing for the best surface.** At these scales the top skin is all
that is visible, and the corrugation and rib patterns show every layer line.
Ironing drags the hot nozzle once more over the finished top surface and melts
it smooth, which is the single biggest quality gain for these parts:

* **PrusaSlicer / SuperSlicer** — **Print settings → Layers and perimeters →
  Ironing** (check *Ironing only on top* to keep the time down).
* **Cura** — search **ironing** in the print settings. The settings live in the
  *Skin* category and are hidden by default: tick **Ironing** under
  **Preferences → Configure tool settings**, then enable **Enable Ironing** in the *Prepare* sidebar. Tune **Ironing  Flow**, **Ironing Speed** and **Ironing Line Spacing** if the surface looks shiny-but-rough.

It adds a little print time per part and is worth it on the walls, roof and
doors. Print the parts flat with the outside face up, and keep the first layer
slow so thin parts do not warp off the bed.

---

## 6. Troubleshooting

* **No Scaletainer in the workbench list** — quit FreeCAD fully and start it
  again; the list is only built at startup. Then confirm the folder really is
  `Mod/Scaletainer` and that
  `Scaletainer/InitGui.py` is inside it.
* **The folder is right but nothing appears** — a second FreeCAD version on the
  same machine may use a different `Mod` folder. Check the exact path with the
  `FreeCAD.getUserAppDataDir()` line from [section 1](#option-b--copy-the-folder-yourself).
* **The panel shows an error in the status line** — it is telling you which
  field is impossible (usually a rib count too high for the size, or a dimension
  of zero). Fix that field; nothing bad has been written.
* **The files are not where you expected** — the status line after generating
  lists the full paths, and the `.json` beside them repeats the folder.
* **A generated model looks empty in the 3D view** — at `1:160` it is small;
  press **View → Standard views → Fit all** (shortcut `V` then `F`) to zoom to
  it.

---

## 7. Licence and links

* Licence: **GNU LGPL 2.1 or later** — see [LICENSE.md](LICENSE.md).
* Source and issue tracker: [github.com/smellit/scaletainer](https://github.com/smellit/scaletainer)
* Author: smellit
* Running headless in a terminal, the file formats, the geometry maths and the
  test suite are documented for developers and scripters in
  **[DEVELOPER.md](DEVELOPER.md)**.
