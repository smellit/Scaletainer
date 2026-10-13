"""Workbench registration test.

A real GUI session cannot run in headless CI, so this stubs the small part of
``FreeCADGui`` that ``InitGui.py`` uses and executes the file the way FreeCAD
does: with *separate* globals and locals dictionaries and ``os``/``sys``/``Gui``
pre-injected into globals.  That distinction matters -- an earlier version of
the add-on referenced a module-level variable from inside the workbench class
body, which raised ``NameError`` only in a real GUI session.
"""

import builtins
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT_GUI = os.path.join(ROOT, "InitGui.py")
INIT_PY = os.path.join(ROOT, "Init.py")
#: where the add-on lives once installed, used for the icon path check
INSTALLED = os.path.expanduser(
    "~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/NtrakContainer/InitGui.py")


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


def exec_freecad_style(path: str, gui, target: str) -> dict:
    """Run *path* the way FreeCAD runs InitGui.py and return the globals."""
    source = open(path).read()
    globals_dict, locals_dict = {}, {}
    globals_dict["__builtins__"] = builtins
    globals_dict["__file__"] = target
    globals_dict["os"] = os
    globals_dict["sys"] = sys
    globals_dict["Gui"] = gui
    exec(compile(source, path, "exec"), globals_dict, locals_dict)
    return globals_dict


class WorkbenchInitTest(unittest.TestCase):
    def setUp(self):
        sys.modules.pop("ntrak_container.commands", None)
        self._saved_gui = sys.modules.get("FreeCADGui")
        self.gui = FakeGui()
        sys.modules["FreeCADGui"] = self.gui

    def tearDown(self):
        if self._saved_gui is not None:
            sys.modules["FreeCADGui"] = self._saved_gui
        else:
            sys.modules.pop("FreeCADGui", None)
        sys.modules.pop("ntrak_container.commands", None)

    def test_registers_under_freedcad_exec_semantics(self):
        exec_freecad_style(INIT_GUI, self.gui, INSTALLED)
        self.assertEqual(len(self.gui.added), 1,
                         "workbench must register exactly once")
        workbench = self.gui.added[0]
        self.assertEqual(workbench.MenuText, "Ntrak Container")
        self.assertEqual(workbench.GetClassName(), "Gui::PythonWorkbench")

    def test_icon_path_resolves_next_to_installed_init(self):
        exec_freecad_style(INIT_GUI, self.gui, INSTALLED)
        icon = self.gui.added[0].Icon
        self.assertTrue(icon.endswith("resources/container.svg"), icon)
        self.assertTrue(os.path.isabs(icon), icon)

    def test_relative_dunder_file_still_finds_the_package(self):
        """FreeCAD hands InitGui.py a relative path, so cwd must not matter.

        The old code did ``abspath(__file__)`` blindly, which pointed the icon
        at an unrelated folder when the process ran from elsewhere.
        """
        installed_dir = os.path.dirname(INSTALLED)
        # FreeCAD hands over a path relative to its own working directory.
        target = os.path.relpath(INSTALLED, installed_dir)
        saved = os.getcwd()
        try:
            os.chdir(installed_dir)
            exec_freecad_style(INIT_GUI, self.gui, target)
        finally:
            os.chdir(saved)
        icon = self.gui.added[0].Icon
        self.assertEqual(icon, os.path.join(installed_dir, "resources",
                                            "container.svg"), icon)
        self.assertTrue(os.path.isfile(icon), icon)

    def test_icon_exists_in_repository(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "resources",
                                                    "container.svg")))

    def test_initialize_installs_command_and_menu(self):
        exec_freecad_style(INIT_GUI, self.gui, INSTALLED)
        workbench = self.gui.added[0]
        workbench.Initialize()
        self.assertIn("Ntrak_Container_Generate", self.gui.commands)
        self.assertEqual(workbench.toolbars,
                         [("Ntrak Container", ["Ntrak_Container_Generate"])])
        self.assertEqual(workbench.menus, [("Ntrak", ["Ntrak_Container_Generate"])])

    def test_console_stub_registers_nothing(self):
        """A FreeCADGui without the workbench API must be ignored silently."""
        stub = types.ModuleType("FreeCADGui")
        sys.modules["FreeCADGui"] = stub
        exec_freecad_style(INIT_GUI, stub, INSTALLED)   # must not raise

    def test_missing_dunder_file_falls_back_to_argv(self):
        source = open(INIT_GUI).read()
        globals_dict, locals_dict = {}, {}
        globals_dict["__builtins__"] = builtins
        globals_dict["os"] = os
        globals_dict["sys"] = sys
        globals_dict["Gui"] = self.gui
        saved = sys.argv
        sys.argv = ["freecadcmd", INSTALLED]
        try:
            exec(compile(source, INIT_GUI, "exec"), globals_dict, locals_dict)
        finally:
            sys.argv = saved
        self.assertEqual(len(self.gui.added), 1)

    def test_init_py_adds_addon_dir_to_path(self):
        source = open(INIT_PY).read()
        saved = list(sys.path)
        try:
            sys.path.remove(os.path.dirname(INIT_PY))
        except ValueError:
            pass
        globals_dict, locals_dict = {}, {}
        globals_dict["__builtins__"] = builtins
        globals_dict["__file__"] = INIT_PY
        globals_dict["os"] = os
        globals_dict["sys"] = sys
        exec(compile(source, INIT_PY, "exec"), globals_dict, locals_dict)
        self.assertIn(os.path.dirname(INIT_PY), sys.path)
        sys.path[:] = saved

    def test_command_resources_point_at_icon(self):
        from ntrak_container import commands

        resources = commands.GenerateCommand().GetResources()
        self.assertTrue(resources["Pixmap"].endswith("container.svg"))
        self.assertIn("Generate container", resources["MenuText"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    sys.exit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
