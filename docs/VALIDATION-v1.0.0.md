# Release validation record

Release: **1.0.0**. Checks completed on **2026-10-20**.

This record distinguishes real checkpoint execution, numerical/control-flow tests, and deployment checks that still require the user's Windows NVIDIA environment. No model was retrained and no resistance result was fabricated.

## Tested runtime

The build environment was Linux x86-64, Python 3.12.14, with a temporary PyTorch **2.5.1+cpu** installation. The checks used NumPy 2.3.5, Matplotlib 3.10.8, Plotly 5.24.1, Stable-Baselines3 2.7.0 and Gymnasium 1.2.3. CUDA was unavailable. This is separate from the deployment runtime recorded in `environment/original-windows.yml` and `environment/runtime-spec.json`.

The preferred deployment interpreter remains `D:\anaconda3\envs\mypythorch\python.exe`. The recorded deployment versions include Python 3.11.10 and PyTorch 2.5.1+cu121. A successful CPU check does not establish Windows process behavior, NVIDIA kernel execution, or sparse-convolution compatibility on a specific GPU.

## Automated test suite

The final suite ran **74 tests: 73 passed and 1 was skipped**. The skipped test requires the native Windows launcher. See [validation-summary.json](validation-summary.json) for the machine-readable record and [validation-tests.txt](validation-tests.txt) for individual results.

| Area | Evidence |
| --- | --- |
| CLI and JSON requests | Unknown/type-invalid fields rejected, explicit CLI overrides honored, JSON point paths resolved relative to the JSON, and dry runs create no design case. |
| Environment routing | Preferred interpreter and explicit overrides, preserving existing environments, JSON-only lightweight commands, malformed-request behavior, Unicode/space argument forwarding, and invocation directory retention. |
| Physical units | Tonnes to cubic metres, density assumptions, conventional block coefficient versus raw conditioning ratio, Froude speed conversion, and uniform XYZ scaling. |
| Geometry | Analytical box/wedge volume comparisons, binary STL topology, symmetry, orientation, invalid waterline rejection, and point order preservation. |
| Prediction inputs | CSV shape/finiteness/origin checks, explicit scale and draft requirements, exact 3 m normalization, and hash-bound reuse of design metadata. |
| Output allocation | Maximum existing suffix plus one, same-date/prefix isolation, filename collision rejection, and active output locks. |
| Search control | Strict target comparison, best feasible fallback across episodes, bounded initialization, fixed TD3 condition and initial resistance, trained observation order/action bounds/horizon, and no fabricated result when infeasible. |
| Export consistency | Predictions consume the persisted geometry; significant repeated-prediction drift or a threshold crossing prevents publication. Invalid resistance during generation causes another candidate attempt. |

Optimization and predictor behavior in the control-flow tests use **explicit synthetic test doubles**. Their numerical resistance values are test fixtures, not measurements from `prediction_best.pth`. They establish branching and file-handling behavior, not hydrodynamic accuracy.

To rerun the suite using a prepared interpreter, run from the project root:

```powershell
& 'D:\anaconda3\envs\mypythorch\python.exe' -m unittest discover -s tests -v
```

Use the actual interpreter reported by the environment checker if the project is installed on another device. The real actor comparison is skipped when PyTorch or Stable-Baselines3 is unavailable.

## Real trained-model checks

### Generator and final geometry

The real `stage2_final.pth` loaded and generated 1000-point half hulls on CPU. Complete generation runs produced CSV, closed full-hull STL, PNG and self-contained HTML for these physical cases:

| Dimensions L/B/D, m | Draft, m | Requested mass, t | Estimated mass from exported geometry, t | Relative mass error |
| --- | --- | --- | --- | --- |
| 90 / 15.6 / 7.5 | 3.75 | 3000 | approximately 3005.01457 | +0.16715% |
| 90 / 15.6 / 7.5 | 5.6 | 5000 | 5006.817935218643 | +0.13636% |

Both runs used density 1025 kg/m³, seed 42 and a **0.5%** configured volume tolerance. The general application default is **5%**. No resistance inference accompanied these CPU generation checks.

