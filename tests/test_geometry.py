"""Geometry tests that need FreeCAD: shapes, volumes and scale behaviour.

Run headless with::

    flatpak run --command=freecadcmd org.freecad.FreeCAD tests/test_geometry.py

The expected volumes and bounding boxes come from the original hand-modelled
reference container (see README).  The generated geometry is translated and
mirrored relative to it, so the comparison uses sizes and volumes, not
positions.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scaletainer import builder
from scaletainer.params import BuildConfig, ContainerParams, derive

#: reference ground truth at 1:160, measured from the original hand-modelled container
REFERENCE = {
    "SideWallRight": {"volume": 2189.6384, "size": (89.94, 1.5, 18.0975)},
    "SideWallLeft": {"volume": 2189.6384, "size": (89.94, 1.5, 18.0975)},
    "Roof": {"volume": 1334.8501, "size": (89.94, 13.1925, 1.25)},
    "Floor": {"volume": 1242.9017, "size": (89.94, 13.1925, 1.375)},
    "MountFrame": {"volume": 3 * 773.28, "size": (89.94, 13.1925, 15.4725)},
    "DoorSide": {"volume": 163.4849, "size": (0.625, 16.1925, 18.0975)},
}


def build(divider=160.0, *, include_far_door=False, **cfg):
    params = ContainerParams.reference()
    geom = derive(params, BuildConfig(scale_divider=divider, **cfg))
    return geom, builder.build_components(geom, include_far_door=include_far_door)


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

    def test_door_relief_faces_outwards(self):
        """The door plate backs onto the walls; its crests bulge out (X = 0).

        Mirroring this the wrong way buries the corrugation inside the
        container, which is what an earlier revision did.
        """
        import Part

        door = self.by_name["DoorSide"]
        fw = self.geom.door_frame_width
        bb = door.bounding_box
        probe = 1e-4
        outer = door.shape.common(
            Part.makeBox(probe, bb.YLength + 2, bb.ZLength + 2,
                         __import__("FreeCAD").Vector(-1, bb.YMin - 1, bb.ZMin - 1)
                         + __import__("FreeCAD").Vector(0, 0, 0)))
        # slice just inside the outer face (crest plane) and just inside the
        # plate back; the plate side must hold more material
        def area_at(x):
            solid = door.shape.common(Part.makeBox(
                probe, bb.YLength + 2, bb.ZLength + 2,
                __import__("FreeCAD").Vector(x - probe / 2, bb.YMin - 1, bb.ZMin - 1)))
            return solid.Volume / probe
        crest_side = area_at(1e-4)
        plate_side = area_at(fw - 1e-4)
        self.assertGreater(plate_side, crest_side,
                           f"plate side {plate_side:.3f} vs crest side {crest_side:.3f}")
        self.assertAlmostEqual(plate_side, self.geom.width * self.geom.height, places=1)

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
        names = [c.name for c in builder.build_components(
            geom, include_mount_frame=False, include_door=False,
            include_far_door=False)]
        self.assertEqual(names, ["SideWallRight", "SideWallLeft", "Roof", "Floor"])


class FarDoorTest(unittest.TestCase):
    """The realistic double-door end must stay inside the overall length."""

    @classmethod
    def setUpClass(cls):
        cls.geom, cls.components = build(include_far_door=True)
        cls.by_name = {c.name: c for c in cls.components}

    def test_far_door_present(self):
        self.assertIn("FarDoor", self.by_name)

    def test_assembly_never_exceeds_nominal_length(self):
        """The hard requirement: XMax lands exactly on the 1:1 length."""
        bb = builder.assembly_shape(self.components).BoundBox
        self.assertLessEqual(bb.XMax, self.geom.length + 1e-6)
        self.assertAlmostEqual(bb.XMax, self.geom.length, places=6)

    def test_far_door_flush_at_both_ends(self):
        door = self.by_name["FarDoor"].bounding_box
        self.assertAlmostEqual(door.XMin, self.geom.far_door_x0, places=6)
        self.assertAlmostEqual(door.XMax, self.geom.far_door_x1, places=6)
        self.assertAlmostEqual(self.geom.far_door_x1, self.geom.length, places=6)

    def test_far_door_is_one_valid_solid(self):
        shape = self.by_name["FarDoor"].shape
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)

    def test_far_door_spans_full_cross_section(self):
        bb = self.by_name["FarDoor"].bounding_box
        self.assertAlmostEqual(bb.YLength, self.geom.width, places=6)
        self.assertAlmostEqual(bb.ZLength, self.geom.height, places=6)

    def test_layers_sum_to_band(self):
        self.assertAlmostEqual(self.geom.far_door_plate + self.geom.far_door_hardware,
                               self.geom.far_door_available, places=9)

    def test_backing_plate_is_printable(self):
        # a solid base at least 0.2 mm at the smallest common scale
        self.assertGreaterEqual(self.geom.far_door_plate, 0.2)

    def test_toggle_removes_far_door(self):
        _, with_door = build(include_far_door=True)
        _, without = build(include_far_door=False)
        self.assertEqual(len(with_door), len(without) + 1)
        self.assertNotIn("FarDoor", {c.name for c in without})

    def test_far_door_survives_scaling(self):
        """1:87 and 1:160 both keep the door flush at the nominal length."""
        for divider in (87.0, 160.0, 225.0):
            geom, parts = build(divider, include_far_door=True)
            bb = builder.assembly_shape(parts).BoundBox
            with self.subTest(divider=divider):
                self.assertLessEqual(bb.XMax, geom.length + 1e-6)
                door = next(c for c in parts if c.name == "FarDoor")
                self.assertTrue(door.shape.isValid())


class DocumentTest(unittest.TestCase):
    def test_add_to_document_creates_group_and_features(self):
        import FreeCAD as App

        geom, parts = build()
        doc = App.newDocument("scaletainer_test")
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
