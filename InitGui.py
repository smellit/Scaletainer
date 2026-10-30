"""GUI initialisation: install the "Scaletainer" workbench and its menu.

FreeCAD runs this file with *separate* globals and locals dictionaries and may
pass a relative ``__file__``, so the add-on folder is located by testing
candidate paths instead of trusting the process working directory.  Plain
module-level statements see their own assignments, but a ``class`` body resolves
names in globals only -- which is why the workbench is built inside the factory
function below and handed everything it needs as arguments.

``freecadcmd`` loads this file too but offers a stub ``FreeCADGui`` without the
workbench API, so registration only happens in a real GUI session.
"""

import os
import sys

import FreeCADGui as Gui


def _find_package_dir():
    """Directory holding ``scaletainer`` and ``resources``.

    Tried in order: the folder of ``__file__`` (when it really is this file),
    the ``sys.path`` entries added by ``Init.py``, and the usual FreeCAD ``Mod``
    directories.  The first candidate that contains the package wins, which
    avoids resolving a relative ``__file__`` against the wrong working directory.
    """
    candidates = []
    here = globals().get("__file__")
    if here:
        candidates.append(os.path.abspath(os.path.dirname(here)))
    candidates.extend(p for p in sys.path if p)
    app_data = os.path.expanduser("~")
    for flavour in (".var/app/org.freecad.FreeCAD/data", ".local/share", ".FreeCAD"):
        candidates.append(os.path.join(app_data, flavour, "FreeCAD", "Mod"))
    for folder in candidates:
        if os.path.isdir(os.path.join(folder, "scaletainer")):
            return os.path.normpath(folder)
    return os.path.dirname(os.path.abspath(here)) if here else os.getcwd()


_package_dir = _find_package_dir()

if _package_dir not in sys.path:
    sys.path.insert(0, _package_dir)


def _make_workbench(package_dir, gui, path_join):
    """Create the workbench class without relying on module-level globals.

    *gui* and *path_join* are passed in because a class body cannot see the
    names this module imported; *package_dir* locates the icon.
    """

    class ScaletainerWorkbench(gui.Workbench):
        MenuText = "Scaletainer"
        ToolTip = "Generate scaled transport containers from 1:1 dimensions"
        Icon = path_join(package_dir, "resources", "container.svg")

        def Initialize(self):
            from scaletainer.commands import install

            install()
            self.appendToolbar("Scaletainer", ["Scaletainer_Generate"])
            self.appendMenu("Scaletainer", ["Scaletainer_Generate"])

        def GetClassName(self):
            return "Gui::PythonWorkbench"

    return ScaletainerWorkbench


if hasattr(Gui, "addWorkbench") and hasattr(Gui, "Workbench"):
    Gui.addWorkbench(_make_workbench(_package_dir, Gui, os.path.join)())
