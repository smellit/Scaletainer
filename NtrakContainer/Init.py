"""FreeCAD workbench initialisation for the Ntrak container generator.

This file runs in every session, GUI or console.  It only puts the add-on
folder on ``sys.path`` so ``import ntrak_container`` works, which lets
``freecadcmd`` generate containers without any workbench machinery::

    freecadcmd
    >>> from ntrak_container import tasks
    >>> tasks.generate({"scale_divider": 87}, "~/Ntrak", formats=("stl",))

``__file__`` is missing when FreeCAD evaluates this file in console mode, hence
the guarded lookup.
"""

import os
import sys

_here = globals().get("__file__") or sys.argv[0]
_package_dir = os.path.dirname(os.path.abspath(_here))
if os.path.basename(_package_dir) == "Mod" and _package_dir not in sys.path:
    sys.path.insert(0, _package_dir)
