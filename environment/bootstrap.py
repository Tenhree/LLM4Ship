#!/usr/bin/env python3
"""Select an existing interpreter or provision an isolated project runtime.

Only the Python standard library is needed to start this program. An existing
user environment is inspected and reused, never upgraded or repaired in place.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import importlib.util
import io
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
PREFERRED_WINDOWS_PYTHON = Path(r"D:\anaconda3\envs\mypythorch\python.exe")
OWNER = "WhutOceanShip-Skills"
MINIFORGE_BASE = "https://github.com/conda-forge/miniforge/releases/download"


class BootstrapError(RuntimeError):
    """An actionable bootstrap error that must not modify another environment."""


@dataclass(frozen=True)
class PythonSelection:
    executable: Path
    origin: str
    runtime_root: Path | None = None


def log(message: str) -> None:
    print(f"[LLM4Ship] {message}", file=sys.stderr, flush=True)


def load_spec() -> dict[str, Any]:
    return json.loads((HERE / "runtime-spec.json").read_text(encoding="utf-8"))


def platform_key(system: str | None = None, machine: str | None = None) -> str:
    system, machine = system or platform.system(), (machine or platform.machine()).lower()
    if system not in {"Windows", "Linux"} or machine not in {"amd64", "x86_64", "x64"}:
        raise BootstrapError(f"Automatic setup supports Windows/Linux x86-64; found {system} {machine}.")
    return system


def python_in_prefix(prefix: Path, system: str | None = None) -> Path:
    return prefix / ("python.exe" if (system or platform.system()) == "Windows" else "bin/python")


def cache_root(environ: Mapping[str, str] | None = None, system: str | None = None) -> Path:
    env, system = os.environ if environ is None else environ, system or platform.system()
    if env.get("WHUTOCEANSHIP_CACHE"):
        return Path(env["WHUTOCEANSHIP_CACHE"]).expanduser().resolve()
    if system == "Windows":
        base = Path(env.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    else:
        base = Path(env.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / OWNER


def runtime_candidates(project_root: Path, override: str | None = None, environ: Mapping[str, str] | None = None) -> list[Path]:
    env = os.environ if environ is None else environ
    configured = override or env.get("WHUTOCEANSHIP_RUNTIME_ROOT")
    if configured:
        return [Path(configured).expanduser().resolve()]
    project_id = hashlib.sha256(str(project_root.resolve()).encode("utf-8")).hexdigest()[:12]
    return [project_root / "runtime", cache_root(env) / f"runtime-{project_id}"]


def resolve_python(value: str) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(value))
    candidate = Path(expanded)
    if candidate.is_file():
        return candidate.resolve()
    located = shutil.which(expanded)
    if located:
        return Path(located).resolve()
    raise BootstrapError(f"Requested Python was not found: {value}. Check --python or WHUTOCEANSHIP_PYTHON.")


def select_python(project_root: Path, *, explicit: str | None = None, isolated: bool = False, runtime_override: str | None = None, environ: Mapping[str, str] | None = None, system: str | None = None) -> PythonSelection | None:
    env, system = os.environ if environ is None else environ, system or platform.system()
    requested = explicit or env.get("WHUTOCEANSHIP_PYTHON")
    if requested and not isolated:
        return PythonSelection(resolve_python(requested), "explicit interpreter")
    if not isolated and system == "Windows" and PREFERRED_WINDOWS_PYTHON.is_file():
        return PythonSelection(PREFERRED_WINDOWS_PYTHON.resolve(), "existing mypythorch environment")
    for root in runtime_candidates(project_root, runtime_override, env):
        executable = python_in_prefix(root / "env", system)
        marker_path = root / "managed-runtime.json"
        if marker_path.is_file():
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if marker.get("owner") != OWNER or marker.get("prefix") != str((root / "env").resolve()):
                raise BootstrapError(f"Runtime ownership marker does not match: {marker_path}")
            if executable.is_file() and marker.get("complete"):
                return PythonSelection(executable.resolve(), "managed isolated environment", root)
    return None


def child_environment(executable: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", PYTHONNOUSERSITE="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    env.pop("PYTHONHOME", None)
    if executable is not None and platform.system() == "Windows":
        prefix = executable.parent
        additions = [prefix, prefix / "Library/bin", prefix / "Scripts"]
        env["PATH"] = os.pathsep.join(str(item) for item in additions) + os.pathsep + env.get("PATH", "")
    return env


def run_command(command: list[str], *, env: dict[str, str] | None = None) -> None:
    # A list with shell=False preserves Unicode, spaces, and literal metacharacters.
    display = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
    log(display)
    result = subprocess.run(command, env=env, check=False)
    if result.returncode:
        raise BootstrapError(f"Command exited with code {result.returncode}. See the live output above; no user environment was upgraded.")


def inspect_python(executable: Path, *, quick: bool = True, require_gpu: bool = False) -> tuple[int, dict[str, Any]]:
    command = [str(executable), str(HERE / "doctor.py"), "--json"]
    if quick:
        command.append("--quick")
    if require_gpu:
        command.append("--require-gpu")
    log(f"Checking {executable}")
    try:
        result = subprocess.run(command, env=child_environment(executable), stdout=subprocess.PIPE, stderr=None, encoding="utf-8", errors="replace", timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError(f"The selected Python could not complete the environment check: {exc}") from exc
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BootstrapError(f"Environment check did not return JSON (exit {result.returncode}). Output: {result.stdout[-3000:]}") from exc
    return result.returncode, report


def show_check(report: dict[str, Any], *, full: bool = False, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return
    log(f"Python {report.get('python')}; CUDA available: {report.get('cuda_available', False)}; model checks: not run")
    if full:
        for name, item in report.get("packages", {}).items():
            log(f"{name}: {item.get('installed') or 'missing'}; import={'OK' if item.get('import_ok') else 'FAILED'}")
        for name, value in report.get("checks", {}).items():
            log(f"{name}: {value}")
    for message in report.get("warnings", []):
        log(f"NOTE: {message}")
    for message in report.get("errors", []):
        log(f"ERROR: {message}")


def choose_writable_runtime(project_root: Path, override: str | None = None) -> Path:
    failures: list[str] = []
    for candidate in runtime_candidates(project_root, override):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            if candidate.is_symlink():
                raise BootstrapError(f"Refusing to manage a symbolic-link runtime: {candidate}")
            with tempfile.TemporaryFile(dir=candidate):
                pass
            return candidate.resolve()
        except OSError as exc:
            failures.append(f"{candidate}: {exc}")
    raise BootstrapError("No writable isolated runtime location. Set WHUTOCEANSHIP_RUNTIME_ROOT. " + "; ".join(failures))


def find_conda() -> Path | None:
    candidates: list[Path] = []
    for value in (os.environ.get("CONDA_EXE"), shutil.which("conda")):
        if value:
            candidate = Path(value)
            if candidate.suffix.lower() in {".bat", ".cmd"}:
                candidate = candidate.parent.parent / "Scripts/conda.exe"
            candidates.append(candidate)
    bases = [Path.home() / name for name in ("miniforge3", "miniconda3", "anaconda3")]
    if platform.system() == "Windows":
        bases.append(Path(r"D:\anaconda3"))
    bases.append(cache_root() / "bootstrap/miniforge3")
    for base in bases:
        candidates.append(base / ("Scripts/conda.exe" if platform.system() == "Windows" else "bin/conda"))
    return next((item.resolve() for item in candidates if item.is_file()), None)


def miniforge_urls(system: str) -> tuple[str, str]:
    release = (HERE / "miniforge-release.txt").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-[0-9]+", release):
        raise BootstrapError("Invalid pinned Miniforge release.")
    suffix = "Windows-x86_64.exe" if system == "Windows" else "Linux-x86_64.sh"
    url = f"{MINIFORGE_BASE}/{release}/Miniforge3-{release}-{suffix}"
    return url, url + ".sha256"


def verify_sha256(path: Path, checksum_text: str) -> None:
    match = re.search(r"\b([0-9a-fA-F]{64})\b", checksum_text)
    if not match:
        raise BootstrapError("The official Miniforge checksum file contains no SHA-256 digest.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != match.group(1).lower():
        raise BootstrapError("Miniforge SHA-256 verification failed. The installer was not executed.")


def download_file(url: str, destination: Path) -> None:
    """Stream a download with progress while avoiding a dependency on requests."""
    copied, last_log = 0, time.monotonic()
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as output:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            output.write(chunk)
            copied += len(chunk)
            if time.monotonic() - last_log >= 5:
                log(f"Miniforge download: {copied / (1024 * 1024):.1f} MiB received")
                last_log = time.monotonic()
    log(f"Miniforge download finished: {copied / (1024 * 1024):.1f} MiB")


def install_miniforge(system: str) -> Path:
    prefix = cache_root() / "bootstrap/miniforge3"
    conda = prefix / ("Scripts/conda.exe" if system == "Windows" else "bin/conda")
    if conda.is_file():
        return conda
    if prefix.exists():
        raise BootstrapError(f"Incomplete or foreign Miniforge prefix exists: {prefix}. Choose a different WHUTOCEANSHIP_CACHE; it will not be overwritten.")
    if system == "Windows":
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if not powershell:
            raise BootstrapError("PowerShell is needed to install Miniforge on a machine without conda.")
        run_command([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "install-miniforge.ps1"), "-Prefix", str(prefix)])
    else:
        prefix.parent.mkdir(parents=True, exist_ok=True)
        url, checksum_url = miniforge_urls(system)
        log(f"Downloading the official isolated Miniforge installer: {url}")
        with tempfile.TemporaryDirectory(prefix="whutocean-miniforge-") as temporary:
            installer = Path(temporary) / "Miniforge3.sh"
            try:
                download_file(url, installer)
                with urllib.request.urlopen(checksum_url, timeout=60) as response:
                    checksum = response.read(1024 * 1024).decode("utf-8")
            except OSError as exc:
                raise BootstrapError(f"Official Miniforge download failed: {exc}. Check network access to github.com.") from exc
            verify_sha256(installer, checksum)
            run_command(["bash", str(installer), "-b", "-p", str(prefix)])
    if not conda.is_file():
        raise BootstrapError(f"Miniforge installation did not create conda: {conda}")
    return conda


def write_marker(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def installation_commands(conda: Path, python: Path, spec: dict[str, Any]) -> list[list[str]]:
    prefix = python.parent if platform.system() == "Windows" else python.parent.parent
    pip = [str(python), "-m", "pip", "--isolated", "--disable-pip-version-check", "install"]
    torch_pins = [f"{name}=={item['version']}" for name, item in spec["torch_packages"].items()]
    return [
        [str(conda), "create", "--yes", "--prefix", str(prefix), "--override-channels", "--channel", "conda-forge", f"python={spec['python']}", f"pip={spec['pip']}"],
        pip + ["--index-url", spec["torch_index"], "--extra-index-url", spec["package_index"], "--constraint", str(HERE / "constraints.txt")] + torch_pins,
        pip + ["--index-url", spec["package_index"], "--constraint", str(HERE / "constraints.txt"), "--requirement", str(HERE / "requirements-runtime.txt")],
        [str(python), "-m", "pip", "--isolated", "check"],
    ]


def ensure_managed_environment(root: Path, *, repair: bool = False) -> PythonSelection:
    marker_path, prefix = root / "managed-runtime.json", root / "env"
    if root.is_symlink() or prefix.is_symlink():
        raise BootstrapError(f"Refusing to install through a symbolic-link runtime or environment: {root}")
    old: dict[str, Any] = {}
    if marker_path.exists():
        old = json.loads(marker_path.read_text(encoding="utf-8"))
        if old.get("owner") != OWNER or old.get("prefix") != str(prefix.resolve()):
            raise BootstrapError(f"Runtime ownership marker does not match: {marker_path}")
    elif prefix.exists():
        raise BootstrapError(f"Refusing to install into an unowned environment: {prefix}")
    executable = python_in_prefix(prefix)
    if executable.is_file() and old.get("complete") and not repair:
        return PythonSelection(executable.resolve(), "managed isolated environment", root)
    lock = root / ".setup.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise BootstrapError(f"Another setup may be running: {lock}. After an interrupted setup, verify no setup process is running before removing this lock.") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        marker = {"owner": OWNER, "prefix": str(prefix.resolve()), "complete": False, "spec": load_spec()}
        write_marker(marker_path, marker)
        conda = find_conda() or install_miniforge(platform_key())
        commands = installation_commands(conda, executable, marker["spec"])
        if not executable.is_file():
            # Windows conda also needs its own DLL directory when no shell was activated.
            run_command(commands[0], env=child_environment(python_in_prefix(conda.parent.parent)))
        else:
            # Repair is limited to a runtime bearing our ownership marker.
            log(f"Rechecking packages in the owned runtime: {prefix}")
        for command in commands[1:]:
            run_command(command, env=child_environment(executable))
        marker["complete"] = True
        write_marker(marker_path, marker)
    finally:
        lock.unlink(missing_ok=True)
    return PythonSelection(executable.resolve(), "managed isolated environment", root)


def application_command(executable: Path, arguments: list[str], project_root: Path = PROJECT_ROOT) -> list[str]:
    return [str(executable), str(project_root / "scripts/hull_explore.py"), *arguments]


def parse_request_for_routing(arguments: list[str]) -> dict[str, Any]:
    """Use the application's stdlib-only parser without calling a workflow.

    Reusing read_request keeps JSON validation and explicit CLI overrides in one
    place. Its parser reads only the top-level request and rejects nested request
    and help fields. A private package name avoids collisions with another skill.
    No main(), workflow, doctor, model, NumPy, or torch import is needed here.
    """
    package = PROJECT_ROOT / "scripts/hullexplore"
    suffix = hashlib.sha256(str(package.resolve()).encode("utf-8")).hexdigest()[:12]
    package_name = f"_whut_bootstrap_request_{suffix}"
    if package_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(package_name, package / "__init__.py", submodule_search_locations=[str(package)])
        if spec is None or spec.loader is None:
            raise BootstrapError(f"Cannot load the application's request parser: {package}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(package_name, None)
            raise
    cli = importlib.import_module(package_name + ".cli")
    # A bad request must be reported once by the actual application, not echoed
    # by this preflight and then followed by an unnecessary environment install.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        request, _debug = cli.read_request(arguments)
    return request


def is_lightweight_command(arguments: list[str]) -> bool:
    """Let the application inspect inputs and explain missing optional packages."""
    if not arguments or any(item in {"--help", "-h", "--version", "--dry-run"} for item in arguments):
        return True
    if any(item == "--request" or item.startswith("--request=") for item in arguments):
        try:
            request = parse_request_for_routing(arguments)
        except (Exception, SystemExit):
            # Invalid JSON, unknown fields/options, or a missing file are input
            # errors, so forward them unchanged for normal application reporting.
            return True
        return bool(request.get("dry_run")) or request.get("mode") in {"doctor", "validate"}
    return arguments[0] in {"doctor", "validate"}


def run_application(executable: Path, arguments: list[str]) -> int:
    command = application_command(executable, arguments)
    if not Path(command[1]).is_file():
        raise BootstrapError(f"Application entry point is missing: {command[1]}")
    # Do not chdir: user-supplied relative request/output paths belong to the caller.
    return subprocess.call(command, env=child_environment(executable))


def parse_options(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--python")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--runtime-dir")
    parser.add_argument("--bootstrap-help", action="store_true")
    options, remaining = parser.parse_known_args(argv)
    if options.setup and options.check:
        parser.error("--setup and --check are mutually exclusive")
    if options.python and options.isolated:
        parser.error("--python and --isolated are mutually exclusive")
    if remaining and remaining[0] == "--":
        remaining = remaining[1:]
    return options, remaining


def main(argv: list[str] | None = None) -> int:
    options, arguments = parse_options(sys.argv[1:] if argv is None else argv)
    if options.bootstrap_help:
        print("run.cmd / run.sh [--python PATH] [--check | --setup] [--isolated] [--runtime-dir PATH] [application arguments]\n"
              "--check never installs anything; add --require-gpu to require a GPU.\n"
              "--setup --isolated creates or repairs only the managed project runtime.\n"
              "Priority: --python, WHUTOCEANSHIP_PYTHON, existing Windows mypythorch, managed runtime.\n"
              "Missing runtime: create an isolated conda environment automatically.\n"
              "Existing selected environment with missing dependencies: report errors and stop.\n"
              "See environment/README.md for paths and installation sources.")
        return 0
    platform_key()
    selection = select_python(PROJECT_ROOT, explicit=options.python, isolated=options.isolated, runtime_override=options.runtime_dir)
    if options.check:
        unknown = [value for value in arguments if value not in {"--json", "--require-gpu"}]
        if unknown:
            raise BootstrapError(f"Unknown environment check options: {unknown}")
        if selection is None:
            log("No selected model runtime exists; reporting the bootstrap interpreter without installing anything.")
            selection = PythonSelection(Path(sys.executable), "bootstrap interpreter (not a configured runtime)")
        code, report = inspect_python(selection.executable, quick=False, require_gpu="--require-gpu" in arguments)
        report["selection"] = selection.origin
        show_check(report, full=True, as_json="--json" in arguments)
        return code
    if options.setup and arguments:
        raise BootstrapError("--setup does not accept application arguments. Run the application after setup completes.")
    if not options.setup and is_lightweight_command(arguments):
        if selection is None:
            selection = PythonSelection(Path(sys.executable), "bootstrap interpreter for a lightweight command")
        log(f"Selected {selection.origin}: {selection.executable}")
        return run_application(selection.executable, arguments)
    if selection is None or (options.setup and options.isolated):
        root = selection.runtime_root if selection and selection.runtime_root else choose_writable_runtime(PROJECT_ROOT, options.runtime_dir)
        log(f"Using isolated runtime location: {root}")
        selection = ensure_managed_environment(root, repair=options.setup)
    log(f"Selected {selection.origin}: {selection.executable}")
    code, report = inspect_python(selection.executable, quick=not options.setup)
    show_check(report, full=options.setup)
    if code:
        if selection.runtime_root:
            log("Run --setup --isolated to repair this project's managed runtime.")
        else:
            log("This selected existing environment was not modified. Use --setup --isolated to prepare a separate environment, or select another interpreter with --python.")
        return code
    if options.setup:
        log("Environment setup/check completed. Model checkpoint compatibility is checked by the application.")
        return 0
    return run_application(selection.executable, arguments)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BootstrapError, OSError, ValueError) as exc:
        log(f"ERROR: {exc}")
        raise SystemExit(2)
