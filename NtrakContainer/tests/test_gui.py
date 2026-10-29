"""GUI smoke tests: the panel builds, previews and generates headless.

Skipped unless Qt is importable.  Run through ``tests/run_tests.py`` with
``QT_QPA_PLATFORM=offscreen``, which ``make test`` sets.
"""

import json
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
        # restore_defaults only covers the widgets above; keep the per-test
        # output settings isolated so tests cannot leak files into each other
        self.panel.dir_edit.setText(self.tmp)
        self.panel.remember_export.setChecked(True)
        for key, check in self.panel.format_checks:
            check.setChecked(key in ("fcstd", "stl"))
        self.panel.parts_check.setChecked(True)

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

    def test_scale_combo_only(self):
        """The preset combo is the only scale input; no custom field remains."""
        self.assertFalse([w for w in self.panel.findChildren(QtWidgets.QLineEdit)
                          if "custom" in w.placeholderText()],
                         "custom modelling scale field should be gone")
        self.panel.scale_combo.setCurrentIndex(self.panel.scale_combo.findData(87.0))
        self.assertEqual(self.panel._scale_divider(), 87.0)
        self.panel.scale_combo.setCurrentIndex(self.panel.scale_combo.findData(160.0))
        self.panel._refresh_preview()
        self.assertNotIn("Invalid", self.panel.status.text())

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
        self.panel.scale_combo.setCurrentIndex(self.panel.scale_combo.findData(225.0))
        self.assertEqual(self.panel._scale_divider(), 225.0)
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

    def test_typed_value_with_unit_suffix_is_accepted(self):
        """Regression: the whole display line ("9000 mm") must parse, not revert.

        valueFromText used to call float() on the text including the unit
        suffix, which raised and silently kept the old value -- so a manually
        entered dimension never took effect.
        """
        box = self.panel._fields["length"]
        self.assertEqual(box.valueFromText("9000 mm"), 9000.0)
        self.assertEqual(box.valueFromText("  9000  mm "), 9000.0)
        self.assertEqual(box.valueFromText("9000"), 9000.0)
        # an unparsable entry must keep the current value rather than crash
        box.setValue(14630.4)
        self.assertEqual(box.valueFromText("abc mm"), 14630.4)

    def test_typing_into_custom_field_updates_the_model(self):
        self.panel.size_combo.setCurrentIndex(0)      # "-- custom --"
        box = self.panel._fields["length"]
        box.lineEdit().setText("9000 mm")
        box.interpretText()
        self.assertAlmostEqual(box.value(), 9000.0, places=6)
        self.assertAlmostEqual(self.panel.input_values()["length"], 9000.0,
                               places=6)

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

    def test_fresh_panel_opens_on_reference_size(self):
        """Startup must select the reference size without restore_defaults."""
        from ntrak_container import gui

        fresh = gui.create_panel(self.tmp)
        try:
            self.assertEqual(fresh.size_combo.currentText(),
                             "48 ft x 8.5 x 9.5 ft (reference)")
            self.assertAlmostEqual(fresh._fields["length"].value(), 14630.4,
                                   places=6)
        finally:
            fresh.close()

    def test_tab_order(self):
        titles = [self.panel.tabs.tabText(i) for i in range(self.panel.tabs.count())]
        self.assertEqual(
            titles,
            ["Dimensions (1:1)", "Corrugation", "Scale & options", "Preview",
             "Generate"])

    def test_no_restore_defaults_button(self):
        buttons = [b.text() for b in self.panel.findChildren(QtWidgets.QPushButton)]
        self.assertFalse([t for t in buttons if "Restore" in t], buttons)

    # ------------------------------------------------------------ config I/O
    def test_save_config_writes_the_panel(self):
        from ntrak_container import config as config_io

        self.panel.size_combo.setCurrentIndex(
            self.panel.size_combo.findText("20 ft dry (ISO 1AA)"))
        self.panel.scale_combo.setCurrentIndex(self.panel.scale_combo.findData(87.0))
        self.panel.config_name_edit.setText("20 footer")
        path = os.path.join(self.tmp, "saved.json")
        written = self.panel.save_config(path)
        self.assertEqual(written, path)
        self.assertEqual(self.panel.config_label.text(),
                         "20 footer - " + path)
        cfg = config_io.load(path)
        self.assertEqual(cfg.name, "20 footer")
        self.assertAlmostEqual(cfg.values["length"], 6058.0, places=6)
        self.assertEqual(cfg.values["scale_divider"], 87.0)
        self.assertEqual(cfg.values["side_ribs"]["count"], 24)
        # output settings travel with the file
        self.assertEqual(cfg.export.directory, self.panel.dir_edit.text())
        self.assertEqual(cfg.export.formats, self.panel.selected_formats())
        self.assertIs(cfg.export.separate_parts, self.panel.parts_check.isChecked())

    def test_save_then_load_restores_every_field(self):
        """The round trip must be lossless, including the input unit."""
        self.panel.unit_combo.setCurrentIndex(
            self.panel.unit_combo.findData("in"))
        self.panel.size_combo.setCurrentIndex(
            self.panel.size_combo.findText("40 ft high cube (1BB)"))
        self.panel._fields["frame_size"].setValue(5.0)
        self.panel._rib_fields["side_ribs"]["count"].setValue(31)
        self.panel._rib_fields["top_ribs"]["ratio"].setValue(0.33)
        self.panel.min_feature.setValue(0.4)
        self.panel.inc_mount.setChecked(False)
        self.panel.parts_check.setChecked(False)
        self.panel.scale_combo.setCurrentIndex(
            self.panel.scale_combo.findData(225.0))
        before = self.panel.input_values()
        before_unit = self.panel._unit
        path = os.path.join(self.tmp, "roundtrip.json")
        self.assertIsNotNone(self.panel.save_config(path))

        self.panel.restore_defaults()
        self.panel.unit_combo.setCurrentIndex(
            self.panel.unit_combo.findData("in"))
        loaded = self.panel.load_config(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(self.panel._unit, before_unit)
        self.assertEqual(self.panel.input_values(), before)
        self.assertFalse(self.panel.inc_mount.isChecked())
        self.assertFalse(self.panel.parts_check.isChecked())
        self.assertAlmostEqual(self.panel._fields["frame_size"].value(), 5.0,
                               places=6)
        self.assertEqual(self.panel._rib_fields["side_ribs"]["count"].value(), 31)
        self.assertEqual(self.panel.size_combo.currentText(),
                         "40 ft high cube (1BB)")
        self.assertIn("Loaded", self.panel.status.text())

    def test_load_keeps_hidden_options(self):
        """A file carrying console-only toggles must not lose them."""
        from ntrak_container import config as config_io, tasks

        cfg = config_io.build(self.panel.input_values(), "mm",
                              name="no far door")
        cfg.values["include_far_door"] = False
        cfg.values["include_door_side"] = False
        path = os.path.join(self.tmp, "hidden.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(cfg.to_json())

        self.assertIsNotNone(self.panel.load_config(path))
        values = self.panel.input_values()
        self.assertIs(values["include_far_door"], False)
        self.assertIs(values["include_door_side"], False)
        built = tasks.build_config(values)
        self.assertFalse(built.include_far_door)
        self.assertFalse(built.include_door_side)

    def test_load_accepts_generated_sidecar(self):
        """The .json the generator writes can be read back into the panel."""
        from ntrak_container import config as config_io

        cfg = config_io.build(self.panel.input_values(), "mm")
        side = {"generator": "NtrakContainer", "unit": "mm",
                "input_1to1": {k: v for k, v in cfg.values.items()
                               if k in config_io.LENGTH_KEYS
                               or k in config_io.RIB_KEYS
                               or k in config_io.COUNT_KEYS},
                "build_config": {"scale_divider": 150.0,
                                 "include_mount_frame": False},
                "notes": []}
        path = os.path.join(self.tmp, "sidecar.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(side, handle)

        self.panel.scale_combo.setCurrentIndex(
            self.panel.scale_combo.findData(150.0))
        expected = self.panel.input_values()
        self.assertIsNotNone(self.panel.load_config(path))
        self.assertEqual(self.panel._scale_divider(), 150.0)
        self.assertFalse(self.panel.inc_mount.isChecked())
        loaded = self.panel.input_values()
        shared = [k for k in config_io.LENGTH_KEYS if k in expected]
        self.assertEqual({k: expected[k] for k in shared},
                         {k: loaded[k] for k in shared})
        # a field with no widget keeps the reference value
        self.assertNotIn("far_door_stile", loaded)

    def test_load_non_config_file_reports_in_panel(self):
        path = os.path.join(self.tmp, "junk.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"not": "a container"}')
        before = self.panel._fields["length"].value()
        self.assertIsNone(self.panel.load_config(path))
        self.assertIn("Could not load", self.panel.status.text())
        self.assertAlmostEqual(self.panel._fields["length"].value(), before,
                               places=6)

    def test_load_malformed_json_reports_in_panel(self):
        path = os.path.join(self.tmp, "broken.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"values": ')
        self.assertIsNone(self.panel.load_config(path))
        self.assertIn("Could not load", self.panel.status.text())

    def test_save_adds_json_extension(self):
        path = os.path.join(self.tmp, "noext")
        written = self.panel.save_config(path)
        self.assertTrue(written.endswith(".json"))
        self.assertTrue(os.path.isfile(written))

    def test_suggested_name_ends_in_json(self):
        """Regression: the dotted default name lost its .json suffix.

        The reference size is 14630.4 x 2590.8 x 2895.6 mm, so the suggested
        file name is full of decimal points; os.path.splitext treated the last
        one as an extension and Save wrote a file named without .json.
        """
        name = self.panel._default_config_name()
        self.assertTrue(name.endswith(".json"), name)
        self.assertNotIn(".", name[:-len(".json")], name)
        self.assertIn("14630x2591x2896", name)
        self.assertIn("-1-160", name)
        self.assertEqual(name, "container-14630x2591x2896-1-160.json")

        # whatever the dialog returns is still honoured verbatim
        state = self._stub_dialogs(save=os.path.join(self.tmp, name))
        try:
            written = self.panel.save_config()
        finally:
            self._restore_dialogs()
        self.assertTrue(written.endswith(".json"), written)
        self.assertTrue(os.path.isfile(written), written)
        self.assertEqual(self.panel.config_path, written)

    def test_suggested_name_for_decimal_units(self):
        """Inches keep decimals in the fields; the name must stay dot-free."""
        self.panel.unit_combo.setCurrentIndex(
            self.panel.unit_combo.findData("in"))
        name = self.panel._default_config_name()
        self.assertTrue(name.endswith(".json"), name)
        self.assertNotIn(".", name[:-len(".json")], name)
        self.panel.restore_defaults()

    def test_out_of_range_value_is_reported(self):
        """Qt clamps silently, so the panel must say which field was limited."""
        from ntrak_container import config as config_io

        values = dict(self.panel.input_values())
        values["mount_frame_count"] = 999        # widget tops out at 50
        values["length"] = 5_000_000.0           # above the spin box range
        path = os.path.join(self.tmp, "clamped.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(config_io.build(values, "mm").to_json())

        self.panel.load_config(path)
        self.assertIn("clamped", self.panel.status.text())
        self.assertIn("length", self.panel.status.text())
        self.assertIn("mount_frame_count", self.panel.status.text())
        self.assertEqual(self.panel.mount_count.value(), 50)
        self.panel.restore_defaults()
        self.assertNotIn("clamped", self.panel.status.text())

    def test_in_range_load_does_not_warn(self):
        path = os.path.join(self.tmp, "clean.json")
        self.panel.save_config(path)
        self.panel.load_config(path)
        self.assertNotIn("clamped", self.panel.status.text())
        self.assertTrue(self.panel.status.text().startswith("Loaded"))

    def test_partial_file_loads_with_reference_defaults(self):
        """A hand-written file with only a few keys must not break the panel."""
        from ntrak_container import config as config_io
        from ntrak_container.params import ContainerParams

        path = os.path.join(self.tmp, "partial.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(config_io.build(
                {"length": 6058.0, "width": 2438.0, "height": 2591.0,
                 "scale_divider": 87.0}, "mm").to_json())
        reference = ContainerParams.reference()
        self.assertIsNotNone(self.panel.load_config(path))
        self.assertAlmostEqual(self.panel._fields["length"].value(), 6058.0,
                               places=6)
        self.assertEqual(self.panel._scale_divider(), 87.0)
        # rib sets the file did not mention keep the reference values
        self.assertEqual(self.panel._rib_fields["top_ribs"]["count"].value(),
                         reference.top_ribs.count)
        self.assertAlmostEqual(
            self.panel._rib_fields["side_ribs"]["slope"].value(),
            reference.side_ribs.slope, places=6)
        self.assertEqual(self.panel.mount_count.value(),
                         reference.mount_frame_count)

    def test_browse_updates_the_output_folder(self):
        """Regression: getExistingDirectory returns a str, not a (path, filter)."""
        target = os.path.join(self.tmp, "chosen-folder")
        state = self._stub_dialogs(existing=target)
        try:
            self.panel._browse()
            self.assertEqual(self.panel.dir_edit.text(), target)
            self.assertEqual(self.panel.output_directory(), target)
            state["existing"] = ""     # cancelled dialog keeps the current folder
            self.panel._browse()
            self.assertEqual(self.panel.dir_edit.text(), target)
        finally:
            self._restore_dialogs()

    def test_dialog_buttons_use_their_results(self):
        """Save/Load driven by the file dialogs (no explicit path) must work."""
        path = os.path.join(self.tmp, "dialog.json")
        self._stub_dialogs(save=path, load=path)
        try:
            self.panel.config_name_edit.setText("via dialog")
            self.assertEqual(self.panel.save_config(), path)
            self.assertTrue(os.path.isfile(path), path)
            self.panel.restore_defaults()
            self.panel.load_config()
            self.assertEqual(self.panel.config_name, "via dialog")
            self.assertEqual(self.panel.config_path, path)
            self.assertIn("Loaded", self.panel.status.text())
        finally:
            self._restore_dialogs()

    def test_cancelled_dialogs_do_nothing(self):
        self._stub_dialogs()
        before = self.panel.dir_edit.text()
        try:
            self.assertIsNone(self.panel.save_config())
            self.assertIsNone(self.panel.load_config())
            self.panel._browse()
            self.assertEqual(self.panel.dir_edit.text(), before)
            self.assertIsNone(self.panel.config_path)
        finally:
            self._restore_dialogs()

    # -------------------------------------------------------- dialog stubs
    def _stub_dialogs(self, existing="", save="", load=""):
        """Replace the three static QFileDialog queries; returns the answers.

        Mutate the returned dict to change what a dialog hands back, e.g. to
        simulate a cancelled dialog.  ``_restore_dialogs`` undoes the patch.
        """
        cls = QtWidgets.QFileDialog
        if not hasattr(cls, "_ntrak_originals"):
            cls._ntrak_originals = (cls.getExistingDirectory,
                                    cls.getSaveFileName, cls.getOpenFileName)
        answers = {"existing": existing, "save": save, "load": load}
        cls.getExistingDirectory = staticmethod(
            lambda *a, **k: answers["existing"] or "")
        cls.getSaveFileName = staticmethod(
            lambda *a, **k: (answers["save"] or "", "Container configuration (*.json)"))
        cls.getOpenFileName = staticmethod(
            lambda *a, **k: (answers["load"] or "", "Container configuration (*.json)"))
        return answers

    def _restore_dialogs(self):
        cls = QtWidgets.QFileDialog
        originals = cls._ntrak_originals
        cls.getExistingDirectory, cls.getSaveFileName, cls.getOpenFileName = originals
        del cls._ntrak_originals

    def test_config_buttons_exist(self):
        """The Save/Load buttons are present; their slots are tested directly."""
        for button in (self.panel.save_config_button, self.panel.load_config_button):
            self.assertTrue(button.text().endswith("config..."), button.text())
            self.assertFalse(button.isCheckable())
            self.assertTrue(button.toolTip())

    def test_non_preset_scale_from_file_is_kept(self):
        """A scale outside the presets must not snap back to a preset."""
        from ntrak_container import config as config_io

        def write(divider):
            path = os.path.join(self.tmp, f"scale{divider:g}.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(config_io.build(
                    dict(self.panel.input_values(), scale_divider=divider),
                    "mm").to_json())
            return path

        base = self.panel.scale_combo.count()
        self.panel.load_config(write(96.0))
        self.assertEqual(self.panel._scale_divider(), 96.0)
        self.assertIn("1:96", self.panel.scale_combo.currentText())
        self.assertEqual(self.panel.scale_combo.count(), base + 1)
        # loading another odd scale replaces the entry instead of stacking up
        self.panel.load_config(write(98.0))
        self.assertEqual(self.panel._scale_divider(), 98.0)
        self.assertEqual(self.panel.scale_combo.count(), base + 1)
        self.assertNotIn(96.0,
                         [self.panel.scale_combo.itemData(i)
                          for i in range(self.panel.scale_combo.count())])
        # and a preset scale afterwards still works
        self.panel.load_config(write(87.0))
        self.assertEqual(self.panel._scale_divider(), 87.0)
        self.assertEqual(self.panel.scale_combo.count(), base)

    def test_restore_defaults_clears_the_config_file(self):
        path = os.path.join(self.tmp, "clear.json")
        self.panel.save_config(path)
        self.assertEqual(self.panel.config_path, path)
        self.panel.restore_defaults()
        self.assertIsNone(self.panel.config_path)
        self.assertEqual(self.panel.config_label.text(), "no configuration file")
        self.assertEqual(self.panel.config_name_edit.text(), "")
        self.assertEqual(self.panel._hidden_options, {})

    def test_export_option_can_be_left_out_of_the_file(self):
        from ntrak_container import config as config_io

        self.panel.remember_export.setChecked(False)
        path = os.path.join(self.tmp, "values-only.json")
        self.panel.save_config(path)
        cfg = config_io.load(path)
        self.assertIsNone(cfg.export)
        # loading it must leave the current output settings alone
        self.panel.dir_edit.setText(os.path.join(self.tmp, "elsewhere"))
        self.panel.load_config(path)
        self.assertEqual(self.panel.dir_edit.text(),
                         os.path.join(self.tmp, "elsewhere"))

    def test_config_roundtrip_then_generate(self):
        """A loaded configuration still produces the same files."""
        self.panel.scale_combo.setCurrentIndex(self.panel.scale_combo.findData(87.0))
        path = os.path.join(self.tmp, "gen.json")
        self.panel.save_config(path)
        self.panel.restore_defaults()
        self.panel.load_config(path)
        out = os.path.join(self.tmp, "gen-out")
        os.makedirs(out, exist_ok=True)
        self.panel.dir_edit.setText(out)
        self.panel.generate()
        self.assertIn("Wrote", self.panel.status.text())
        written = os.listdir(out)
        self.assertTrue(any(f.endswith(".json") for f in written), written)
        with open(os.path.join(out, [f for f in written
                                     if f.endswith(".json")][0]),
                  encoding="utf-8") as handle:
            side = json.load(handle)
        self.assertEqual(side["scale"], "1:87")

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
