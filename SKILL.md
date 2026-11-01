---
name: llm4ship
description: Generate exploratory ship hulls from length, beam, depth, draft and displacement; export a half-hull CSV, full-hull STL and point-cloud previews; predict 3 m model-scale total resistance; or use the supplied TD3 actor to search below a resistance target. Use when users name LLM4Ship, request ship hull generation, resistance prediction from a point cloud, or resistance-constrained hull exploration in Chinese or English.
---

# LLM4Ship

Translate a Chinese or English engineering request into the parameters of the bundled application. Use the supplied trained weights. Report measured program results and actual file paths in the user's language.

Read [REQUEST_SCHEMA.md](references/REQUEST_SCHEMA.md) for argument details. Read [PHYSICS_AND_MODELS.md](references/PHYSICS_AND_MODELS.md) before converting displacement, speed or geometry scale. Read [OUTPUTS.md](references/OUTPUTS.md) when interpreting status and delivering files.

## Select one workflow

| User intent | Application command | Required inputs |
| --- | --- | --- |
| Generate geometry | `generate` | Full dimensions `length`, `beam`, `depth`, `draft`, and one displacement specification |
| Generate geometry and estimate resistance | `generate` with speed | The same design inputs, plus a speed with unit and scale |
| Explore below a resistance target | `optimize` | The design inputs, design speed, and model-scale `target_resistance` in N |
| Predict a supplied hull | `predict` | Point-cloud path and scale, speed with unit and scale, and draft or `draft_ratio` |

Use the model names as implementation identifiers, not as alternatives for the user to choose. Geometry uses `stage2_final.pth`; prediction uses `prediction_best.pth`; exploration uses the trained TD3 actor from `td3_final.zip` with the generator and predictor.

## Collect and interpret inputs

1. Interpret length, full beam, molded depth and draft in metres. Treat displacement written as tonnes as metric tonnes of mass. Use `density=1025` kg/m³ when unspecified and state the assumption in the result. Accept an explicit displacement volume or conventional block coefficient as alternatives.
2. Reuse previously confirmed parameters only when they apply to the same hull and operating condition. Do not infer an operating draft solely from a full-depth point cloud. Ask for draft or `T/D` when missing.
3. Distinguish the input speed's scale from its unit. Use explicitly model-scale m/s directly. Convert an explicitly full-scale speed using Froude similarity. If the scale of an m/s speed is ambiguous, ask the user. Do not treat tokens such as `xxx` or `m/s` without a number as numerical input.
4. Interpret a resistance target as a 3 m model-scale value in N. The implemented optimization target is strictly below the supplied value. Ask when the user's inequality conflicts with a reduction objective, or when they explicitly request a different target direction. Do not silently turn an explicit lower bound into an upper bound.
5. Preserve the user's output directory. If unspecified, let the application allocate a dated case folder under the invocation working directory. Do not change to the skill directory before launching a design task.
6. Validate user-supplied point clouds before prediction. Require an unheaded, finite 1000-by-3 XYZ CSV representing a half hull with the documented axes and origin. Request corrected data when invalid. Do not resample, add points, guess columns, or strip an unknown header to make a file pass.

Keep engineering input collection separate from shell syntax. Prefer a UTF-8 JSON request file for complex requests or paths containing spaces or non-ASCII characters. Write real JSON with English `snake_case` keys; pass it as one quoted file argument. Do not interpolate a user's free-form prompt into a shell command.

## Locate the project and runtime

LLM4Ship is a standalone skill. The directory containing this `SKILL.md` is the project root, where `package.json`, `run.cmd` and `run.sh` are also located. Resolve `scripts/`, `references/`, `vendor/` and `environment/` directly from this directory. Resolve a command-line `--points` path and every relative output path from the user's working directory. Resolve a relative `points` value inside a JSON request from that JSON file's directory. The request file's own path is relative to the invocation working directory.

Prefer `D:\anaconda3\envs\mypythorch\python.exe` through the provided launcher. Respect an explicit `--python` override or `WHUTOCEANSHIP_PYTHON`. Use the existing working environment first. Let the bundled bootstrap establish an isolated environment on a supported replacement machine when no preferred environment exists. Surface specific installation failures and preserve their logs.

The `WHUTOCEANSHIP_*` environment variables, legacy cache names and runtime ownership identifiers remain in use for compatibility. The skill's display name is `LLM4Ship`, and its registered identifier is `llm4ship`.

