"""Workflow regressions using analytic geometry and explicit synthetic test doubles.

No checkpoint, Generator, Predictor, or TD3 neural network is executed here.
Scripted resistance values test selection logic only; they are not physical
predictions and must never be presented as a model-validation result.
"""

from __future__ import annotations

import contextlib
import csv
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from hullexplore import models, workflow
from hullexplore.contracts import Design, model_speed
from hullexplore.geometry import compute_volume


def synthetic_half_cloud(length=90.0, beam=15.6, depth=7.5):
    """Analytic wedge; it is a test solid, not a generated ship design."""
    x, z = np.meshgrid(np.linspace(0, length, 50), np.linspace(0, depth, 20))
    y = beam / 2 * x / length
    return np.stack((x, y, z), axis=-1).reshape(1000, 3)


def synthetic_request(**changes):
    request = {
        "mode": "optimize", "length": 90.0, "beam": 15.6, "depth": 7.5,
        "draft": 3.75, "displacement_volume": 90 * 15.6 * 3.75 / 2,
        "speed": 1.2, "speed_unit": "m/s", "speed_scale": "model",
        "target_resistance": 1.0, "max_episodes": 1, "seed": 42,
    }
    request.update(changes)
    return request


def synthetic_candidate(design, *, z=(0, 0, 0), resistance=10, condition=0.25,
                        raw_error=0, volume_error=0, episode=0, step=0, mesh_valid=True):
    points = synthetic_half_cloud(design.length, design.beam, design.depth).astype(np.float32)
    points[:, 1] *= 1 + volume_error
    return workflow.Candidate(
        z=np.asarray(z, dtype=np.float32).copy(), condition=condition,
        raw_actual=condition * (1 + raw_error), raw_error=raw_error, points=points,
        volume=design.displacement_volume * (1 + volume_error), volume_error=volume_error,
        geometry_loss=0, resistance=resistance, episode=episode, step=step,
        quality={"synthetic_mesh_acceptance": mesh_valid},
    )


def preview_test_double(points, directory, basename):
    """Write temporary marker files; the geometry integration test uses the real STL exporter."""
    paths = {kind: Path(directory) / f"{basename}.{kind}" for kind in ("png", "html")}
    for path in paths.values():
        path.write_text("Synthetic preview test double; not an image or model result.", encoding="utf-8")
    return {kind: str(path) for kind, path in paths.items()}


@contextlib.contextmanager
def in_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class FixedDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 20, 12, 0, tzinfo=tz)


class PointCloudContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "synthetic_half_hull.csv"
        self.points = synthetic_half_cloud()
        np.savetxt(self.path, self.points, delimiter=",", fmt="%.17g")
        self.original_bytes = self.path.read_bytes()

    def request(self, **changes):
        request = {"points": str(self.path), "speed": 1.2, "speed_unit": "m/s", "speed_scale": "model"}
        request.update(changes)
        return request

    def save_metadata(self, **changes):
        data = {"geometry_scale": "full", "point_cloud_sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
                "design": {"draft_ratio": 5.6 / 7.5}}
        data.update(changes)
        metadata = self.directory / "result.json"
        metadata.write_text(json.dumps(data), encoding="utf-8")
        return metadata

    def test_uniform_scaling_preserves_point_order_half_breadth_and_draft_ratio(self):
        # An unstructured input remains in its original order; no reconstruction is attempted.
        permutation = np.random.default_rng(7).permutation(1000)
        points = self.points[permutation]
        np.savetxt(self.path, points, delimiter=",", fmt="%.17g")
        before = self.path.read_bytes()
        model, ratio, speed, context = workflow.prediction_context(
            self.request(point_scale="full", draft=5.6, speed=20, speed_unit="kn", speed_scale="full"))
        np.testing.assert_array_equal(model, (points / 30).astype(np.float32))
        np.testing.assert_allclose(model.max(axis=0), [3, 0.26, 0.25], rtol=1e-6)
        self.assertAlmostEqual(ratio, 5.6 / 7.5)
        self.assertAlmostEqual(speed["model_speed_m_s"], (20 * 1852 / 3600) / math.sqrt(30))
        self.assertEqual(context["point_scale"], "full")
        self.assertAlmostEqual(context["coordinate_multiplier_to_model"], 1 / 30)
        self.assertEqual(self.path.read_bytes(), before)

    def test_matching_hash_reuses_only_missing_scale_and_draft_metadata(self):
        metadata = self.save_metadata()
        _, ratio, speed, context = workflow.prediction_context(self.request())
        self.assertAlmostEqual(ratio, 5.6 / 7.5)
        self.assertEqual(context["reused_design_metadata"], str(metadata))
        self.assertEqual(context["point_scale"], "full")
        self.assertEqual(speed["model_speed_m_s"], 1.2)
        self.assertEqual(context["source_sha256"], hashlib.sha256(self.original_bytes).hexdigest())
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        _, explicit, _, _ = workflow.prediction_context(self.request(draft=3.75))
        self.assertEqual(explicit, 0.5)
        _, explicit, _, _ = workflow.prediction_context(self.request(draft_ratio=0.6))
        self.assertEqual(explicit, 0.6)

    def test_changed_csv_cannot_silently_reuse_stale_draft_or_scale(self):
        self.save_metadata()
        # A byte change invalidates provenance even when the CSV remains numerically valid.
        self.path.write_bytes(self.original_bytes + b"\n")
        with self.assertRaisesRegex(ValueError, "point_scale"):
            workflow.prediction_context(self.request())
        with self.assertRaisesRegex(ValueError, "draft_ratio"):
            workflow.prediction_context(self.request(point_scale="full"))
        _, _, _, context = workflow.prediction_context(self.request(point_scale="full", draft_ratio=0.5))
        self.assertIsNone(context["reused_design_metadata"])

    def test_metadata_never_supplies_a_previous_operating_speed(self):
        self.save_metadata(speed={"model_speed_m_s": 1.2})
        with self.assertRaisesRegex(ValueError, "speed"):
            workflow.prediction_context(self.request(speed=None))

    def test_cloud_alone_does_not_establish_scale_or_operating_draft(self):
        for changes, message in (({}, "point_scale"), ({"point_scale": "full"}, "draft_ratio")):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                workflow.prediction_context(self.request(**changes))

    def test_model_csv_is_renormalized_to_exact_three_metres(self):
        points = self.points * (3.000387 / 90)
        np.savetxt(self.path, points, delimiter=",", fmt="%.17g")
        model, ratio, speed, context = workflow.prediction_context(
            self.request(point_scale="model", draft_ratio=0.5, full_length=90, speed=20, speed_unit="kn", speed_scale="full"))
        self.assertEqual(float(model[:, 0].max()), 3.0)
        np.testing.assert_allclose(model, self.points.astype(np.float32) / 30, atol=3e-7)
        self.assertEqual(ratio, 0.5)
        self.assertAlmostEqual(speed["model_speed_m_s"], (20 * 1852 / 3600) / math.sqrt(30))
        self.assertAlmostEqual(context["coordinate_multiplier_to_model"], 3 / 3.000387)

    def test_scale_mismatch_and_inconsistent_draft_are_rejected(self):
        requests = [self.request(point_scale="model", draft_ratio=0.5),
                    self.request(point_scale="full", full_length=80, draft_ratio=0.5),
                    self.request(point_scale="full", draft=5.6, draft_ratio=0.5),
                    self.request(point_scale="full", draft_ratio=1.1)]
        for request in requests:
            with self.subTest(request=request), self.assertRaises(ValueError):
                workflow.prediction_context(request)
        np.savetxt(self.path, self.points / 30, delimiter=",", fmt="%.17g")
        with self.assertRaisesRegex(ValueError, "reference length"):
            workflow.prediction_context(self.request(point_scale="model", draft_ratio=0.5, speed_scale="full"))
        with self.assertRaisesRegex(ValueError, "Draft ratio"):
            workflow.prediction_context(self.request(point_scale="model", draft=5.6))


