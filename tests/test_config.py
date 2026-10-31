"""Configuration file tests: the JSON format, validation and round trips.

Plain Python -- no FreeCAD, no Qt::

    python3 -m unittest discover -s tests -p 'test_config.py'
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scaletainer import config
from scaletainer.params import BuildConfig, ContainerParams


def sample_values() -> dict:
    """Everything the panel collects, as the reference container."""
    p = ContainerParams.reference()
    return {
        "length": p.length, "width": p.width, "height": p.height,
        "frame_size": p.frame_size, "door_frame_width": p.door_frame_width,
        "top_skin": p.top_skin, "bottom_skin": p.bottom_skin,
        "mount_frame_depth": p.mount_frame_depth,
        "mount_frame_wall": p.mount_frame_wall,
        "mount_frame_chamfer": p.mount_frame_chamfer,
        "mount_frame_count": p.mount_frame_count,
        "far_door_plate": p.far_door_plate,
        "far_door_rod_width": p.far_door_rod_width,
        "far_door_gap": p.far_door_gap, "far_door_corner": p.far_door_corner,
        "side_ribs": {"count": p.side_ribs.count, "slope": p.side_ribs.slope,
                      "ratio": p.side_ribs.ratio, "height": p.side_ribs.height},
        "top_ribs": {"count": p.top_ribs.count, "slope": p.top_ribs.slope,
                     "ratio": p.top_ribs.ratio, "height": p.top_ribs.height},
        "bottom_ribs": {"count": p.bottom_ribs.count, "slope": p.bottom_ribs.slope,
                        "ratio": p.bottom_ribs.ratio, "height": p.bottom_ribs.height},
        "door_ribs": {"count": p.door_ribs.count, "slope": p.door_ribs.slope,
                      "ratio": p.door_ribs.ratio, "height": p.door_ribs.height},
        "scale_divider": 87.0, "min_feature_mm": 0.25, "min_rib_pitch_mm": 0.0,
        "include_mount_frame": True,
    }


class RoundTripTest(unittest.TestCase):
    def test_full_config_survives_json(self):
        values = sample_values()
        cfg = config.build(values, "mm", {"directory": "~/Scaletainer",
                                          "formats": ["stl", "3mf"],
                                          "separate_parts": False},
                           name="my box")
        back = config.from_json(cfg.to_json())
        self.assertEqual(back.values, cfg.values)
        self.assertEqual(back.unit, "mm")
        self.assertEqual(back.name, "my box")
        self.assertEqual(back.export.directory, "~/Scaletainer")
        self.assertEqual(back.export.formats, ("stl", "3mf"))
        self.assertIs(back.export.separate_parts, False)

    def test_file_roundtrip(self):
        tmp = tempfile.mkdtemp(prefix="scaletainer_cfg_")
        try:
            path = config.save(os.path.join(tmp, "box.json"), sample_values(),
                               "mm", config.ExportOptions(
                                   directory=tmp, formats=("fcstd",),
                                   separate_parts=True), name="box")
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(data["generator"], config.FORMAT)
            self.assertEqual(data["config_version"], config.CONFIG_VERSION)
            back = config.load(path)
            self.assertEqual(back.values["length"], ContainerParams.reference().length)
            self.assertEqual(back.name, "box")
            self.assertEqual(back.export.directory, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_creates_missing_folder(self):
        tmp = tempfile.mkdtemp(prefix="scaletainer_cfg_")
        try:
            target = os.path.join(tmp, "configs", "box.json")
            config.save(target, {"length": 6058.0})
            self.assertTrue(os.path.isfile(target))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_values_are_usable_by_tasks(self):
        """A loaded file feeds the same pipeline the GUI calls."""
        from scaletainer import tasks

        cfg = config.build(sample_values(), "mm")
        params = tasks.container_params(cfg.values, cfg.unit)
        built = tasks.build_config(cfg.values)
        self.assertAlmostEqual(params.length, ContainerParams.reference().length,
                               places=6)
        self.assertEqual(built.scale_divider, 87.0)
        self.assertEqual(built.min_feature_mm, 0.25)
        self.assertTrue(built.include_mount_frame)
        # toggles the panel no longer exposes keep their default
        self.assertTrue(built.include_door_side)
        self.assertTrue(built.include_far_door)
        self.assertTrue(built.include_floor_corrugation)

    def test_typed_values_normalise(self):
        cfg = config.build({"length": 6058, "mount_frame_count": 3.0,
                            "side_ribs": {"count": 24.0, "slope": 50,
                                          "ratio": 0.2, "height": 36}})
        self.assertIsInstance(cfg.values["length"], float)
        self.assertIsInstance(cfg.values["mount_frame_count"], int)
        self.assertIsInstance(cfg.values["side_ribs"]["count"], int)
        self.assertIsInstance(cfg.values["side_ribs"]["slope"], float)


class AlternateShapesTest(unittest.TestCase):
    def test_bare_values_dict(self):
        cfg = config.from_dict({"length": 6058.0, "width": 2438.0,
                                "height": 2591.0, "scale_divider": 160})
        self.assertEqual(cfg.unit, "mm")
        self.assertIsNone(cfg.export)
        self.assertAlmostEqual(cfg.values["length"], 6058.0)

    def test_bare_dict_rejects_junk_keys(self):
        with self.assertRaises(config.ConfigError):
            config.from_dict({"length": 6058.0, "totally_unrelated": 1})

    def test_sidecar_is_readable(self):
        """The .json the generator writes can be loaded back as a config."""
        side = {
            "generator": "Scaletainer", "unit": "mm", "scale": "1:87",
            "input_1to1": {k: v for k, v in sample_values().items()
                           if k in config.LENGTH_KEYS + config.RIB_KEYS
                           or k in config.COUNT_KEYS},
            "build_config": {
                "scale_divider": 87.0, "min_feature_mm": 0.25,
                "min_rib_pitch_mm": 0.0, "include_mount_frame": True,
                "include_door_side": True, "include_far_door": False},
            "derived_scale_space": {"length": 168.0},
            "notes": ["side_ribs: 24 -> 20 ribs"],
        }
        cfg = config.from_dict(side)
        self.assertAlmostEqual(cfg.values["length"], ContainerParams.reference().length)
        self.assertEqual(cfg.values["scale_divider"], 87.0)
        self.assertIs(cfg.values["include_far_door"], False)
        self.assertEqual(cfg.unit, "mm")
        # it then feeds tasks unchanged
        from scaletainer import tasks
        self.assertFalse(tasks.build_config(cfg.values).include_far_door)

    def test_legacy_generator_marker_accepted(self):
        """Files saved before the add-on was named Scaletainer still load."""
        cfg = config.from_dict({"generator": "NtrakContainer/config",
                                "config_version": 1,
                                "values": sample_values()})
        self.assertAlmostEqual(cfg.values["length"], sample_values()["length"])

    def test_other_generator_marker_rejected(self):
        with self.assertRaises(config.ConfigError):
            config.from_dict({"generator": "SomethingElse", "values": {"length": 1}})

    def test_newer_version_rejected(self):
        with self.assertRaises(config.ConfigError) as ctx:
            config.from_dict({"generator": config.FORMAT,
                              "config_version": config.CONFIG_VERSION + 1,
                              "values": {"length": 1.0}})
        self.assertIn("newer version", str(ctx.exception))

    def test_unrecognised_shape_rejected(self):
        for bad in ({}, {"foo": 1}, [1, 2], "text", None):
            with self.subTest(bad=bad):
                with self.assertRaises(config.ConfigError):
                    config.from_dict(bad)


class ValidationTest(unittest.TestCase):
    def test_unknown_key_rejected(self):
        with self.assertRaises(config.ConfigError) as ctx:
            config.build({"lenght": 6058.0})
        self.assertIn("lenght", str(ctx.exception))

    def test_rib_pattern_must_be_complete(self):
        with self.assertRaises(config.ConfigError):
            config.build({"side_ribs": {"count": 24, "slope": 50.0}})
        with self.assertRaises(config.ConfigError):
            config.build({"side_ribs": {"count": 24, "slope": 50.0,
                                        "ratio": 0.2, "height": 36.0,
                                        "extra": 1}})
        with self.assertRaises(config.ConfigError):
            config.build({"side_ribs": 24})

    def test_counts_must_be_whole(self):
        with self.assertRaises(config.ConfigError):
            config.build({"mount_frame_count": 3.5})
        with self.assertRaises(config.ConfigError):
            config.build({"side_ribs": {"count": 24.5, "slope": 50.0,
                                        "ratio": 0.2, "height": 36.0}})

    def test_booleans_must_be_booleans(self):
        with self.assertRaises(config.ConfigError):
            config.build({"include_mount_frame": "yes"})

    def test_numbers_must_be_numbers(self):
        with self.assertRaises(config.ConfigError):
            config.build({"length": "6058"})

    def test_unknown_unit_rejected(self):
        with self.assertRaises(config.ConfigError):
            config.build({"length": 6058.0}, "furlong")

    def test_export_formats_validated(self):
        with self.assertRaises(config.ConfigError) as ctx:
            config.build({"length": 6058.0}, "mm", {"formats": ["obj"]})
        self.assertIn("obj", str(ctx.exception))
        # case and spacing are normalised, a bare string is accepted
        self.assertEqual(config.build({"length": 6058.0}, "mm",
                                      {"formats": [" STL ", "3MF"]}).export.formats,
                         ("stl", "3mf"))
        self.assertEqual(config.build({"length": 6058.0}, "mm",
                                      {"formats": "step"}).export.formats, ("step",))
        self.assertEqual(config.build({"length": 6058.0}, "mm",
                                      {"formats": []}).export.formats, ())

    def test_export_shape_validated(self):
        with self.assertRaises(config.ConfigError):
            config.build({"length": 6058.0}, "mm", {"directory": 5})
        with self.assertRaises(config.ConfigError):
            config.build({"length": 6058.0}, "mm", {"separate_parts": "sure"})
        with self.assertRaises(config.ConfigError):
            config.build({"length": 6058.0}, "mm", {"whoops": 1})
        with self.assertRaises(config.ConfigError):
            config.build({"length": 6058.0}, "mm", "not-an-object")

    def test_bad_json_reports_position(self):
        with self.assertRaises(config.ConfigError) as ctx:
            config.from_json('{"values": {"length": 1,}}')
        self.assertIn("invalid JSON", str(ctx.exception))

    def test_missing_file_reports_path(self):
        with self.assertRaises(config.ConfigError) as ctx:
            config.load("/nonexistent/dir/box.json")
        self.assertIn("could not read", str(ctx.exception).lower())

    def test_error_names_the_file(self):
        tmp = tempfile.mkdtemp(prefix="scaletainer_cfg_")
        try:
            path = os.path.join(tmp, "broken.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"values": {"nonsense": 1}}')
            with self.assertRaises(config.ConfigError) as ctx:
                config.load(path)
            self.assertIn("broken.json", str(ctx.exception))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_none_values_are_dropped(self):
        cfg = config.build({"length": 6058.0, "width": None})
        self.assertEqual(list(cfg.values), ["length"])


class HelperTest(unittest.TestCase):
    def test_with_extension(self):
        self.assertEqual(config.with_extension("box"), "box.json")
        self.assertEqual(config.with_extension("box.json"), "box.json")
        self.assertEqual(config.with_extension("box.cfg"), "box.cfg")
        self.assertEqual(config.with_extension("dir/box", ".json"), "dir/box.json")

    def test_with_extension_ignores_decimal_points(self):
        """Regression: a name with dots is not an extension.

        The suggested save name carries the exact 1:1 size
        ("container-14630.4x2590.8x2895.6-1-160"); os.path.splitext calls the
        trailing ".6-1-160" an extension, which left the file without .json.
        """
        dotted = "container-14630.4x2590.8x2895.6-1-160"
        self.assertEqual(config.with_extension(dotted), dotted + ".json")
        self.assertEqual(config.with_extension("container-238.5x96x102-1-87"),
                         "container-238.5x96x102-1-87.json")
        # a real extension is still respected
        self.assertEqual(config.with_extension("box.JSON"), "box.JSON")
        self.assertEqual(config.with_extension("archive.tar.gz"), "archive.tar.gz")
        self.assertEqual(config.with_extension("my.box"), "my.box")

    def test_describe(self):
        cfg = config.build({"length": 6058.0, "width": 2438.0, "height": 2591.0,
                            "scale_divider": 87.0}, "mm", name="20 ft HO")
        self.assertEqual(cfg.describe(), "20 ft HO, 6058 x 2438 x 2591 mm, 1:87")
        self.assertEqual(config.build({}).describe(), "container configuration")

    def test_json_is_stable_and_readable(self):
        text = config.to_json(sample_values(), "mm", name="x")
        again = config.to_json(config.from_json(text).values, "mm", name="x")
        self.assertEqual(text, again)
        self.assertIn('\n  "values"', text)


class ParamsInteropTest(unittest.TestCase):
    def test_config_values_build_reference_params(self):
        """A saved reference config reproduces ContainerParams.reference()."""
        cfg = config.build(sample_values(), "mm")
        params = ContainerParams.from_dict(cfg.values)
        self.assertEqual(params.to_dict(), ContainerParams.reference().to_dict())

    def test_reference_buildconfig_matches_sidecar_keys(self):
        built = BuildConfig(**{k: v for k, v in config.build(
            sample_values()).values.items()
            if k in BuildConfig.__dataclass_fields__})
        self.assertEqual(built.scale_divider, 87.0)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
