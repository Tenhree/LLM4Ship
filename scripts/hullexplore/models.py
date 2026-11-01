"""Adapters for the unmodified supplied Generator, Predictor and TD3 actor."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class InvalidResistanceError(ValueError):
    """A finite near-zero prediction subject to the trained rejection streak."""


def verify_models(names: tuple[str, ...] = ("Generator", "Predictor", "Hull_RL_Optimization")) -> list[dict]:
    manifest = json.loads((PROJECT_ROOT / "models-manifest.json").read_text(encoding="utf-8"))
    results = []
    for item in manifest["models"]:
        if not any(f"/{name}/" in item["path"] for name in names):
            continue
        path = PROJECT_ROOT / item["path"]
        if not path.is_file():
            raise FileNotFoundError(f"Missing trained model: {path}. Extract the complete project ZIP, including vendor/.")
        with path.open("rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"Trained model checksum mismatch: {path}")
        results.append({**item, "verified": True})
    return results


def select_device(requested="auto", require_gpu=False):
    import torch
    if requested not in {"auto", "cpu", "cuda"}:
        raise ValueError("device must be auto, cpu or cuda")
    device = torch.device("cuda" if requested == "auto" and torch.cuda.is_available() else
                          "cpu" if requested == "auto" else requested)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable in the selected interpreter. Run the environment check first.")
    if require_gpu and device.type != "cuda":
        raise RuntimeError("The supplied resistance predictor requires the validated NVIDIA/spconv GPU path. Use a CUDA-capable environment.")
    torch.set_num_threads(1)
    return device


def _backends():
    # The vendor package scopes its legacy config/utils imports. Do not globally
    # import Generator/models.py as 'models', which can collide with other skills.
    path = str(PROJECT_ROOT / "vendor" / "Hull_RL_Optimization")
    if path not in sys.path:
        sys.path.insert(0, path)
    from hull_rl.backends import GeneratorBackend, PredictorBackend
    return GeneratorBackend, PredictorBackend


class Generator:
    def __init__(self, device):
        verify_models(("Generator",))
        backend, _ = _backends()
        base = PROJECT_ROOT / "vendor" / "Generator"
        self.backend = backend(base, base / "stage2_final.pth", device, point_scaling_mode="point2hull")
        self.device = device

    def evaluate(self, z, draft_ratio, raw_condition, length, beam, depth):
        return self.backend.evaluate_geometry(np.asarray(z, dtype=np.float32), draft_ratio,
                                              raw_condition, length, beam, depth)


class Predictor:
    def __init__(self, device):
        if device.type != "cuda":
            raise RuntimeError("Resistance inference requires the NVIDIA GPU runtime for this spconv checkpoint.")
        verify_models(("Predictor",))
        _, backend = _backends()
        base = PROJECT_ROOT / "vendor" / "Predictor"
        self.backend = backend(base, base / "prediction_best.pth", device, amp=False)

    def predict(self, points, draft_ratio, speed):
        points = np.asarray(points, dtype=np.float32)
        if points.shape != (1000, 3) or not np.isfinite(points).all():
            raise ValueError("Predictor requires a finite 1000 x 3 point cloud.")
        if abs(float(points[:, 0].max()) - 3.0) > 1e-5:
            raise ValueError("Predictor input must have Xmax=3 m.")
        if not 0 < draft_ratio <= 1 or not np.isfinite(speed) or speed <= 0:
            raise ValueError("Invalid predictor draft ratio or speed.")
        result = float(self.backend.predict(points, draft_ratio, speed))
        if not np.isfinite(result):
            raise FloatingPointError(f"Predictor returned a non-finite total resistance ({result!r} N).")
        if result <= 0.001:
            raise InvalidResistanceError(f"Predictor returned an invalid or near-zero total resistance ({result!r} N).")
        return result


class TD3Actor:
    """Load only the trained actor tensors, avoiding cloudpickle/Python-version coupling.

    This is the exact saved Linear-ReLU-Linear-ReLU-Linear-Tanh actor, with
    identity action unscaling because the trained action limits are [-1, 1].
    No policy is trained or substituted here.
    """
    observation_size = 11
    action_size = 3
    episode_length = 5
    action_scale = 0.01
    z_min, z_max = -5.0, 5.0

    def __init__(self, device):
        import torch
        from torch import nn
        verify_models(("Hull_RL_Optimization",))
        path = PROJECT_ROOT / "vendor/Hull_RL_Optimization/runs/td3/models/td3_final.zip"
        with zipfile.ZipFile(path) as archive:
            state = torch.load(io.BytesIO(archive.read("policy.pth")), map_location="cpu", weights_only=True)
        actor_state = {key[len("actor.mu."):]: value for key, value in state.items() if key.startswith("actor.mu.")}
        self.network = nn.Sequential(nn.Linear(11, 256), nn.ReLU(), nn.Linear(256, 256),
                                     nn.ReLU(), nn.Linear(256, 3), nn.Tanh())
        self.network.load_state_dict(actor_state, strict=True)
        self.network.to(device).eval()
        self.device = device
        for p in self.network.parameters():
            p.requires_grad_(False)

    def action(self, observation):
        import torch
        obs = np.asarray(observation, dtype=np.float32)
        if obs.shape != (11,) or not np.isfinite(obs).all():
            raise ValueError("The trained TD3 actor requires 11 finite observation values.")
        with torch.inference_mode():
            result = self.network(torch.as_tensor(obs, device=self.device).unsqueeze(0))
        return result[0].cpu().numpy().astype(np.float32)
