"""Command-line and UTF-8 JSON entry points for Pi-agent orchestration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback

from . import __version__
from .contracts import Design, domain_warnings, model_speed, positive

MODES = ("generate", "predict", "optimize", "validate", "doctor")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="LLM4Ship hull generation, resistance prediction and trained TD3 exploration.", allow_abbrev=False)
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="mode", required=True)
    for mode in MODES:
        command = commands.add_parser(mode, allow_abbrev=False)
        command.add_argument("--request", help="UTF-8 JSON request; explicit command-line values override it.")
        command.add_argument("--dry-run", action="store_true", help="Validate inputs and convert units without loading models or writing output files.")
        command.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
        command.add_argument("--debug", action="store_true", help="Print a traceback after the structured error.")
        if mode == "doctor":
            command.add_argument("--models", action="store_true", help="Load and exercise the real generator/TD3 actor; also exercise the predictor when CUDA is available.")
            continue
        if mode in {"predict", "validate"}:
            command.add_argument("--points", help="Headerless 1000 x 3 half-hull CSV in meters.")
        if mode == "validate":
            continue
        command.add_argument("--output", help="Output folder, relative to the invocation working directory when not absolute.")
        command.add_argument("--speed", type=float)
        command.add_argument("--speed-unit", choices=("m/s", "km/h", "kn"))
        command.add_argument("--speed-scale", choices=("model", "full"))
        command.add_argument("--draft", type=float)
        if mode == "predict":
            command.add_argument("--point-scale", choices=("model", "full"))
            command.add_argument("--draft-ratio", type=float)
            command.add_argument("--full-length", type=float, help="Full-scale reference length; required for model CSV with full-scale speed.")
        else:
            for name in ("length", "beam", "depth", "displacement-tonnes", "displacement-volume", "block-coefficient"):
                command.add_argument("--" + name, type=float)
            command.add_argument("--density", type=float, default=1025.0)
            command.add_argument("--volume-tolerance", type=float, default=0.05)
            command.add_argument("--seed", type=int, default=42)
            command.add_argument("--max-attempts", type=int, default=200)
            command.add_argument("--max-episodes", type=int, default=100)
            if mode == "optimize":
                command.add_argument("--target-resistance", type=float, help="Strict upper limit for model-scale total resistance, in N.")
    return root


def read_request(argv: list[str]) -> tuple[dict, bool]:
    cli = parser()
    values = {}
    arguments = list(argv)
    request_path = None
    request_arguments = [i for i, value in enumerate(arguments) if value == "--request" or value.startswith("--request=")]
    if len(request_arguments) > 1:
        raise ValueError("Specify only one JSON request file.")
    if request_arguments:
        index = request_arguments[0]
        if arguments[index] == "--request":
            if index + 1 >= len(arguments):
                raise ValueError("--request needs a file path.")
            request_path = Path(arguments[index + 1]).expanduser().resolve()
            del arguments[index:index + 2]
        else:
            request_path = Path(arguments.pop(index).split("=", 1)[1]).expanduser().resolve()
        values = json.loads(request_path.read_text(encoding="utf-8-sig"))
        if not isinstance(values, dict):
            raise ValueError("A JSON request must be one object.")
        if values.get("points") and not Path(values["points"]).is_absolute():
            values["points"] = str((request_path.parent / values["points"]).resolve())
    mode = next((value for value in arguments[:1] if value in MODES), values.get("mode"))
    if mode in MODES:
        if values.get("mode") not in (None, mode):
            raise ValueError("The JSON mode conflicts with the command.")
        if not arguments or arguments[0] not in MODES:
            arguments.insert(0, mode)
        subparsers = next(action for action in cli._actions if isinstance(action, argparse._SubParsersAction))
        selected = subparsers.choices[mode]
        allowed = {action.dest for action in selected._actions} - {"help", "request"} | {"mode"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError("Unknown JSON request fields: " + ", ".join(sorted(unknown)))
        # Preserve argparse's type validation for JSON numeric fields and choices.
        actions = {action.dest: action for action in selected._actions}
        for key, value in values.items():
            if key == "mode" or value is None:
                continue
            action = actions[key]
            if isinstance(action, argparse._StoreTrueAction) and not isinstance(value, bool):
                raise ValueError(f"{key} must be a JSON boolean.")
            if action.type is not None:
                if isinstance(value, bool):
                    raise ValueError(f"{key} must be numeric, not a boolean.")
                if action.type is int and (isinstance(value, float) and not value.is_integer()):
                    raise ValueError(f"{key} must be an integer.")
                values[key] = action.type(value)
            elif not isinstance(action, argparse._StoreTrueAction) and not isinstance(value, str):
                raise ValueError(f"{key} must be a string.")
            if action.choices is not None and values[key] not in action.choices:
                raise ValueError(f"Invalid {key}: {values[key]!r}.")
        selected.set_defaults(**{key: value for key, value in values.items() if key != "mode"})
    namespace = cli.parse_args(arguments)
    request = vars(namespace)
    request.pop("request", None)
    debug = bool(request.pop("debug", False))
    if request["mode"] in {"generate", "optimize"}:
        Design.from_request(request)
        for key in ("max_attempts", "max_episodes"):
            if not isinstance(request[key], int) or request[key] <= 0:
                raise ValueError(f"{key} must be a positive integer.")
        if not isinstance(request["seed"], int) or request["seed"] < 0:
            raise ValueError("seed must be a nonnegative integer.")
        if request["mode"] == "optimize":
            request["target_resistance"] = positive(request.get("target_resistance"), "target_resistance")
        has_speed_fields = any(request.get(key) is not None for key in ("speed", "speed_unit", "speed_scale"))
        if has_speed_fields or request["mode"] == "optimize":
            model_speed(request.get("speed"), request.get("speed_unit"), request.get("speed_scale"), request["length"])
    return request, debug


def dry_run(request: dict) -> dict:
    if request["mode"] in {"generate", "optimize"}:
        design = Design.from_request(request)
        speed = model_speed(request["speed"], request["speed_unit"], request["speed_scale"], design.length) if request.get("speed") is not None else None
        ratio = design.length / 3.0
        return {"status": "validated", "dry_run": True, "mode": request["mode"],
                "design": design.to_dict(), "speed": speed,
                "model_geometry_m": {"length": 3.0, "beam": design.beam / ratio,
                                     "depth": design.depth / ratio, "draft": design.draft / ratio},
                "target_resistance_N": request.get("target_resistance"),
                "target_operator": "lt" if request["mode"] == "optimize" else None,
                "warnings": domain_warnings(design, speed["model_speed_m_s"] if speed else None) if request["mode"] == "optimize" else [],
                "output_directory": request.get("output"), "files_written": False, "models_loaded": False}
    if request["mode"] == "predict":
        from .workflow import prediction_context
        points, ratio, speed, context = prediction_context(request)
        return {"status": "validated", "dry_run": True, "mode": "predict", "input": context,
                "draft_ratio": ratio, "speed": speed, "model_xmax_m": float(points[:, 0].max()),
                "files_written": False, "models_loaded": False}
    if request["mode"] == "validate":
        return {**validate_request(request), "dry_run": True, "models_loaded": False}
    return {"status": "validated", "dry_run": True, "mode": request["mode"], "models_loaded": False, "files_written": False}


def validate_request(request: dict) -> dict:
    from .geometry import validate_half_cloud
    if not request.get("points"):
        raise ValueError("validate requires --points.")
    points = validate_half_cloud(request["points"])
    return {"status": "valid", "mode": "validate", "shape": list(points.shape),
            "min_xyz": points.min(axis=0).tolist(), "max_xyz": points.max(axis=0).tolist(),
            "point_order_preserved": True, "files_written": False,
            "note": "Format validation alone does not establish the operating draft or the physical scale."}


def doctor(request: dict) -> tuple[dict, int]:
    import importlib.metadata
    import importlib.util
    from .models import PROJECT_ROOT, verify_models
    result = {"status": "checked", "mode": "doctor", "python_executable": sys.executable,
              "python_version": sys.version.split()[0], "project_root": str(PROJECT_ROOT),
              "model_files": verify_models(), "versions": {}, "runtime_checks": {}}
    for package in ("torch", "numpy", "spconv-cu121", "stable-baselines3", "gymnasium", "matplotlib", "plotly"):
        try:
            result["versions"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result["versions"][package] = None
    if importlib.util.find_spec("torch") is None:
        result["runtime_checks"]["models"] = "not_run; PyTorch is missing"
        return result, 1 if request.get("models") else 0
    import torch
    result["cuda_available"] = torch.cuda.is_available()
    if request.get("models"):
        import numpy as np
        from .models import Generator, Predictor, TD3Actor, select_device
        from .workflow import to_model_points
        from .geometry import validate_half_cloud
        device = select_device(request.get("device", "auto"))
        generator = Generator(device)
        generated = generator.evaluate(np.zeros(3, dtype=np.float32), 0.5, 0.25, 3, 0.6, 0.3)
        actor = TD3Actor(device)
        obs = np.asarray([0, 0, 0, .2, .1, .5, .25, 1.2, 1, 0, 1], dtype=np.float32)
        result["runtime_checks"]["generator_shape"] = list(generated.physical_points.shape)
        result["runtime_checks"]["td3_action"] = actor.action(obs).tolist()
        if device.type == "cuda":
            predictor = Predictor(device)
            points = validate_half_cloud(PROJECT_ROOT / "vendor/Predictor/Branchmark/ship1.csv")
            resistance = predictor.predict(to_model_points(points), 0.495283019, 0.8)
            result["runtime_checks"]["benchmark_model_resistance_N"] = resistance
            result["runtime_checks"]["predictor"] = "passed"
        else:
            result["runtime_checks"]["predictor"] = "not_run; NVIDIA GPU required"
            result["status"] = "checked_with_gpu_tests_skipped"
    return result, 0


def main(argv=None) -> int:
    debug = False
    try:
        request, debug = read_request(sys.argv[1:] if argv is None else argv)
        if request.get("dry_run"):
            result, code = dry_run(request), 0
        elif request["mode"] == "doctor":
            result, code = doctor(request)
        elif request["mode"] == "validate":
            result, code = validate_request(request), 0
        else:
            from .workflow import design_workflow, predict_workflow
            result, code = predict_workflow(request) if request["mode"] == "predict" else design_workflow(request)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), flush=True)
        return code
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted", "message": "Task interrupted by the user."}), file=sys.stderr)
        return 130
    except Exception as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        if debug:
            traceback.print_exc()
        return 1
