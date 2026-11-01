import os
from typing import List, Optional, Sequence
import hashlib
import glob
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset
from multiprocessing import Pool, cpu_count

class HullGeometryDataset(Dataset):
    """
    Geometry-only hull dataset loaded from CSV files.

    Each CSV is expected to contain at least 2 columns:
        col 0 -> X coordinate
        col 1 -> Y coordinate

    After loading:
        raw shape: [num_wl * num_x, 2]
        reshaped : [num_wl, num_x, 2]
        transposed -> [2, num_wl, num_x]

    Returned item format:
        {
            "geometry": tensor [2, H, W],
            "cond": empty tensor
        }
    """

    def __init__(self, root_dir, num_wl, num_x, transform=None, dtype=torch.float32, return_empty_cond=True):
        self.root_dir = root_dir
        self.transform = transform
        self.num_wl = num_wl
        self.num_x = num_x
        self.dtype = dtype
        self.return_empty_cond = return_empty_cond

        # 递归读取所有 csv
        self.file_paths = glob.glob(
            os.path.join(root_dir, "**", "*.csv"),
            recursive=True
        )

        if len(self.file_paths) == 0:
            raise RuntimeError(f"No CSV files found in {root_dir}")

        # 排序，保证读取顺序稳定
        self.file_paths = sorted(self.file_paths)

    def __len__(self):
        return len(self.file_paths)

    def _normalize_columnwise(self, data: np.ndarray) -> np.ndarray:
        """
        Keep the same logic as your original code:
        - x and y are normalized independently to [0,1]
        """
        data = data.copy()

        # x column
        data[:, 0] = data[:, 0] - np.min(data[:, 0])
        x_max = np.max(data[:, 0])
        if x_max > 0:
            data[:, 0] = data[:, 0] / x_max
        else:
            data[:, 0] = 0.0

        # y column
        data[:, 1] = data[:, 1] - np.min(data[:, 1])
        y_max = np.max(data[:, 1])
        if y_max > 0:
            data[:, 1] = data[:, 1] / y_max
        else:
            data[:, 1] = 0.0

        return data

    def __getitem__(self, idx):
        file_path = self.file_paths[idx]

        try:
            # 读取 CSV
            data = pd.read_csv(file_path, header=None).values.astype(np.float32)

            # 至少要有两列
            if data.shape[1] < 2:
                raise ValueError(f"CSV must contain at least 2 columns, got shape {data.shape}")

            # 只取前两列，与你原代码一致
            data = data[:, :2]

            # 行数检查
            expected_rows = self.num_wl * self.num_x
            if data.shape[0] != expected_rows:
                raise ValueError(
                    f"CSV row count mismatch in {file_path}. "
                    f"Expected {expected_rows} rows (= num_wl*num_x), got {data.shape[0]}"
                )

            # 保留你原来的归一化逻辑
            data = np.round(data, 5)
            data = self._normalize_columnwise(data)

            # reshape: [num_wl*num_x, 2] -> [num_wl, num_x, 2]
            data = data.reshape(self.num_wl, self.num_x, 2)

            # transpose -> [2, num_wl, num_x]
            data = data.transpose(2, 0, 1)

            # transform
            if self.transform is not None:
                data = self.transform(data)

            # 转 tensor
            if not isinstance(data, torch.Tensor):
                data = torch.tensor(data, dtype=self.dtype)
            else:
                data = data.to(self.dtype)

            # 安全起见截断到 [0,1]
            data = torch.clamp(data, 0.0, 1.0)

            # 保证维度为 [2, H, W]
            if data.ndim != 3 or data.shape[0] != 2:
                raise ValueError(f"Expected sample shape [2, H, W], got {tuple(data.shape)}")

        except Exception as e:
            raise RuntimeError(f"Error reading {file_path}: {e}")

        if self.return_empty_cond:
            cond = torch.empty(0, dtype=self.dtype)
        else:
            cond = None

        return {
            "x": data,
        }


