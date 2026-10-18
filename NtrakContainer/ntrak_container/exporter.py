"""Write the generated model out as FreeCAD, STEP, STL and 3MF files.

The exporters work from a FreeCAD document that already contains the components
(see :func:`builder.add_to_document`), which keeps the mesh/STEP writers on the
same tessellation we want for small scales.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import FreeCAD as App
import Mesh
import MeshPart

from . import builder
from .params import BuildConfig, ContainerParams, ScaledGeometry, derive

#: formats accepted by :func:`export_all`
FORMATS = ("fcstd", "step", "stl", "3mf")


@dataclass
class ExportResult:
    """Paths written by :func:`export_all`."""

    directory: str
    stem: str
    files: list[str]

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
    """Name carrying the key inputs, e.g. ``Ntrak-90x16x18-1-160``."""
    geom = geom or derive(params, cfg)
    return safe_name(f"Ntrak-{geom.length:.0f}x{geom.width:.0f}x{geom.height:.0f}"
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
        "generator": "NtrakContainer",
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
    name = group_label or f"Ntrak container 1-{cfg.scale_divider:g}"
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

    if separate_parts:
        sub = os.path.join(directory, f"{stem}-parts")
        os.makedirs(sub, exist_ok=True)
        for obj, comp in zip(objects, components):
            part = safe_name(comp.name)
            if "stl" in formats:
                files.append(write_mesh([obj], os.path.join(sub, f"{stem}-{part}.stl"), geom))
            if "3mf" in formats:
                files.append(write_mesh([obj], os.path.join(sub, f"{stem}-{part}.3mf"), geom))
            if "step" in formats:
                files.append(write_step([obj], os.path.join(sub, f"{stem}-{part}.step")))
        report(f"wrote {len(components)} part files in {sub}")
    if not keep_document:
        App.closeDocument(doc.Name)
    return ExportResult(directory=directory, stem=stem, files=files)
