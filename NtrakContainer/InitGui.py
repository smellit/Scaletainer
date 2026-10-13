"""GUI initialisation: install the "Ntrak Container" workbench and its menu.

``freecadcmd`` loads this file too but offers a stub ``FreeCADGui`` without the
workbench API, so registration only happens in a real GUI session.
"""

import os
import sys

import FreeCADGui as Gui

_here = globals().get("__file__") or sys.argv[0]
_package_dir = os.path.dirname(os.path.abspath(_here))
if _package_dir not in sys.path:
    sys.path.insert(0, _package_dir)


if hasattr(Gui, "addWorkbench") and hasattr(Gui, "Workbench"):

    class NtrakContainerWorkbench(Gui.Workbench):
        MenuText = "Ntrak Container"
        ToolTip = "Generate scaled transport containers from 1:1 dimensions"
        Icon = os.path.join(_package_dir, "resources", "container.svg")

        def Initialize(self):
            from ntrak_container.commands import install

            install()
            self.appendToolbar("Ntrak Container", ["Ntrak_Container_Generate"])
            self.appendMenu("Ntrak", ["Ntrak_Container_Generate"])

        def GetClassName(self):
            return "Gui::PythonWorkbench"

    Gui.addWorkbench(NtrakContainerWorkbench())
