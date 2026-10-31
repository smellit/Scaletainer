"""Write the generated model out as FreeCAD, STEP, STL and 3MF files.

The exporters work from a FreeCAD document that already contains the components
(see :func:`builder.add_to_document`), which keeps the mesh/STEP writers on the
same tessellation we want for small scales.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field

import FreeCAD as App
import Mesh
import MeshPart
import Part as FreeCADPart

from . import builder
from .params import BuildConfig, ContainerParams, ScaledGeometry, derive

#: formats accepted by :func:`export_all`
FORMATS = ("fcstd", "step", "stl", "3mf")


@dataclass
class Part:
    """One component rotated flat and placed on the build plate."""

    name: str
    shape: object
    color: tuple[float, float, float] = (0.78, 0.78, 0.78)


#: distance kept between laid-out parts on the build plate (model mm)
PART_SPACING_MM = 2.0


def lay_out_parts(objects, components=None, *,
                  spacing: float = PART_SPACING_MM) -> list[Part]:
    """Orient every component for printing and pack the set onto one plate.

    The parts are laid out flat with the outside face up (see
    :func:`place_flat`) and distributed over a near-square grid of rows, which
    keeps the whole multi-part job within a printable build volume.
    """
    parts = [place_flat(obj, comp) for obj, comp in _pair(objects, components)]
    if not parts:
        return []
    # rows of two long walls each keep the plate roughly as deep as it is long
    widest = max(part.shape.BoundBox.XLength for part in parts)
    deepest = max(part.shape.BoundBox.YLength for part in parts)
    per_row = max(1, math.ceil(math.sqrt(len(parts) * deepest / (widest + spacing))))
    laid: list[Part] = []
    x = y = 0.0
    for index, part in enumerate(parts):
        if index and index % per_row == 0:
            x = 0.0
            y = max((p.shape.BoundBox.YMax for p in laid), default=0.0) + spacing
        shape = part.shape
        shape.translate(App.Vector(x - shape.BoundBox.XMin, y - shape.BoundBox.YMin, 0.0))
        x = shape.BoundBox.XMax + spacing
        laid.append(part)
    return laid

def place_flat(obj, comp=None) -> Part:
    """Orient one component for printing and rest it on ``Z = 0``.

    Thin sheets are tipped so the ribbed outside face points up: that is the
    surface a slicer ironing pass smooths and the way the parts in a
    ``...-parts`` folder should be printed -- lying flat, no supports.  Sturdy
    parts are left as built, which already stands them on a face.
    """
    from .builder import Component

    if comp is None:
        comp = obj if isinstance(obj, Component) else Component("part", _shape_of(obj))
    shape = comp.shape.copy()
    shape.translate(-App.Vector(*_bbox_centre(shape.BoundBox)))

    rings = _ring_axis(shape)
    if rings is not None:
        shape = _lay_out_rings(shape, rings)
    else:
        # The thinnest dimension must end up vertical: that is the face a part
        # lies on, and for the ribbed sheets it is the flat outer face (relief
        # up) that an ironing pass smooths.
        axis = _thinnest_axis(shape.BoundBox)
        relief_up = _relief_dir(shape, axis)
        if axis == 0:                      # door ends: plate faces along X
            shape.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0),
                         90.0 if relief_up < 0 else -90.0)
        elif axis == 1:                    # side walls: plate faces along Y
            shape.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0),
                         -90.0 if relief_up < 0 else 90.0)
        elif relief_up < 0:                # floor: ribs built downwards
            shape.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), 180.0)

    shape.translate(-App.Vector(*_bbox_centre(shape.BoundBox)))
    shape.translate(App.Vector(0.0, 0.0, -shape.BoundBox.ZMin))
    return Part(name=comp.name, shape=shape, color=comp.color)


def write_3mf(parts: list[Part], path: str, geom: ScaledGeometry) -> str:
    """Write every part into one 3MF, one ``<object>`` per part.

    ``Mesh.export`` keeps the part placements, so the slicer receives separate
    printable objects laid out side by side rather than one merged blob.
    """
    doc = App.newDocument(safe_name(os.path.splitext(os.path.basename(path))[0]))
    try:
        objects = []
        for part in parts:
            obj = doc.addObject("Part::Feature", safe_name(part.name))
            obj.Label = part.name
            obj.Shape = part.shape
            builder._apply_color(obj, part.color)
            objects.append(obj)
        doc.recompute()
        Mesh.export(objects, path, tessellation(geom)["LinearDeflection"])
    finally:
        App.closeDocument(doc.Name)
    return path


def _pair(objects, components):
    if components is None:
        return [(obj, None) for obj in objects]
    return list(zip(objects, components))


def _shape_of(obj):
    return obj.Shape if hasattr(obj, "Shape") else obj


def _thinnest_axis(bb) -> int:
    return min(range(3), key=lambda axis: getattr(bb, "XYZ"[axis] + "Length"))


#: gap that marks rib rings as separate pieces rather than one joined part (mm)
_MIN_RING_GAP_MM = 0.05


def _ring_axis(shape) -> int | None:
    """Axis the ribs of a compound repeat along, or ``None`` for other parts.

    The mounting ribs are separate rings spread along their extrusion.  That
    repeated, gapped axis is the hole axis, and it has to end up vertical so
    each ring lies on its annulus face with the hole open upwards: a ring that
    stands on edge would have to bridge its own opening.
    """
    boxes = [solid.BoundBox for solid in getattr(shape, "Solids", [])]
    if len(boxes) < 2:
        return None
    for axis in range(3):
        low = sorted(getattr(box, "XYZ"[axis] + "Min") for box in boxes)
        high = sorted(getattr(box, "XYZ"[axis] + "Max") for box in boxes)
        if len({round(hi - lo, 6) for lo, hi in zip(low, high)}) != 1:
            continue
        if any(gap < _MIN_RING_GAP_MM for gap in (start - end for start, end in zip(low[1:], high))):
            continue
        return axis
    return None


def _lay_out_rings(shape, axis: int):
    """Tip every rib onto its annular face and line the rings up in one row."""
    rings = []
    x = 0.0
    for solid in shape.Solids:
        ring = solid.copy()
        ring.translate(-App.Vector(*_bbox_centre(ring.BoundBox)))
        if axis == 0:
            ring.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), 90.0)
        elif axis == 1:
            ring.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), 90.0)
        bb = ring.BoundBox
        ring.translate(App.Vector(x - bb.XMin, -bb.YMin, -bb.ZMin))
        x = ring.BoundBox.XMax + PART_SPACING_MM
        rings.append(ring)
    return FreeCADPart.makeCompound(rings)


def _bbox_centre(bb) -> tuple[float, float, float]:
    return tuple((getattr(bb, "XYZ"[axis] + "Min") + getattr(bb, "XYZ"[axis] + "Max")) / 2.0
                 for axis in range(3))


def _relief_dir(shape, axis: int) -> int:
    """Which way along *axis* the raised detail points (``-1`` or ``+1``).

    A ribbed sheet carries its plate on one side and its relief on the other,
    so the centre of mass sits slightly towards the plate.
    """
    mid = _bbox_centre(shape.BoundBox)[axis]
    solids = shape.Solids
    mass = sum(solid.Volume for solid in solids)
    if mass <= 0:
        return 1
    centre = sum(solid.Volume * getattr(solid.CenterOfMass, "xyz"[axis])
                 for solid in solids) / mass
    return -1 if centre > mid else 1


@dataclass
class ExportResult:
    """Paths written by :func:`export_all`."""

    directory: str
    stem: str
    files: list[str]
    #: parts of a multi-part print, each rotated flat for the build plate
    loose: list = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.files)

    def text(self) -> str:
        return "\n".join(self.files)


def safe_name(text: str) -> str:
    """Filesystem-friendly name: ``1:160`` becomes ``1-160``."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text).strip())
    return cleaned.strip("-._") or "container"