class OutputReservationTests(unittest.TestCase):
    def test_next_case_uses_highest_same_day_suffix_not_directory_count(self):
        with tempfile.TemporaryDirectory() as folder, in_directory(folder), patch.object(workflow, "datetime", FixedDate):
            root = Path(folder)
            for name in ("DesignCase-20261020-1", "DesignCase-20261020-4", "DesignCase-20261020-19",
                         "DesignCase-20261019-999", "OPTDesignCase-20261020-999", "DesignCase-20261020-999-extra"):
                (root / name).mkdir()
            directory, basename, lock = workflow.reserve_output("generate")
            self.assertEqual(directory.name, "DesignCase-20261020-20")
            self.assertEqual(basename, "DesignCaseShip")
            self.assertTrue(lock.is_file())
            lock.unlink()
            second, _, second_lock = workflow.reserve_output("generate")
            self.assertEqual(second.name, "DesignCase-20261020-21")
            second_lock.unlink()

    def test_existing_file_and_active_lock_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            existing = directory / "result.json"
            existing.write_bytes(b"existing user result")
            with self.assertRaises(FileExistsError):
                workflow.reserve_output("generate", str(directory))
            self.assertEqual(existing.read_bytes(), b"existing user result")
            self.assertFalse((directory / ".hullexplore.lock").exists())
            existing.unlink()
            _, _, lock = workflow.reserve_output("generate", str(directory))
            with self.assertRaisesRegex(FileExistsError, "Another hull task"):
                workflow.reserve_output("generate", str(directory))
            self.assertTrue(lock.exists())
            lock.unlink()

    def test_automatic_reservation_skips_a_conflicting_file_name(self):
        with tempfile.TemporaryDirectory() as folder, in_directory(folder), patch.object(workflow, "datetime", FixedDate):
            conflict = Path(folder) / "PredictionCase-20261020-1"
            conflict.write_bytes(b"unrelated file")
            directory, basename, lock = workflow.reserve_output("predict")
            self.assertEqual(directory.name, "PredictionCase-20261020-2")
            self.assertEqual(basename, "ResistancePrediction")
            self.assertEqual(conflict.read_bytes(), b"unrelated file")
            lock.unlink()


class FinalArtifactTests(unittest.TestCase):
    def test_final_result_uses_saved_geometry_mass_and_strict_resistance_threshold(self):
        request = synthetic_request(target_resistance=11.25)
        design = Design.from_request(request)
        candidate = synthetic_candidate(design, resistance=11.25)
        recorded = []

        def synthetic_prediction(points, draft_ratio, speed):
            recorded.append((points.copy(), draft_ratio, speed))
            return 11.25  # Explicit test double; this is not a trained-model prediction.

        predictor = Mock(predict=Mock(side_effect=synthetic_prediction))
        speed_info = model_speed(1.2, "m/s", "model", design.length)
        with tempfile.TemporaryDirectory() as folder, patch.object(workflow, "preview", side_effect=preview_test_double):
            directory = Path(folder)
            result = workflow._design_result(candidate, design, request, directory, "SyntheticTestHull", predictor, speed_info)
            saved = np.loadtxt(result["artifacts"]["point_cloud"], delimiter=",")
            saved_model = np.loadtxt(result["artifacts"]["model_point_cloud"], delimiter=",", dtype=np.float32)
            self.assertEqual(len(recorded), 1)
            np.testing.assert_array_equal(saved, candidate.points.astype(np.float64))
            np.testing.assert_array_equal(recorded[0][0], saved_model)
            np.testing.assert_array_equal(saved_model, workflow.to_model_points(saved))
            np.testing.assert_array_equal(saved_model, workflow.to_model_points(candidate.points))
            self.assertEqual(recorded[0][1:], (design.draft_ratio, 1.2))
            self.assertAlmostEqual(result["actual_displacement_volume_m3"], compute_volume(saved, design.draft))
            self.assertAlmostEqual(result["actual_displacement_tonnes"], result["actual_displacement_volume_m3"] * 1025 / 1000)
            self.assertEqual(result["point_cloud_sha256"], workflow.file_sha256(Path(result["artifacts"]["point_cloud"])))
            self.assertTrue(result["mesh_quality"]["watertight"])
            self.assertEqual(result["mesh_quality"]["path"], result["artifacts"]["stl"])
            self.assertFalse(result["target_met"])
            self.assertEqual(result["target_operator"], "lt")
            self.assertEqual(result["status"], "target_not_met")
            self.assertEqual(result["candidate"]["model_total_resistance_N"], 11.25)
            self.assertEqual(result["final_prediction_consistency"]["absolute_difference_N"], 0.0)
            self.assertEqual(json.loads((directory / "result.json").read_text())["model_total_resistance_N"], 11.25)
            _, ratio, _, context = workflow.prediction_context({
                "points": result["artifacts"]["point_cloud"], "speed": 1.2, "speed_unit": "m/s", "speed_scale": "model"})
            self.assertEqual(ratio, design.draft_ratio)
            self.assertEqual(context["reused_design_metadata"], str(directory / "result.json"))

    def test_failed_final_volume_check_publishes_no_geometry(self):
        request = synthetic_request()
        design = Design.from_request(request)
        candidate = synthetic_candidate(design)
        candidate.points[:, 1] *= 0.5
        with tempfile.TemporaryDirectory() as folder, patch.object(workflow, "preview") as views:
            with self.assertRaisesRegex(ValueError, "physical displacement tolerance"):
                workflow._design_result(candidate, design, request, Path(folder), "SyntheticInvalidHull", None, None)
            self.assertEqual(list(Path(folder).iterdir()), [])
            views.assert_not_called()


    def test_repeated_prediction_drift_or_threshold_flip_prevents_publication(self):
        # The second case crosses the strict target while remaining inside the
        # numerical repeatability tolerance; it still must not claim success.
        cases = [(10.0, 11.0, 20.0), (10.0, 10.0 + 1e-7, 10.0 + 5e-8)]
        for searched, repeated, target in cases:
            request = synthetic_request(target_resistance=target)
            design = Design.from_request(request)
            candidate = synthetic_candidate(design, resistance=searched)
            predictor = Mock(predict=Mock(return_value=repeated))
            speed_info = model_speed(1.2, "m/s", "model", design.length)
            with self.subTest(case=(searched, repeated, target)), tempfile.TemporaryDirectory() as folder:
                with patch.object(workflow, "preview", side_effect=preview_test_double):
                    with self.assertRaisesRegex(RuntimeError, "Repeated Predictor inference"):
                        workflow._design_result(candidate, design, request, Path(folder), "SyntheticDriftTest", predictor, speed_info)
                self.assertEqual(list(Path(folder).iterdir()), [])


