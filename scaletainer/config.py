r"""Save and reload a container configuration as JSON.

A configuration file records everything the panel collects -- the **1:1**
dimensions in whichever input unit they were typed, the corrugation patterns,
the modelling scale, the printability safety nets, the option toggles -- plus
the output settings (folder, formats, per-component files).  Loading it again
restores the panel exactly, so a design can be archived, versioned, shared or
used as the starting point for a variant.

The file is a single JSON object::

    {
      "generator": "Scaletainer/config",
      "config_version": 1,
      "name": "48 ft reference at 1:160",
      "unit": "mm",
      "values": { "length": 14630.4, ..., "side_ribs": {...}, ... },
      "export": { "directory": "~/Scaletainer", "formats": ["fcstd", "stl"],
                  "separate_parts": true }
    }

``values`` holds the plain dict :mod:`scaletainer.tasks` expects, so a file
can also be fed straight to :func:`scaletainer.tasks.generate`.  Two other
shapes are accepted on load for convenience:

* a **bare values dict** (top-level ``length``/``width``/``height``), which is
  treated as a configuration with the default unit and no export settings;
* the **sidecar** the generator writes next to the models (``input_1to1`` plus
  ``build_config``), which is converted back into a configuration.

Only this module and the panel deal with files; nothing here imports Qt or
FreeCAD, so the format is testable in plain Python.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .units import UNITS

#: what a real file extension looks like (``.json``, ``.tar.gz`` tail, ...)
_EXT_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}")

#: marks the file and guards against reading someone else's JSON
FORMAT = "Scaletainer/config"
#: files written before the add-on was renamed from "Ntrak Container"
LEGACY_FORMATS = ("NtrakContainer/config",)
CONFIG_VERSION = 1

#: 1:1 lengths, stored in the file's ``unit``
LENGTH_KEYS = (
    "length", "width", "height", "frame_size", "door_frame_width",
    "top_skin", "bottom_skin", "mount_frame_depth", "mount_frame_wall",
    "mount_frame_chamfer", "far_door_plate", "far_door_rod_width",
    "far_door_gap", "far_door_corner", "far_door_stile",
)
#: whole-number counts
COUNT_KEYS = ("mount_frame_count", "far_door_rod_count")
#: unitless numbers
NUMBER_KEYS = ("scale_divider", "min_feature_mm", "min_rib_pitch_mm")
#: rib pattern sub-dicts and the fields each one must carry
RIB_KEYS = ("side_ribs", "top_ribs", "bottom_ribs", "door_ribs")
RIB_FIELDS = ("count", "slope", "ratio", "height")
#: option toggles; the panel only writes the first, the others are console-only
BOOL_KEYS = ("include_mount_frame", "include_door_side", "include_far_door",
             "include_floor_corrugation")

#: every key accepted inside ``values``
VALUE_KEYS = LENGTH_KEYS + COUNT_KEYS + NUMBER_KEYS + RIB_KEYS + BOOL_KEYS

#: formats accepted by :func:`scaletainer.tasks.generate`
EXPORT_FORMATS = ("fcstd", "step", "stl", "3mf")


class ConfigError(ValueError):
    """A configuration file could not be read or is not valid."""


@dataclass
class ExportOptions:
    """The Generate tab settings stored with a configuration."""

    directory: str | None = None
    formats: tuple[str, ...] = ()
    separate_parts: bool | None = None

    def to_dict(self) -> dict:
        return {
            "directory": self.directory,
            "formats": list(self.formats),
            "separate_parts": self.separate_parts,
        }


@dataclass
class ContainerConfig:
    """A named container configuration: panel values plus output settings."""

    values: dict = field(default_factory=dict)
    unit: str = "mm"
    export: ExportOptions | None = None
    name: str = ""

    def to_dict(self) -> dict:
        payload = {
            "generator": FORMAT,
            "config_version": CONFIG_VERSION,
            "name": self.name,
            "unit": self.unit,
            "values": dict(self.values),
        }
        if self.export is not None:
            payload["export"] = self.export.to_dict()
        return payload

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def describe(self) -> str:
        """Short human-readable summary for the panel status line."""
        divider = self.values.get("scale_divider")
        size = " x ".join(
            f"{float(self.values[k]):g}" for k in ("length", "width", "height")
            if self.values.get(k) is not None)
        bits = []
        if self.name:
            bits.append(self.name)
        if size:
            bits.append(f"{size} {self.unit}")
        if divider:
            bits.append(f"1:{float(divider):g}")
        return ", ".join(bits) or "container configuration"


def _number(value, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key}: expected a number, got {value!r}")
    return float(value)


def _integer(value, key: str) -> int:
    number = _number(value, key)
    if int(number) != number:
        raise ConfigError(f"{key}: expected a whole number, got {value!r}")
    return int(number)


def _boolean(value, key: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{key}: expected true or false, got {value!r}")
    return value


def _rib(value, key: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigError(f"{key}: expected an object with {', '.join(RIB_FIELDS)}")
    missing = [f for f in RIB_FIELDS if value.get(f) is None]
    if missing:
        raise ConfigError(f"{key}: missing {', '.join(missing)}")
    unknown = [k for k in value if k not in RIB_FIELDS]
    if unknown:
        raise ConfigError(f"{key}: unknown field(s) {', '.join(sorted(unknown))}")
    return {"count": _integer(value["count"], f"{key}.count"),
            "slope": _number(value["slope"], f"{key}.slope"),
            "ratio": _number(value["ratio"], f"{key}.ratio"),
            "height": _number(value["height"], f"{key}.height")}


def clean_values(values: dict) -> dict:
    """Validate and normalise a panel value dict.

    Numbers get their proper Python type (counts are ints, lengths floats), rib
    patterns are rebuilt as plain four-key dicts, and unknown keys raise
    :class:`ConfigError` so a typo in a hand-written file is reported instead of
    silently ignored.
    """
    if not isinstance(values, dict):
        raise ConfigError("configuration must be a JSON object")
    unknown = [k for k in values if k not in VALUE_KEYS]
    if unknown:
        raise ConfigError(f"unknown key(s): {', '.join(sorted(unknown))}")
    out: dict = {}
    for key in LENGTH_KEYS + NUMBER_KEYS:
        if values.get(key) is not None:
            out[key] = _number(values[key], key)
    for key in COUNT_KEYS:
        if values.get(key) is not None:
            out[key] = _integer(values[key], key)
    for key in BOOL_KEYS:
        if values.get(key) is not None:
            out[key] = _boolean(values[key], key)
    for key in RIB_KEYS:
        if values.get(key) is not None:
            out[key] = _rib(values[key], key)
    return out


def _clean_export(export) -> ExportOptions | None:
    if export is None:
        return None
    if not isinstance(export, dict):
        raise ConfigError("export settings must be an object")
    unknown = [k for k in export
               if k not in ("directory", "formats", "separate_parts")]
    if unknown:
        raise ConfigError(f"export: unknown key(s) {', '.join(sorted(unknown))}")
    directory = export.get("directory")
    if directory is not None and not isinstance(directory, str):
        raise ConfigError("export.directory: expected a path string")
    formats = export.get("formats") or ()
    if isinstance(formats, str):
        formats = [formats]
    if not isinstance(formats, (list, tuple)):
        raise ConfigError("export.formats: expected a list of formats")
    formats = tuple(str(f).strip().lower() for f in formats)
    bad = [f for f in formats if f not in EXPORT_FORMATS]
    if bad:
        raise ConfigError(
            f"export.formats: unknown format(s) {', '.join(bad)} "
            f"(expected any of {', '.join(EXPORT_FORMATS)})")
    separate = export.get("separate_parts")
    if separate is not None:
        separate = _boolean(separate, "export.separate_parts")
    return ExportOptions(directory=directory, formats=formats, separate_parts=separate)


def build(values: dict, unit: str = "mm", export=None, name: str = "") -> ContainerConfig:
    """Create a validated :class:`ContainerConfig` from panel values.

    *export* may be an :class:`ExportOptions` or a plain dict.
    """
    if unit not in UNITS:
        raise ConfigError(f"unknown unit: {unit!r}")
    if export is not None and not isinstance(export, (ExportOptions, dict)):
        raise ConfigError("export settings must be an object")
    return ContainerConfig(
        values=clean_values(values),
        unit=unit,
        export=export if isinstance(export, ExportOptions) else _clean_export(export),
        name=str(name or ""),
    )


def _values_from_sidecar(data: dict) -> tuple[dict, str]:
    """Convert a generator sidecar into panel values (all lengths are 1:1 mm)."""
    inputs = data.get("input_1to1") or {}
    cfg = data.get("build_config") or {}
    if not isinstance(inputs, dict) or not isinstance(cfg, dict):
        raise ConfigError("sidecar: input_1to1 and build_config must be objects")
    values = {k: v for k, v in inputs.items() if k in VALUE_KEYS}
    for key in NUMBER_KEYS + BOOL_KEYS:
        if cfg.get(key) is not None:
            values[key] = cfg[key]
    return values, str(data.get("unit") or "mm")


def from_dict(data: dict) -> ContainerConfig:
    """Read any accepted JSON shape into a :class:`ContainerConfig`."""
    if not isinstance(data, dict):
        raise ConfigError("configuration must be a JSON object")
    if "input_1to1" in data:
        values, unit = _values_from_sidecar(data)
        return build(values, unit, name=str(data.get("name") or ""))
    if "values" in data or data.get("generator") in (FORMAT, *LEGACY_FORMATS):
        marker = data.get("generator")
        if marker not in (None, FORMAT, *LEGACY_FORMATS):
            raise ConfigError(f"not a container configuration: {marker!r}")
        version = data.get("config_version", CONFIG_VERSION)
        try:
            version = int(version)
        except (TypeError, ValueError):
            raise ConfigError(
                f"config_version must be a number, got {version!r}") from None
        if version > CONFIG_VERSION:
            raise ConfigError(
                f"configuration was written by a newer version "
                f"(config_version {version} > {CONFIG_VERSION})")
        unit = str(data.get("unit") or "mm")
        export = _clean_export(data.get("export"))
        return build(data.get("values") or {}, unit, export,
                     name=str(data.get("name") or ""))
    if any(key in data for key in ("length", "width", "height")):
        # bare values dict: usable as-is, with the default unit
        extra = [k for k in data if k not in VALUE_KEYS and k != "name"]
        if extra:
            raise ConfigError(
                f"unknown key(s) in a bare values dict: {', '.join(sorted(extra))}")
        values = {k: v for k, v in data.items() if k in VALUE_KEYS}
        return build(values, "mm", None, name=str(data.get("name") or ""))
    raise ConfigError(
        "not a container configuration: expected a 'values' object "
        "(or an 'input_1to1' sidecar)")


def from_json(text: str) -> ContainerConfig:
    """Parse configuration JSON text."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON: {exc}") from exc
    return from_dict(data)