The 5000 t run was repeated using the final exact-round-trip CSV writer. The volume obtained from the written CSV matched the selected candidate's physical-volume computation. Its 3858-face mesh was connected, watertight and consistently oriented, with zero boundary and nonmanifold edges. Full-depth mesh volume and waterline-integrated full-depth volume differed by approximately 0.03141%; this is a numerical geometry comparison, not the requested-draft displacement error.

The final example is included in [examples/generated_sample](../examples/generated_sample/README.md). Its geometry and measured values are unchanged; paths in `sample_result.json` were made relative for portability. The PNG was visually inspected. The HTML uses embedded Plotly rather than an external script URL.

Additional targeted geometry probes used two latent vectors, two draft ratios and six coarse conditioning values. Of 24 coarse candidates, 23 passed the new mesh checks and one was correctly rejected for a multivalued waterline. Six local calibration evaluations also passed. This checked handling of real generator geometry and calibration near target volumes; it is not a broad design-domain benchmark.

### TD3 actor compatibility

The real `policy.pth` tensors inside `td3_final.zip` loaded on CPU. The portable actor's actions were compared with a Stable-Baselines3 `TD3Policy` loaded from exactly the same policy state for **64 observations** spanning the configured input ranges. All comparisons passed an absolute tolerance of `1e-7`.

This verifies the `11 -> 256 -> 256 -> 3` actor computation, hidden ReLU activations and Tanh actions. It does not validate complete GPU optimization or prove the quality of a resulting design.

### Checkpoint integrity

All three checkpoint files were checked against [models-manifest.json](../models-manifest.json). Model adapters verify these hashes before loading. The release packager also checks the same hashes and reads the finished archive for CRC errors. Original supporting source, training configuration and the uploaded environment record are retained for traceability.

## Skill and request checks

Both active `SKILL.md` files passed the official Skill format validator. The Pi package manifest explicitly references both files. All five JSON request examples were run as dry runs from outside the project directory. Documentation links and referenced artifacts were checked.

Scenario reviews confirmed Chinese and English routing, clarification when operating draft or scale is missing, and clarification of contradictory inequalities such as “not less than 30 N” paired with a reduction objective. A 90 m hull at a full-scale 18 kn converts to a 3 m model speed of **1.690636960832613 m/s**, with a length ratio of 30:1. This is an analytical conversion, not a predicted resistance.

No authenticated Pi-agent session was run in this build environment. Host package registration is documented against the official Pi package and Skill interfaces; install and reload the package in the user's Pi instance.

## Checks requiring the deployment device

The following were **not executed** here:

- Native Windows `.cmd`/PowerShell execution.
- First-time Miniforge and complete CUDA dependency installation.
- The supplied Predictor's NVIDIA/spconv inference.
- Full TD3 exploration using real predictor outputs.
- CFD or experimental resistance validation.
- General mesh self-intersection testing.

On the Windows NVIDIA machine, run the environment check followed by checkpoint checks:

```powershell
& 'D:\Tools\WhutOceanShip-Skills\run.cmd' --check --require-gpu --json
& 'D:\Tools\WhutOceanShip-Skills\run.cmd' doctor --models --device cuda
```

Then run [tests/run_gpu_smoke.py](../tests/run_gpu_smoke.py) with the verified Python interpreter. It performs real generation plus prediction, re-predicts the exported CSV, and executes two TD3 episodes with a deliberately unattainable strict target to check useful fallback output. It writes a new `GPUCheck-<timestamp>` directory under the invocation directory and never uses hard-coded resistance predictions. See the root [README](../README.md) for the exact PowerShell invocation.

The included 90 m / 5000 t example has `T/D≈0.7467`, outside the TD3 configuration's nominal upper sampling bound of 0.60. Generation succeeded for the checked candidate; this does not remove the TD3 extrapolation limitation. The GPU smoke case uses `T/D=0.50`.

## Source history and rebuilding

The engineering source is recorded in a local Git history. The release includes `docs/source-history.bundle`, which can be inspected with `git bundle verify` or cloned as a source history. Large trained weights are included in the full release ZIP and identified by SHA-256; they are excluded from the source Git history.

To rebuild a complete portable archive from this project, run:

```powershell
& 'D:\anaconda3\envs\mypythorch\python.exe' tools/package_project.py --output '..\WhutOceanShip-Skills-rebuilt.zip'
```

The packager includes explicit entries for the three empty reserved skill directories, excludes temporary/runtime caches and refuses to overwrite an existing archive.