class CalibrationTests(unittest.TestCase):
    def test_failed_bracket_midpoint_is_not_repeated_and_a_new_feasible_point_is_found(self):
        design = Design.from_request(synthetic_request())
        conditions = []

        def synthetic_evaluation(generator, actual_design, z, condition, *, episode):
            conditions.append(condition)
            if math.isclose(condition, 0.3125, rel_tol=0, abs_tol=1e-12):
                raise ValueError("Synthetic geometry defect at one calibration condition.")
            # Analytic test response: desired volume occurs at condition=0.30.
            return synthetic_candidate(actual_design, z=z, condition=condition,
                                       volume_error=(condition - 0.30) / 0.30, episode=episode)

        with tempfile.TemporaryDirectory() as folder:
            history = workflow.History(Path(folder) / "synthetic_history.csv")
            try:
                with patch.object(workflow, "evaluate", side_effect=synthetic_evaluation):
                    candidate = workflow.calibrate(object(), design, np.zeros(3), history, episode=1, max_steps=10)
            finally:
                history.close()
        self.assertIsNotNone(candidate)
        self.assertLessEqual(abs(candidate.volume_error), design.volume_tolerance)
        self.assertLessEqual(len(conditions), 10)
        self.assertEqual(sum(math.isclose(q, 0.3125, rel_tol=0, abs_tol=1e-12) for q in conditions), 1)
        self.assertEqual(len(conditions), len(set(conditions)))

    def test_calibration_exception_budget_is_finite_and_does_not_fabricate_candidate(self):
        design = Design.from_request(synthetic_request())
        with tempfile.TemporaryDirectory() as folder:
            history = workflow.History(Path(folder) / "synthetic_history.csv")
            try:
                with patch.object(workflow, "evaluate", side_effect=ValueError("Synthetic invalid geometry")) as evaluate:
                    candidate = workflow.calibrate(object(), design, np.zeros(3), history, max_steps=4)
                self.assertIsNone(candidate)
                self.assertEqual(evaluate.call_count, 4)
                self.assertEqual(history.count, 4)
            finally:
                history.close()


