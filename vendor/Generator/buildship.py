import torch
import random
import os
from config import ModelConfig, TrainConfig, PathConfig
from models import TwoStageCVAE
from utils import plot_hull_3d,estimate_cb_from_half_hull,hausdorff_distance,build_points,Point2Hull
import csv
import pandas as pd
import numpy as np




@torch.no_grad()
def sample_conditioned_geometry(model, draft_value, cb_value, z, device):
    model.eval()
    cond = torch.tensor([[draft_value, cb_value]], device=device).repeat(1, 1)
    return model.sample(z, cond, device)

def main():
    model_cfg = ModelConfig()
    train_cfg = TrainConfig()
    path_cfg = PathConfig()
    model = TwoStageCVAE(
            in_channels=model_cfg.in_channels,
            latent_dim=model_cfg.latent_dim,
            cond_dim=model_cfg.cond_dim,
            hidden_dim=model_cfg.hidden_dim,
            base_channels=model_cfg.base_channels,
            use_structured_output=model_cfg.use_structured_output,
        )
    checkpoint = torch.load(
            os.path.join(path_cfg.stage2_ckpt_path, "stage2_final.pth"),
            map_location=train_cfg.device
        )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(train_cfg.device)


    L=90
    Bd=15.6/2
    Dd=7
    T2Dd=5/9
    cb_true=0.33333333
    z = torch.randn(1, model_cfg.latent_dim, device=train_cfg.device)
    x_gen = sample_conditioned_geometry(
            model=model,
            draft_value=T2Dd,
            cb_value=cb_true,
            z=z,
            device=train_cfg.device,
        )
    h, w = x_gen.shape[2], x_gen.shape[3]
    Z = np.linspace(0.0, 1.0, h, dtype=np.float32).reshape(h, 1).repeat(w, axis=1).ravel()
    S1 = x_gen[0].detach().cpu().numpy()
    points = build_points(S1, Z, L, Bd, Dd)
    return points









if __name__ == "__main__":
    # 设置随机种子
    seed = 42

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    # 如果使用 GPU
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    main()