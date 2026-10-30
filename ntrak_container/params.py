"""Parameter model for a scaled transport container.

Everything the user enters is a **1:1** (full size) dimension in millimetres.
Scaling divides those values by the scale divider, reproducing the
``Dimension 1:1 [mm]`` -> ``Scaled Dimension [mm]`` columns of the original
spreadsheets -- but computed here in plain Python, with no spreadsheet object
anywhere in the document.

Two optional safety nets exist for very small scales, because a 1:160 container
ends up with features thinner than a printer nozzle:

* ``min_feature_mm`` -- a floor: every scaled length below it is raised to it,
  and ribs are dropped where the raised profile no longer fits the span.
* ``min_rib_pitch_mm`` -- an explicit minimum pitch: the rib count is lowered
  until the pitch reaches it.

Both default to ``0`` (disabled), so the reference geometry is reproduced
exactly.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace

#: one foot in millimetres; container lengths are traditionally given in feet
FT = 304.8

#: The side wall depth is derived from the frame size (2 x frame_size in the
#: reference model), which keeps the corrugated wall flush with the end frames.
SIDE_ENVELOPE_FRAMES = 2


@dataclass(frozen=True)
class RibPattern:
    """Corrugation / ribbing description.  All lengths are 1:1 values.

    ``count``
        number of ribs across the span
    ``slope``
        horizontal run of each ramp leading into the flat rib crest
    ``ratio``
        fraction of the remaining flat span that becomes the crest;
        ``1 - ratio`` is left for the valley between two ribs
    ``height``
        relief depth of the rib, measured from the valley plane
    """

    count: int
    slope: float
    ratio: float
    height: float

    def validate(self, name: str) -> None:
        if int(self.count) != self.count or self.count < 1:
            raise ValueError(f"{name}: rib count must be a whole number >= 1")
        if self.slope < 0:
            raise ValueError(f"{name}: slope size must not be negative")
        if not 0.0 <= self.ratio <= 1.0:
            raise ValueError(f"{name}: ratio must be between 0 and 1")
        if self.height < 0:
            raise ValueError(f"{name}: rib height must not be negative")


@dataclass
class ContainerParams:
    """Full size (1:1) description of a corrugated transport container."""

    # --- outer dimensions, 1:1 mm ---
    length: float = 48 * FT          # 48 ft ISO container
    width: float = 8.5 * FT          # 8 ft 6 in
    height: float = 9.5 * FT         # 9 ft 6 in (high cube)
    #: width of the end frame / corner fittings; also sets the side wall depth
    frame_size: float = 120.0

    # --- skin plate thickness, 1:1 mm ---
    top_skin: float = 160.0          # 1.0 mm at 1:160
    bottom_skin: float = 160.0       # 1.0 mm at 1:160

    # --- corrugation, 1:1 mm ---
    side_ribs: RibPattern = field(default_factory=lambda: RibPattern(24, 50.0, 0.2, 36.0))
    top_ribs: RibPattern = field(default_factory=lambda: RibPattern(48, 80.0, 0.5, 40.0))
    bottom_ribs: RibPattern = field(default_factory=lambda: RibPattern(48, 10.0, 0.1, 60.0))
    door_ribs: RibPattern = field(default_factory=lambda: RibPattern(7, 50.0, 0.5, 25.0))
    #: border / slab thickness of the ribbed door end
    door_frame_width: float = 100.0

    # --- mounting frame that holds the container, 1:1 mm ---
    #: depth of a mounting rib along the container length (8 mm at 1:160)
    mount_frame_depth: float = 8.0 * 160
    #: wall thickness of the mounting rib (2 mm at 1:160)
    mount_frame_wall: float = 2.0 * 160
    #: corner chamfer of the mounting rib (1 mm at 1:160)
    mount_frame_chamfer: float = 1.0 * 160
    #: number of mounting ribs spread over the corrugated span
    mount_frame_count: int = 3

    # --- far (double) door end, 1:1 mm ---------------------------------
    #: solid backing plate of the door leaves.  The leaves live in the band
    #: between the corrugated shell and the nominal container end, so the sum of
    #: plate, corrugation relief and hardware is fixed; a thicker plate means a
    #: stronger, more printable base and a shallower corrugation.
    far_door_plate: float = 48.0
    #: diameter of the vertical locking rods (square bars for printability)
    far_door_rod_width: float = 45.0
    #: width of the centre seam between the two door leaves
    far_door_gap: float = 34.0
    #: size of the corner castings / hinge and handle blocks
    far_door_corner: float = 60.0
    #: width of the raised door frame (stiles and rails) around each leaf
    far_door_stile: float = 70.0
    #: vertical locking rods per door leaf (2 on a real ISO box)
    far_door_rod_count: int = 2

    def validate(self) -> None:
        for attr in ("length", "width", "height", "frame_size", "door_frame_width",
                     "top_skin", "bottom_skin", "mount_frame_depth",
                     "mount_frame_wall", "mount_frame_chamfer",
                     "far_door_plate", "far_door_rod_width", "far_door_gap",
                     "far_door_corner", "far_door_stile"):
            if getattr(self, attr) <= 0:
                raise ValueError(f"{attr} must be greater than zero")
        if int(self.far_door_rod_count) != self.far_door_rod_count \
                or self.far_door_rod_count < 1:
            raise ValueError("far_door_rod_count must be a whole number >= 1")
        if int(self.mount_frame_count) != self.mount_frame_count or self.mount_frame_count < 1:
            raise ValueError("mount_frame_count must be a whole number >= 1")
        if 2 * self.frame_size >= min(self.length, self.width):
            raise ValueError("frame size is too large for the container cross section")
        if self.height <= 2 * self.frame_size:
            raise ValueError("container height must exceed twice the frame size")
        for pattern, name in ((self.side_ribs, "side_ribs"), (self.top_ribs, "top_ribs"),
                              (self.bottom_ribs, "bottom_ribs"),
                              (self.door_ribs, "door_ribs")):
            pattern.validate(name)
        span = self.length - 2 * self.frame_size
        for attr, pattern in (("side_ribs", self.side_ribs), ("top_ribs", self.top_ribs),
                              ("bottom_ribs", self.bottom_ribs)):
            if 2 * pattern.slope * pattern.count >= span:
                raise ValueError(f"{attr}: total slope width exceeds the corrugated span")
            if pattern.height >= SIDE_ENVELOPE_FRAMES * self.frame_size:
                raise ValueError(f"{attr}: rib height leaves no room for the wall plate")
        door_span = self.width - 2 * self.door_frame_width
        if door_span <= 0:
            raise ValueError("door_frame_width is too large for the container width")
        if 2 * self.door_ribs.slope * self.door_ribs.count >= door_span:
            raise ValueError("door_ribs: total slope width exceeds the door span")
        if self.door_ribs.height >= self.door_frame_width:
            raise ValueError("door_ribs: rib height leaves no room for the door plate")

    def replaced(self, **changes) -> "ContainerParams":
        return replace(self, **changes)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ContainerParams":
        data = dict(data)
        for key in ("side_ribs", "top_ribs", "bottom_ribs", "door_ribs"):
            if isinstance(data.get(key), dict):
                data[key] = RibPattern(**data[key])
        allowed = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in allowed})

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "ContainerParams":
        return cls.from_dict(json.loads(text))

    @classmethod
    def reference(cls) -> "ContainerParams":
        """The 48 ft ISO reference size the original model was built from (1:160)."""
        return cls()


@dataclass
class BuildConfig:
    """How a :class:`ContainerParams` becomes scale-space geometry."""

    scale_divider: float = 160.0
    #: absolute floor for every scaled length (0 disables it)
    min_feature_mm: float = 0.0
    #: ribs are dropped until the scaled pitch reaches this value (0 disables it)
    min_rib_pitch_mm: float = 0.0
    #: build the mounting frame ribs that hold the container
    include_mount_frame: bool = True
    #: build the ribbed door end
    include_door_side: bool = True
    #: build the realistic double-door end on the far side
    include_far_door: bool = True

    def replaced(self, **changes) -> "BuildConfig":
        return replace(self, **changes)


@dataclass
class ScaledRib:
    """A rib pattern resolved into scale-space millimetres."""

    count: int
    pitch: float
    slope: float
    valley: float
    hill: float
    height: float
    #: original 1:1 count before ``min_rib_pitch_mm`` possibly reduced it
    requested_count: int = 0

    @property
    def span(self) -> float:
        """Length covered by ``count`` ribs."""
        return self.pitch * self.count

    @property
    def was_reduced(self) -> bool:
        return self.requested_count not in (0, self.count)


@dataclass
class ScaledGeometry:
    """Every scale-space length the builder needs, plus derivation notes."""

    scale_divider: float
    length: float
    width: float
    height: float
    frame_size: float
    top_skin: float
    bottom_skin: float
    side: ScaledRib
    top: ScaledRib
    bottom: ScaledRib
    door: ScaledRib
    door_frame_width: float
    mount_frame_depth: float
    mount_frame_wall: float
    mount_frame_chamfer: float
    mount_frame_count: int
    #: far door end: backing plate of the leaves
    far_door_plate: float = 0.0
    #: far door end: width of the vertical locking rods, and how far they
    #: stand proud of the corrugation
    far_door_rod: float = 0.0
    #: far door end: centre seam between the two leaves
    far_door_gap: float = 0.0
    #: far door end: size of hinge, handle and corner-casting blocks
    far_door_corner: float = 0.0
    #: far door end: width of the raised frame around each leaf
    far_door_stile: float = 0.0
    #: far door end: vertical locking rods per leaf
    far_door_rod_count: int = 2
    #: far door end: depth of the raised relief (band minus backing plate)
    far_door_hardware: float = 0.0
    #: human readable log of every floor / rib-count adjustment
    notes: list[str] = field(default_factory=list)

    # --- derived helpers -------------------------------------------------
    @property
    def inner_length(self) -> float:
        """Corrugated span between the two end frames."""
        return self.length - 2 * self.frame_size

    @property
    def side_envelope(self) -> float:
        """Total side wall depth from crest plane to inner face."""
        return SIDE_ENVELOPE_FRAMES * self.frame_size

    @property
    def side_plate(self) -> float:
        """Side wall plate thickness left over after the rib relief."""
        return self.side_envelope - self.side.height

    @property
    def door_span(self) -> float:
        """Width available for the door ribs between the border stiles."""
        return self.width - 2 * self.door_frame_width

    @property
    def overall_length(self) -> float:
        """Length of the finished model: corrugated span plus the door end.

        The reference model replaces one end frame by the ribbed door panel, so
        this is ``inner_length + door_frame_width`` -- slightly shorter than the
        nominal 1:1 length whenever the door border is thinner than a frame.
        """
        return self.inner_length + self.door_frame_width

    @property
    def far_door_available(self) -> float:
        """Length left between the corrugated end and the nominal container end.

        The model currently stops at ``overall_length`` (the corrugated walls
        plus the near door).  A real container's door end is flush with the
        corner fittings at the full 1:1 ``length``, so this is the depth the far
        door may use: ``length - overall_length``, i.e. ``2 * frame_size -
        door_frame_width`` in scale space.  Building the far door inside exactly
        this band guarantees the model never exceeds the overall length.
        """
        return max(0.0, self.length - self.overall_length)

    @property
    def mount_span(self) -> float:
        """Width a mounting rib spans between the two side walls."""
        return self.width - 2 * self.side_envelope

    @property
    def mount_height(self) -> float:
        """Height of a mounting rib between floor and roof corrugation."""
        return (self.height
                - self.bottom.height - self.bottom_skin
                - self.top.height - self.top_skin)

    @property
    def mount_x(self) -> list[float]:
        """X origins of the mounting ribs, spread over the corrugated span."""
        n = max(int(self.mount_frame_count), 1)
        usable = self.inner_length - self.mount_frame_depth
        if n == 1 or usable <= 0:
            return [0.0]
        step = usable / (n - 1)
        return [i * step for i in range(n)]

    # --- far (double) door end -----------------------------------------
    @property
    def far_door_x0(self) -> float:
        """X where the far door starts: the end of the corrugated shell."""
        return self.overall_length

    @property
    def far_door_x1(self) -> float:
        """X of the far door's outer face -- exactly the nominal length.

        Keeping the outer face here is what stops the door end from ever
        exceeding the overall container length.
        """
        return self.length

    @property
    def far_door_leaf_width(self) -> float:
        """Width of one door leaf between the centre seam and a corner."""
        usable = self.width - self.far_door_gap
        return usable / 2.0

    @property
    def far_door_centre(self) -> float:
        """Y of the centre seam between the two leaves."""
        return self.width / 2.0


def _floor(value: float, limit: float, notes: list[str], what: str) -> float:
    if limit <= 0 or value >= limit:
        return value
    notes.append(f"{what}: {value:.4f} mm is below the {limit:.4f} mm floor, "
                 f"raised to {limit:.4f} mm")
    return limit


def _flats(pitch: float, slope: float, hill_share: float,
           min_feature: float) -> tuple[float, float]:
    """Crest and valley widths of one rib, with the floor applied.

    A flat whose share is zero does not exist, so it stays at zero instead of
    being raised to the minimum feature size.
    """
    flat = pitch - 2 * slope
    hill = flat * hill_share
    valley = flat * (1 - hill_share)
    if min_feature > 0:
        hill = max(hill, min_feature) if hill > 0 else hill
        valley = max(valley, min_feature) if valley > 0 else valley
    return hill, valley


def _resolve_rib(pattern: RibPattern, span_1to1: float, divider: float,
                 cfg: BuildConfig, notes: list[str], name: str) -> ScaledRib:
    """Turn a 1:1 rib pattern into the ribs that actually fit at *divider*.

    The pitch of a rib is ``span_1to1 / count / divider``.  ``min_rib_pitch_mm``
    and ``min_feature_mm`` can only be honoured by *dropping* ribs: growing the
    pitch instead would push the last rib past the end of the span.
    """
    pattern.validate(name)
    slope = pattern.slope / divider
    height = pattern.height / divider
    hill_share = pattern.ratio
    if cfg.min_feature_mm > 0:
        slope = _floor(slope, cfg.min_feature_mm, notes, f"{name} slope")
        height = _floor(height, cfg.min_feature_mm, notes, f"{name} height")

    # narrowest pitch that can still hold one rib: two slopes plus the flats
    tolerance = 1e-9 * max(span_1to1 / divider, 1.0)
    count = int(pattern.count)
    pitch = span_1to1 / count / divider
    min_pitch = cfg.min_rib_pitch_mm
    while count > 1:
        hill, valley = _flats(pitch, slope, hill_share, cfg.min_feature_mm)
        if pitch + tolerance >= 2 * slope + hill + valley \
                and pitch + tolerance >= min_pitch:
            break
        count -= 1
        pitch = span_1to1 / count / divider
    else:
        hill, valley = _flats(pitch, slope, hill_share, cfg.min_feature_mm)
        needed = 2 * slope + hill + valley
        if pitch + tolerance < needed:
            raise ValueError(f"{name}: even a single {pitch:.4f} mm rib cannot hold a "
                             f"{needed:.4f} mm profile at the requested minimum "
                             f"feature size")

    if count != int(pattern.count):
        notes.append(f"{name}: rib count reduced from {pattern.count} to {count} "
                     f"so that {pitch:.4f} mm ribs fit the "
                     f"{span_1to1 / divider:.4f} mm span")
    flat = pitch - 2 * slope
    if flat <= 0:
        raise ValueError(f"{name}: slope {slope:.4f} mm is too large for a "
                         f"{pitch:.4f} mm rib pitch")
    hill, valley = _flats(pitch, slope, hill_share, cfg.min_feature_mm)
    return ScaledRib(
        count=count,
        pitch=pitch,
        slope=slope,
        valley=valley,
        hill=hill,
        height=height,
        requested_count=int(pattern.count),
    )


def derive(params: ContainerParams, cfg: BuildConfig) -> ScaledGeometry:
    """Scale *params* with *cfg* and resolve all derived lengths.

    The formulas mirror the original spreadsheets:
    ``pitch = (span - 2 * frame_size) / count / divider`` and
    ``flat = pitch - 2 * slope`` split into crest and valley by ``ratio``.
    """
    params.validate()
    if cfg.scale_divider <= 0:
        raise ValueError("scale divider must be greater than zero")

    d = cfg.scale_divider
    notes: list[str] = []
    corrugated_span = params.length - 2 * params.frame_size
    door_span = params.width - 2 * params.door_frame_width

    side = _resolve_rib(params.side_ribs, corrugated_span, d, cfg, notes, "side ribs")
    top = _resolve_rib(params.top_ribs, corrugated_span, d, cfg, notes, "top ribs")
    bottom = _resolve_rib(params.bottom_ribs, corrugated_span, d, cfg, notes, "bottom ribs")
    door = _resolve_rib(params.door_ribs, door_span, d, cfg, notes, "door ribs")

    # --- far (double) door end -----------------------------------------
    # The leaves live in the fixed band between the corrugated shell (X =
    # overall_length) and the nominal container end (X = length), so the outer
    # face sits exactly at ``length`` and can never exceed the overall length.
    # The band is a solid backing plate plus a layer of raised relief; the relief
    # depth is simply ``band - plate``, so the plate is capped to leave room for
    # the door detail.  The hardware sizes are planar (in the door face).
    band = max(0.0, params.length / d - (params.length - 2 * params.frame_size
                                         + params.door_frame_width) / d)
    rod = _floor(params.far_door_rod_width / d, cfg.min_feature_mm, notes,
                 "far door rod width")
    corner = _floor(params.far_door_corner / d, cfg.min_feature_mm, notes,
                    "far door corner size")
    gap = _floor(params.far_door_gap / d, cfg.min_feature_mm, notes,
                 "far door centre seam")
    stile = _floor(params.far_door_stile / d, cfg.min_feature_mm, notes,
                   "far door frame stile")
    plate = _floor(params.far_door_plate / d, cfg.min_feature_mm, notes,
                   "far door plate")
    if band > 0:
        plate = min(plate, band * 0.6)          # keep at least 40% for the relief

    geom = ScaledGeometry(
        scale_divider=d,
        length=params.length / d,
        width=params.width / d,
        height=params.height / d,
        frame_size=params.frame_size / d,
        top_skin=_floor(params.top_skin / d, cfg.min_feature_mm, notes, "roof plate"),
        bottom_skin=_floor(params.bottom_skin / d, cfg.min_feature_mm, notes, "floor plate"),
        side=side, top=top, bottom=bottom, door=door,
        door_frame_width=params.door_frame_width / d,
        mount_frame_depth=_floor(params.mount_frame_depth / d, cfg.min_feature_mm,
                                 notes, "mount frame depth"),
        mount_frame_wall=_floor(params.mount_frame_wall / d, cfg.min_feature_mm,
                                notes, "mount frame wall"),
        mount_frame_chamfer=_floor(params.mount_frame_chamfer / d, cfg.min_feature_mm,
                                   notes, "mount frame chamfer"),
        mount_frame_count=int(params.mount_frame_count),
        far_door_plate=plate,
        far_door_rod=rod,
        far_door_gap=gap,
        far_door_corner=corner,
        far_door_stile=stile,
        far_door_rod_count=int(params.far_door_rod_count),
        far_door_hardware=band - plate,
        notes=notes,
    )
    _check_fit(geom, notes)
    return geom


def _check_fit(geom: ScaledGeometry, notes: list[str]) -> None:
    """Raise or warn when applied floors changed a wall so it no longer fits."""
    if geom.side_envelope <= geom.side.height:
        raise ValueError("side rib height leaves no wall plate: increase the "
                         "frame size or lower the minimum feature size")
    for name, rib, span in (("side", geom.side, geom.inner_length),
                            ("top", geom.top, geom.inner_length),
                            ("bottom", geom.bottom, geom.inner_length),
                            ("door", geom.door, geom.door_span)):
        if rib.span > span + 1e-9:
            notes.append(f"{name} ribs overshoot their span by "
                         f"{rib.span - span:.4f} mm because a floor was applied")
    if geom.mount_height <= 0:
        raise ValueError("no room left for the mounting frame between the skins")
    if geom.mount_span <= 2 * geom.mount_frame_wall:
        raise ValueError("mounting frame wall too thick for the available span")
