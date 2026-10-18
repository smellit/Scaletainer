"""One-call entry points shared by the GUI, the workbench and ``freecadcmd``.

:func:`generate` takes plain Python values (exactly what the dialog collects),
builds the container and writes the requested files.  :func:`preview` returns
the derived scale-space numbers so the GUI can show them before generating.
"""

from __future__ import annotations

from dataclasses import dataclass

from .params import BuildConfig, ContainerParams, RibPattern, derive
from .units import Scale, to_mm

#: scalar 1:1 dimension fields, in the order the dialog shows them
INPUT_FIELDS = ("length", "width", "height", "frame_size", "door_frame_width",
                "top_skin", "bottom_skin")
#: fields holding a :class:`~ntrak_container.params.RibPattern`
RIB_FIELDS = ("side_ribs", "top_ribs", "bottom_ribs", "door_ribs")
#: mounting frame fields
MOUNT_FIELDS = ("mount_frame_depth", "mount_frame_wall", "mount_frame_chamfer")
#: far door hardware fields, also 1:1 lengths
FAR_DOOR_FIELDS = ("far_door_plate", "far_door_rod_width", "far_door_gap",
                   "far_door_corner")


@dataclass
class Preview:
    """Derived scale-space numbers for the preview table."""

    scale: Scale
    length: float
    width: float
    height: float
    inner_length: float
    side_envelope: float
    side_plate: float
    mount_span: float
    mount_height: float
    ribs: dict
    notes: list[str]
    #: far door end summary: band depth, plate, relief, hardware, rods, seam
    far_door: dict | None = None

    def rows(self) -> list[tuple[str, str]]:
        """``(label, value)`` pairs, handy for a table widget."""
        out = [
            ("Model length", f"{self.length:.4f} mm"),
            ("Model width", f"{self.width:.4f} mm"),
            ("Model height", f"{self.height:.4f} mm"),
            ("Corrugated span", f"{self.inner_length:.4f} mm"),
            ("Side wall depth", f"{self.side_envelope:.4f} mm"),
            ("Side wall plate", f"{self.side_plate:.4f} mm"),
            ("Mount rib span", f"{self.mount_span:.4f} mm"),
            ("Mount rib height", f"{self.mount_height:.4f} mm"),
        ]
        for name, rib in self.ribs.items():
            out.append((f"{name} ribs",
                        f"{rib['count']} x {rib['pitch']:.4f} mm pitch, "
                        f"{rib['height']:.4f} mm deep"))
        if self.far_door:
            fd = self.far_door
            out.append(("Far door band", f"{fd['band']:.4f} mm (flush at model length)"))
            out.append(("Far door plate", f"{fd['plate']:.4f} mm backing"))
            out.append(("Far door relief", f"{fd['relief']:.4f} mm raised detail"))
            out.append(("Far door frame", f"{fd['frame']:.4f} mm stiles/rails"))
            out.append(("Far door rods", f"{fd['rods_per_leaf']} per leaf, "
                        f"{fd['rod']:.4f} mm wide, seam {fd['gap']:.4f} mm"))
        return out


def container_params(values: dict, unit: str = "mm") -> ContainerParams:
    """Build :class:`ContainerParams` from dialog values expressed in *unit*.

    Only the keys present in *values* are overridden; everything else keeps the
    reference (48 ft ISO) value, so a partial dict is fine.
    """
    kwargs = {}
    for name in INPUT_FIELDS + MOUNT_FIELDS + FAR_DOOR_FIELDS:
        if values.get(name) is not None:
            kwargs[name] = to_mm(float(values[name]), unit)
    for name in RIB_FIELDS:
        raw = values.get(name)
        if raw is None:
            continue
        if isinstance(raw, RibPattern):
            kwargs[name] = raw
        else:
            kwargs[name] = RibPattern(int(raw["count"]), float(raw["slope"]),
                                      float(raw["ratio"]), float(raw["height"]))
    if values.get("mount_frame_count") is not None:
        kwargs["mount_frame_count"] = int(values["mount_frame_count"])
    return ContainerParams.reference().replaced(**kwargs)


def build_config(values: dict) -> BuildConfig:
    """Build :class:`BuildConfig` from dialog values.

    ``scale_divider`` (a number) or ``scale`` (a string like ``"1:87"``) selects
    the modelling scale; the rest are optional safety nets and toggles.
    """
    divider = values.get("scale_divider")
    if divider is None:
        from .units import parse_scale

        divider = parse_scale(str(values.get("scale", "1:160"))).divider
    return BuildConfig(
        scale_divider=float(divider),
        min_feature_mm=float(values.get("min_feature_mm") or 0.0),
        min_rib_pitch_mm=float(values.get("min_rib_pitch_mm") or 0.0),
        include_mount_frame=bool(values.get("include_mount_frame", True)),
        include_door_side=bool(values.get("include_door_side", True)),
        include_far_door=bool(values.get("include_far_door", True)),
    )


def preview(values: dict, unit: str = "mm") -> Preview:
    """Derive the scale-space geometry without building any shape."""
    params = container_params(values, unit)
    cfg = build_config(values)
    geom = derive(params, cfg)
    ribs = {name: {"count": rib.count, "pitch": rib.pitch, "height": rib.height}
            for name, rib in (("side", geom.side), ("top", geom.top),
                              ("bottom", geom.bottom), ("door", geom.door))}
    far_door = None
    if cfg.include_far_door and geom.far_door_available > 0:
        far_door = {"band": geom.far_door_available, "plate": geom.far_door_plate,
                    "relief": geom.far_door_hardware, "rod": geom.far_door_rod,
                    "gap": geom.far_door_gap, "corner": geom.far_door_corner,
                    "frame": geom.far_door_stile,
                    "rods_per_leaf": geom.far_door_rod_count}
    return Preview(
        scale=Scale(cfg.scale_divider),
        length=geom.length, width=geom.width, height=geom.height,
        inner_length=geom.inner_length, side_envelope=geom.side_envelope,
        side_plate=geom.side_plate, mount_span=geom.mount_span,
        mount_height=geom.mount_height, ribs=ribs, notes=list(geom.notes),
        far_door=far_door,
    )


def generate(values: dict, directory: str, *, unit: str = "mm",
             formats=("fcstd", "step", "stl", "3mf"),
             separate_parts: bool = True, keep_document: bool = True,
             progress=None):
    """Generate the model and write the requested files.

    Returns an :class:`ntrak_container.exporter.ExportResult`.  Unless ``keep_document``
    is set, the temporary FreeCAD document is closed again, which keeps headless
    runs tidy.
    """
    from .exporter import export_all

    params = container_params(values, unit)
    cfg = build_config(values)
    geom = derive(params, cfg)
    return export_all(params, cfg, directory, formats=formats,
                      separate_parts=separate_parts, geom=geom,
                      keep_document=keep_document, progress=progress)
