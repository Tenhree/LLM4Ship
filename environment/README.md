# Runtime setup and diagnostics

LLM4Ship keeps the existing `WHUTOCEANSHIP_*` environment variables, legacy
`WhutOceanShip-Skills` cache directory names and runtime ownership identifiers
for compatibility with previously configured environments. The renamed skill
still prefers `D:\anaconda3\envs\mypythorch\python.exe` on Windows.

The launchers use an existing working environment when one is configured. They
create an isolated environment only when a model command needs one and no model
environment has been selected. The existing `mypythorch` environment, other
Python environments, shell initialization, system PATH, and NVIDIA drivers are
never upgraded or edited by setup.

## Start on Windows

Run these commands from Command Prompt, replacing the project path as needed:

```bat
"D:\Projects\LLM4Ship\run.cmd" --help
"D:\Projects\LLM4Ship\run.cmd" --check
"D:\Projects\LLM4Ship\run.cmd" --check --require-gpu
"D:\Projects\LLM4Ship\run.cmd" --setup --isolated
"D:\Projects\LLM4Ship\run.cmd" --python "D:\anaconda3\envs\mypythorch\python.exe" doctor --models
```

From PowerShell, put `&` before a quoted launcher path. From Git Bash (including
a Pi session using Git Bash), use `bash /path/to/LLM4Ship/run.sh`.
All launchers preserve the caller's working directory. Relative command-line
request, point cloud, and output paths are resolved from that directory. A
relative `points` value inside a request JSON is resolved from the JSON file's
directory; `output` inside JSON remains relative to the caller. Quote paths
containing spaces or shell metacharacters. Unicode arguments are passed through
native process APIs; no application argument is evaluated as Python or a shell
command by bootstrap.

## Start on Linux

```sh
bash /path/to/LLM4Ship/run.sh --help
bash /path/to/LLM4Ship/run.sh --check --json
bash /path/to/LLM4Ship/run.sh --setup --isolated
bash /path/to/LLM4Ship/run.sh --python /path/to/python doctor --models
```

Automatic installation supports Windows and Linux on x86-64. NVIDIA GPU
availability is checked separately. The supplied resistance model uses CUDA
sparse convolutions; CPU-only diagnostics do not certify resistance prediction
or optimization. Setup does not install a GPU driver or CUDA system toolkit.

## Interpreter selection

The model interpreter is selected in this order:

1. `--python PATH`, then `WHUTOCEANSHIP_PYTHON`.
2. On Windows, `D:\anaconda3\envs\mypythorch\python.exe`, if it exists.
3. A complete isolated runtime belonging to this project.
4. For a normal model command or `--setup`, a newly created isolated runtime.

`--isolated` skips the explicit environment variable and preferred Windows
environment. It cannot be combined with `--python`. A selected existing
environment with missing packages, import failures, or a broken NumPy/PyTorch
bridge produces a detailed error. It is not repaired implicitly. To prepare a
separate environment, run `--setup --isolated`.

The managed environment normally lives at `PROJECT/runtime/env`. If the project
is not writable, it uses a project-specific directory under the user cache.
`--runtime-dir PATH` or `WHUTOCEANSHIP_RUNTIME_ROOT` chooses the managed root;
the Python environment is created at `PATH/env`. Combine this override with
`--isolated` to bypass the preferred existing interpreter.

The cache defaults to `%LOCALAPPDATA%\WhutOceanShip-Skills` on Windows and
`${XDG_CACHE_HOME:-~/.cache}/WhutOceanShip-Skills` on Linux.
`WHUTOCEANSHIP_CACHE` overrides it. These settings affect only the new private
runtime; they do not relocate an existing user environment. Setup writes an
ownership marker and uses a setup lock. It refuses to install into an unmarked
environment or through a runtime symlink.

## Command behavior

| Command | Behavior |
| --- | --- |
| `--bootstrap-help` | Describe launcher flags using the standard library. |
| `--help`, `--version`, no arguments | Forward to the application without checking or installing model packages. |
| Any subcommand with `--dry-run` | Forward input and scale checks without installing model packages. |
| `validate` | Forward to geometry validation; NumPy must already be available. |
| `doctor` / `doctor --models` | Forward diagnostics without silently installing or repairing packages; model checks are owned by the application. |
| `--check` | Inspect the selected environment without installing anything. If none exists, inspect the launcher Python and label it accordingly. |
| `--check --json` | Write the environment report as JSON to stdout; launcher logs remain on stderr. |
| `--check --require-gpu` | Additionally fail if NVIDIA CUDA is unavailable. |
| `--setup` | Check an existing selected environment, or provision a missing private environment. |
| `--setup --isolated` | Create or repair only the private runtime owned by this project. |
| `generate`, `predict`, `optimize` | Select/provision an environment, check imports and the NumPy/Tensor bridge, and invoke the application with the same arguments. |

