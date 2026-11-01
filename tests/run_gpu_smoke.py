"""Run real end-to-end inference checks in the selected NVIDIA environment.

Example: D:\\anaconda3\\envs\\mypythorch\\python.exe tests/run_gpu_smoke.py
This creates a new GPUCheck-<timestamp> directory under the invocation directory.
The resistance values are computed by the supplied model; none are hard-coded.
"""
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def main():
    from hullexplore.models import select_device
    from hullexplore.workflow import design_workflow, predict_workflow, save_json
    # Fail before creating an output directory when CUDA is unavailable.
    select_device("cuda", require_gpu=True)
    folder = Path.cwd() / ("GPUCheck-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    folder.mkdir(exist_ok=False)
    base = {"length": 90, "beam": 15.6, "depth": 7.5, "draft": 3.75,
            "displacement_tonnes": 3000, "density": 1025, "volume_tolerance": .05,
            "seed": 42, "device": "cuda", "speed": 1.2, "speed_unit": "m/s", "speed_scale": "model"}
    print("Running real generation plus model resistance...", flush=True)
    generated, code = design_workflow({**base, "mode": "generate", "output": str(folder / "generate"), "max_attempts": 20})
    if code or generated["status"] != "completed":
        raise RuntimeError("Generation plus prediction did not complete.")
    print("Re-predicting the exact exported full-scale CSV, using its hash-verified metadata...", flush=True)
    predicted, code = predict_workflow({"mode": "predict", "points": generated["artifacts"]["point_cloud"],
                                        "speed": 1.2, "speed_unit": "m/s", "speed_scale": "model", "device": "cuda",
                                        "output": str(folder / "repredict")})
    r1, r2 = generated["model_total_resistance_N"], predicted["model_total_resistance_N"]
    if code or abs(r1 - r2) > max(1e-5, 1e-5 * abs(r1)):
        raise RuntimeError(f"Export/re-prediction consistency check failed: {r1} N versus {r2} N.")
    print("Running two trained TD3 episodes and checking useful fallback output...", flush=True)
    # All accepted predictor outputs exceed 0.001 N; this strict target deliberately
    # exercises fallback selection. It is not an attainable design requirement.
    optimized, code = design_workflow({**base, "mode": "optimize", "target_resistance": .001,
                                       "max_episodes": 2, "output": str(folder / "optimize")})
    if code != 2 or optimized["status"] != "target_not_met" or optimized["target_met"] is not False:
        raise RuntimeError("TD3 fallback semantics did not match the expected strict comparison.")
    for result in (generated, predicted, optimized):
        for artifact in result["artifacts"].values():
            if not Path(artifact).is_file():
                raise RuntimeError(f"Missing reported artifact: {artifact}")
    report = {"status": "passed", "runtime": sys.executable, "output_directory": str(folder),
              "generator_prediction_N": r1, "repeated_prediction_N": r2,
              "td3_fallback_prediction_N": optimized["model_total_resistance_N"],
              "td3_target_N": .001, "note": "Execution and export consistency only; not a CFD or experimental accuracy test."}
    save_json(folder / "gpu_smoke_result.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
