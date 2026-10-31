"""Export tests: the written files must exist, be non-empty and re-readable.

Run headless with::

    flatpak run --command=freecadcmd org.freecad.FreeCAD tests/test_export.py
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import FreeCAD as App

from scaletainer import exporter
from scaletainer.params import BuildConfig, ContainerParams, derive


class ExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="scaletainer_test_")
        cls.params = ContainerParams.reference()
        cls.cfg = BuildConfig(scale_divider=87.0)
        cls.result = exporter.export_all(cls.params, cls.cfg, cls.tmp,
                                         progress=lambda m: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_requested_format_written(self):
        for ext in ("FCStd", "step", "stl", "3mf", "json"):
            path = os.path.join(self.tmp, f"{self.result.stem}.{ext}")
            with self.subTest(ext=ext):
                self.assertTrue(os.path.isfile(path), f"missing {path}")
                self.assertGreater(os.path.getsize(path), 100)

    def test_part_files_written(self):
        sub = os.path.join(self.tmp, f"{self.result.stem}-parts")
        self.assertTrue(os.path.isdir(sub))
        geom = derive(self.params, self.cfg)
        names = [c.name for c in exporter.builder.build_components(geom)]
        for name in names:
            with self.subTest(part=name):
                self.assertTrue(os.path.isfile(os.path.join(sub, f"{self.result.stem}-{name}.stl")))

    def test_parts_combined_3mf_holds_every_part(self):
        import zipfile

        path = os.path.join(self.tmp, f"{self.result.stem}-parts.3mf")
        self.assertTrue(os.path.isfile(path))
        with zipfile.ZipFile(path) as archive:
            model = archive.read("3D/3dmodel.model").decode("utf-8")
        num_parts = len(exporter.builder.build_components(derive(self.params, self.cfg)))
        self.assertEqual(model.count("<item "), num_parts)
        # every part keeps its own placement on the plate
        transforms = set(re.findall(r'<item objectid="\d+" transform="([^"]+)"', model))
        self.assertEqual(len(transforms), num_parts)

    def test_combined_parts_rest_on_one_plane(self):
        parts = self.result.loose
        self.assertEqual(len(parts), 7)
        for part in parts:
            bb = part.shape.BoundBox
            with self.subTest(part=part.name):
                self.assertAlmostEqual(bb.ZMin, 0.0, places=6)
                self.assertGreaterEqual(bb.XMin, -1e-6)
                self.assertGreaterEqual(bb.YMin, -1e-6)
        boxes = [p.shape.BoundBox for p in parts]
        # no two parts may overlap on the build plate
        for i, a in enumerate(boxes):
            for j, b in enumerate(boxes[i + 1:], start=i + 1):
                overlap = (min(a.XMax, b.XMax) - max(a.XMin, b.XMin) > 1e-6
                           and min(a.YMax, b.YMax) - max(a.YMin, b.YMin) > 1e-6)
                self.assertFalse(overlap, f"{parts[i].name} overlaps {parts[j].name}")

    def test_combined_parts_are_flat(self):
        """Each part lies on its broad face, not standing on a thin edge."""
        for part in self.result.loose:
            bb = part.shape.BoundBox
            with self.subTest(part=part.name):
                self.assertLessEqual(bb.ZLength, min(bb.XLength, bb.YLength) + 1e-6,
                                     "part stands on its thin edge instead of lying flat")

    def test_mount_rings_lie_flat_for_printing(self):
        """The mounting ribs print as rings on their annular face, in one row."""
        frame = [part for part in self.result.loose if part.name == "MountFrame"][0]
        ribs = frame.shape.Solids
        self.assertGreater(len(ribs), 1, "mounting frame lost its separate ribs")
        for rib in ribs:
            bb = rib.BoundBox
            with self.subTest(rib=ribs.index(rib)):
                self.assertLessEqual(bb.ZLength, min(bb.XLength, bb.YLength) + 1e-6,
                                     "rib stands on edge instead of lying as a ring")
                self.assertAlmostEqual(bb.ZMin, 0.0, places=6)
                self.assertAlmostEqual(bb.YMin, ribs[0].BoundBox.YMin, places=6)
                self.assertAlmostEqual(bb.YMax, ribs[0].BoundBox.YMax, places=6)

    def test_stl_is_reimportable(self):
        import Mesh

        path = os.path.join(self.tmp, f"{self.result.stem}.stl")
        mesh = Mesh.Mesh(path)
        self.assertGreater(mesh.CountFacets, 1000)
        bb = mesh.BoundBox
        geom = derive(self.params, self.cfg)
        # the far door extends the model to the full nominal length
        self.assertAlmostEqual(bb.XLength, geom.length, places=2)
        self.assertLessEqual(bb.XMax, geom.length + 1e-3)
        self.assertAlmostEqual(bb.YLength, geom.width, places=2)
        self.assertAlmostEqual(bb.ZLength, geom.height, places=2)

    def test_document_reloads_with_no_spreadsheet(self):
        path = os.path.join(self.tmp, f"{self.result.stem}.FCStd")
        doc = App.openDocument(path)
        try:
            types = {o.TypeId for o in doc.Objects}
            self.assertNotIn("Spreadsheet::Sheet", types,
                             "generated document must not contain spreadsheets")
            features = [o for o in doc.Objects if o.TypeId == "Part::Feature"]
            self.assertEqual(len(features), 7)
            total = sum(o.Shape.Volume for o in features)
            self.assertGreater(total, 0)
        finally:
            App.closeDocument(doc.Name)

    def test_params_sidecar_matches_inputs(self):
        path = os.path.join(self.tmp, f"{self.result.stem}.json")
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertEqual(payload["scale"], "1:87")
        self.assertEqual(payload["input_1to1"]["length"], 48 * 304.8)
        self.assertEqual(payload["build_config"]["scale_divider"], 87.0)
        self.assertAlmostEqual(payload["derived_scale_space"]["width"],
                               2590.8 / 87.0, places=9)
        self.assertIn("components", payload)
        self.assertEqual(len(payload["components"]), 7)

    def test_unknown_format_rejected(self):
        with self.assertRaises(ValueError):
            exporter.export_all(self.params, self.cfg, self.tmp, formats=("dwg",))

    def test_safe_name_strips_colons(self):
        self.assertEqual(exporter.safe_name("1:160 (N)"), "1-160-N")
        self.assertEqual(exporter.safe_name("///"), "container")

    def test_sidecar_loads_as_config(self):
        """The written sidecar is a valid input for scaletainer.config."""
        from scaletainer import config as config_io

        path = os.path.join(self.tmp, f"{self.result.stem}.json")
        cfg = config_io.load(path)
        self.assertEqual(cfg.unit, "mm")
        self.assertAlmostEqual(cfg.values["length"], 48 * 304.8, places=6)
        self.assertEqual(cfg.values["scale_divider"], 87.0)
        self.assertEqual(cfg.values["side_ribs"]["count"],
                         ContainerParams.reference().side_ribs.count)
        # and it feeds tasks unchanged
        from scaletainer import tasks

        built = tasks.build_config(cfg.values)
        self.assertTrue(built.include_mount_frame)
        self.assertTrue(built.include_far_door)


class ConfigGenerateTest(unittest.TestCase):
    """commands.generate_from_config builds straight from a saved file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="scaletainer_cfggen_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _config_file(self, directory=None):
        from scaletainer import config as config_io

        p = ContainerParams.reference()
        values = {"length": p.length, "width": p.width, "height": p.height,
                  "scale_divider": 87.0,
                  "side_ribs": {"count": p.side_ribs.count, "slope": p.side_ribs.slope,
                                "ratio": p.side_ribs.ratio, "height": p.side_ribs.height}}
        export = {"directory": directory or self.tmp, "formats": ["stl"],
                  "separate_parts": False}
        return config_io.save(os.path.join(self.tmp, "box.json"), values, "mm",
                              export, name="probe")

    def test_generates_from_file(self):
        from scaletainer import commands

        result = commands.generate_from_config(self._config_file(),
                                               progress=lambda m: None)
        stl = os.path.join(self.tmp, result.stem + ".stl")
        self.assertTrue(os.path.isfile(stl))
        self.assertEqual(result.stem, "Scaletainer-168x30x33-1-87")

    def test_directory_argument_overrides_the_file(self):
        from scaletainer import commands

        override = os.path.join(self.tmp, "elsewhere")
        result = commands.generate_from_config(self._config_file(), override,
                                               progress=lambda m: None)
        self.assertEqual(result.directory, override)
        self.assertTrue(os.path.isdir(override))




if __name__ == "__main__":
    def main():
        suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

    sys.exit(main())
