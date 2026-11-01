#!/usr/bin/env python3
"""Inspect this interpreter without installing packages or loading model files."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.metadata
import json
import platform
import struct
import sys
from pathlib import Path
from typing import Any


def load_spec() -> dict[str, Any]:
    return json.loads(Path(__file__).with_name("runtime-spec.json").read_text(encoding="utf-8"))


def collect_report(*, quick: bool = False, require_gpu: bool = False) -> dict[str, Any]:
    spec = load_spec()
    report: dict[str, Any] = {
        "python": platform.python_version(),
        "executable": sys.executable,
        "platform": platform.system(),
        "machine": platform.machine(),
        "bits": struct.calcsize("P") * 8,
        "packages": {},
        "checks": {},
        "errors": [],
        "warnings": [],
        "models_checked": False,
    }
    errors, warnings = report["errors"], report["warnings"]
    if sys.version_info < (3, 11):
        errors.append("Python 3.11 or later is required for this project.")
    elif report["python"] != spec["python"]:
        warnings.append(f"Python differs from the recorded runtime ({spec['python']}); model loading still needs verification.")
    if report["platform"] not in {"Windows", "Linux"} or report["bits"] != 64 or report["machine"].lower() not in {"amd64", "x86_64", "x64"}:
        errors.append("Automatic runtime support is limited to Windows/Linux on x86-64.")

    imported: dict[str, Any] = {}
    for name, info in {**spec["torch_packages"], **spec["packages"]}.items():
        item: dict[str, Any] = {"expected": info["version"], "installed": None, "import_ok": False}
        report["packages"][name] = item
        try:
            item["installed"] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            # Other CUDA builds can provide the same module in an existing environment.
            aliases = []
            if name.startswith("spconv-"):
                aliases = ["spconv", "spconv-cu118", "spconv-cu120", "spconv-cu124", "spconv-cu126"]
            elif name.startswith("cumm-"):
                aliases = ["cumm", "cumm-cu118", "cumm-cu120", "cumm-cu124", "cumm-cu126"]
            for alias in aliases:
                try:
                    item["installed"] = importlib.metadata.version(alias)
                    item["distribution"] = alias
                    break
                except importlib.metadata.PackageNotFoundError:
                    pass
            if item["installed"] is None:
                errors.append(f"Missing package: {name}=={info['version']}.")
                continue
        if item["installed"] != info["version"] or item.get("distribution", name) != name:
            warnings.append(f"{name}: found {item.get('distribution', name)} {item['installed']}; recorded version is {info['version']}. No package was changed.")
        module_name = info.get("module")
        if not module_name:
            item["import_ok"] = True
            continue
        try:
            # Keep JSON output machine-readable if a native package prints during import.
            with contextlib.redirect_stdout(sys.stderr):
                imported[name] = importlib.import_module(module_name)
            item["import_ok"] = True
        except Exception as exc:
            item["import_error"] = f"{type(exc).__name__}: {exc}"
            errors.append(f"Cannot import {module_name}: {item['import_error']}")

    np, torch = imported.get("numpy"), imported.get("torch")
    if np is not None and torch is not None:
        try:
            original = np.arange(6, dtype=np.float32).reshape(2, 3)
            tensor = torch.from_numpy(original)
            returned = tensor.detach().cpu().numpy()
            if not np.array_equal(original, returned):
                raise RuntimeError("Array values changed during the round trip.")
            torch.as_tensor(original, dtype=torch.float32)
            report["checks"]["numpy_tensor_roundtrip"] = "passed"
        except Exception as exc:
            report["checks"]["numpy_tensor_roundtrip"] = "failed"
            errors.append(f"NumPy/Tensor bridge failed: {type(exc).__name__}: {exc}")
    else:
        report["checks"]["numpy_tensor_roundtrip"] = "not run: NumPy or PyTorch is unavailable"

    cuda_available = False
    if torch is not None:
        report["torch_cuda_build"] = torch.version.cuda
        try:
            cuda_available = bool(torch.cuda.is_available())
            report["cuda_available"] = cuda_available
            if cuda_available:
                report["gpu"] = torch.cuda.get_device_name(0)
                report["gpu_capability"] = list(torch.cuda.get_device_capability(0))
        except Exception as exc:
            errors.append(f"CUDA discovery failed: {type(exc).__name__}: {exc}")
    if not cuda_available:
        message = "NVIDIA CUDA is unavailable. CPU-only checks do not validate the sparse-convolution hull prediction/optimization workflow."
        (errors if require_gpu else warnings).append(message)
        report["checks"]["spconv_gpu"] = "not run: CUDA is unavailable"
    elif quick:
        report["checks"]["spconv_gpu"] = "not run in quick mode; use --check for the GPU kernel check"
    else:
        spconv = imported.get("spconv-cu121")
        if spconv is None:
            report["checks"]["spconv_gpu"] = "not run: spconv import failed"
        else:
            try:
                with torch.inference_mode():
                    features = torch.ones((2, 4), dtype=torch.float32, device="cuda")
                    indices = torch.tensor([[0, 1, 1, 1], [0, 1, 1, 2]], dtype=torch.int32, device="cuda")
                    sparse = spconv.SparseConvTensor(features, indices, spatial_shape=[4, 4, 4], batch_size=1)
                    layer = spconv.SubMConv3d(4, 4, kernel_size=3, bias=True).cuda().eval()
                    result = layer(sparse).features
                    torch.cuda.synchronize()
                    if tuple(result.shape) != (2, 4) or not bool(torch.isfinite(result).all()):
                        raise RuntimeError("The sparse convolution returned an invalid shape or non-finite values.")
                report["checks"]["spconv_gpu"] = "passed"
            except Exception as exc:
                report["checks"]["spconv_gpu"] = "failed"
                errors.append(f"spconv GPU kernel failed: {type(exc).__name__}: {exc}")
    report["ok"] = not errors
    report["gpu_workflow_checked"] = report["checks"].get("spconv_gpu") == "passed"
    return report


def print_report(report: dict[str, Any]) -> None:
    print(f"Python: {report['python']} ({report['executable']})")
    print(f"Platform: {report['platform']} {report['machine']} {report['bits']}-bit")
    for name, item in report["packages"].items():
        status = "OK" if item["import_ok"] else "ERROR"
        print(f"[{status}] {name}: {item['installed'] or 'missing'} (reference {item['expected']})")
    for name, value in report["checks"].items():
        print(f"[CHECK] {name}: {value}")
    if report.get("gpu"):
        print(f"GPU: {report['gpu']}; PyTorch CUDA build: {report.get('torch_cuda_build')}")
    for message in report["warnings"]:
        print(f"[NOTE] {message}")
    for message in report["errors"]:
        print(f"[ERROR] {message}")
    print("Model checkpoints were not loaded by the environment doctor.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Skip the actual GPU convolution.")
    parser.add_argument("--require-gpu", action="store_true", help="Treat unavailable CUDA as an error.")
    parser.add_argument("--json", action="store_true", help="Write a structured report to stdout.")
    options = parser.parse_args(argv)
    report = collect_report(quick=options.quick, require_gpu=options.require_gpu)
    if options.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
