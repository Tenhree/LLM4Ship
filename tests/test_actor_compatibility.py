"""Compare the REAL saved TD3 actor with Stable-Baselines3, entirely on CPU.

This checks policy actions, not resistance predictions or optimization quality.
It uses only policy.pth tensors and does not deserialize the saved Python objects.
"""
import importlib.util
import io
from pathlib import Path
import sys
import unittest
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


@unittest.skipUnless(importlib.util.find_spec("torch") and importlib.util.find_spec("stable_baselines3"),
                     "PyTorch and Stable-Baselines3 are needed for the real actor comparison")
class SavedActorCompatibility(unittest.TestCase):
    def test_actions_match_sb3_policy_loaded_from_same_real_checkpoint(self):
        import torch
        from gymnasium.spaces import Box
        from stable_baselines3.td3.policies import TD3Policy
        from hullexplore.models import TD3Actor

        torch.set_num_threads(1)
        portable = TD3Actor(torch.device("cpu"))
        reference = TD3Policy(
            observation_space=Box(-np.inf, np.inf, shape=(11,), dtype=np.float32),
            action_space=Box(-1, 1, shape=(3,), dtype=np.float32),
            lr_schedule=lambda _: 0.0,
            net_arch=[256, 256], activation_fn=torch.nn.ReLU)
        path = ROOT / "vendor/Hull_RL_Optimization/runs/td3/models/td3_final.zip"
        with zipfile.ZipFile(path) as archive:
            state = torch.load(io.BytesIO(archive.read("policy.pth")), map_location="cpu", weights_only=True)
        reference.load_state_dict(state, strict=True)
        reference.set_training_mode(False)

        rng = np.random.default_rng(2718)
        for index in range(64):
            obs = np.asarray([*rng.uniform(-5, 5, 3), rng.uniform(.15, .25), rng.uniform(.07, .17),
                              rng.uniform(.35, .60), rng.uniform(.1, .5), rng.uniform(.6, 1.8),
                              rng.uniform(.5, 1.5), rng.uniform(-.05, .05), (index % 5 + 1) / 5],
                             dtype=np.float32)
            expected, _ = reference.predict(obs, deterministic=True)
            np.testing.assert_allclose(portable.action(obs), expected, rtol=0, atol=1e-7)


if __name__ == "__main__":
    unittest.main()
