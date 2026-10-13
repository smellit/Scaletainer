"""Workbench registration test.

A real GUI session cannot run in headless CI, so this stubs the small part of
``FreeCADGui`` that ``InitGui.py`` uses and checks that the workbench class, its
toolbar/menu entries and the command registration come out right.
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeWorkbench:
    """Stand-in for ``Gui.Workbench`` recording toolbar/menu calls."""

    def __init__(self):
        self.toolbars = []
        self.menus = []

    def appendToolbar(self, name, commands):
        self.toolbars.append((name, list(commands)))

    def appendMenu(self, name, commands):
        self.menus.append((name, list(commands)))


class FakeGui(types.ModuleType):
    def __init__(self):
        super().__init__("FreeCADGui")
        self.added = []
        self.commands = {}
        self.Workbench = FakeWorkbench

    def addWorkbench(self, instance):
        self.added.append(instance)

    def addCommand(self, name, handler):
        self.commands[name] = handler


class WorkbenchInitTest(unittest.TestCase):
    def setUp(self):
        # Drop cached modules so InitGui.py re-imports our stub.
        for name in ("ntrak_container.commands",):
            sys.modules.pop(name, None)
        self.gui = FakeGui()
        self._saved = sys.modules.get("FreeCADGui")
        sys.modules["FreeCADGui"] = self.gui

    def tearDown(self):
        if self._saved is not None:
            sys.modules["FreeCADGui"] = self._saved
        else:
            sys.modules.pop("FreeCADGui", None)
        sys.modules.pop("ntrak_container.commands", None)

    def _exec_init(self, source: str):
        path = os.path.join(ROOT, "InitGui.py")
        module = types.ModuleType("InitGui")
        module.__file__ = path
        exec(compile(source, path, "exec"), module.__dict__)
        return module

    def test_console_stub_does_not_register(self):
        """A FreeCADGui without the workbench API must be ignored silently."""
        console = types.ModuleType("FreeCADGui")
        sys.modules["FreeCADGui"] = console
        self._exec_init(open(os.path.join(ROOT, "InitGui.py")).read())
        self.assertEqual(console.__dict__.get("NtrakContainerWorkbench"), None)

    def test_workbench_is_registered(self):
        source = open(os.path.join(ROOT, "InitGui.py")).read()
        self._exec_init(source)
        self.assertEqual(len(self.gui.added), 1)
        workbench = self.gui.added[0]
        self.assertEqual(workbench.MenuText, "Ntrak Container")
        self.assertTrue(os.path.isfile(workbench.Icon), "icon file must exist")
        self.assertEqual(workbench.GetClassName(), "Gui::PythonWorkbench")

    def test_initialize_installs_command_and_menu(self):
        source = open(os.path.join(ROOT, "InitGui.py")).read()
        self._exec_init(source)
        workbench = self.gui.added[0]
        workbench.Initialize()
        self.assertIn("Ntrak_Container_Generate", self.gui.commands)
        self.assertEqual(workbench.toolbars,
                         [("Ntrak Container", ["Ntrak_Container_Generate"])])
        self.assertEqual(workbench.menus, [("Ntrak", ["Ntrak_Container_Generate"])])

    def test_command_resources_point_at_icon(self):
        from ntrak_container import commands

        handler = commands.GenerateCommand()
        resources = handler.GetResources()
        self.assertTrue(resources["Pixmap"].endswith("container.svg"))
        self.assertIn("Generate container", resources["MenuText"])


if __name__ == "__main__":
    import unittest

    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    sys.exit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
