"""Pure Python tests: unit handling, scales and the parameter derivation.

Run with ``python3 -m unittest discover -s tests`` from the add-on folder; no
FreeCAD needed.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scaletainer.params import (BuildConfig, ContainerParams, RibPattern,
                                    derive)
from scaletainer.units import (SCALE_PRESETS, Scale, from_mm, parse_scale,
                                   to_mm)


class UnitsTest(unittest.TestCase):
    def test_roundtrip(self):
        for unit in ("mm", "cm", "m", "in", "ft"):
            self.assertAlmostEqual(from_mm(to_mm(12.345, unit), unit), 12.345, places=9)

    def test_foot_is_exact(self):
        self.assertEqual(to_mm(1.0, "ft"), 304.8)
        self.assertAlmostEqual(to_mm(48.0, "ft"), 14630.4, places=9)

    def test_unknown_unit(self):
        with self.assertRaises(ValueError):
            to_mm(1.0, "furlong")

    def test_scale_parsing(self):
        for text in ("1:87", "87", "1/87", " 1 : 87 "):
            self.assertEqual(parse_scale(text).divider, 87.0)
        self.assertEqual(str(Scale(87.0)), "1:87")
        self.assertEqual(str(Scale(43.5)), "1:43.5")
        with self.assertRaises(ValueError):
            Scale(0)

    def test_presets_cover_ho_and_n(self):
        self.assertEqual(SCALE_PRESETS["1:87 (HO)"], 87.0)
        self.assertEqual(SCALE_PRESETS["1:160 (N)"], 160.0)


class DerivationTest(unittest.TestCase):
    """The reference model is the specification: every number must match."""

    def setUp(self):
        self.params = ContainerParams.reference()
        self.geom = derive(self.params, BuildConfig(scale_divider=160.0))

    def test_outer_dimensions(self):
        self.assertAlmostEqual(self.geom.length, 91.44, places=9)
        self.assertAlmostEqual(self.geom.width, 16.1925, places=9)
        self.assertAlmostEqual(self.geom.height, 18.0975, places=9)

    def test_derived_lengths(self):
        self.assertAlmostEqual(self.geom.inner_length, 89.94, places=9)
        self.assertAlmostEqual(self.geom.side_envelope, 1.5, places=9)
        self.assertAlmostEqual(self.geom.side_plate, 1.275, places=9)
        self.assertAlmostEqual(self.geom.mount_span, 13.1925, places=9)
        self.assertAlmostEqual(self.geom.mount_height, 15.4725, places=9)

    def test_side_rib(self):
        rib = self.geom.side
        self.assertEqual(rib.count, 24)
        self.assertAlmostEqual(rib.pitch, 3.7475, places=9)
        self.assertAlmostEqual(rib.slope, 0.3125, places=9)
        self.assertAlmostEqual(rib.valley, 2.498, places=9)
        self.assertAlmostEqual(rib.hill, 0.6245, places=9)
        self.assertAlmostEqual(rib.height, 0.225, places=9)

    def test_mount_positions(self):
        self.assertEqual(len(self.geom.mount_x), 3)
        self.assertAlmostEqual(self.geom.mount_x[0], 0.0, places=9)
        self.assertAlmostEqual(self.geom.mount_x[1], 40.97, places=6)
        self.assertAlmostEqual(self.geom.mount_x[2], 81.94, places=6)

    def test_no_notes_for_reference(self):
        self.assertEqual(self.geom.notes, [])

    def test_scale_invariance(self):
        """Doubling the divider must halve every length."""
        other = derive(self.params, BuildConfig(scale_divider=320.0))
        self.assertAlmostEqual(other.length, self.geom.length / 2, places=9)
        self.assertAlmostEqual(other.side.pitch, self.geom.side.pitch / 2, places=9)

    def test_min_rib_pitch_reduces_count(self):
        cfg = BuildConfig(scale_divider=160.0, min_rib_pitch_mm=6.0)
        geom = derive(self.params, cfg)
        self.assertLess(geom.side.count, 24)
        self.assertGreaterEqual(geom.side.pitch, 6.0)
        self.assertTrue(any("rib count reduced" in n for n in geom.notes))

    def test_min_feature_raises_small_ribs(self):
        cfg = BuildConfig(scale_divider=160.0, min_feature_mm=0.5)
        geom = derive(self.params, cfg)
        self.assertGreaterEqual(geom.side.slope, 0.5)
        self.assertTrue(any("floor" in n for n in geom.notes))

    def test_floors_never_overshoot_the_span(self):
        """Rib counts drop instead of the corrugation running past the wall."""
        for divider in (87.0, 160.0, 225.0):
            for floor in (0.0, 0.25, 0.5):
                geom = derive(self.params, BuildConfig(scale_divider=divider,
                                                       min_feature_mm=floor))
                with self.subTest(divider=divider, floor=floor):
                    self.assertEqual(geom.notes.count("overshoot"), 0)
                    for rib in (geom.side, geom.top, geom.bottom, geom.door):
                        self.assertLessEqual(rib.span, geom.inner_length + 1e-9)

    def test_rib_span_matches_pattern(self):
        for rib in (self.geom.side, self.geom.top, self.geom.bottom, self.geom.door):
            self.assertAlmostEqual(rib.span, rib.pitch * rib.count, places=9)
            self.assertAlmostEqual(rib.hill + rib.valley + 2 * rib.slope,
                                   rib.pitch, places=9)

    def test_validation_rejects_nonsense(self):
        with self.assertRaises(ValueError):
            derive(self.params.replaced(length=0), BuildConfig())
        with self.assertRaises(ValueError):
            derive(self.params.replaced(side_ribs=RibPattern(24, 5000.0, 0.2, 36.0)),
                   BuildConfig())
        with self.assertRaises(ValueError):
            derive(self.params, BuildConfig(scale_divider=0))

    def test_json_roundtrip(self):
        restored = ContainerParams.from_json(self.params.to_json())
        self.assertEqual(restored, self.params)


if __name__ == "__main__":
    unittest.main()
