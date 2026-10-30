"""FreeCAD workbench initialisation for the Scaletainer container generator.

This file runs in every session, GUI or console.  It only puts the add-on
folder on ``sys.path`` so ``import scaletainer`` works, which lets
``freecadcmd`` generate containers without any workbench machinery::

    freecadcmd
    >>> from scaletainer import tasks
    >>> tasks.generate({"scale_divider": 87}, "~/Scaletainer", formats=("stl",))

FreeCAD executes the file with separate globals/locals dictionaries, may pass a
relative ``__file__`` and omits ``__file__`` in console mode, so the folder is
found by testing candidates rather than trusting the working directory.
"""

import os
import sys


def _find_package_dir():
    """Directory containing the ``scaletainer`` package."""
    candidates = []
    here = globals().get("__file__")
    if here:
        candidates.append(os.path.abspath(os.path.dirname(here)))
    candidates.extend(p for p in sys.path if p)
    home = os.path.expanduser("~")
    for flavour in (".var/app/org.freecad.FreeCAD/data", ".local/share", ".FreeCAD"):
        candidates.append(os.path.join(home, flavour, "FreeCAD", "Mod"))
    for folder in candidates:
        if os.path.isdir(os.path.join(folder, "scaletainer")):
            return os.path.normpath(folder)
    return os.path.dirname(os.path.abspath(here)) if here else os.getcwd()


_package_dir = _find_package_dir()

if _package_dir not in sys.path:
    sys.path.insert(0, _package_dir)
