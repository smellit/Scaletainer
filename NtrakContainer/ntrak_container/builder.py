"""Build the container solids from derived scale-space parameters.

No spreadsheet is involved: :func:`params.derive` computes the lengths and this
module turns them into ``Part`` shapes.  Every component is returned as a
:class:`Component`, so the same code path runs in the GUI and in ``freecadcmd``.

Coordinate system (scale-space millimetres), kept in the first octant so the
model is ready to slice:

* ``X`` -- container length.  The ribbed door end occupies
  ``0 .. door_frame_width`` and the corrugated side walls run from there over
  the corrugated span.
* ``Y`` -- container width, measured crest plane to crest plane: the right
  wall crest is at ``Y = 0`` and the left wall crest at ``Y = width``.
* ``Z`` -- container height; the floor's rib crest plane is at ``Z = 0`` and
  the roof's at ``Z = height``.

The corrugated walls are flush with the mounting frame ribs and the skins
close the box between them, which is how the reference model is built.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import FreeCAD as App
import Part

from . import profiles
from .params import ScaledGeometry

Vec = App.Vector


@dataclass
class Component:
    """One printable / selectable part of the container."""

    name: str
    shape: Part.Shape
    color: tuple[float, float, float] = (0.78, 0.78, 0.78)
    #: extra numbers shown in the report (rib counts, thicknesses, ...)
    info: dict[str, float | int] = field(default_factory=dict)

    @property
    def volume(self) -> float:
        return self.shape.Volume

    @property
    def bounding_box(self) -> App.BoundBox:
        return self.shape.BoundBox

    def summary(self) -> str:
        bb = self.bounding_box
        return (f"{self.name}: {self.volume:.3f} mm3, "
                f"{bb.XLength:.3f} x {bb.YLength:.3f} x {bb.ZLength:.3f} mm")


# --------------------------------------------------------------------------
# low level helpers
# --------------------------------------------------------------------------


def make_face(loops: list[list[tuple[float, float]]], origin: tuple[float, float, float],
              u_axis: tuple[float, float, float],
              v_axis: tuple[float, float, float]) -> Part.Face:
    """Make a face from 2D loops placed at *origin* with axes *u* and *v*.

    The first loop is the outline, any further loops become holes.
    """
    u, v, base = Vec(*u_axis), Vec(*v_axis), Vec(*origin)

    def wire(loop, reversed_loop):
        pts = list(reversed(loop)) if reversed_loop else loop
        points = [base + u * px + v * py for px, py in pts]
        points.append(points[0])
        return Part.makePolygon(points)

    # OCC needs the hole wires wound against the outline.
    wires = [wire(loops[0], False)] + [wire(l, True) for l in loops[1:]]
    return Part.Face(wires)


def extrude(face: Part.Face, direction: tuple[float, float, float],
            length: float) -> Part.Shape:
    return face.extrude(Vec(*direction) * length)


def moved(shape: Part.Shape, offset: tuple[float, float, float]) -> Part.Shape:
    return shape.translated(Vec(*offset))


def pattern(shape: Part.Shape, direction: tuple[float, float, float],
            offset: float, occurrences: int) -> list[Part.Shape]:
    """Copy *shape* ``occurrences`` times spaced by *offset* along *direction*."""
    step = Vec(*direction) * offset
    return [moved(shape, (step.x * i, step.y * i, step.z * i))
            for i in range(max(int(occurrences), 1))]


# --------------------------------------------------------------------------
# components
# --------------------------------------------------------------------------


def build_side_wall(geom: ScaledGeometry, *, right: bool) -> Component:
    """Corrugated long side wall, extruded over the full container height.

    Solid rails of ``frame_size`` height close the corrugation at the bottom
    and top of the wall, as in the reference model (its two extra pads).
    """
    rib = geom.side
    loop = profiles.side_wall(rib, geom.side_envelope)
    x0 = geom.door_frame_width
    length = rib.pitch * rib.count
    if right:
        origin, v_axis, y0 = (x0, rib.height, 0.0), (0.0, -1.0, 0.0), 0.0
    else:
        origin, v_axis, y0 = (x0, geom.width - rib.height, 0.0), (0.0, 1.0, 0.0), \
            geom.width - geom.side_envelope
    face = make_face([loop], origin, (1.0, 0.0, 0.0), v_axis)
    shape = extrude(face, (0.0, 0.0, 1.0), geom.height)
    rails = [Part.makeBox(length, geom.side_envelope, geom.frame_size,
                          Vec(x0, y0, z))
             for z in (0.0, geom.height - geom.frame_size)]
    shape = shape.multiFuse(rails)
    return Component(
        "SideWallRight" if right else "SideWallLeft", shape, (0.78, 0.78, 0.78),
        {"ribs": rib.count, "pitch": rib.pitch, "plate": geom.side_plate,
         "relief": rib.height, "depth": geom.side_envelope},
    )


def build_roof(geom: ScaledGeometry) -> Component:
    """Corrugated roof: ribs outwards, plate towards the interior."""
    rib = geom.top
    loop = profiles.roof(rib, geom.top_skin)
    origin = (geom.door_frame_width, geom.side_envelope, geom.height - rib.height)
    face = make_face([loop], origin, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    shape = extrude(face, (0.0, 1.0, 0.0), geom.mount_span)
    return Component("Roof", shape, (0.69, 0.69, 0.69),
                     {"ribs": rib.count, "pitch": rib.pitch, "plate": geom.top_skin})


def build_floor(geom: ScaledGeometry) -> Component:
    """Corrugated floor: ribs into the interior, crest plane flush with ``Z = 0``."""
    rib = geom.bottom
    loop = profiles.floor(rib, geom.bottom_skin)
    origin = (geom.door_frame_width, geom.side_envelope, rib.height)
    face = make_face([loop], origin, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    shape = extrude(face, (0.0, 1.0, 0.0), geom.mount_span)
    return Component("Floor", shape, (0.63, 0.63, 0.63),
                     {"ribs": rib.count, "pitch": rib.pitch, "plate": geom.bottom_skin})


def build_mount_frame(geom: ScaledGeometry) -> Component:
    """Mounting ribs that hold the container, spread over the corrugated span.

    Each rib is a ring: an outer rectangle with chamfered corners and a
    rectangular opening, so the walls and skins sit inside it.
    """
    loops = profiles.frame_ring(geom.mount_span, geom.mount_height,
                                geom.mount_frame_wall, geom.mount_frame_chamfer)
    origin = (geom.door_frame_width, geom.side_envelope,
              geom.bottom.height + geom.bottom_skin)
    face = make_face(loops, origin, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    rib = extrude(face, (1.0, 0.0, 0.0), geom.mount_frame_depth)
    shapes = [moved(rib, (x, 0.0, 0.0)) for x in geom.mount_x]
    return Component("MountFrame", Part.makeCompound(shapes), (0.50, 0.55, 0.58),
                     {"ribs": len(shapes), "wall": geom.mount_frame_wall,
                      "depth": geom.mount_frame_depth, "span": geom.mount_span,
                      "height": geom.mount_height})


def build_door_side(geom: ScaledGeometry) -> Component:
    """Ribbed door end: a frame border ring plus the vertical ribs inside it."""
    rib = geom.door
    fw = geom.door_frame_width
    outer = profiles.chamfered_rect(geom.width, geom.height, 0.0)
    inner = [(fw, fw), (geom.width - fw, fw),
             (geom.width - fw, geom.height - fw), (fw, geom.height - fw)]
    border = make_face([outer, inner], (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    parts = [extrude(border, (1.0, 0.0, 0.0), fw)]

    loop = profiles.door(rib, fw)
    y_start = fw + (geom.door_span - rib.span) / 2.0
    # local v = +X, placed so the skin's outer face is at X = 0 and the rib
    # crests reach inward to X = fw; the loop already holds every rib
    rib_face = make_face([loop], (fw - rib.height, y_start, fw),
                         (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    parts.append(extrude(rib_face, (0.0, 0.0, 1.0), geom.height - 2 * fw))
    return Component("DoorSide", Part.makeCompound(parts), (0.78, 0.78, 0.78),
                     {"ribs": rib.count, "pitch": rib.pitch, "border": fw,
                      "relief": rib.height})


def build_end_frame(geom: ScaledGeometry) -> Component:
    """Corner posts at both ends, as a separate support frame part."""
    post = geom.side_envelope
    x0 = geom.door_frame_width
    x1 = x0 + geom.inner_length - post
    shapes = [Part.makeBox(post, post, geom.height, Vec(x, y, 0.0))
              for x in (x0, x1) for y in (0.0, geom.width - post)]
    return Component("EndFrame", Part.makeCompound(shapes), (0.50, 0.55, 0.58),
                     {"post": post})


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def build_components(geom: ScaledGeometry, *, include_mount_frame: bool = True,
                     include_door: bool = True,
                     include_end_frame: bool = False) -> list[Component]:
    """Assemble every requested component of the container."""
    parts = [
        build_side_wall(geom, right=True),
        build_side_wall(geom, right=False),
        build_roof(geom),
        build_floor(geom),
    ]
    if include_mount_frame:
        parts.append(build_mount_frame(geom))
    if include_door:
        parts.append(build_door_side(geom))
    if include_end_frame:
        parts.append(build_end_frame(geom))
    return parts


def assembly_shape(components: list[Component]) -> Part.Shape:
    """Single compound shape holding every component."""
    return Part.makeCompound([c.shape for c in components])


def add_to_document(doc, components: list[Component], *,
                    group_label: str = "Container") -> list:
    """Add one ``Part::Feature`` per component to *doc*, inside a group.

    Returns the created objects so the caller can select or export them.
    """
    group = doc.addObject("App::DocumentObjectGroup", "ContainerGroup")
    group.Label = group_label
    created = []
    for comp in components:
        obj = doc.addObject("Part::Feature", comp.name)
        obj.Label = comp.name
        obj.Shape = comp.shape
        created.append(obj)
        group.addObject(obj)
        _apply_color(obj, comp.color)
    doc.recompute()
    return created


def _apply_color(obj, rgb: tuple[float, float, float]) -> None:
    """Best-effort colouring; headless sessions have no view object."""
    try:
        obj.ViewObject.ShapeColor = rgb
    except Exception:
        pass
