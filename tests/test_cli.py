"""Validate the public CLI contract without loading any model or creating a case."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from hullexplore.cli import main, read_request


class CliTests(unittest.TestCase):
    def request(self):
        return {"length": 90, "beam": 15.6, "depth": 7.5, "draft": 3.75,
                "displacement_tonnes": 3000}

    def call(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_design_dry_run_has_no_model_or_filesystem_side_effects(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "request.json"
            output = Path(folder) / "must-not-exist"
            source.write_text(json.dumps({**self.request(), "output": str(output),
                                         "speed": 18, "speed_unit": "kn", "speed_scale": "full"}))
            with patch("hullexplore.models.select_device", side_effect=AssertionError("Models must not be loaded")):
                code, stdout, stderr = self.call(["generate", "--request", str(source), "--dry-run"])
            self.assertEqual(code, 0, stderr)
            result = json.loads(stdout)
            self.assertFalse(result["models_loaded"])
            self.assertFalse(result["files_written"])
            self.assertFalse(output.exists())
            self.assertAlmostEqual(result["speed"]["model_speed_m_s"], 1.690636960832613)

    @unittest.skipIf(os.name == "nt", "Windows paths are native on Windows")
    def test_windows_destination_is_not_silently_treated_as_a_linux_relative_path(self):
        from hullexplore.contracts import resolved_path
        with self.assertRaisesRegex(ValueError, "Windows drive or UNC path"):
            resolved_path(r"C:\Users\User\Desktop\ship")

    def test_cli_override_json_and_json_mode_without_subcommand(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "request.json"
            source.write_text(json.dumps({"mode": "generate", **self.request(), "seed": 7}))
            request, debug = read_request(["--request", str(source), "--seed", "12", "--dry-run"])
            self.assertEqual(request["mode"], "generate")
            self.assertEqual(request["seed"], 12)
            self.assertFalse(debug)

    def test_relative_json_cloud_uses_json_folder_not_invocation_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "request.json"
            source.write_text(json.dumps({"points": "half hull.csv", "output": "my-output"}))
            request, _ = read_request(["predict", "--request", str(source)])
            self.assertEqual(request["points"], str(Path(folder) / "half hull.csv"))
            self.assertEqual(request["output"], "my-output")
            override, _ = read_request(["predict", "--request", str(source), "--points", "override.csv"])
            self.assertEqual(override["points"], "override.csv")

    def test_json_typographical_and_type_errors_are_rejected(self):
        bad = [{"density_kg_m3": 1025}, {"dry_run": "false"}, {"length": True},
               {"seed": 2.5}, {"speed_unit": "knots"}, {"output": ["a"]},
               {"mode": "predict"}, {"request": "nested.json"}]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "request.json"
            for extra in bad:
                with self.subTest(extra=extra):
                    source.write_text(json.dumps({**self.request(), **extra}))
                    with self.assertRaises((ValueError, TypeError)):
                        read_request(["generate", "--request", str(source)])

    def test_missing_speed_scale_and_duplicate_displacement_are_rejected(self):
        base = ["generate", "--length", "90", "--beam", "15.6", "--depth", "7.5",
                "--draft", "3.75", "--displacement-tonnes", "3000"]
        for extra in (["--speed", "1.2", "--speed-unit", "m/s"],
                      ["--displacement-volume", "2926"]):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                read_request(base + extra)

    def test_validate_dry_run_still_reads_and_validates_cloud(self):
        source = ROOT / "vendor/Predictor/Branchmark/ship1.csv"
        code, out, err = self.call(["validate", "--points", str(source), "--dry-run"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["shape"], [1000, 3])
        with tempfile.TemporaryDirectory() as folder:
            invalid = Path(folder) / "invalid.csv"
            invalid.write_text("x,y,z\n1,2,3\n")
            code, out, err = self.call(["validate", "--points", str(invalid), "--dry-run"])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(err)["status"], "error")

    def test_prediction_dry_run_requires_operating_draft_and_explicit_scale(self):
        source = ROOT / "vendor/Predictor/Branchmark/ship1.csv"
        base = ["predict", "--points", str(source), "--speed", ".8", "--speed-unit", "m/s", "--dry-run"]
        for extra in ([], ["--speed-scale", "model"], ["--speed-scale", "model", "--point-scale", "model"]):
            code, out, err = self.call(base + extra)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(err)["status"], "error")
        code, out, err = self.call(base + ["--speed-scale", "model", "--point-scale", "model", "--draft-ratio", ".495283019"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["model_xmax_m"], 3.0)


if __name__ == "__main__":
    unittest.main()
