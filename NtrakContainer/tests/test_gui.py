"""GUI smoke tests: the panel builds, previews and generates headless.

Skipped unless Qt is importable.  Run through ``tests/run_tests.py`` with
``QT_QPA_PLATFORM=offscreen``, which ``make test`` sets.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide import QtWidgets
    HAS_QT = True
except Exception:  # pragma: no cover - console-only builds
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide not available")
class PanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        from ntrak_container import gui

        cls.tmp = tempfile.mkdtemp(prefix="ntrak_gui_")
        cls.panel = gui.create_panel(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        cls.panel.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.panel.restore_defaults()

    def test_defaults_are_the_reference_container(self):
        values = self.panel.input_values()
        self.assertAlmostEqual(values["length"], 48 * 304.8, places=6)
        self.assertEqual(values["scale_divider"], 160.0)
        self.assertEqual(values["side_ribs"]["count"], 24)

    def test_preview_matches_derivation(self):
        from ntrak_container.params import BuildConfig, ContainerParams, derive

        geom = derive(ContainerParams.reference(), BuildConfig(**{
            k: v for k, v in self.panel.input_values().items()
            if k in BuildConfig.__dataclass_fields__}))
        data = self.panel.preview_data()
        self.assertIsNotNone(data)
        self.assertAlmostEqual(data.length, geom.length, places=9)
        rows = dict(self.panel.preview_rows())
        self.assertIn("Model length", rows)
        self.assertAlmostEqual(float(rows["Model length"].split()[0]), geom.length, places=3)

    def test_unit_change_preserves_model_size(self):
        from ntrak_container.units import to_mm

        before = to_mm(self.panel._fields["length"].value(),
                       str(self.panel.unit_combo.currentData()))
        index = self.panel.unit_combo.findData("ft")
        self.panel.unit_combo.setCurrentIndex(index)
        after = to_mm(self.panel._fields["length"].value(), "ft")
        self.assertAlmostEqual(before, after, places=3)
        self.assertAlmostEqual(self.panel._fields["length"].value(), 48.0, places=4)
        self.panel.unit_combo.setCurrentIndex(0)

    def test_custom_scale_field(self):
        self.panel.custom_scale.setText("1:87")
        self.panel._custom_scale_applied()
        self.assertEqual(self.panel._scale_divider(), 87.0)
        self.panel.custom_scale.setText("nonsense")
        self.panel._custom_scale_applied()
        self.assertIn("Could not read", self.panel.status.text())
        self.panel.custom_scale.clear()
        self.panel._refresh_preview()

    def test_invalid_parameters_reported_not_raised(self):
        original = self.panel._fields["length"].value()
        self.panel._fields["frame_size"].setValue(
            self.panel._fields["length"].value())
        self.assertIn("Invalid parameters", self.panel.status.text())
        self.panel._fields["frame_size"].setValue(120.0)
        self.panel._fields["length"].setValue(original)
        self.panel._refresh_preview()
        self.assertNotIn("Invalid", self.panel.status.text())

    def test_generate_writes_files(self):
        self.panel.custom_scale.setText("1:220")
        self.panel._custom_scale_applied()
        self.assertEqual(self.panel._scale_divider(), 220.0)
        self.panel.generate()
        self.assertIn("Wrote", self.panel.status.text())
        written = sorted(os.listdir(self.tmp))
        self.assertTrue(any(f.endswith(".FCStd") for f in written), written)
        self.assertTrue(any(f.endswith(".json") for f in written), written)
        self.assertTrue(self.panel._stem)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp,
                                                   f"{self.panel._stem}-parts")))

    def test_reset_restores_defaults(self):
        self.panel._fields["height"].setValue(1.0)
        self.panel._rib_fields["side_ribs"]["count"].setValue(3)
        self.panel._reset_dimensions()
        self.assertAlmostEqual(self.panel._fields["height"].value(), 2895.6, places=3)
        self.assertEqual(self.panel._rib_fields["side_ribs"]["count"].value(), 24)

    def test_dimension_fields_show_whole_numbers_without_buttons(self):
        box = self.panel._fields["length"]
        # no up/down arrows
        self.assertEqual(box.buttonSymbols(),
                         QtWidgets.QAbstractSpinBox.NoButtons)
        # reference length is 14630.4 mm but only the integer is displayed
        self.assertAlmostEqual(box.value(), 14630.4, places=6)
        self.assertEqual(box.text().split()[0], "14630")

    def test_size_selection_fills_dimensions_exactly(self):
        index = self.panel.size_combo.findText("20 ft dry (ISO 1AA)")
        self.assertGreater(index, 0)
        self.panel.size_combo.setCurrentIndex(index)
        self.assertAlmostEqual(self.panel._fields["length"].value(), 6058.0, places=6)
        self.assertAlmostEqual(self.panel._fields["width"].value(), 2438.0, places=6)
        self.assertAlmostEqual(self.panel._fields["height"].value(), 2591.0, places=6)

    def test_reference_size_selected_by_default(self):
        self.assertEqual(self.panel.size_combo.currentText(),
                         "48 ft x 8.5 x 9.5 ft (reference)")

    def test_manual_dimension_edit_drops_size_selection(self):
        index = self.panel.size_combo.findText("20 ft dry (ISO 1AA)")
        self.panel.size_combo.setCurrentIndex(index)
        self.panel._fields["length"].setValue(7000.0)
        self.assertEqual(self.panel.size_combo.currentIndex(), 0,
                         "manual edit must revert to -- custom --")
        self.assertAlmostEqual(self.panel._fields["width"].value(), 2438.0,
                               places=6, msg="only the edited field should change")

    def test_size_selection_does_not_revert_itself(self):
        """Programmatic fills must not look like a manual edit."""
        index = self.panel.size_combo.findText("40 ft high cube (1BB)")
        self.panel.size_combo.setCurrentIndex(index)
        self.assertEqual(self.panel.size_combo.currentIndex(), index)

    def test_unit_change_keeps_size_selection(self):
        index = self.panel.size_combo.findText("20 ft dry (ISO 1AA)")
        self.panel.size_combo.setCurrentIndex(index)
        self.panel.unit_combo.setCurrentIndex(
            self.panel.unit_combo.findData("ft"))
        self.assertEqual(self.panel.size_combo.currentIndex(), index)
        self.assertAlmostEqual(self.panel._fields["length"].value(),
                               6058.0 / 304.8, places=4)
        self.panel.unit_combo.setCurrentIndex(0)
        self.assertAlmostEqual(self.panel._fields["length"].value(), 6058.0, places=4)


@unittest.skipUnless(HAS_QT, "PySide not available")
class CommandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_command_resources_and_panel(self):
        from ntrak_container import commands

        cmd = commands.GenerateCommand()
        resources = cmd.GetResources()
        self.assertEqual(resources["MenuText"], "Generate container...")
        self.assertTrue(cmd.IsActive())
        panel = commands.open_panel()
        self.assertTrue(panel.isVisible())
        panel.hide()
        self.assertIs(commands.open_panel(), panel, "panel should be reused")


if __name__ == "__main__":
    import unittest

    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    sys.exit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