def to_json(values: dict, unit: str = "mm", export=None, name: str = "",
            indent: int = 2) -> str:
    """Validate *values* and return the file text (no intermediate object)."""
    return build(values, unit, export, name).to_json(indent=indent)


def write(cfg: ContainerConfig, path: str, indent: int = 2) -> str:
    """Write an existing :class:`ContainerConfig` to *path*.

    ``~`` is expanded, missing folders are created, and the real path is
    returned.
    """
    target = os.path.abspath(os.path.expanduser(path))
    folder = os.path.dirname(target)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(cfg.to_json(indent=indent))
    return target


def save(path: str, values: dict, unit: str = "mm", export=None,
         name: str = "", indent: int = 2) -> str:
    """Validate *values* and write them to *path*; returns the real path."""
    return write(build(values, unit, export, name), path, indent=indent)


def load(path: str) -> ContainerConfig:
    """Read a configuration file written by :func:`save` (or a sidecar)."""
    target = os.path.abspath(os.path.expanduser(path))
    try:
        with open(target, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise ConfigError(f"could not read {target}: {exc.strerror or exc}") from exc
    try:
        config = from_json(text)
    except ConfigError as exc:
        raise ConfigError(f"{os.path.basename(target)}: {exc}") from exc
    return config


def with_extension(path: str, extension: str = ".json") -> str:
    """Append *extension* when a chosen save path has none.

    ``os.path.splitext`` alone is not enough: a name carrying decimal points
    (``container-14630.4x2590.8x2895.6-1-160``) looks like it already has the
    "extension" ``.6-1-160``.  Only a suffix that really looks like an
    extension -- a dot followed by a short alphanumeric run starting with a
    letter -- counts, so such a name still gets ``.json`` appended.
    """
    existing = os.path.splitext(path)[1]
    if _EXT_RE.fullmatch(existing or ""):
        return path
    return path + extension
