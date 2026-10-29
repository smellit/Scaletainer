"""Ntrak container generator package.

Modules:

* :mod:`ntrak.units` -- input units, scale presets and parsing
* :mod:`ntrak_container.params` -- 1:1 parameter model and the scale-space derivation
* :mod:`ntrak.profiles` -- 2D rib / frame cross-sections
* :mod:`ntrak.builder` -- FreeCAD ``Part`` shapes and document assembly
* :mod:`ntrak_container.exporter` -- FCStd / STEP / STL / 3MF writers
* :mod:`ntrak_container.tasks` -- one-call headless entry point used by the GUI and CLI
* :mod:`ntrak_container.config` -- JSON save/load of panel values and options

The whole pipeline runs without a spreadsheet object: every parameter is
computed in Python and baked into the geometry.
"""

__version__ = "0.1.0"
