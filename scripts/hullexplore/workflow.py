"""Bounded design searches, final-geometry checks and non-destructive exports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

import numpy as np

from .contracts import Design, domain_warnings, model_speed, positive, resolved_path
from .geometry import compute_volume, export_stl, points_from_grid, preview, validate_half_cloud


def save_json(path: Path, value: dict):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def to_model_points(points: np.ndarray) -> np.ndarray:
    result = np.asarray(points, dtype=np.float64) * (3.0 / float(np.max(points[:, 0])))
    return result.astype(np.float32)


def reserve_output(mode: str, requested: str | None = None) -> tuple[Path, str, Path]:
    prefix, basename = {"generate": ("DesignCase", "DesignCaseShip"),
                        "optimize": ("OPTDesignCase", "OPTDesignCaseShip"),
                        "predict": ("PredictionCase", "ResistancePrediction")}[mode]
    if requested:
        directory = resolved_path(requested)
        directory.mkdir(parents=True, exist_ok=True)
    else:
        parent = Path.cwd()
        stamp = datetime.now().strftime("%Y%m%d")
        pattern = re.compile(re.escape(f"{prefix}-{stamp}-") + r"(\d+)$")
        numbers = [int(match.group(1)) for p in parent.iterdir()
                   if p.is_dir() and (match := pattern.fullmatch(p.name))]
        number = max(numbers, default=0) + 1
        while True:
            directory = parent / f"{prefix}-{stamp}-{number}"
            try:
                directory.mkdir()
                break
            except FileExistsError:
                number += 1
    reserved = ["request.json", "result.json", "failure.json", "search_history.csv",
                f"{basename}.csv", f"{basename}.stl", f"{basename}.png", f"{basename}.html",
                f"{basename}_model_3m.csv"]
    collisions = [name for name in reserved if (directory / name).exists()]
    if collisions:
        raise FileExistsError(f"Output files already exist in {directory}: {', '.join(collisions)}. Choose another output directory.")
    lock = directory / ".hullexplore.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    except FileExistsError as exc:
        raise FileExistsError(f"Another hull task is using {directory}; choose a different folder.") from exc
    # Recheck after acquiring the lock to close the concurrent-writer race.
    if any((directory / name).exists() for name in reserved):
        lock.unlink(missing_ok=True)
        raise FileExistsError(f"Output files appeared in {directory}; choose another output directory.")
    return directory.resolve(), basename, lock


@dataclass
class Candidate:
    z: np.ndarray
    condition: float
    raw_actual: float
    raw_error: float
    points: np.ndarray
    volume: float
    volume_error: float
    geometry_loss: float
    resistance: float | None = None
    episode: int = 0
    step: int = 0
    quality: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {"latent_z": [float(x) for x in self.z],
                "generator_condition_delta": self.condition,
                "raw_volume_actual": self.raw_actual,
                "raw_volume_relative_error": self.raw_error,
                "physical_displacement_volume_m3": self.volume,
                "physical_volume_relative_error": self.volume_error,
                "geometry_loss": self.geometry_loss,
                "model_total_resistance_N": self.resistance,
                "episode": self.episode, "step": self.step}


class History:
    columns = ["evaluation", "episode", "step", "z1", "z2", "z3", "condition_delta",
               "raw_actual", "raw_error", "physical_volume_m3", "physical_volume_error",
               "resistance_N", "status", "detail"]

    def __init__(self, path: Path):
        self.handle = path.open("w", encoding="utf-8", newline="")
        self.writer = csv.DictWriter(self.handle, fieldnames=self.columns)
        self.writer.writeheader()
        self.count = 0

    def write(self, candidate=None, *, status="evaluated", detail="", episode=0, step=0):
        self.count += 1
        row = {"evaluation": self.count, "episode": episode, "step": step, "status": status, "detail": detail}
        if candidate is not None:
            c = candidate
            row.update({"episode": c.episode, "step": c.step,
                        "z1": float(c.z[0]), "z2": float(c.z[1]), "z3": float(c.z[2]),
                        "condition_delta": c.condition, "raw_actual": c.raw_actual,
                        "raw_error": c.raw_error, "physical_volume_m3": c.volume,
                        "physical_volume_error": c.volume_error, "resistance_N": c.resistance})
        self.writer.writerow(row)
        self.handle.flush()

    def close(self):
        self.handle.close()


def evaluate(generator, design, z, condition, predictor=None, speed=None, episode=0, step=0):
    generated = generator.evaluate(z, design.draft_ratio, condition, design.length, design.beam, design.depth)
    grid = generated.normalized_grid
    points = points_from_grid(grid[0], grid[1], design.length, design.beam, design.depth).astype(np.float32)
    volume = float(compute_volume(points, design.draft))
    raw = float(generated.actual_cb)
    components = generated.geometry_components
    weights = {"x_mono": 5, "range": 1, "x0": 10, "y0": 10, "line_smooth": 2, "z_smooth": 2, "z_osc": 1}
    loss = sum(float(v) * weights.get(k, 1) for k, v in components.items())
    if not all(math.isfinite(v) for v in (volume, raw, loss)) or volume <= 0:
        raise ValueError("Generated hull has invalid geometric measurements.")
    c = Candidate(np.asarray(z, dtype=np.float32).copy(), float(condition), raw,
                  (raw - condition) / condition, points, volume,
                  (volume - design.displacement_volume) / design.displacement_volume,
                  loss, episode=episode, step=step)
    if predictor is not None:
        c.resistance = predictor.predict(to_model_points(points), design.draft_ratio, speed)
    return c


def volume_feasible(candidate: Candidate, design: Design, require_raw=False) -> bool:
    return abs(candidate.volume_error) <= design.volume_tolerance and (
        not require_raw or abs(candidate.raw_error) <= 0.05)


def calibrate(generator, design, z, history, episode=0, require_raw=False, max_steps=12):
    """Calibrate the decoder's RAW volume condition against dimensioned geometry.

    The learned decoder and its condition semantics remain unchanged. The
    independent physical volume check corrects the legacy exporter normalization
    mismatch. Search both sides and use a bracket when available; do not assume
    the learned response is globally monotonic.
    """
    lo, hi = 0.001, min(0.999, design.draft_ratio * 0.999)
    desired = float(np.clip(design.physical_volume_ratio, lo, hi))
    queue = [desired, desired * 0.5, desired * 1.5, hi * 0.02, hi, hi * 0.25, hi * 0.75]
    tried = []
    visited = []
    best = None
    for _ in range(max_steps):
        bracket = None
        ordered = sorted(tried, key=lambda c: c.condition)
        for a, b in zip(ordered, ordered[1:]):
            if a.volume_error * b.volume_error < 0:
                if bracket is None or b.condition - a.condition < bracket[1].condition - bracket[0].condition:
                    bracket = (a, b)
        q = None
        if bracket:
            left, right = bracket[0].condition, bracket[1].condition
            # A geometrically invalid midpoint must not consume the remaining
            # budget by being retried. Probe unused dyadic interior points.
            for level in range(1, 6):
                for numerator in range(1, 2**level, 2):
                    proposed = left + (right - left) * numerator / 2**level
                    if not any(abs(proposed - old) < 1e-7 for old in visited):
                        q = proposed
                        break
                if q is not None:
                    break
        while q is None and queue:
            proposed = float(np.clip(queue.pop(0), lo, hi))
            if not any(abs(proposed - old) < 1e-7 for old in visited):
                q = proposed
        if q is None:
            break
        visited.append(q)
        try:
            c = evaluate(generator, design, z, q, episode=episode)
        except (ValueError, RuntimeError, FloatingPointError) as exc:
            history.write(status="invalid_geometry", detail=str(exc), episode=episode)
            continue
        history.write(c, status="condition_calibration")
        tried.append(c)
        score = abs(c.volume_error) + (max(0, abs(c.raw_error) - 0.05) if require_raw else 0)
        best_score = math.inf if best is None else abs(best.volume_error) + (max(0, abs(best.raw_error) - 0.05) if require_raw else 0)
        if score < best_score:
            best = c
        if volume_feasible(c, design, require_raw=require_raw):
            return c
    return best


def check_mesh(candidate, probe: Path):
    candidate.quality = export_stl(candidate.points, probe)
    return candidate


def _design_result(candidate, design, request, directory, basename, predictor, speed_info):
    # Build and validate every artifact in task-owned staging before publishing.
    with tempfile.TemporaryDirectory(prefix=".hull-export-", dir=directory) as temporary:
        stage = Path(temporary)
        pc_path = stage / f"{basename}.csv"
        # Seventeen significant digits round-trip the exact float64 value of
        # each generated float32 coordinate. Search and final CSV inference then
        # normalize identical coordinates, including near rounding boundaries.
        np.savetxt(pc_path, candidate.points, delimiter=",", fmt="%.17g")
        points = validate_half_cloud(pc_path)
        actual = float(compute_volume(points, design.draft))
        error = (actual - design.displacement_volume) / design.displacement_volume
        if abs(error) > design.volume_tolerance:
            raise ValueError("Exported CSV failed the physical displacement tolerance.")
        quality = export_stl(points, stage / f"{basename}.stl")
        views = preview(points, stage, basename)
        artifacts = {"point_cloud": str(directory / pc_path.name),
                     "stl": str(directory / f"{basename}.stl"),
                     "preview_png": str(directory / Path(views["png"]).name),
                     "preview_html": str(directory / Path(views["html"]).name)}
        resistance = None
        consistency = None
        if predictor is not None:
            model_points = to_model_points(points)
            model_path = stage / f"{basename}_model_3m.csv"
            np.savetxt(model_path, model_points, delimiter=",", fmt="%.10g")
            # Re-read exactly the persisted model geometry before final inference.
            resistance = predictor.predict(np.loadtxt(model_path, delimiter=",", dtype=np.float32),
                                           design.draft_ratio, speed_info["model_speed_m_s"])
            if candidate.resistance is not None:
                consistency = {"search_resistance_N": candidate.resistance, "repeated_resistance_N": resistance,
                               "absolute_difference_N": abs(resistance - candidate.resistance)}
                if not math.isclose(resistance, candidate.resistance, rel_tol=1e-5, abs_tol=1e-5):
                    raise RuntimeError("Repeated Predictor inference changed materially for the exported geometry; candidate ranking cannot be verified. See search_history.csv and check runtime determinism.")
                threshold = request.get("target_resistance")
                if threshold is not None and (candidate.resistance < threshold) != (resistance < threshold):
                    raise RuntimeError("Repeated Predictor inference crossed the strict resistance threshold. Target satisfaction cannot be verified; no successful design is claimed.")
            artifacts["model_point_cloud"] = str(directory / model_path.name)
        target = request.get("target_resistance")
        target_met = None if target is None else resistance < float(target)
        status = "target_not_met" if target_met is False else "completed"
        warnings = domain_warnings(design, None if speed_info is None else speed_info["model_speed_m_s"],
                                   candidate.condition) if request["mode"] == "optimize" else []
        result = {
            "schema_version": 1, "status": status, "mode": request["mode"],
            "created_at": datetime.now().astimezone().isoformat(),
            "output_directory": str(directory), "geometry_scale": "full", "geometry_units": "m",
            "point_cloud_format": "headerless CSV; 1000 x 3 XYZ; half hull; 20 x 50 original grid",
            "design": design.to_dict(), "candidate": candidate.summary(),
            "actual_displacement_volume_m3": actual,
            "actual_displacement_tonnes": actual * design.density / 1000,
            "physical_volume_relative_error": error,
            "volume_method": "piecewise-linear waterline-area integration up to the specified draft",
            "density_assumption": "Use the requested density, or 1025 kg/m^3 when omitted.",
            "speed": speed_info, "model_total_resistance_N": resistance,
            "final_prediction_consistency": consistency,
            "resistance_scale": "L=3 m model" if resistance is not None else None,
            "target_resistance_N": target, "target_operator": "lt" if target is not None else None,
            "target_met": target_met,
            "selection": "lowest valid resistance found during this search" if target_met is False else
                         "first feasible target-reaching candidate" if target_met else "first physically feasible generated hull",
            "warnings": warnings,
            "mesh_quality": {**quality, "path": artifacts["stl"]}, "artifacts": artifacts,
            "point_cloud_sha256": file_sha256(pc_path),
            "seed": request.get("seed", 42),
            "limitations": ["Predicted resistance is a model estimate, not a CFD or towing-tank measurement.",
                            "No full-scale total-resistance extrapolation is performed.",
                            "Mesh edge closure and orientation are checked; general self-intersection testing is not performed."],
        }
        result["candidate"]["model_total_resistance_N"] = resistance
        save_json(stage / "result.json", result)
        for path in stage.iterdir():
            destination = directory / path.name
            if destination.exists():
                raise FileExistsError(f"Refusing to overwrite {destination}")
        for path in stage.iterdir():
            os.replace(path, directory / path.name)
        return result


def design_workflow(request: dict) -> tuple[dict, int]:
    from .models import Generator, InvalidResistanceError, Predictor, TD3Actor, select_device
    design = Design.from_request(request)
    optimizing = request["mode"] == "optimize"
    need_predictor = optimizing or request.get("speed") is not None
    speed_info = model_speed(request.get("speed"), request.get("speed_unit"), request.get("speed_scale"),
                             design.length) if need_predictor else None
    device = select_device(request.get("device", "auto"), require_gpu=need_predictor)
    generator = Generator(device)
    predictor = Predictor(device) if need_predictor else None
    actor = TD3Actor(device) if optimizing else None
    rng = np.random.default_rng(request.get("seed", 42))
    directory, basename, lock = reserve_output(request["mode"], request.get("output"))
    history = None
    best = None
    try:
        save_json(directory / "request.json", request)
        history = History(directory / "search_history.csv")
        with tempfile.TemporaryDirectory(prefix=".mesh-check-", dir=directory) as temporary:
            probe = Path(temporary) / "candidate.stl"
            if not optimizing:
                for attempt in range(1, request.get("max_attempts", 200) + 1):
                    z = np.clip(rng.normal(size=3), -5, 5).astype(np.float32)
                    c = calibrate(generator, design, z, history, episode=attempt)
                    if c is None or not volume_feasible(c, design):
                        continue
                    try:
                        check_mesh(c, probe)
                    except ValueError as exc:
                        history.write(c, status="mesh_rejected", detail=str(exc))
                        continue
                    if predictor is not None:
                        try:
                            c.resistance = predictor.predict(to_model_points(c.points), design.draft_ratio,
                                                             speed_info["model_speed_m_s"])
                        except (ValueError, FloatingPointError) as exc:
                            history.write(c, status="predictor_rejected", detail=str(exc))
                            continue
                    best = c
                    history.write(c, status="selected")
                    break
            else:
                target = positive(request.get("target_resistance"), "target_resistance")
                speed = speed_info["model_speed_m_s"]
                found = False
                for episode in range(1, request.get("max_episodes", 100) + 1):
                    current = None
                    # Preserve the trained strict raw-volume initialization gate.
                    for _ in range(20):
                        z = np.clip(rng.normal(size=3), -5, 5).astype(np.float32)
                        c = calibrate(generator, design, z, history, episode=episode, require_raw=True)
                        if c is None or abs(c.raw_error) >= 0.05:
                            continue
                        try:
                            c.resistance = predictor.predict(to_model_points(c.points), design.draft_ratio, speed)
                        except ValueError as exc:
                            history.write(c, status="predictor_rejected", detail=str(exc))
                            continue
                        current = c
                        break
                    if current is None:
                        history.write(status="episode_initialization_failed", episode=episode)
                        continue
                    initial_resistance = current.resistance
                    invalid_streak = 0
                    for step in range(0, actor.episode_length + 1):
                        if step > 0:
                            obs = np.asarray([*current.z, design.beam / design.length, design.depth / design.length,
                                              design.draft_ratio, current.condition, speed,
                                              current.resistance / initial_resistance, current.raw_error,
                                              (actor.episode_length - (step - 1)) / actor.episode_length], dtype=np.float32)
                            action = np.clip(actor.action(obs), -1, 1)
                            z = np.clip(current.z + actor.action_scale * action, actor.z_min, actor.z_max)
                            try:
                                proposal = evaluate(generator, design, z, current.condition, predictor,
                                                    speed, episode=episode, step=step)
                            except InvalidResistanceError as exc:
                                invalid_streak += 1
                                history.write(status="invalid_step", detail=str(exc), episode=episode, step=step)
                                if invalid_streak >= 3:
                                    break
                                continue
                            except (ValueError, RuntimeError, FloatingPointError) as exc:
                                history.write(status="episode_evaluation_failed", detail=str(exc), episode=episode, step=step)
                                break
                            current = proposal
                            invalid_streak = 0
                        history.write(current, status="rollout")
                        if volume_feasible(current, design, require_raw=True) and (
                                best is None or current.resistance < best.resistance):
                            try:
                                check_mesh(current, probe)
                            except ValueError as exc:
                                history.write(current, status="mesh_rejected", detail=str(exc))
                                continue
                            best = current
                            history.write(best, status="best_feasible")
                        if best is not None and best.resistance < target:
                            found = True
                            break
                    if episode % 10 == 0:
                        value = "none" if best is None else f"{best.resistance:.6g} N"
                        print(f"Evaluated {episode} episodes; best feasible resistance: {value}", file=sys.stderr, flush=True)
                    if found:
                        break
            if best is None:
                raise ValueError("No valid design met the physical displacement and mesh requirements within the search budget. No compliant hull is claimed. See search_history.csv, increase the budget or revise the requirements.")
            result = _design_result(best, design, request, directory, basename, predictor, speed_info)
            result["history_rows"] = history.count
            save_json(directory / "result.json", result)
            return result, 2 if result["status"] == "target_not_met" else 0
    except Exception as exc:
        save_json(directory / "failure.json", {"status": "failed", "mode": request["mode"],
                                               "message": str(exc), "output_directory": str(directory)})
        raise
    finally:
        if history is not None:
            history.close()
        lock.unlink(missing_ok=True)


def prediction_context(request: dict) -> tuple[np.ndarray, float, dict, dict]:
    if not request.get("points"):
        raise ValueError("Provide a half-hull point-cloud CSV via points/--points.")
    path = resolved_path(request["points"])
    points = validate_half_cloud(path)
    data = dict(request)
    metadata_used = None
    metadata_path = path.parent / "result.json"
    if metadata_path.is_file():
        try:
            previous = json.loads(metadata_path.read_text(encoding="utf-8"))
            if (previous.get("point_cloud_sha256") == file_sha256(path) and
                    previous.get("geometry_scale") == "full" and isinstance(previous.get("design"), dict)):
                if not data.get("point_scale"):
                    data["point_scale"] = "full"
                if data.get("draft") is None and data.get("draft_ratio") is None:
                    data["draft_ratio"] = previous["design"]["draft_ratio"]
                metadata_used = str(metadata_path)
        except (KeyError, ValueError, TypeError):
            pass
    if data.get("point_scale") not in {"model", "full"}:
        raise ValueError("Specify point_scale as model or full. Shape alone cannot establish physical scale.")
    input_length, input_depth = float(points[:, 0].max()), float(points[:, 2].max())
    if data["point_scale"] == "model":
        if not math.isclose(input_length, 3.0, rel_tol=0.002, abs_tol=1e-6):
            raise ValueError("A model-scale input cloud must have Xmax close to 3 m (0.2% tolerance).")
        full_length = None if data.get("full_length") is None else positive(data["full_length"], "full_length")
    else:
        full_length = input_length
        if data.get("full_length") is not None:
            supplied = positive(data["full_length"], "full_length")
            if not math.isclose(supplied, input_length, rel_tol=0.002):
                raise ValueError("full_length disagrees with the full-scale point cloud Xmax.")
            full_length = supplied
    if data.get("draft_ratio") is not None:
        ratio = positive(data["draft_ratio"], "draft_ratio")
        if data.get("draft") is not None and not math.isclose(positive(data["draft"], "draft") / input_depth, ratio, rel_tol=1e-4):
            raise ValueError("draft and draft_ratio are inconsistent for the supplied point-cloud depth.")
    elif data.get("draft") is not None:
        ratio = positive(data["draft"], "draft") / input_depth
    else:
        raise ValueError("Provide draft_ratio=T/D or a draft measured at the same scale as the CSV. Point clouds alone do not identify the operating draft.")
    if ratio > 1:
        raise ValueError("Draft ratio must be in (0,1]. Check the draft and point-cloud scales.")
    speed_info = model_speed(data.get("speed"), data.get("speed_unit"), data.get("speed_scale"), full_length)
    context = {"source_point_cloud": str(path), "source_sha256": file_sha256(path),
               "point_scale": data["point_scale"], "input_xmax_m": input_length,
               "input_depth_m": input_depth, "draft_ratio": ratio,
               "coordinate_multiplier_to_model": 3.0 / input_length,
               "reused_design_metadata": metadata_used}
    return to_model_points(points), ratio, speed_info, context


def predict_workflow(request: dict) -> tuple[dict, int]:
    from .models import Predictor, select_device
    points, ratio, speed_info, context = prediction_context(request)
    device = select_device(request.get("device", "auto"), require_gpu=True)
    predictor = Predictor(device)
    resistance = predictor.predict(points, ratio, speed_info["model_speed_m_s"])
    directory, basename, lock = reserve_output("predict", request.get("output"))
    try:
        save_json(directory / "request.json", request)
        model_path = directory / f"{basename}_model_3m.csv"
        np.savetxt(model_path, points, delimiter=",", fmt="%.10g")
        result = {"schema_version": 1, "status": "completed", "mode": "predict",
                  "created_at": datetime.now().astimezone().isoformat(),
                  "output_directory": str(directory), "input": context,
                  "speed": speed_info, "model_total_resistance_N": resistance,
                  "resistance_scale": "L=3 m model", "draft_ratio": ratio,
                  "artifacts": {"model_point_cloud": str(model_path)},
                  "limitations": ["The supplied Predictor estimates model-scale total resistance in N.",
                                  "A syntactically valid point cloud does not establish in-distribution accuracy."]}
        save_json(directory / "result.json", result)
        return result, 0
    finally:
        lock.unlink(missing_ok=True)
