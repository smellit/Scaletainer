"""Geometry tests that need FreeCAD: shapes, volumes and scale behaviour.

Run headless with::

    flatpak run --command=freecadcmd org.freecad.FreeCAD tests/test_geometry.py

The expected volumes and bounding boxes are measured from the reference model
``Container.FCStd`` (see README).  The generated geometry is translated and
mirrored relative to it, so the comparison uses sizes and volumes, not
positions.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ntrak_container import builder
from ntrak_container.params import BuildConfig, ContainerParams, derive

#: reference ground truth at 1:160, measured from Container.FCStd
REFERENCE = {
    "SideWallRight": {"volume": 2189.6384, "size": (89.94, 1.5, 18.0975)},
    "SideWallLeft": {"volume": 2189.6384, "size": (89.94, 1.5, 18.0975)},
    "Roof": {"volume": 1334.8501, "size": (89.94, 13.1925, 1.25)},
    "Floor": {"volume": 1242.9017, "size": (89.94, 13.1925, 1.375)},
    "MountFrame": {"volume": 3 * 773.28, "size": (89.94, 13.1925, 15.4725)},
    "DoorSide": {"volume": 163.4849, "size": (0.625, 16.1925, 18.0975)},
}


def build(divider=160.0, **cfg):
    params = ContainerParams.reference()
    geom = derive(params, BuildConfig(scale_divider=divider, **cfg))
    return geom, builder.build_components(geom)


class ReferenceMatchTest(unittest.TestCase):
    """At 1:160 the generated parts must equal the reference model."""

    @classmethod
    def setUpClass(cls):
        cls.geom, cls.components = build()
        cls.by_name = {c.name: c for c in cls.components}

    def test_all_reference_parts_present(self):
        self.assertEqual(sorted(self.by_name), sorted(REFERENCE))

    def test_volumes_and_sizes(self):
        for name, expected in REFERENCE.items():
            comp = self.by_name[name]
            bb = comp.bounding_box
            with self.subTest(part=name):
                self.assertAlmostEqual(comp.volume, expected["volume"], places=3)
                for got, want in zip((bb.XLength, bb.YLength, bb.ZLength),
                                     expected["size"]):
                    self.assertAlmostEqual(got, want, places=3)

    def test_shapes_are_valid_solids(self):
        for comp in self.components:
            with self.subTest(part=comp.name):
                self.assertTrue(comp.shape.isValid(), f"{comp.name} is invalid")

    def test_model_sits_in_first_octant(self):
        for comp in self.components:
            bb = comp.bounding_box
            with self.subTest(part=comp.name):
                self.assertGreaterEqual(bb.XMin, -1e-9)
                self.assertGreaterEqual(bb.YMin, -1e-9)
                self.assertGreaterEqual(bb.ZMin, -1e-9)

    def test_overall_envelope_is_the_scaled_box(self):
        shape = builder.assembly_shape(self.components)
        bb = shape.BoundBox
        self.assertAlmostEqual(bb.XLength, self.geom.overall_length, places=6)
        self.assertAlmostEqual(bb.YLength, self.geom.width, places=6)
        self.assertAlmostEqual(bb.ZLength, self.geom.height, places=6)


class ScaleBehaviourTest(unittest.TestCase):
    def test_ho_scale_is_sixteen_sixteenths_of_n(self):
        """1:160 -> 1:87 multiplies every length by 160/87."""
        geom_n, parts_n = build(160.0)
        geom_ho, parts_ho = build(87.0)
        ratio = 160.0 / 87.0
        by_name = {c.name: c for c in parts_ho}
        for comp in parts_n:
            with self.subTest(part=comp.name):
                self.assertAlmostEqual(by_name[comp.name].volume,
                                       comp.volume * ratio ** 3, places=1)

    def test_rib_counts_survive_scaling(self):
        _, parts_ho = build(87.0)
        side = next(c for c in parts_ho if c.name == "SideWallRight")
        self.assertEqual(side.info["ribs"], 24)

    def test_min_feature_keeps_geometry_valid(self):
        geom, parts = build(225.0, min_feature_mm=0.25, min_rib_pitch_mm=0.8)
        self.assertTrue(geom.notes, "expected adjustment notes at 1:225")
        for comp in parts:
            with self.subTest(part=comp.name):
                self.assertTrue(comp.shape.isValid())
        for rib in (geom.side, geom.top, geom.bottom, geom.door):
            self.assertLessEqual(rib.span, geom.inner_length + 1e-9)

    def test_toggles_drop_parts(self):
        geom = derive(ContainerParams.reference(),
                      BuildConfig(include_mount_frame=False, include_door_side=False))
        names = [c.name for c in builder.build_components(geom, include_mount_frame=False,
                                                          include_door=False)]
        self.assertEqual(names, ["SideWallRight", "SideWallLeft", "Roof", "Floor"])


class DocumentTest(unittest.TestCase):
    def test_add_to_document_creates_group_and_features(self):
        import FreeCAD as App

        geom, parts = build()
        doc = App.newDocument("ntrak_test")
        try:
            objects = builder.add_to_document(doc, parts, group_label="Container")
            self.assertEqual(len(objects), len(parts))
            self.assertEqual(doc.getObject("ContainerGroup").Label, "Container")
            doc.recompute()
            for obj in objects:
                self.assertFalse(obj.Shape.isNull())
                self.assertNotIn("Invalid", str(obj.State))
        finally:
            App.closeDocument(doc.Name)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(
        sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
