"""Geometry tests that need FreeCAD: shapes, volumes and scale behaviour.

Run headless with::

    flatpak run --command=freecadcmd org.freecad.FreeCAD tests/test_geometry.py

The expected volumes and bounding boxes come from the original hand-modelled
reference container (see DEVELOPER.md).  The generated geometry is translated and
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


def build(divider=160.0, *, include_far_door=False, params=None, **cfg):
    params = params or ContainerParams.reference()
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


class FlatFloorTest(unittest.TestCase):
    """Disabling the floor corrugation must not change the container height."""

    @classmethod
    def setUpClass(cls):
        cls.geom, cls.components = build(include_floor_corrugation=False)
        cls.by_name = {c.name: c for c in cls.components}

    def test_floor_is_a_flat_plate(self):
        floor = self.by_name["Floor"]
        self.assertEqual(floor.info["ribs"], 0)
        self.assertAlmostEqual(floor.bounding_box.ZLength, self.geom.floor_depth,
                               places=6)
        self.assertAlmostEqual(floor.volume,
                               self.geom.inner_length * self.geom.mount_span
                               * self.geom.floor_depth, places=3)

    def test_floor_keeps_the_corrugated_depth(self):
        corrugated, _ = build()
        self.assertAlmostEqual(self.geom.floor_depth,
                               corrugated.bottom.height + corrugated.bottom_skin,
                               places=9)
        self.assertAlmostEqual(self.geom.bottom_flat_plate, self.geom.floor_depth,
                               places=9)

    def test_overall_height_is_unchanged(self):
        corrugated, parts = build()
        flat_bb = builder.assembly_shape(self.components).BoundBox
        corrugated_bb = builder.assembly_shape(parts).BoundBox
        self.assertAlmostEqual(flat_bb.ZLength, corrugated_bb.ZLength, places=6)
        self.assertAlmostEqual(flat_bb.ZLength, self.geom.height, places=6)
        self.assertAlmostEqual(self.geom.mount_height, corrugated.mount_height,
                               places=9)

    def test_floor_still_sits_on_the_build_plate(self):
        bb = self.by_name["Floor"].bounding_box
        self.assertAlmostEqual(bb.ZMin, 0.0, places=6)
        self.assertAlmostEqual(bb.ZMax, self.geom.floor_depth, places=6)

    def test_flat_floor_survives_scaling(self):
        for divider in (87.0, 160.0, 225.0):
            geom, parts = build(divider, include_floor_corrugation=False)
            floor = next(c for c in parts if c.name == "Floor")
            with self.subTest(divider=divider):
                self.assertTrue(floor.shape.isValid())
                self.assertAlmostEqual(floor.bounding_box.ZLength, geom.floor_depth,
                                       places=6)
                self.assertAlmostEqual(
                    builder.assembly_shape(parts).BoundBox.ZLength, geom.height,
                    places=6)


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


class MagnetStackTest(unittest.TestCase):
    """Magnet pockets are blind holes in the middle rib and the floor.

    The counterpart only needs a shallow seat in the roof's underside, so the
    rib's top member stays solid and the container stays closed.
    """

    @classmethod
    def setUpClass(cls):
        cls.geom, cls.components = build(include_magnets=True)
        cls.by_name = {c.name: c for c in cls.components}
        cls.plain_geom, cls.plain = build()
        cls.plain_by_name = {c.name: c for c in cls.plain}

    def test_pockets_are_off_by_default(self):
        self.assertEqual(self.plain_geom.magnet_pocket, 0.0)
        self.assertEqual(self.plain_geom.counterpart_pocket, 0.0)
        for name, expected in REFERENCE.items():
            with self.subTest(part=name):
                self.assertAlmostEqual(self.plain_by_name[name].volume,
                                       expected["volume"], places=3)

    def test_pocket_sizes_come_from_the_bought_parts(self):
        self.assertAlmostEqual(self.geom.magnet_pocket, 3.0 + 0.2, places=9)
        self.assertAlmostEqual(self.geom.counterpart_pocket, 7.0 + 0.2, places=9)
        self.assertAlmostEqual(self.geom.magnet_thickness, 1.0, places=9)
        self.assertAlmostEqual(self.geom.counterpart_thickness, 0.5, places=9)

    def test_only_the_middle_rib_gets_a_pocket(self):
        # three ribs: the middle one only, the outer two stay untouched
        self.assertEqual(len(self.geom.magnet_x), 1)
        self.assertAlmostEqual(
            self.geom.magnet_x[0],
            self.geom.door_frame_width + self.geom.mount_x[1]
            + self.geom.mount_frame_depth / 2.0, places=9)

    def test_an_even_rib_count_gets_the_two_middle_ribs(self):
        geom, _ = build(include_magnets=True,
                        params=ContainerParams(mount_frame_count=4))
        self.assertEqual(len(geom.magnet_x), 2)
        for x, rib_x in zip(geom.magnet_x, geom.mount_x[1:3]):
            with self.subTest(x=x):
                self.assertAlmostEqual(
                    x, geom.door_frame_width + rib_x
                    + geom.mount_frame_depth / 2.0, places=9)

    def test_a_single_rib_gets_the_pocket(self):
        geom, _ = build(include_magnets=True,
                        params=ContainerParams(mount_frame_count=1))
        self.assertEqual(len(geom.magnet_x), 1)
        self.assertAlmostEqual(
            geom.magnet_x[0],
            geom.door_frame_width + geom.mount_x[0]
            + geom.mount_frame_depth / 2.0, places=9)

    def test_pockets_are_centred_on_the_container(self):
        self.assertAlmostEqual(self.geom.magnet_y,
                               self.geom.side_envelope + self.geom.mount_span / 2.0,
                               places=9)

    def test_pockets_are_blind_holes_that_stop_at_a_membrane(self):
        # the pocket runs through the rib member and into the floor plate,
        # stopping magnet_membrane short of the outer face
        self.assertAlmostEqual(self.geom.magnet_floor_top,
                               self.geom.floor_depth + self.geom.mount_frame_wall,
                               places=9)
        self.assertAlmostEqual(self.geom.magnet_floor_depth,
                               self.geom.mount_frame_wall + self.geom.floor_depth
                               - self.geom.magnet_membrane, places=9)
        self.assertAlmostEqual(self.geom.magnet_floor_top
                               - self.geom.magnet_floor_depth,
                               self.geom.magnet_membrane, places=9)

    def test_counterpart_seat_is_a_shallow_recess_in_the_roof(self):
        # the seat starts at the roof's inner face and is only as deep as the
        # washer, so the rib's top member is never cut
        self.assertAlmostEqual(self.geom.magnet_roof_bottom,
                               self.geom.height - self.geom.roof_depth, places=9)
        self.assertAlmostEqual(self.geom.magnet_roof_depth,
                               self.geom.counterpart_thickness, places=9)
        self.assertLess(self.geom.magnet_roof_depth, self.geom.roof_depth)
        # the roof keeps its membrane above the seat
        self.assertAlmostEqual(self.geom.roof_depth - self.geom.magnet_roof_depth,
                               self.geom.roof_depth - self.geom.counterpart_thickness,
                               places=9)
        self.assertGreaterEqual(self.geom.roof_depth - self.geom.magnet_roof_depth,
                                self.geom.magnet_membrane - 1e-9)
        # a thin washer needs no relief in the rib at all
        self.assertEqual(self.geom.magnet_rib_top_depth, 0.0)

    def test_a_thick_counterpart_is_relieved_out_of_the_rib(self):
        # a 2.4 mm counterpart does not fit in the 0.75 mm roof seat, so the
        # rest of its thickness is cut out of the rib's top member
        geom, parts = build(include_magnets=True, counterpart_thickness_mm=2.4)
        self.assertAlmostEqual(geom.magnet_roof_depth,
                               self.geom.roof_depth - self.geom.magnet_membrane,
                               places=9)
        self.assertAlmostEqual(self.geom.magnet_rib_top_depth, 0.0, places=9)
        self.assertAlmostEqual(geom.magnet_rib_top_depth,
                               geom.counterpart_thickness - geom.magnet_roof_depth,
                               places=9)
        self.assertAlmostEqual(geom.magnet_roof_depth
                               + geom.magnet_rib_top_depth,
                               geom.counterpart_thickness, places=9)
        self.assertTrue(any("cut out of the mounting rib" in note
                            for note in geom.notes))
        for comp in parts:
            self.assertTrue(comp.shape.isValid())

    def test_the_rib_relief_is_capped_at_the_member_thickness(self):
        # a 3 mm counterpart is thicker than the seat plus the rib member, so
        # the relief stops at the member and a note says it will protrude
        geom, _ = build(include_magnets=True, counterpart_thickness_mm=3.0)
        self.assertAlmostEqual(geom.magnet_rib_top_depth,
                               geom.mount_frame_wall, places=9)
        self.assertTrue(any("protrude into the container" in note
                            for note in geom.notes))

    def test_the_rib_relief_is_cut_out_of_the_top_member(self):
        import Part
        from FreeCAD import Vector as Vec

        geom, parts = build(include_magnets=True, counterpart_thickness_mm=2.4)
        frame = next(c for c in parts if c.name == "MountFrame").shape
        rr = geom.counterpart_pocket / 2.0 * 0.9
        for x in geom.magnet_x:
            with self.subTest(x=x):
                # the relief is hollow, right under the roof's inner face
                probe = Part.makeCylinder(
                    rr, geom.magnet_rib_top_depth - 0.02,
                    Vec(x, geom.magnet_y,
                        geom.magnet_roof_bottom - geom.magnet_rib_top_depth + 0.01),
                    Vec(0, 0, 1))
                self.assertAlmostEqual(frame.common(probe).Volume, 0.0, places=6)
                # the member below the relief is still solid
                probe = Part.makeCylinder(
                    rr, 0.04,
                    Vec(x, geom.magnet_y,
                        geom.magnet_roof_bottom - geom.magnet_rib_top_depth - 0.05),
                    Vec(0, 0, 1))
                self.assertGreater(frame.common(probe).Volume, 0.0)

    def test_magnet_gap_is_the_floor_membrane_plus_the_roof_above_the_seat(self):
        self.assertAlmostEqual(
            self.geom.magnet_gap,
            self.geom.magnet_membrane + self.geom.roof_depth
            - self.geom.magnet_roof_depth, places=9)

    def test_pockets_are_deep_enough_for_the_parts(self):
        self.assertGreaterEqual(self.geom.magnet_floor_depth,
                                self.geom.magnet_thickness)
        self.assertGreaterEqual(self.geom.magnet_roof_depth,
                                self.geom.counterpart_thickness)

    def test_pockets_remove_material_from_floor_roof_and_ribs(self):
        for name in ("Floor", "Roof", "MountFrame"):
            with self.subTest(part=name):
                self.assertLess(self.by_name[name].volume,
                                self.plain_by_name[name].volume)

    def test_rib_top_member_is_left_solid(self):
        import Part
        from FreeCAD import Vector as Vec

        frame = self.by_name["MountFrame"].shape
        rr = self.geom.counterpart_pocket / 2.0 * 0.9
        for x in self.geom.magnet_x:
            with self.subTest(x=x):
                # the whole top member is untouched, from its underside up to
                # the roof's inner face
                probe = Part.makeCylinder(
                    rr, self.geom.mount_frame_wall - 0.02,
                    Vec(x, self.geom.magnet_y, self.geom.mount_height
                        - self.geom.mount_frame_wall + 0.01),
                    Vec(0, 0, 1))
                self.assertGreater(frame.common(probe).Volume, 0.0)

    def test_floor_and_roof_stay_closed(self):
        import Part
        from FreeCAD import Vector as Vec

        floor = self.by_name["Floor"].shape
        roof = self.by_name["Roof"].shape
        frame = self.by_name["MountFrame"].shape
        r = self.geom.magnet_pocket / 2.0 * 0.9
        rr = self.geom.counterpart_pocket / 2.0 * 0.9
        for x in self.geom.magnet_x:
            with self.subTest(x=x):
                # the rib's bottom member is hollowed out ...
                probe = Part.makeCylinder(
                    r, 0.05,
                    Vec(x, self.geom.magnet_y, self.geom.magnet_floor_top - 0.06),
                    Vec(0, 0, 1))
                self.assertAlmostEqual(frame.common(probe).Volume, 0.0, places=6)
                # ... and so is the floor plate, down to the membrane
                probe = Part.makeCylinder(
                    r, 0.05,
                    Vec(x, self.geom.magnet_y, self.geom.magnet_membrane + 0.01),
                    Vec(0, 0, 1))
                self.assertAlmostEqual(floor.common(probe).Volume, 0.0, places=6)
                # ... but the membrane itself is still solid
                probe = Part.makeCylinder(
                    r, 0.05,
                    Vec(x, self.geom.magnet_y, self.geom.magnet_membrane / 2.0),
                    Vec(0, 0, 1))
                self.assertGreater(floor.common(probe).Volume, 0.0)
                # the roof's underside is recessed for the washer ...
                probe = Part.makeCylinder(
                    rr, self.geom.magnet_roof_depth - 0.02,
                    Vec(x, self.geom.magnet_y, self.geom.magnet_roof_bottom + 0.01),
                    Vec(0, 0, 1))
                self.assertAlmostEqual(roof.common(probe).Volume, 0.0, places=6)
                # ... but the plate above the seat is still solid
                probe = Part.makeCylinder(
                    rr, 0.04,
                    Vec(x, self.geom.magnet_y,
                        self.geom.magnet_roof_bottom
                        + self.geom.magnet_roof_depth + 0.01),
                    Vec(0, 0, 1))
                self.assertGreater(roof.common(probe).Volume, 0.0)

    def test_overall_size_is_unchanged(self):
        bb = builder.assembly_shape(self.components).BoundBox
        plain_bb = builder.assembly_shape(self.plain).BoundBox
        self.assertAlmostEqual(bb.ZLength, plain_bb.ZLength, places=6)
        self.assertAlmostEqual(bb.ZLength, self.geom.height, places=6)
        self.assertAlmostEqual(bb.XLength, plain_bb.XLength, places=6)
        self.assertAlmostEqual(bb.YLength, plain_bb.YLength, places=6)

    def test_magnets_survive_scaling(self):
        for divider in (87.0, 160.0, 225.0):
            geom, parts = build(divider, include_magnets=True)
            with self.subTest(divider=divider):
                self.assertAlmostEqual(geom.magnet_pocket, 3.2, places=9)
                self.assertAlmostEqual(geom.counterpart_pocket, 7.2, places=9)
                for comp in parts:
                    self.assertTrue(comp.shape.isValid())
                self.assertAlmostEqual(
                    builder.assembly_shape(parts).BoundBox.ZLength, geom.height,
                    places=6)

    def test_magnets_work_with_a_flat_floor(self):
        geom, parts = build(include_magnets=True, include_floor_corrugation=False)
        floor = next(c for c in parts if c.name == "Floor")
        self.assertAlmostEqual(geom.magnet_floor_depth,
                               geom.mount_frame_wall + geom.floor_depth
                               - geom.magnet_membrane, places=9)
        self.assertTrue(floor.shape.isValid())
        self.assertAlmostEqual(builder.assembly_shape(parts).BoundBox.ZLength,
                               geom.height, places=6)

    def test_membrane_never_goes_below_the_minimum(self):
        from scaletainer.params import MAGNET_MEMBRANE_MIN_MM

        self.assertGreaterEqual(MAGNET_MEMBRANE_MIN_MM, 0.5)
        geom, _ = build(include_magnets=True, magnet_membrane_mm=0.1)
        self.assertAlmostEqual(geom.magnet_membrane, MAGNET_MEMBRANE_MIN_MM,
                               places=9)
        self.assertTrue(any("magnet membrane raised" in note
                            for note in geom.notes))
        # the floor keeps at least the minimum under the pocket
        self.assertAlmostEqual(geom.magnet_floor_top - geom.magnet_floor_depth,
                               MAGNET_MEMBRANE_MIN_MM, places=9)

    def test_a_thicker_membrane_is_honoured(self):
        geom, _ = build(include_magnets=True, magnet_membrane_mm=1.2)
        self.assertAlmostEqual(geom.magnet_membrane, 1.2, places=9)
        self.assertFalse(any("magnet membrane raised" in note
                             for note in geom.notes))

    def test_wide_counterpart_is_reported(self):
        geom, _ = build(divider=225.0, include_magnets=True)
        self.assertTrue(any("counterpart seat" in note for note in geom.notes))


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