def _hash_file(path: str) -> str:
    """用文件路径+mtime做一个轻量hash，判断缓存是否需要重算"""
    st = os.stat(path)
    s = f"{path}|{st.st_size}|{st.st_mtime}"
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def _compute_one_delta(args):
    """
    args: (fp, fh, T, num_wl, num_x)
    return: (fh, T, Delta, fp)
    """
    fp, fh, T, num_wl, num_x = args

    # --- 这里复制 _load_one 的逻辑，避免在子进程里依赖 self（更稳） ---
    data = pd.read_csv(fp, header=None).values.astype(np.float32).round(5)

    # 兼容两种 CSV 形状： (H*W,3) or (3,H*W)
    if data.shape[0] == 3 and data.shape[1] == num_wl * num_x:
        data = data.T  # -> (H*W,3)

    data = data[:, :2]  # X,Y

    data[:, 0] -= np.min(data[:, 0])
    data[:, 1] -= np.min(data[:, 1])

    max_x = np.max(data[:, 0])
    max_y = np.max(data[:, 1])
    if max_x > 0:
        data[:, 0] /= max_x
    if max_y > 0:
        data[:, 1] /= max_y

    S = data.reshape(num_wl, num_x, 2).transpose(2, 0, 1)  # (2,num_wl,num_x)

    # --- 计算排水量 ---
    Delta = calc_displacement(S, float(T), num_wl, num_x)
    return fh, float(T), float(Delta), fp

def calc_displacement(S_xy: np.ndarray, T: float,num_wl,num_x) -> float:
    """
    TODO: 用你的显式物理计算器替换这里。
    输入:
      S_xy: numpy, shape (2, H, W), ch0=X, ch1=Y, 归一化后
      T: 吃水（建议用归一化 0~1），会传给 calc(S,T)
    输出:
      Delta: float
    """
    # -----------------------------
    # 示例占位：请替换成你的 calc(S, T)
    # -----------------------------
    X = S_xy[0]
    Y = S_xy[1]
    Z = np.linspace(0,1,num_wl).reshape(-1, 1).repeat(num_x, axis=1)
    z_values = np.unique(Z)
    z_below = z_values[z_values <= T].max()
    z_above = z_values[z_values >= T].min()
    X_np = X
    Z_np = Z
    Y_np = Y
    # 找到对应层
    mask_below = (Z_np == z_below)
    mask_above = (Z_np == z_above)

    # 提取对应的 X 集合
    X_below = X_np[mask_below]
    X_above = X_np[mask_above]
    Y_below = Y_np[mask_below]
    Y_above = Y_np[mask_above]
    alpha = (T - z_below) / (z_above - z_below)
    X_new = X_below + alpha * (X_above - X_below)
    Y_new = Y_below + alpha * (Y_above - Y_below)

    z_all = np.sort(np.append(z_values[z_values < T], T))

    def waterline_area(X_layer, Y_layer):
        idx = np.argsort(X_layer)
        X_layer = X_layer[idx]
        Y_layer = Y_layer[idx]
        return  np.trapz(Y_layer, X_layer)

    areas = []
    Btemp = []
    for z in z_all:
        if np.isclose(z, T):
            A = waterline_area(X_new, Y_new)
            Btemptemp=np.max(Y_new)
        else:
            mask = np.abs(Z_np - z) < 1e-6
            A = waterline_area(X_np[mask], Y_np[mask])
            Btemptemp = np.max(Y_np[mask])
        areas.append(A)
        Btemp.append(Btemptemp)
    areas = np.array(areas)
    volume = np.trapz(areas, z_all)
    # Lwl=np.max(X_new)-np.min(X_new)
    # B=np.max(Btemp)
    # Cb=volume/Lwl/B/T/2
    Cb = volume  #半船的排水量
    return Cb

