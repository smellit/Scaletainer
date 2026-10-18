"""Export tests: the written files must exist, be non-empty and re-readable.

Run headless with::

    flatpak run --command=freecadcmd org.freecad.FreeCAD tests/test_export.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import FreeCAD as App

from ntrak_container import exporter
from ntrak_container.params import BuildConfig, ContainerParams, derive


class ExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ntrak_test_")
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


if __name__ == "__main__":
    def main():
        suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

    sys.exit(main())
