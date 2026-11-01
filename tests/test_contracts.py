"""Physical contracts and request parsing; no trained model is loaded or run."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from hullexplore.contracts import Design, domain_warnings, model_speed, positive
from hullexplore.cli import dry_run, read_request


def example_request(**changes):
    """User-specified dimensions, used only for arithmetic contract tests."""
    request = {
        "mode": "generate", "length": 90.0, "beam": 15.6, "depth": 7.5,
        "draft": 5.6, "displacement_tonnes": 5000.0,
    }
    request.update(changes)
    return request


class PhysicalContractTests(unittest.TestCase):
    def test_metric_tonnes_and_density_produce_volume_in_cubic_metres(self):
        design = Design.from_request(example_request())
        self.assertEqual(design.density, 1025.0)
        self.assertAlmostEqual(design.displacement_volume, 4_878.048780487805)
        self.assertAlmostEqual(design.to_dict()["displacement_tonnes"], 5000.0)
        fresh_water = Design.from_request(example_request(density=1000.0))
        self.assertAlmostEqual(fresh_water.displacement_volume, 5000.0)
        self.assertEqual(fresh_water.to_dict()["density"], 1000.0)

    def test_conventional_block_coefficient_uses_draft_not_depth(self):
        design = Design.from_request(example_request())
        self.assertAlmostEqual(design.block_coefficient, design.displacement_volume / (90 * 15.6 * 5.6))
        self.assertAlmostEqual(design.physical_volume_ratio, design.displacement_volume / (90 * 15.6 * 7.5))
        self.assertAlmostEqual(design.physical_volume_ratio, design.block_coefficient * design.draft_ratio)
        self.assertGreater(design.block_coefficient, design.physical_volume_ratio)
        self.assertAlmostEqual(design.to_dict()["length_scale_ratio_full_to_model"], 30.0)

    def test_three_displacement_representations_are_equivalent(self):
        mass_request = example_request()
        expected = Design.from_request(mass_request)
        volume_request = example_request(displacement_tonnes=None, displacement_volume=expected.displacement_volume)
        coefficient_request = example_request(displacement_tonnes=None, block_coefficient=expected.block_coefficient)
        for request in (volume_request, coefficient_request):
            with self.subTest(request=request):
                actual = Design.from_request(request)
                self.assertAlmostEqual(actual.displacement_volume, expected.displacement_volume)
                self.assertAlmostEqual(actual.to_dict()["displacement_tonnes"], 5000.0)

    def test_volume_input_is_not_divided_by_density_a_second_time(self):
        design = Design.from_request(example_request(displacement_tonnes=None, displacement_volume=4500, density=1000))
        self.assertEqual(design.displacement_volume, 4500.0)
        self.assertEqual(design.to_dict()["displacement_tonnes"], 4500.0)

    def test_inconsistent_or_impossible_designs_are_rejected(self):
        cases = [
            {"displacement_tonnes": None},
            {"displacement_volume": 4000},
            {"block_coefficient": 0.6},
            {"draft": 7.6},
            {"depth": 0},
            {"beam": True},
            {"length": float("inf")},
            {"density": float("nan")},
            {"displacement_tonnes": None, "block_coefficient": 1.0},
            {"displacement_tonnes": None, "displacement_volume": 90 * 15.6 * 5.6},
            {"volume_tolerance": 0},
            {"volume_tolerance": 1},
        ]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                Design.from_request(example_request(**change))

    def test_nonpositive_nonfinite_and_boolean_numbers_are_rejected(self):
        for value in (None, True, False, 0, -1, "", "not numeric", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                positive(value, "test_quantity")
        self.assertEqual(positive("3.25", "test_quantity"), 3.25)

    def test_full_scale_speed_conversion_preserves_froude_number(self):
        speed_knots = 20.0
        result = model_speed(speed_knots, "kn", "full", 90.0)
        full_speed = speed_knots * 1852 / 3600
        self.assertAlmostEqual(result["model_speed_m_s"], full_speed / math.sqrt(30))
        self.assertAlmostEqual(full_speed / math.sqrt(9.81 * 90), result["model_speed_m_s"] / math.sqrt(9.81 * 3))
        self.assertEqual(result["length_scale_ratio_full_to_model"], 30.0)
        self.assertEqual(result["conversion"], "Froude similarity")

    def test_speed_units_and_scale_are_separate_contracts(self):
        for quantity, unit in ((10.0, "m/s"), (36.0, "km/h"), (10.0 * 3600 / 1852, "kn")):
            with self.subTest(unit=unit):
                self.assertAlmostEqual(model_speed(quantity, unit, "full", 90)["model_speed_m_s"], 10 / math.sqrt(30))
                self.assertAlmostEqual(model_speed(quantity, unit, "model", None)["model_speed_m_s"], 10)
        # Providing the reference length never rescales an explicitly model-scale speed.
        self.assertEqual(model_speed(1.2, "m/s", "model", 90)["model_speed_m_s"], 1.2)
        self.assertEqual(model_speed(1.2, "m/s", "model", 90)["conversion"], "unit conversion only")

    def test_ambiguous_speed_and_missing_reference_length_are_rejected(self):
        cases = [(1, None, "model", None), (1, "m/s", None, 90),
                 (1, "m/s", "full", None), (1, "knots", "full", 90),
                 (0, "m/s", "model", None), (1, "m/s", "full", 0)]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                model_speed(*args)

    def test_out_of_domain_conditions_are_reported_without_changing_design(self):
        design = Design.from_request(example_request())
        before = design.to_dict()
        messages = domain_warnings(design, 2.0, 0.6)
        self.assertEqual(len(messages), 3)
        self.assertTrue(any("T/D" in message for message in messages))
        self.assertTrue(any("model speed" in message for message in messages))
        self.assertTrue(any("raw-volume condition" in message for message in messages))
        self.assertEqual(before, design.to_dict())
        nominal = Design.from_request(example_request(draft=3.75, displacement_tonnes=3000))
        self.assertEqual(domain_warnings(nominal, 0.6, 0.1), [])
        self.assertEqual(domain_warnings(nominal, 1.8, 0.5), [])


class RequestContractTests(unittest.TestCase):
    def test_dry_run_states_model_geometry_and_strict_threshold_without_writing(self):
        request = example_request(mode="optimize", speed=20, speed_unit="kn", speed_scale="full", target_resistance=15)
        result = dry_run(request)
        self.assertEqual(result["model_geometry_m"]["length"], 3.0)
        self.assertAlmostEqual(result["model_geometry_m"]["beam"], 0.52)
        self.assertAlmostEqual(result["model_geometry_m"]["depth"], 0.25)
        self.assertAlmostEqual(result["model_geometry_m"]["draft"], 5.6 / 30)
        self.assertEqual(result["target_operator"], "lt")
        self.assertFalse(result["files_written"])
        self.assertFalse(result["models_loaded"])

    def test_json_values_survive_defaults_and_explicit_cli_values_override_them(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "request.json"
            path.write_text(json.dumps(example_request(density=1000, volume_tolerance=0.02, seed=7)), encoding="utf-8")
            request, debug = read_request(["generate", "--request", str(path), "--seed", "9", "--dry-run"])
            self.assertEqual(request["density"], 1000)
            self.assertEqual(request["volume_tolerance"], 0.02)
            self.assertEqual(request["seed"], 9)
            self.assertTrue(request["dry_run"])
            self.assertFalse(debug)

    def test_partial_speed_unknown_fields_and_nonintegral_budgets_are_rejected(self):
        for changes in ({"speed": 12}, {"speed_scale": "full"}, {"unknown_input": 1},
                        {"max_episodes": 1.5}, {"seed": True}, {"max_attempts": 0}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "request.json"
                path.write_text(json.dumps(example_request(**changes)), encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_request(["generate", "--request", str(path)])


if __name__ == "__main__":
    unittest.main()