class GenerationControlFlowTests(unittest.TestCase):
    def test_generation_with_prediction_retries_an_invalid_resistance_candidate(self):
        request = synthetic_request(mode="generate", max_attempts=2)
        request.pop("target_resistance")
        design = Design.from_request(request)
        first = synthetic_candidate(design, z=(0, 0, 0), resistance=None, episode=1)
        second = synthetic_candidate(design, z=(0.1, 0.2, 0.3), resistance=None, episode=2)
        # First candidate is geometrically valid but its scripted resistance is
        # rejected. The second candidate and its final repeat are both usable.
        predictor = Mock(predict=Mock(side_effect=[models.InvalidResistanceError("Synthetic invalid resistance"), 12.0, 12.0]))
        with tempfile.TemporaryDirectory() as folder, contextlib.ExitStack() as stack:
            request["output"] = folder
            stack.enter_context(patch.object(models, "select_device", return_value="synthetic test device"))
            stack.enter_context(patch.object(models, "Generator", return_value=object()))
            stack.enter_context(patch.object(models, "Predictor", return_value=predictor))
            actor = stack.enter_context(patch.object(models, "TD3Actor"))
            calibrate = stack.enter_context(patch.object(workflow, "calibrate", side_effect=[first, second]))
            stack.enter_context(patch.object(workflow, "preview", side_effect=preview_test_double))
            result, code = workflow.design_workflow(request)
            self.assertEqual(code, 0)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["model_total_resistance_N"], 12.0)
            self.assertEqual(result["candidate"]["episode"], 2)
            self.assertEqual(calibrate.call_count, 2)
            self.assertEqual(predictor.predict.call_count, 3)
            actor.assert_not_called()
            with (Path(folder) / "search_history.csv").open(newline="", encoding="utf-8") as handle:
                statuses = [row["status"] for row in csv.DictReader(handle)]
            self.assertIn("predictor_rejected", statuses)
            self.assertFalse((Path(folder) / "failure.json").exists())
            self.assertFalse((Path(folder) / ".hullexplore.lock").exists())


class RecordingActor:
    """Deterministic action source for control-flow tests, not a substitute TD3 policy."""
    episode_length = 5
    action_scale = 0.01
    z_min, z_max = -5.0, 5.0

    def __init__(self, action=(0.25, -0.5, 1.0)):
        self.output = np.asarray(action, dtype=np.float32)
        self.observations = []

    def action(self, observation):
        self.observations.append(observation.copy())
        return self.output.copy()


class SyntheticSearch:
    """Drive the real search orchestration with labelled, scripted evaluation results."""
    def __init__(self, initial_specs, step_specs, action=(0.25, -0.5, 1.0)):
        self.initial_specs = list(initial_specs)
        self.initial_iterator = iter(self.initial_specs)
        self.step_specs = step_specs
        self.actor = RecordingActor(action)
        self.selected = None
        self.calibrate = Mock(side_effect=self._calibrate)
        self.evaluate = Mock(side_effect=self._evaluate)
        valid_initial = [item["resistance"] for item in self.initial_specs
                         if item is not None and abs(item.get("raw_error", 0)) < 0.05]
        self.predictor = Mock(predict=Mock(side_effect=valid_initial))
        self.mesh = Mock(side_effect=self._mesh)
        self.export = Mock(side_effect=self._export)

    def _calibrate(self, generator, design, z, history, *, episode=0, require_raw=False):
        specification = next(self.initial_iterator)
        if specification is None:
            return None
        values = dict(specification)
        values.setdefault("z", z)
        return synthetic_candidate(design, episode=episode, **values)

    def _evaluate(self, generator, design, z, condition, predictor, speed, *, episode, step):
        specification = self.step_specs[episode][step - 1]
        if isinstance(specification, Exception):
            raise specification
        return synthetic_candidate(design, z=z, condition=condition, episode=episode, step=step, **specification)

    @staticmethod
    def _mesh(candidate, probe):
        if not candidate.quality["synthetic_mesh_acceptance"]:
            raise ValueError("Synthetic mesh rejection used only to test acceptance logic.")
        return candidate

    def _export(self, candidate, design, request, directory, basename, predictor, speed_info):
        self.selected = candidate
        met = candidate.resistance < request["target_resistance"]
        return {"status": "completed" if met else "target_not_met", "target_met": met,
                "target_operator": "lt", "candidate": candidate.summary(),
                "testing_only": "Synthetic search fixture; no trained model was executed."}

    def run(self, request):
        with contextlib.ExitStack() as stack:
            for name, value in (("select_device", Mock(return_value="synthetic test device")),
                                ("Generator", Mock(return_value=object())),
                                ("Predictor", Mock(return_value=self.predictor)),
                                ("TD3Actor", Mock(return_value=self.actor))):
                stack.enter_context(patch.object(models, name, value))
            for name, value in (("calibrate", self.calibrate), ("evaluate", self.evaluate),
                                ("check_mesh", self.mesh), ("_design_result", self.export)):
                stack.enter_context(patch.object(workflow, name, value))
            return workflow.design_workflow(request)