class HullPhysicalConditionDataset(Dataset):
    """
    扩增版数据集：
    - 每个原始CSV样本扩增为 len(draft_list) 个训练样本
    - 每个扩增样本携带条件 (T, Delta)
    - Delta 通过 calc_displacement(S, T) 计算，并缓存到磁盘避免重复计算
    """

    def __init__(
        self,
        root_dir: str,
        num_wl: int,
        num_x: int,
        draft_list=(0.3,0.4,0.5,0.6,0.7,0.8),
        transform=None,
        cache_dir=None,
        cache_name="delta_cache.csv",
        force_recompute=False,
    ):
        self.transform = transform
        self.num_wl = num_wl
        self.num_x = num_x
        self.draft_list = [float(t) for t in draft_list]

        # 递归读取所有 csv
        self.file_paths = glob.glob(os.path.join(root_dir, "**", "*.csv"), recursive=True)
        if len(self.file_paths) == 0:
            raise RuntimeError(f"No CSV files found in {root_dir}")

        # 缓存路径
        if cache_dir is None:
            cache_dir = root_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_path = os.path.join(cache_dir, cache_name)

        # 先构建扩增索引：每个 (file_idx, t_idx) 对应一个样本
        self.index = []
        for i in range(len(self.file_paths)):
            for j in range(len(self.draft_list)):
                self.index.append((i, j))

        # 计算/读取 Delta 缓存：key=(file_hash, T) -> Delta
        self.delta_map = {}  # (file_hash, T) -> Delta
        if (not force_recompute) and os.path.exists(self.cache_path):
            try:
                df_cache = pd.read_csv(self.cache_path)
                for _, row in df_cache.iterrows():
                    self.delta_map[(row["file_hash"], float(row["T"]))] = float(row["Delta"])
            except Exception as e:
                print(f"[Warn] Failed to read cache {self.cache_path}: {e}. Will recompute.")
                self.delta_map = {}

        # 扫一遍，看哪些 (file_hash, T) 还缺
        missing = []
        for fp in self.file_paths:
            fh = _hash_file(fp)
            for T in self.draft_list:
                if (fh, T) not in self.delta_map:
                    missing.append((fp, fh, T))

        # 缺的就补算并写缓存
        if len(missing) > 0:
            print(f"[Info] Need to compute Delta for {len(missing)} (file,T) pairs...")

            # 进程数：建议 <= CPU 核心数；如果 calc 很重可以用 cpu_count()
            n_workers = min(cpu_count(), 8)  # 你也可以改成配置项
            tasks = [(fp, fh, T, self.num_wl, self.num_x) for (fp, fh, T) in missing]

            new_rows = []
            with Pool(processes=n_workers) as pool:
                # chunksize 调大一点通常更快（减少进程间调度开销）
                for fh, T, Delta, fp in pool.imap_unordered(_compute_one_delta, tasks, chunksize=32):
                    self.delta_map[(fh, T)] = float(Delta)
                    new_rows.append({"file_path": fp, "file_hash": fh, "T": float(T), "Delta": float(Delta)})

            # 合并写入缓存
            if os.path.exists(self.cache_path) and (not force_recompute):
                df_old = pd.read_csv(self.cache_path)
                df_new = pd.DataFrame(new_rows)
                df_all = pd.concat([df_old, df_new], ignore_index=True)
            else:
                df_all = pd.DataFrame(new_rows)

            df_all = df_all.drop_duplicates(subset=["file_hash", "T"], keep="last")
            df_all.to_csv(self.cache_path, index=False)
            print(f"[Info] Saved delta cache to: {self.cache_path}")

    def __len__(self):
        return len(self.index)

    def _load_one(self, file_path: str) -> np.ndarray:
        """
        读取单个CSV并转换为 (2, num_wl, num_x) 的 X/Y 网格
        你原始的 reshape/transpose 逻辑保持不变
        """
        try:
            data = pd.read_csv(file_path, header=None).values.astype(np.float32).round(5)

            # 只取 X,Y
            data = data[:, :2]  # shape (H*W, 2)  (你注释里是(3,H*W)，这里按实际 csv 调整)
            # 注意：如果你的csv是 (N,3) 列格式：X,Y,Z，那么上面就正确
            # 如果你的csv是 (3, H*W) 行格式，需要先转置：data = data.T

            # 移到原点 + 归一化到 [0,1]
            data[:, 0] = data[:, 0] - np.min(data[:, 0])
            data[:, 1] = data[:, 1] - np.min(data[:, 1])

            max_x = np.max(data[:, 0])
            max_y = np.max(data[:, 1])
            if max_x > 0:
                data[:, 0] = data[:, 0] / max_x
            if max_y > 0:
                data[:, 1] = data[:, 1] / max_y

            # reshape -> (num_wl, num_x, 2) -> transpose to (2, num_wl, num_x)
            data = data.reshape(self.num_wl, self.num_x, 2)
            data = data.transpose(2, 0, 1)

        except Exception as e:
            raise RuntimeError(f"Error reading {file_path}: {e}")

        if self.transform:
            data = self.transform(data)

        if len(data.shape) == 2:
            data = np.expand_dims(data, axis=0)  # [1, H, W]

        return data.astype(np.float32)
    def __getitem__(self, idx):
        file_idx, t_idx = self.index[idx]
        file_path = self.file_paths[file_idx]

        geometry = self._load_one(file_path)  # (2,H,W)
        T = self.draft_list[t_idx]

        fh = _hash_file(file_path)
        Delta = self.delta_map[(fh, T)]
        sample = {
            "x": geometry,
            "draft": T,
            "cb": Delta
        }
        # 返回：几何 + 条件（T, Delta）
        # latent 向量你在训练脚本里随机采样，不在 dataset 里返回
        return sample