def default_stem(params: ContainerParams, cfg: BuildConfig,
                 geom: ScaledGeometry | None = None) -> str:
    """Name carrying the key inputs, e.g. ``Scaletainer-90x16x18-1-160``."""
    geom = geom or derive(params, cfg)
    return safe_name(f"Scaletainer-{geom.length:.0f}x{geom.width:.0f}x{geom.height:.0f}"
                     f"-1-{cfg.scale_divider:g}")


def tessellation(geom: ScaledGeometry) -> dict:
    """Scale-aware mesh deflection.

    ``LinearDeflection`` is absolute, so one fixed value would smooth the
    corrugation away at 1:220; a fraction of the smallest rib slope works at
    every scale.
    """
    slopes = [rib.slope for rib in (geom.side, geom.top, geom.bottom, geom.door)
              if rib.slope > 0]
    return {"LinearDeflection": max(min(slopes) * 0.25, 1e-4),
            "AngularDeflection": 22.5,
            "Relative": False}


def mesh_of(shape, geom: ScaledGeometry):
    return MeshPart.meshFromShape(Shape=shape, **tessellation(geom))


def write_mesh(objects, path: str, geom: ScaledGeometry) -> str:
    """Mesh *objects* (FreeCAD objects or shapes) and write one mesh file."""
    combined = Mesh.Mesh()
    for obj in objects:
        shape = obj.Shape if hasattr(obj, "Shape") else obj
        combined.addMesh(mesh_of(shape, geom))
    combined.write(path)
    return path


def write_document(doc, path: str) -> str:
    doc.saveAs(path)
    return path


def write_step(objects, path: str) -> str:
    import Import

    Import.export(objects, path)
    return path


