r"""Cross-section profiles.

Every function returns one closed polygon in a sketch's local ``(u, v)``
coordinates, in **scale space** millimetres.  The builder turns a polygon into
a face and extrudes it along the local normal -- the same shape as the
reference model's sketch + pad + linear pattern, but as a single solid per
component, which is friendlier for slicing.

Corrugation convention (``Side`` / ``Top`` / ``Bottom`` sheets of the original
spreadsheets)::

        crest              crest
      ________            ________      <- crest plane, relief depth `height`
     /        \          /        \     <- slope (`slope` wide)
    /          \________/          \
    u=0                            u=span
    |-hill/2-|slope|---valley---|slope|-hill/2-|

``flat = pitch - 2 * slope`` is split into ``hill = flat * ratio`` and
``valley = flat * (1 - ratio)``.  The skin plate of thickness ``plate`` closes
the polygon on the far side of the ribs, so the total wall depth is
``plate + height``.
"""

from __future__ import annotations

from .params import ScaledRib

TOLERANCE = 1e-9


def _clean(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop consecutive duplicates; the caller closes the loop."""
    out: list[tuple[float, float]] = []
    for p in points:
        if out and abs(out[-1][0] - p[0]) < TOLERANCE and abs(out[-1][1] - p[1]) < TOLERANCE:
            continue
        out.append(p)
    while len(out) > 2 and abs(out[0][0] - out[-1][0]) < TOLERANCE \
            and abs(out[0][1] - out[-1][1]) < TOLERANCE:
        out.pop()
    return out


def corrugated_slab(rib: ScaledRib, plate: float, *, crest_towards: int = +1,
                    count: int | None = None) -> list[tuple[float, float]]:
    """``count`` pitches of corrugation plus the backing plate.

    ``crest_towards=+1`` puts the crest at ``v = +height`` and the plate behind
    it at ``v = -plate`` (side walls, roof).  ``-1`` mirrors the profile so the
    crest is at ``v = -height`` and the plate beyond it at ``v = +plate``
    (floor, door).  Which way is "outwards" is decided by how the builder
    orients ``v`` in 3D, not by the sign here.

    ``u`` runs along the corrugation from ``0`` to ``rib.pitch * count``.
    """
    if plate <= 0:
        raise ValueError(f"plate thickness must be positive, got {plate:.6f} mm")
    n = rib.count if count is None else max(int(count), 1)
    s = 1.0 if crest_towards >= 0 else -1.0
    h = s * rib.height
    half_hill = rib.hill / 2.0
    pts: list[tuple[float, float]] = [(0.0, h)]
    for i in range(n):
        x = i * rib.pitch
        pts += [
            (x + half_hill, h),
            (x + half_hill + rib.slope, 0.0),
            (x + half_hill + rib.slope + rib.valley, 0.0),
            (x + half_hill + 2 * rib.slope + rib.valley, h),
            (x + rib.pitch, h),
        ]
    span = rib.pitch * n
    pts += [(span, -s * plate), (0.0, -s * plate)]
    return _clean(pts)


def side_wall(rib: ScaledRib, envelope: float) -> list[tuple[float, float]]:
    """Side wall over all its ribs.

    ``envelope`` is the total wall depth from crest plane to inner face; the
    reference model derives it as ``2 * frame_size``.  The plate is whatever is
    left after the rib relief.
    """
    return corrugated_slab(rib, envelope - rib.height, crest_towards=+1)


def roof(rib: ScaledRib, plate: float) -> list[tuple[float, float]]:
    """Roof: corrugation outwards, plate towards the interior."""
    return corrugated_slab(rib, plate, crest_towards=+1)


def floor(rib: ScaledRib, plate: float) -> list[tuple[float, float]]:
    """Floor: corrugation into the interior, plate on the outside."""
    return corrugated_slab(rib, plate, crest_towards=-1)


def flat_floor(rib: ScaledRib, thickness: float) -> list[tuple[float, float]]:
    """Flat floor plate spanning the same corrugated length as :func:`floor`.

    ``thickness`` is the full floor depth, so the plate reaches exactly as far
    into the interior as the corrugated floor did and the container height is
    unchanged.  ``v`` runs from ``-rib.height`` (outer face, the crest plane of
    the corrugated floor) to ``thickness - rib.height`` (interior face).
    """
    if thickness <= 0:
        raise ValueError(f"floor thickness must be positive, got {thickness:.6f} mm")
    span = rib.pitch * rib.count
    return _clean([(0.0, -rib.height), (span, -rib.height),
                   (span, thickness - rib.height), (0.0, thickness - rib.height)])


def door(rib: ScaledRib, depth: float) -> list[tuple[float, float]]:
    """Ribbed door end: flat backing plate with the crests facing outwards.

    ``depth`` is the total panel depth from rib crest to plate back, i.e. the
    door frame width of the reference model.  ``crest_towards=-1`` matches the
    other walls: the plate closes the box on the inside and the corrugation
    bulges to the outside, so ``v`` runs from ``-height`` (crest plane) to
    ``depth - height`` (plate back).
    """
    return corrugated_slab(rib, depth - rib.height, crest_towards=-1)


def chamfered_rect(width: float, height: float, chamfer: float) -> list[tuple[float, float]]:
    """Rectangle from ``(0, 0)`` to ``(width, height)`` with chamfered corners."""
    c = min(chamfer, width / 2.0, height / 2.0)
    if c <= TOLERANCE:
        return _clean([(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)])
    return _clean([
        (c, 0.0),
        (width - c, 0.0),
        (width, c),
        (width, height - c),
        (width - c, height),
        (c, height),
        (0.0, height - c),
        (0.0, c),
    ])


def frame_ring(width: float, height: float, wall: float,
               chamfer: float = 0.0) -> list[list[tuple[float, float]]]:
    """A rib with a rectangular opening: ``[outer_loop, inner_loop]``.

    ``wall`` insets the opening from every side, ``chamfer`` bevels only the
    outer corners -- the corner posts of a container end frame.
    """
    if width <= 2 * wall or height <= 2 * wall:
        raise ValueError(f"frame wall {wall:.4f} mm too thick for a "
                         f"{width:.4f} x {height:.4f} mm rib")
    outer = chamfered_rect(width, height, chamfer)
    inner = [
        (wall, wall),
        (width - wall, wall),
        (width - wall, height - wall),
        (wall, height - wall),
    ]
    return [outer, inner]
