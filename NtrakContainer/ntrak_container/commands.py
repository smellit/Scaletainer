"""Workbench commands and the console entry point.

``Ntrak_Container_Generate`` opens the panel.  :func:`generate_cli` does the
same job without any Qt, which is what ``freecadcmd`` and the test suite use.
"""

from __future__ import annotations

import os

from . import tasks

#: default output folder: the user's home directory unless NTRAK_OUTPUT says so
DEFAULT_OUTPUT = os.environ.get("NTRAK_OUTPUT") or os.path.expanduser("~/Ntrak")

_COMMAND_ID = "Ntrak_Container_Generate"
_panel = None


def generate_cli(values: dict, directory: str | None = None, *, unit: str = "mm",
                 formats=("fcstd", "step", "stl", "3mf"),
                 separate_parts: bool = True, progress=print):
    """Generate a container from plain values; usable from ``freecadcmd``.

    >>> generate_cli({"length": 14630, "width": 2591, "height": 2896,
    ...               "scale_divider": 87}, "/tmp/out")
    """
    return tasks.generate(values, os.path.expanduser(directory or DEFAULT_OUTPUT),
                          unit=unit, formats=formats,
                          separate_parts=separate_parts, progress=progress)


def open_panel():
    """Show the generator panel, reusing the existing one when possible."""
    global _panel
    from .gui import create_panel

    if _panel is None:
        _panel = create_panel(DEFAULT_OUTPUT)
    _panel.show()
    _panel.raise_()
    _panel.activateWindow()
    return _panel


class GenerateCommand:
    """Qt command object registered with the FreeCAD command framework."""

    def GetResources(self):
        import FreeCADGui as Gui

        icon = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "resources", "container.svg")
        return {
            "Pixmap": icon if os.path.isfile(icon) else "",
            "MenuText": "Generate container...",
            "ToolTip": ("Enter 1:1 container dimensions and a modelling scale, "
                        "then write FCStd / STEP / STL / 3MF files."),
            "Accel": "G, N",
        }

    def IsActive(self):
        return True

    def Activated(self):
        open_panel()


def install():
    """Register the commands; safe to call more than once."""
    import FreeCADGui as Gui

    Gui.addCommand(_COMMAND_ID, GenerateCommand())
    return _COMMAND_ID