def write_params(path: str, params: ContainerParams, cfg: BuildConfig,
                 geom: ScaledGeometry, components=None) -> str:
    """Sidecar with the exact inputs, derived values and any adjustments."""
    payload = {
        "generator": "Scaletainer",
        "unit": "mm",
        "scale": f"1:{cfg.scale_divider:g}",
        "input_1to1": params.to_dict(),
        "build_config": {
            "scale_divider": cfg.scale_divider,
            "min_feature_mm": cfg.min_feature_mm,
            "min_rib_pitch_mm": cfg.min_rib_pitch_mm,
            "include_mount_frame": cfg.include_mount_frame,
            "include_door_side": cfg.include_door_side,
            "include_far_door": cfg.include_far_door,
        },
        "derived_scale_space": {
            "length": geom.length,
            "width": geom.width,
            "height": geom.height,
            "inner_length": geom.inner_length,
            "side_envelope": geom.side_envelope,
            "side_plate": geom.side_plate,
            "mount_span": geom.mount_span,
            "mount_height": geom.mount_height,
            "mount_x": geom.mount_x,
            "ribs": {
                name: {"count": rib.count, "pitch": rib.pitch, "slope": rib.slope,
                       "hill": rib.hill, "valley": rib.valley, "height": rib.height}
                for name, rib in (("side", geom.side), ("top", geom.top),
                                  ("bottom", geom.bottom), ("door", geom.door))
            },
        },
        "notes": list(geom.notes),
    }
    if components:
        payload["components"] = [
            {"name": c.name, "volume_mm3": c.volume,
             "bbox": [c.bounding_box.XLength, c.bounding_box.YLength,
                      c.bounding_box.ZLength],
             "info": c.info}
            for c in components
        ]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return path


def build_document(params: ContainerParams, cfg: BuildConfig, *,
                   geom: ScaledGeometry | None = None,
                   group_label: str | None = None):
    """Create a fresh document holding the generated container."""
    geom = geom or derive(params, cfg)
    components = builder.build_components(
        geom,
        include_mount_frame=cfg.include_mount_frame,
        include_door=cfg.include_door_side,
        include_far_door=cfg.include_far_door,
    )
    name = group_label or f"Scaletainer 1-{cfg.scale_divider:g}"
    doc = App.newDocument(safe_name(name))
    objects = builder.add_to_document(doc, components, group_label=name)
    return doc, components, objects, geom


def export_all(params: ContainerParams, cfg: BuildConfig, directory: str,
               *, stem: str | None = None, formats=FORMATS,
               separate_parts: bool = True,
               geom: ScaledGeometry | None = None,
               keep_document: bool = True,
               progress=None) -> ExportResult:
    """Generate the model and write every requested file format.

    ``separate_parts`` writes one file per component next to the combined
    assembly files, which is what a multi-part print job needs.
    """
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"unknown export format(s): {', '.join(unknown)}")
    os.makedirs(directory, exist_ok=True)
    doc, components, objects, geom = build_document(params, cfg, geom=geom)
    stem = stem or default_stem(params, cfg, geom)
    files: list[str] = []

    def report(message: str) -> None:
        if progress:
            progress(message)

    if "fcstd" in formats:
        files.append(write_document(doc, os.path.join(directory, f"{stem}.FCStd")))
        report(f"wrote {files[-1]}")
    if "step" in formats:
        files.append(write_step(objects, os.path.join(directory, f"{stem}.step")))
        report(f"wrote {files[-1]}")
    if "stl" in formats:
        files.append(write_mesh(objects, os.path.join(directory, f"{stem}.stl"), geom))
        report(f"wrote {files[-1]}")
    if "3mf" in formats:
        files.append(write_mesh(objects, os.path.join(directory, f"{stem}.3mf"), geom))
        report(f"wrote {files[-1]}")
    files.append(write_params(os.path.join(directory, f"{stem}.json"),
                              params, cfg, geom, components))
    report(f"wrote {files[-1]}")

    loose = lay_out_parts(objects, components) if separate_parts else []
    if separate_parts:
        sub = os.path.join(directory, f"{stem}-parts")
        os.makedirs(sub, exist_ok=True)
        for part in loose:
            name = safe_name(part.name)
            if "stl" in formats:
                files.append(write_mesh([part.shape],
                                        os.path.join(sub, f"{stem}-{name}.stl"), geom))
            if "3mf" in formats:
                files.append(write_3mf([part],
                                       os.path.join(sub, f"{stem}-{name}.3mf"), geom))
            if "step" in formats:
                files.append(write_step([part.shape],
                                        os.path.join(sub, f"{stem}-{name}.step")))
        if "3mf" in formats:
            files.append(write_3mf(loose, os.path.join(directory, f"{stem}-parts.3mf"), geom))
            report(f"wrote {files[-1]}")
        report(f"wrote {len(loose)} part files in {sub}")
    if not keep_document:
        App.closeDocument(doc.Name)
    return ExportResult(directory=directory, stem=stem, files=files, loose=loose)