The same routing applies when `mode` or `dry_run` is supplied in JSON. Bootstrap
uses the application's standard-library-only request parser, so explicit CLI
values retain the same precedence and malformed JSON, unknown fields and parser
errors go directly to the application for reporting without installing packages.
Nested `request` and `help` JSON fields are rejected; bootstrap does not follow
another request file named inside the JSON.

The lightweight commands still need a Python interpreter. If none exists, the
Windows/Unix launcher can install a private Miniforge bootstrap to obtain
Python. `--check` is the exception: it reports the absence of Python and installs
nothing. Prediction dry runs and geometry validation need NumPy; the application
reports a missing NumPy dependency rather than installing the full GPU stack.
For completely offline help, use a pre-existing Python interpreter or read the
project's documentation.

An existing interpreter of Python 3.9 or newer can run bootstrap itself. The
project's supported model runtime is Python 3.11 or newer, with 3.11.10 selected
for new managed environments. Core CLI compatibility requirements are reported
by the application and environment doctor.

## What gets installed

`original-windows.yml` is the user's original environment export, copied
verbatim. It retains Windows-specific conda builds, its original channels, and
the original absolute prefix. It is an archival reference; bootstrap does not
feed that file directly into conda on another machine.

`runtime-spec.json`, `requirements-runtime.txt`, and `constraints.txt` describe
the portable inference runtime. Principal pins are:

| Component | Version |
| --- | --- |
| Python / pip | 3.11.10 / 24.3.1 |
| PyTorch / torchvision | 2.5.1+cu121 / 0.20.1+cu121 |
| NumPy / SciPy / pandas | 2.3.2 / 1.15.1 / 2.2.3 |
| spconv-cu121 / cumm-cu121 | 2.3.8 / 0.7.11 |
| Stable-Baselines3 / Gymnasium | 2.7.0 / 1.2.3 |
| numpy-stl / matplotlib / Plotly | 3.2.0 / 3.10.5 / 5.24.1 |
| cloudpickle / tensorboard | 3.1.2 / 2.18.0 |

New runtime creation uses an existing conda executable if available. Otherwise,
bootstrap downloads the official Miniforge release pinned in
`miniforge-release.txt`, checks its official SHA-256 checksum, and installs it
under the private cache. Miniforge supplies the bootstrap and conda; its base
Python version may differ from the separately created model environment.
Windows installation is for the current user, with Python registration and PATH
changes disabled. PowerShell execution policy is bypassed for the launched
process only; no persistent policy is changed.

Conda creates Python and pip from `conda-forge` using explicit channels. PyTorch
and torchvision are installed from the official CUDA 12.1 wheel index, with
PyPI available for their ordinary dependencies. The remaining packages come
from PyPI. Constraints retain the selected torch build during the second pip
phase. Every pip command targets the new environment's explicit Python;
`pip --isolated` ignores personal pip configuration. No global pip upgrade is
performed. A final `pip check` verifies installed package requirements.

The listed application dependencies are pinned. Transitive dependencies that
are not in the constraints file are resolved at setup time; this is not a
bit-for-bit lock of the original Windows environment. Installation needs network
access, sufficient disk space for CUDA wheels, and available wheels for the
selected platform. Setup prints subprocess output as it runs. If download,
package resolution, or GPU checks fail, the error is retained; setup does not
switch package versions or alter the driver silently.

Official distribution references:

- [PyTorch previous versions and CUDA 12.1 installation commands](https://pytorch.org/get-started/previous-versions/)
- [Miniforge installer documentation](https://github.com/conda-forge/miniforge)
- [Pinned Miniforge release](https://github.com/conda-forge/miniforge/releases/tag/26.3.2-3)
- [spconv-cu121 on PyPI](https://pypi.org/project/spconv-cu121/2.3.8/)
- [cumm-cu121 on PyPI](https://pypi.org/project/cumm-cu121/0.7.11/)

## Diagnostics and limits

`python environment/doctor.py --json` checks the active interpreter directly.
It reports versions and import failures, performs a real NumPy-to-Tensor-to-
NumPy round trip, discovers CUDA, and runs a tiny spconv GPU convolution when
CUDA is available. `--quick` skips that convolution; ordinary model startup
uses quick mode. Environment checks never deserialize model checkpoints.
Use the application command `doctor --models` for the checkpoint checks.

Version differences in an existing environment are reported as differences;
they are not automatically classified as an inability to load a model. Actual
imports, the NumPy bridge, GPU kernel checks, and application model checks supply
that evidence. The original policy was trained with a different Linux software
stack; its actor is loaded by the application without reconstructing a pickled
Stable-Baselines3 object. The recorded Windows SB3 version is retained.

If a setup process was interrupted, read its error before retrying. An
incomplete project-owned runtime can be retried with `--setup --isolated`.
An existing unowned or incomplete Miniforge prefix is never overwritten; choose
a new `WHUTOCEANSHIP_CACHE` or inspect that directory manually. A stale setup
lock may be removed only after confirming no setup process is running. Windows
native launch and NVIDIA kernels must be verified on the deployment machine;
Linux unit tests cannot validate those platform-specific operations.
