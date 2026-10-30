"""Scaletainer container generator package.

Modules:

* :mod:`scaletainer.units` -- input units, scale presets and parsing
* :mod:`scaletainer.params` -- 1:1 parameter model and the scale-space derivation
* :mod:`scaletainer.profiles` -- 2D rib / frame cross-sections
* :mod:`scaletainer.builder` -- FreeCAD ``Part`` shapes and document assembly
* :mod:`scaletainer.exporter` -- FCStd / STEP / STL / 3MF writers
* :mod:`scaletainer.tasks` -- one-call headless entry point used by the GUI and CLI
* :mod:`scaletainer.config` -- JSON save/load of panel values and options

The whole pipeline runs without a spreadsheet object: every parameter is
computed in Python and baked into the geometry.
"""

__version__ = "0.1.0"