Use the root launchers:

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' --check --json
& 'D:\Tools\LLM4Ship\run.cmd' generate --request '.\request.json'
```

```bash
bash '/path/to/LLM4Ship/run.sh' generate --request './request.json'
```

Replace the example project path with the actual installed path. `--check` reports environment status without installation; add `--require-gpu` when GPU availability must be a successful check. `--setup` checks the selected existing environment or prepares a missing private one. Use `--setup --isolated` to create or repair this project's private environment while bypassing the preferred interpreter; do not combine `--isolated` with `--python`. Use application `doctor --models` for real checkpoint execution checks; CPU execution skips the GPU predictor explicitly.

Use the application `--help` for the installed interface. Use `generate`, `predict` or `optimize` with `--dry-run` to inspect request normalization and scale conversion before an expensive task; it performs no model inference and creates no result case. Use `validate --points PATH` for actual CSV format checking; adding `--dry-run` still checks the file. Lightweight commands still require an available Python interpreter; prediction dry runs and CSV validation also require NumPy. Omit `--dry-run` from `doctor` when actual environment/model checks are required.

The application entry is `scripts/hull_explore.py` relative to this skill's project root. Call it through the root launchers. Keep the original example scripts in `vendor/` as source references. The integrated launcher controls algorithms, output allocation and errors consistently across the four workflows.

## Execute geometry generation

For a design request without a speed, run `generate`. For a design plus resistance request, run `generate` with a complete speed specification. Let the application perform bounded latent sampling and its physical-volume acceptance check. Report the requested and estimated actual displacement, tolerance and any training-domain notes from the result.

Preserve the trained generator's internal conditioning convention. Do not replace its internal `CB` field with the conventional naval-architecture block coefficient. Let the application handle the conversion and any condition calibration required by output normalization. Do not manually stretch one coordinate direction to force a desired displacement.

Deliver `DesignCaseShip.csv` and `DesignCaseShip.stl` at the requested dimensions, plus `DesignCaseShip.png` and `DesignCaseShip.html`. Optimization uses the corresponding `OPTDesignCaseShip` basename. Display the actual point-cloud preview when the host supports images; otherwise provide its path and the self-contained HTML preview. Do not substitute an illustrative generated image for model geometry.

## Execute resistance prediction

For generation plus prediction, use the application's uniform conversion of the generated hull to `Xmax=3 m`. Keep the principal geometry outputs at the user's requested ship scale.

For standalone prediction, validate the supplied CSV and obtain its point scale and draft condition. The application can reuse the same folder's `result.json` only when its recorded cloud hash matches the input file; otherwise obtain the missing information. If the cloud is already model-scale and a full-scale speed is supplied, obtain the corresponding full-scale length. Use that length only for the speed scale ratio; retain the cloud's model dimensions. A standalone prediction creates a `PredictionCase-YYYYMMDD-x` folder unless the user selects a directory.

Report total resistance only in N at the 3 m model scale. Include the actual model speed and the length scale ratio when a full-scale length is known. For a model-only cloud without that length, state that the full-to-model ratio is unspecified. Preserve the trained predictor's saved condition normalization and inverse target transform. Do not refit normalizers, crop the cloud at draft, or report the model value as full-scale resistance.

## Execute TD3 exploration

Run `optimize` with a direct target in N. Preserve the trained observation order, latent dimension, action scaling, latent bounds and episode horizon. Let the supplied implementation load the archive's `actor.mu` tensors for inference without recovering historical SB3 or cloudpickle objects. Keep the calibrated raw-volume condition fixed during each episode; retain the independent final physical-volume gate.

Track feasible candidates among initial samples and evaluated TD3 steps. Apply the external physical-volume and geometry checks before accepting or exporting a design. Stop according to the configured search budget and target policy; do not promise a global optimum.

Interpret outcomes explicitly:

- If a valid exported design is below the target, report success and its verified model-scale resistance.
- If the target is missed but a feasible design exists, deliver the best feasible design found in the bounded search, report `target_not_met`, and state both its resistance and the target. An exit code of `2` for this outcome accompanies useful output files; inspect the result before treating the process as a generic failure.
- If no feasible design exists, report that outcome and the recorded reason. Do not fabricate a hull or label an infeasible candidate as satisfying the design requirements.

Flag training-domain notes. In particular, the user's illustrative `T=5.6 m, D=7.5 m` gives `T/D≈0.7467`, above the TD3 configuration's nominal upper sampling bound `0.60`. Treat an extrapolated result as such; do not claim that the training domain covers it.

## Deliver the result

Read the program's structured result and inspect reported artifact paths. Design runs write `request.json`, `search_history.csv` and `result.json`; a failed search may instead leave `failure.json` with its history. Prediction runs write `request.json`, `result.json` and `ResistancePrediction_model_3m.csv`. Ordinary errors return exit code `1`; user interruption returns `130`. Verify that promised files exist before claiming completion. Include:

- The status and absolute output directory.
- For design workflows, the half-hull CSV and full-hull STL paths, point-cloud preview paths, requested dimensions and the physical-volume acceptance result.
- For standalone prediction, the supplied input and saved 3 m model-cloud paths.
- When applicable, model speed in m/s, 3 m model-scale total resistance in N, and the full-scale-to-model length ratio.
- For exploration, the target comparison, the search outcome and any domain notes.

If the final repeated prediction changes materially or crosses the strict target threshold, report the application's consistency failure. Do not reinterpret it as a successful design or a verified feasible fallback.

Use the user's language for the response. For example, convey that creation is complete and identify the output folder in Chinese when the request was Chinese. Quote only numbers returned by the application or derived transparently from confirmed inputs.