class OptimizationControlFlowTests(unittest.TestCase):
    def test_trained_actor_contract_is_eleven_observations_three_actions_five_steps(self):
        self.assertEqual(models.TD3Actor.observation_size, 11)
        self.assertEqual(models.TD3Actor.action_size, 3)
        self.assertEqual(models.TD3Actor.episode_length, 5)
        self.assertEqual(models.TD3Actor.action_scale, 0.01)
        self.assertEqual((models.TD3Actor.z_min, models.TD3Actor.z_max), (-5, 5))

    def test_observation_order_fixed_initial_resistance_and_action_bounds_match_training(self):
        script = SyntheticSearch(
            [{"resistance": 12, "condition": 0.23, "raw_error": 0.02, "z": (4.995, -4.995, 0.3)}],
            {1: [{"resistance": resistance, "raw_error": error} for resistance, error in
                 ((10, -0.02), (11, 0.01), (9, 0), (8, 0.02), (7, 0.04))]},
            action=(2, -2, 0.5),
        )
        with tempfile.TemporaryDirectory() as folder:
            result, code = script.run(synthetic_request(output=folder))
            self.assertEqual(code, 2)
            self.assertFalse(result["target_met"])
            self.assertEqual(len(script.actor.observations), 5)
            observations = np.asarray(script.actor.observations)
            self.assertEqual(observations.shape, (5, 11))
            self.assertEqual(observations.dtype, np.float32)
            np.testing.assert_allclose(observations[:, 3:8], np.tile([15.6 / 90, 7.5 / 90, 0.5, 0.23, 1.2], (5, 1)), rtol=1e-6)
            np.testing.assert_allclose(observations[:, 8], np.array([12, 10, 11, 9, 8]) / 12, rtol=1e-6)
            np.testing.assert_allclose(observations[:, 9], [0.02, -0.02, 0.01, 0, 0.02], rtol=1e-6)
            np.testing.assert_allclose(observations[:, 10], [1, 0.8, 0.6, 0.4, 0.2], rtol=1e-6)
            np.testing.assert_allclose(observations[0, :3], [4.995, -4.995, 0.3], rtol=1e-6)
            np.testing.assert_allclose(observations[1, :3], [5, -5, 0.305], rtol=1e-6)
            self.assertEqual(script.evaluate.call_count, 5)
            self.assertTrue(all(abs(call.args[3] - 0.23) < 1e-9 for call in script.evaluate.call_args_list))
            np.testing.assert_allclose(script.selected.z, [5, -5, 0.325], atol=1e-6)
            self.assertEqual(script.selected.step, 5)
            first_points, ratio, speed = script.predictor.predict.call_args.args
            self.assertEqual(float(first_points[:, 0].max()), 3.0)
            self.assertEqual((ratio, speed), (0.5, 1.2))

    def test_equal_threshold_does_not_stop_search_and_strictly_lower_value_does(self):
        script = SyntheticSearch([{"resistance": 10}], {1: [{"resistance": 5}, {"resistance": 4.9}]})
        with tempfile.TemporaryDirectory() as folder:
            result, code = script.run(synthetic_request(output=folder, target_resistance=5))
            self.assertEqual(code, 0)
            self.assertTrue(result["target_met"])
            self.assertEqual(script.evaluate.call_count, 2)
            self.assertEqual(script.selected.resistance, 4.9)
            self.assertEqual(script.selected.step, 2)

    def test_failed_target_returns_lowest_feasible_candidate_across_all_episodes(self):
        script = SyntheticSearch(
            [{"resistance": 9}, {"resistance": 10}],
            {1: [{"resistance": 8}, {"resistance": 2, "volume_error": 0.051},
                 {"resistance": 3, "raw_error": 0.051}, {"resistance": 4, "mesh_valid": False}, {"resistance": 7}],
             2: [{"resistance": 6}, {"resistance": 1, "volume_error": -0.051},
                 {"resistance": 1.5, "mesh_valid": False}, {"resistance": 6.5}, {"resistance": 8}]},
        )
        with tempfile.TemporaryDirectory() as folder:
            result, code = script.run(synthetic_request(output=folder, max_episodes=2, target_resistance=0.5))
            self.assertEqual(code, 2)
            self.assertEqual(result["status"], "target_not_met")
            self.assertFalse(result["target_met"])
            self.assertEqual((script.selected.episode, script.selected.step, script.selected.resistance), (2, 1, 6))
            self.assertEqual(script.calibrate.call_count, 2)
            self.assertEqual(script.evaluate.call_count, 10)
            with (Path(folder) / "search_history.csv").open(newline="", encoding="utf-8") as handle:
                records = list(csv.DictReader(handle))
            self.assertEqual(sum(row["status"] == "mesh_rejected" for row in records), 2)
            accepted = [float(row["resistance_N"]) for row in records if row["status"] == "best_feasible"]
            self.assertEqual(accepted, [9, 8, 7, 6])
            self.assertFalse((Path(folder) / ".hullexplore.lock").exists())

    def test_initial_raw_gate_is_strict_but_feasible_rollout_gate_includes_boundary(self):
        script = SyntheticSearch(
            [{"resistance": 1, "raw_error": 0.05}, {"resistance": 10, "raw_error": 0.049}],
            {1: [{"resistance": r, "raw_error": 0.05} for r in (9, 8, 7, 6, 5)]},
        )
        with tempfile.TemporaryDirectory() as folder:
            _, code = script.run(synthetic_request(output=folder))
            self.assertEqual(code, 2)
            self.assertEqual(script.calibrate.call_count, 2)
            self.assertEqual(script.predictor.predict.call_count, 1)
            self.assertEqual(script.selected.resistance, 5)
            self.assertEqual(script.selected.raw_error, 0.05)

    def test_no_feasible_candidate_fails_without_claiming_or_exporting_a_hull(self):
        script = SyntheticSearch([{"resistance": 10, "volume_error": 0.06}],
                                 {1: [{"resistance": r, "volume_error": 0.06} for r in (9, 8, 7, 6, 5)]})
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "No valid design"):
                script.run(synthetic_request(output=folder))
            script.export.assert_not_called()
            self.assertEqual(script.evaluate.call_count, 5)
            self.assertEqual(json.loads((Path(folder) / "failure.json").read_text())["status"], "failed")
            self.assertFalse((Path(folder) / "result.json").exists())
            self.assertFalse((Path(folder) / ".hullexplore.lock").exists())
            self.assertEqual(list(Path(folder).glob("*.stl")), [])

    def test_failed_initialization_is_bounded_by_twenty_attempts_per_episode(self):
        script = SyntheticSearch([None] * 40, {})
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "within the search budget"):
                script.run(synthetic_request(output=folder, max_episodes=2))
            self.assertEqual(script.calibrate.call_count, 40)
            self.assertEqual(script.actor.observations, [])
            script.predictor.predict.assert_not_called()
            script.export.assert_not_called()

    def test_three_invalid_steps_hold_state_and_stop_the_episode(self):
        script = SyntheticSearch([{"resistance": 10, "z": (0.1, 0.2, 0.3)}],
                                 {1: [models.InvalidResistanceError("Synthetic invalid predictor result")] * 3})
        with tempfile.TemporaryDirectory() as folder:
            _, code = script.run(synthetic_request(output=folder))
            self.assertEqual(code, 2)
            self.assertEqual(script.evaluate.call_count, 3)
            observations = np.asarray(script.actor.observations)
            np.testing.assert_allclose(observations[:, :3], np.tile([0.1, 0.2, 0.3], (3, 1)), atol=1e-7)
            np.testing.assert_array_equal(observations[:, 8], [1, 1, 1])
            np.testing.assert_allclose(observations[:, 10], [1, 0.8, 0.6], rtol=1e-6)
            self.assertEqual((script.selected.step, script.selected.resistance), (0, 10))


    def test_hard_evaluation_failure_ends_episode_immediately(self):
        for error in (ValueError("Synthetic malformed geometry"),
                      RuntimeError("Synthetic execution failure"),
                      FloatingPointError("Synthetic nonfinite geometry")):
            script = SyntheticSearch([{"resistance": 10}], {1: [error]})
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as folder:
                _, code = script.run(synthetic_request(output=folder))
                self.assertEqual(code, 2)
                self.assertEqual(script.evaluate.call_count, 1)
                self.assertEqual(len(script.actor.observations), 1)
                self.assertEqual((script.selected.step, script.selected.resistance), (0, 10))


if __name__ == "__main__":
    unittest.main()
