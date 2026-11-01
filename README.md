# LLM4Ship
From Design Intent to Validated Hull Forms: An LLM-Based Constraint-Aware Agent for Generative Design and Resistance Optimization  

A standalone skill for exploratory ship hull design. **LLM4Ship, version 1.0.0**, brings the existing hull-exploration instructions, application scripts and reference documents into one project-root skill. It preserves the four design and prediction workflows and the supplied trained models.

Skill instructions, new source code and technical documentation are written in English. Users can request work in Chinese or English; Pi interprets the request, supplies structured parameters to the application and responds in the user's language. Quoted Chinese prompts are included as usage examples.

## Contents

- [Capabilities](#capabilities)
- [Install in Pi-agent](#install-in-pi-agent)
- [Migrate from the earlier collection](docs/MIGRATION.md)
- [Python environment](#python-environment)
- [Quick start](#quick-start)
- [Outputs](#outputs)
- [Units and physical meaning](#units-and-physical-meaning)
- [Model implementation](#model-implementation)
- [Project organization](#project-organization)
- [Testing and limitations](#testing-and-limitations)
- [Troubleshooting](#troubleshooting)
- [Reference documentation](#reference-documentation)

## Capabilities

| Workflow | What it does |
| --- | --- |
| Generate geometry | Generate a hull from length, full beam, depth, draft and displacement; export a half-hull CSV, full-hull STL and point-cloud previews. |
| Generate and predict | Perform generation, scale the hull uniformly to a 3 m model and predict total resistance at a specified model speed. |
| Explore a resistance target | Use the supplied trained TD3 actor with the generator and predictor to seek a feasible hull below a specified model-scale resistance. Return the best feasible candidate found if the target is missed. |
| Predict an existing hull | Validate a supplied 1000-by-3 half-hull CSV and predict total resistance from its geometry, draft ratio and model speed. |

The package includes the supplied trained weights and their original supporting source. No training dataset is required for these inference workflows. LLM4Ship registers one skill; the former collection router is retained only as historical documentation.

## Install in Pi-agent

1. Extract the **entire** `LLM4Ship-v1.0.1.zip` archive into an empty, stable folder, for example `D:\Tools\LLM4Ship`. The folder containing `SKILL.md`, `package.json`, `scripts/` and `run.cmd` is the project root. Retain `references/`, `agents/`, `vendor/`, `environment/` and the other bundled directories. When migrating, use a new empty destination to avoid mixing the former collection layout with this standalone package; see [MIGRATION.md](docs/MIGRATION.md).
2. Register that local package with Pi:

   ```powershell
   pi install 'D:\Tools\LLM4Ship'
   ```

3. Restart Pi, or use `/reload` in an existing session. The package exposes `llm4ship`.
4. Invoke the hull skill explicitly when needed:

   ```text
   /skill:llm4ship 请帮我设计一个船长90m、船宽15.6m、型深7.5m、吃水3.75m、排水量3000t的船舶。
   ```

The display name and project folder are `LLM4Ship`. The registered identifier is lowercase, `llm4ship`, to follow the Agent Skills naming convention. The package manifest registers the single root skill:

```json
{
  "pi": {
    "skills": ["./SKILL.md"]
  }
}
```

Pi resolves the manifest path from the package root. This package has no `skills/` collection directory and no additional registered child skills. The former collection router and agent metadata are preserved as `.txt` archives under `docs/`, outside the active Skill registration.

Pi supports local package paths and skills with a `SKILL.md` file. See the official [Pi Packages](https://pi.dev/docs/latest/packages) and [Skills](https://pi.dev/docs/latest/skills) documentation for host-side installation details.

## Python environment

The preferred interpreter is:

```text
D:\anaconda3\envs\mypythorch\python.exe
```

For compatibility, the `WHUTOCEANSHIP_*` environment variables, legacy `WhutOceanShip-Skills` cache directory names and runtime ownership identifiers are retained. They are runtime configuration names; the installed skill and its command are `LLM4Ship` and `/skill:llm4ship`.

The original user environment is preserved in [environment/original-windows.yml](environment/original-windows.yml). Its principal dependencies include:

| Component | Version |
| --- | --- |
| Python | 3.11.10 |
| PyTorch | 2.5.1+cu121 |
| torchvision | 0.20.1+cu121 |
| spconv-cu121 | 2.3.8 |
| cumm-cu121 | 0.7.11 |
| Stable-Baselines3 | 2.7.0 |
| Gymnasium | 1.2.3 |
| NumPy | 2.3.2 |
| numpy-stl | 3.2.0 |
| Matplotlib / Plotly | 3.10.5 / 5.24.1 |

Use the root launcher to resolve the interpreter and keep the invocation working directory:

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' --check --json
```

An explicit `--python PATH` argument or `WHUTOCEANSHIP_PYTHON` environment variable can select another interpreter. For example:

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' --python 'E:\Conda\envs\hulls\python.exe' --check
```

Interpreter selection is explicit `--python`, then `WHUTOCEANSHIP_PYTHON`, then the preferred Windows environment, then the package's managed environment. The launcher reports missing dependencies in an existing selected environment instead of upgrading it. On a supported replacement machine without that environment, the first inference invocation can prepare a private environment automatically.

Use `--setup` to prepare or check the selected environment explicitly. Use `--setup --isolated` to create or repair a private environment while bypassing the preferred interpreter and the environment-variable override; it cannot be combined with `--python`. This is useful when the existing environment is incomplete:

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' --setup --isolated
& 'D:\Tools\LLM4Ship\run.cmd' --check --require-gpu --json
```

`--runtime-dir PATH` or `WHUTOCEANSHIP_RUNTIME_ROOT` selects the managed runtime root. On Linux or in Git Bash, use `bash '/path/to/LLM4Ship/run.sh'` with the same arguments. Automatic runtime installation supports Windows and Linux on x86-64. Keep a compatible NVIDIA driver available for the predictor's GPU sparse-convolution workload.

Migration handles the original YAML's fixed drive prefix and platform-specific packages. The CUDA 12.1 PyTorch wheel index is selected explicitly. Installing Python packages does not install or replace the machine's GPU driver. Consult [environment/README.md](environment/README.md) for the launcher's exact behavior and supported platforms.

Environment checking and model checking are different. `--check --json` reports interpreter selection, packages and runtime compatibility; `--require-gpu` makes unavailable CUDA a failed check. The application command `doctor --models` verifies checkpoint integrity and exercises the actual generator and TD3 actor. It exercises the predictor when CUDA is available and explicitly records skipped GPU checks on CPU. A package list alone does not establish that the three models run on a particular GPU.

Help, version, validation and dry-run commands avoid installing the full model stack. They still need a Python interpreter; reading a point cloud also requires NumPy. A dry run therefore avoids inference and result-folder creation, but it is not an environment-free operation.

## Quick start

Run from the folder where cases should be created. Replace the launcher path below with the actual installed project path. Avoid changing into the skill directory solely to run it.

### 1. Generate geometry

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' generate --length 90 --beam 15.6 --depth 7.5 --draft 3.75 --displacement-tonnes 3000 --seed 42
```

### 2. Generate and predict at a model speed

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' generate --length 90 --beam 15.6 --depth 7.5 --draft 3.75 --displacement-tonnes 3000 --speed 1.2 --speed-unit m/s --speed-scale model --seed 42
```

### 3. Explore a resistance target

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' optimize --length 90 --beam 15.6 --depth 7.5 --draft 3.75 --displacement-tonnes 3000 --speed 1.2 --speed-unit m/s --speed-scale model --target-resistance 15 --max-episodes 100 --seed 42
```

`15 N` is an illustrative target, not an assertion that the model will attain it. The implemented target comparison is strictly `R_model < R_target`.

### 4. Predict the included example cloud

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' predict --points 'D:\Tools\LLM4Ship\vendor\Predictor\Branchmark\ship1.csv' --point-scale model --draft-ratio 0.495283019 --speed 0.8 --speed-unit m/s --speed-scale model
```

The upstream example folder is spelled `Branchmark`. This example uses an existing point cloud; it does not generate a new ship.

### Inspect conversion without inference

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' generate --length 90 --beam 15.6 --depth 7.5 --draft 3.75 --displacement-tonnes 3000 --speed 12 --speed-unit kn --speed-scale full --dry-run
```

This checks input normalization and scale conversion without model inference or a design-result folder. For a 90 m hull, the length ratio is 30:1 and a full-scale speed of 12 kn converts to approximately 1.1270913 m/s at the 3 m model scale.

For complex input, use a UTF-8 JSON request. The included examples contain a `mode` field, so the launcher can determine the command directly:

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' --request 'D:\Tools\LLM4Ship\examples\generate.json'
& 'D:\Tools\LLM4Ship\run.cmd' --request 'D:\Tools\LLM4Ship\examples\user90m5000t_dry_run.json'
```

| Request file | Purpose |
| --- | --- |
| [examples/generate.json](examples/generate.json) | Generate a 90 m hull at a draft ratio of 0.50. |
| [examples/generate_resistance.json](examples/generate_resistance.json) | Generate and predict at a model speed of 1.2 m/s. |
| [examples/optimize.json](examples/optimize.json) | Search for a model resistance below an illustrative 15 N target. |
| [examples/predict_benchmark.json](examples/predict_benchmark.json) | Predict the bundled `Branchmark/ship1.csv` cloud. |
| [examples/user90m5000t_dry_run.json](examples/user90m5000t_dry_run.json) | Inspect the user's original 90 m, 5000 t case with a full-scale speed of 18 kn, including its TD3 draft-ratio warning. It is saved with `dry_run: true`. |

None of these requests fixes an output directory. Paths passed on the command line resolve from the invocation working directory. A relative `points` path inside JSON resolves from that JSON file's directory; relative `output` values always resolve from the invocation working directory. Explicit command-line values override JSON values. See [REQUEST_SCHEMA.md](references/REQUEST_SCHEMA.md) and the installed command's `--help` for all options.

For conversational tests, see [docs/TEST_PROMPTS.md](docs/TEST_PROMPTS.md), which includes Chinese and English examples, input-error cases and expected behavior.

The [preserved CPU-generated sample](examples/generated_sample/README.md) contains real CSV, STL, PNG and HTML outputs for the user's original `L=90 m, B=15.6 m, D=7.5 m, T=5.6 m, displacement=5000 t` case. Its estimated displacement is approximately **5006.82 t**, a **0.13636%** error, within the sample run's **0.5%** tolerance. This historical geometry-only sample contains no resistance prediction. Its accompanying notes describe the executed case; the numerical artifacts were retained unchanged during the standalone refactor.

## Outputs

| Workflow | Default case folder | Geometry and preview files |
| --- | --- | --- |
| Generate | `DesignCase-YYYYMMDD-x` | `DesignCaseShip.csv`, `DesignCaseShip.stl`, `DesignCaseShip.png`, `DesignCaseShip.html` |
| Generate and predict | `DesignCase-YYYYMMDD-x` | The same four files, plus `DesignCaseShip_model_3m.csv` |
| Optimize | `OPTDesignCase-YYYYMMDD-x` | `OPTDesignCaseShip.csv`, `OPTDesignCaseShip.stl`, `OPTDesignCaseShip.png`, `OPTDesignCaseShip.html`, `OPTDesignCaseShip_model_3m.csv` |
| Predict an existing cloud | `PredictionCase-YYYYMMDD-x` | `ResistancePrediction_model_3m.csv` |

Use the executing device's local date. For each date and prefix, choose one more than the highest existing numeric suffix. If `-1` and `-3` exist, the next folder is `-4`. A user-specified `--output` overrides this default location.

The main CSV is a **headerless, 1000-by-3, half-hull XYZ cloud in metres at the requested ship dimensions**. The main STL represents the full hull. STL coordinates are also interpreted in metres; the format itself does not encode physical units.

Every completed workflow writes `request.json` and `result.json`. Design workflows also write `search_history.csv`; their result records contain the physical-volume check, mesh checks, prediction conditions, search outcome and artifact paths. Previews are drawn from the actual half-hull cloud and its mirror. The HTML preview contains its own Plotly JavaScript and can be opened locally; the PNG provides a static alternative. Pi's ability to show the PNG inline depends on the terminal.

For prediction, an auxiliary 3 m point cloud preserves the exact geometry-scale relationship. The final reported resistance always belongs to that model scale. Standalone prediction preserves the supplied input file and writes the auxiliary model cloud and prediction records; it does not generate a new STL or preview.

**If optimization misses the target, a feasible fallback can still be a useful completed result.** The `target_not_met` outcome returns the lowest-resistance feasible candidate found in the bounded search, with exit code `2`. Read its structured result and keep the exported files. A normal completed run exits `0`; invalid input, model errors and absence of a feasible design exit `1`; interruption exits `130`. A design failure after a case folder is allocated records `failure.json` and the available history. Earlier input or runtime failures may have no case folder.

See [OUTPUTS.md](references/OUTPUTS.md) for reporting rules.

## Units and physical meaning

- Interpret full ship length, full beam, depth and draft in metres.
- Convert displacement mass in metric tonnes to volume using the selected water density. The explicit default is `1025 kg/m³`.
- Distinguish conventional block coefficient `volume/(L*B*T)` from the generator's raw-grid volume-conditioning field.
- Convert an existing full-scale cloud with one scale factor for X, Y and Z so that the predictor input has `Xmax=3 m`.
- Convert full-scale speeds using Froude similarity: `V_model=V_full/sqrt(L_full/3)`, after converting the speed to m/s.
- Report total resistance in **N at the 3 m model scale**. This release does not turn it into a full-scale total-resistance or power prediction.

An uploaded predictor cloud must cover the hull's full depth. Its operating draft is a separate input. Obtain `T/D` or a draft in the same scale as the point cloud. A 3 m cloud paired with a full-scale speed additionally needs the corresponding full-scale length. If a generated full-scale CSV is still next to its matching `result.json`, the application can reuse its stored scale and draft only after verifying the cloud's SHA-256 hash. Otherwise those conditions must be supplied. If the source is already a 3 m model and its full-scale length is unknown, report that the full-to-model ratio is unknown rather than inventing one.

See [PHYSICS_AND_MODELS.md](references/PHYSICS_AND_MODELS.md) for formulas, trained-model contracts and source references.

## Model implementation

| Model | Included weight | Inference role |
| --- | --- | --- |
| Generator | `vendor/Generator/stage2_final.pth` | Decode a 3-D latent variable and conditioning inputs into a 20-by-50 half-hull grid. |
| Predictor | `vendor/Predictor/prediction_best.pth` | Predict model-scale total resistance from 1000 XYZ points, `T/D` and speed. |
| TD3 actor | `vendor/Hull_RL_Optimization/runs/td3/models/td3_final.zip` | Adjust the latent design variable with the trained 11-input, 3-action policy. |

Original source files and training configuration are preserved in `vendor/` for traceability. New application code adds parameter normalization, bounded search, physical-volume checks, file allocation, portable model loading and export consistency. Original example scripts are retained as references; the supported user entry is the root launcher.

The predictor's uploaded checkpoint uses saved condition normalization and a `log1p` target transform with its inverse. The adapter preserves that checkpoint behavior. The TD3 inference path preserves the original observation order, action multiplier `0.01`, latent bounds `[-5,5]` and five-step horizon. It reads the `actor.mu` tensors from `policy.pth` inside the supplied TD3 archive into the matching PyTorch network. This avoids restoring older Stable-Baselines3/cloudpickle training objects across Python versions. The supported workflow does not invoke the original `infer_ship.py` example.

The main CSV uses 17 significant digits (`%.17g`) so the search and exported geometry preserve the same coordinate values. The program repeats resistance inference from the saved model input. If that result changes materially or crosses a strict target boundary, it reports a failure because the candidate ranking or target satisfaction cannot be verified.

The original generator normalizes its raw grid by realized coordinate extrema, which can shift the displacement associated with a conditioning value. The integration calibrates that raw scalar condition and measures the final dimensioned cloud's submerged volume. During each TD3 episode the calibrated condition stays fixed so that the policy's observation and transition semantics remain consistent. Acceptance uses the physical volume error, with a default tolerance of 5%; TD3 additionally preserves the trained raw-volume feasibility check. The trained weights are unchanged.

## Project organization

| Path | Purpose |
| --- | --- |
| `SKILL.md` | The single LLM4Ship operational skill |
| `package.json` | Version 1.0.1 package; registers only `./SKILL.md` |
| `agents/openai.yaml` | LLM4Ship display metadata and default prompt |
| `scripts/` | Application and integration modules |
| `references/` | Input, physics and result contracts |
| `environment/` | Original environment record and migration/bootstrap support |
| `run.cmd`, `run.sh` | Windows and Bash launchers |
| `vendor/Generator/` | Original generator sources and trained weight |
| `vendor/Predictor/` | Original predictor sources, trained weight and sample CSV |
| `vendor/Hull_RL_Optimization/` | Original optimization source and trained TD3 archive |
| `tests/` | Automated checks for the integration |
| `examples/` | Five executable JSON requests with no fixed output directory |
| `examples/generated_sample/` | Real CPU-generated 5000 t sample and its execution notes |
| `docs/TEST_PROMPTS.md` | Conversational acceptance examples |
| `docs/VALIDATION-LLM4Ship.md` | Checks performed for the standalone refactor |
| `docs/VALIDATION.md` | Unmodified historical validation of the earlier collection |
| `docs/MIGRATION.md` | Move from the collection to standalone LLM4Ship |
| `docs/MIGRATION-v1.0.1.md` | Historical collection-layout migration instructions |
| `docs/collection-router-v1.0.1.txt`, `docs/collection-agent-v1.0.1.txt` | Archived collection metadata; neither is a callable Skill |

`SKILL.md`, `scripts/`, `references/` and `agents/` share the same project root as the launchers, environment support, trained model assets, request examples and tests. Resolve application paths from that root. Always use the root launcher while preserving the invocation working directory for case outputs.

## Testing and limitations

Start with a no-inference conversion example, then run `doctor --models`, generation and the bundled predictor example on the supported NVIDIA machine. The included automated checks test the integration's contracts. Interpret the release's validation report according to its actual tested runtime: CPU tests cannot establish GPU sparse-convolution execution or resistance accuracy. Native Windows/NVIDIA behavior needs validation on that environment; the documentation does not present an unexecuted GPU result as a measured resistance.

See [docs/VALIDATION-LLM4Ship.md](docs/VALIDATION-LLM4Ship.md) for checks executed after the standalone refactor. [docs/VALIDATION.md](docs/VALIDATION.md) is preserved as historical collection evidence: its version 1.0.1 record reports 74 automated tests, with 72 passed and two explicitly skipped, plus five root-launcher dry runs and all three model checksums. The earlier version 1.0.0 CPU compatibility check compared the portable actor with Stable-Baselines3 using the same real checkpoint over 64 sampled observations; all 64 comparisons passed. Those historical records are not claims of new execution after renaming. The actor check verifies actions, not resistance or optimization quality.

For a real NVIDIA validation run, use the actual Python executable reported by the environment check to run `tests/run_gpu_smoke.py` directly. For example, in PowerShell:

```powershell
$hullCheck = (& 'D:\Tools\LLM4Ship\run.cmd' --check --require-gpu --json) -join "`n"
if ($LASTEXITCODE -ne 0) { throw 'Resolve the reported environment errors before running GPU checks.' }
$hullPython = ($hullCheck | ConvertFrom-Json).executable
& $hullPython 'D:\Tools\LLM4Ship\tests\run_gpu_smoke.py'
```

The script creates a new `GPUCheck-<timestamp>` directory under the invocation working directory. It exercises generation with actual resistance prediction, repeats prediction from the exported CSV using its verified metadata, and runs two TD3 episodes with an intentionally unattainable target to check the feasible-fallback path. A passing run writes `gpu_smoke_result.json` with its measured values. **This script was not executed in the CPU-only build environment.** If the bounded TD3 search finds no feasible candidate, it fails the check rather than reporting a fallback that does not exist.

The nominal TD3 training configuration covers `B/L=0.15–0.25`, `D/L=0.07–0.17`, `T/D=0.35–0.60`, raw conditioning values `0.10–0.50`, and model speeds `0.6–1.8 m/s`. These are configured sampling ranges rather than an accuracy guarantee.

The user's illustrative `L=90 m, B=15.6 m, D=7.5 m, T=5.6 m, displacement=5000 t` case has `T/D≈0.7467`. It is a useful extrapolation test for TD3 and must be identified as outside that configured draft-ratio range. The quick-start cases use `T/D=0.50` to avoid that particular extrapolation.

The physical-volume tolerance is configurable; the default is 5%. The program estimates submerged volume by integrating piecewise-linear waterline areas up to the specified draft and reports its error. Bounded sampling can fail to find a feasible hull, and bounded TD3 exploration can fail to reach a target. Generation defaults to at most 200 latent attempts; optimization defaults to at most 100 episodes, with up to 20 initial-latent trials and five policy steps per episode. A target hit can stop the search early. The fallback is the best feasible design encountered in that bounded search, not a proof of global optimality. Mesh closure and orientation checks do not constitute a general self-intersection test, and they do not independently validate a learned hydrodynamic prediction against CFD or experiments.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Pi does not show the skill | Verify that the complete local package was registered, inspect startup diagnostics, and run `/reload`. Use `/skill:llm4ship` explicitly. |
| Pi still shows the former collection's commands after migration | Inspect `pi list` and the configured skill locations. Follow [MIGRATION.md](docs/MIGRATION.md) to replace the previous package registration with LLM4Ship. |
| The preferred interpreter is not found | Use the bootstrap's setup path or provide `--python`/`WHUTOCEANSHIP_PYTHON`. |
| An existing environment is missing packages | Read the reported dependency list and use an isolated setup if appropriate. Preserve the existing working environment. |
| CUDA or spconv cannot execute | Read `--check` output and verify the compatible NVIDIA driver, GPU and installed CUDA-build packages. |
| Point-cloud validation fails | Provide the expected headerless 1000-by-3 half-hull XYZ file. Keep draft and speed conditions explicit. |
| Prediction asks for draft | Supply `T/D` or a draft in the same scale as the cloud; geometry alone does not determine operating draft. |
| Target was not met | Open the structured result. A feasible fallback may already be exported with `target_not_met`. |
| No feasible design was found | Review the specified dimensions, displacement, tolerance, domain notes and search budget. Do not interpret this as a successful design. |
| A case-output filename already exists | Choose another output directory or retain the automatically allocated next case. |
| Inline preview is unavailable | Open the exported PNG or self-contained HTML preview from the result folder. |

## Reference documentation

- [Pi Skills](https://pi.dev/docs/latest/skills)
- [Pi Packages](https://pi.dev/docs/latest/packages)
- [Pi slash commands and resource reload](https://pi.dev/docs/latest/slash-commands)
- [Pi on Windows](https://pi.dev/docs/latest/windows)
- [Pi terminal capabilities](https://pi.dev/docs/latest/terminal-setup)
- [PyTorch previous versions](https://pytorch.org/get-started/previous-versions/)
- [Stable-Baselines3 2.7.0 installation](https://stable-baselines3.readthedocs.io/en/v2.7.0/guide/install.html)
- [Stable-Baselines3 2.7.0 changelog](https://stable-baselines3.readthedocs.io/en/v2.7.0/misc/changelog.html)

Model-specific behavior is grounded in the user-supplied source and checkpoint metadata. Preserve those assets and their provenance when modifying the integration.
