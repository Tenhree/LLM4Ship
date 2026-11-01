# Request and command reference

## Contents

- [Invocation](#invocation)
- [Design inputs](#design-inputs)
- [Speed and point-scale inputs](#speed-and-point-scale-inputs)
- [Execution controls](#execution-controls)
- [JSON examples](#json-examples)
- [Point-cloud validation](#point-cloud-validation)

## Invocation

LLM4Ship's project root is the directory containing `SKILL.md`, `scripts/`, `run.cmd` and `run.sh`. The application entry is `scripts/hull_explore.py`. Use the application through the project-root launcher:

```text
run.cmd generate [options]
run.cmd predict [options]
run.cmd optimize [options]
run.cmd validate [options]
run.cmd doctor [options]
```

The launcher's `--check`, `--setup`, `--isolated`, `--runtime-dir PATH` and `--python PATH` options manage the execution environment. Use `--check --json` for a structured environment report, `--check --require-gpu` to require CUDA availability, and `--setup --isolated` to prepare this project's private environment. `--isolated` and `--python` are mutually exclusive. Use `--bootstrap-help` for launcher options. The application's `--help` and each command's `--help` describe its exact accepted flags.

Provide options directly or use `COMMAND --request PATH` with a UTF-8 JSON object. Use English `snake_case` keys corresponding to the CLI flags. An optional `mode` field can supply the subcommand; if both the field and a command are present, they must agree. Explicit command-line values override JSON values. Unknown JSON keys are rejected. Use JSON booleans for boolean options and finite numbers for numerical parameters. Use `generate`, `predict` or `optimize` with `--dry-run` to validate and normalize a request without loading a model or allocating a result folder.

Resolve the request-file path and command-line `--points` path from the invocation working directory. Resolve a relative `points` value inside JSON from the JSON file's own directory. Resolve relative `output` values from the invocation working directory, including when they come from JSON. Quote file paths as single arguments. Prefer JSON for paths containing spaces or Chinese characters. JSON backslashes must be escaped, for example `"D:\\Hull Cases\\方案一"`; forward slashes such as `"D:/Hull Cases/方案一"` are also convenient on Windows.

## Design inputs

Use these for `generate` and `optimize`:

| CLI argument | JSON key | Meaning |
| --- | --- | --- |
| `--length` | `length` | Requested full-scale hull length, m |
| `--beam` | `beam` | Requested full beam, m; never pass half beam |
| `--depth` | `depth` | Molded depth, m |
| `--draft` | `draft` | Operating draft, m; positive and no greater than depth |
| `--displacement-tonnes` | `displacement_tonnes` | Metric tonnes of displacement mass |
| `--displacement-volume` | `displacement_volume` | Full-hull submerged displacement volume, m³ |
| `--block-coefficient` | `block_coefficient` | Conventional `volume/(length*beam*draft)` |
| `--density` | `density` | Water density, kg/m³; default 1025 |

Supply exactly one of displacement tonnes, displacement volume or conventional block coefficient. Report the density assumption when mass is converted to volume. Distinguish the user-facing block coefficient from the trained generator's internal volume-conditioning field.

Reject non-finite, non-positive or mutually inconsistent dimensions. A request is not physically feasible merely because its JSON parses. Use the application's physical-volume and geometry checks to judge a generated candidate.

## Speed and point-scale inputs

| CLI argument | JSON key | Meaning |
| --- | --- | --- |
| `--speed` | `speed` | Positive speed value |
| `--speed-unit` | `speed_unit` | `m/s`, `km/h`, or `kn` |
| `--speed-scale` | `speed_scale` | `model` or `full` |
| `--target-resistance` | `target_resistance` | Strict upper target for 3 m model-scale total resistance, N; required by `optimize` |
| `--points` | `points` | Input half-hull CSV for `predict` or `validate` |
| `--point-scale` | `point_scale` | `model` or `full`; state it explicitly for standalone prediction |
| `--draft-ratio` | `draft_ratio` | `T/D`; may be supplied instead of draft for standalone prediction |
| `--full-length` | `full_length` | Corresponding full-scale length when an already model-scale cloud is paired with a full-scale speed |

Omit all speed inputs for geometry-only generation. Supply a complete speed specification to request generation plus resistance. Do not infer a speed scale from `m/s` alone when the conversation is ambiguous.

For a standalone full-scale cloud, interpret `draft` in that cloud's physical scale; compute `T/D` from the full-depth cloud. For an already model-scale cloud, provide draft in model metres or provide the scale-independent `draft_ratio`. Do not mix full-scale draft with model-scale depth.

Do not infer a corresponding real ship's length from an already normalized 3 m cloud. Ask for it when Froude conversion of a full-scale speed requires it.

## Execution controls

| CLI argument | JSON key | Purpose |
| --- | --- | --- |
| `--output` | `output` | User-selected output directory |
| `--seed` | `seed` | Nonnegative random seed for generation or optimization; default 42 |
| `--device` | `device` | `auto`, `cpu`, or `cuda`; predictor execution requires the supported sparse-convolution runtime |
| `--max-attempts` | `max_attempts` | Generation sampling budget; default 200 latent samples, each with bounded condition calibration |
| `--max-episodes` | `max_episodes` | TD3 exploration budget; default 100 episodes, each with at most 20 initialization samples and five policy steps |
| `--volume-tolerance` | `volume_tolerance` | Relative tolerance for final physical displacement volume; default 0.05 |
| `--dry-run` | `dry_run` | Parse and normalize inputs without model execution or result allocation |

`--output` applies to generation, optimization and standalone prediction. `--volume-tolerance`, `--seed`, `--max-attempts` and `--max-episodes` belong to design requests; the generation loop uses `max_attempts`, while the optimization loop uses `max_episodes`. `--device` and `--debug` are accepted by every application subcommand; `--debug` adds an error traceback after the structured error. Use `doctor --models` to exercise real checkpoint loading; its GPU predictor check runs only on a CUDA device.

Use `validate --points PATH` to read and validate a CSV; adding `--dry-run` still performs the file check and adds the dry-run flag to its report. A prediction dry run also reads and validates its input CSV. Both operations require NumPy and a real file. `doctor --dry-run` only validates the command request; omit `--dry-run` for actual environment/model checks.

A reproducible seed does not guarantee bit-identical GPU output on every device. Record model hashes and runtime versions with the result where available. Avoid increasing search budgets automatically without explaining the new cost to the user.

## JSON examples

### Generate geometry

Invoke `run.cmd generate --request request.json` with:

```json
{
  "length": 90.0,
  "beam": 15.6,
  "depth": 7.5,
  "draft": 3.75,
  "displacement_tonnes": 3000.0,
  "density": 1025.0,
  "seed": 42
}
```

### Generate and predict at a model speed

```json
{
  "length": 90.0,
  "beam": 15.6,
  "depth": 7.5,
  "draft": 3.75,
  "displacement_tonnes": 3000.0,
  "speed": 1.2,
  "speed_unit": "m/s",
  "speed_scale": "model",
  "output": "D:/Hull Cases/Design A"
}
```

### Explore a direct resistance target

Invoke `run.cmd optimize --request request.json` with:

```json
{
  "length": 90.0,
  "beam": 15.6,
  "depth": 7.5,
  "draft": 3.75,
  "displacement_tonnes": 3000.0,
  "speed": 1.2,
  "speed_unit": "m/s",
  "speed_scale": "model",
  "target_resistance": 15.0,
  "max_episodes": 100,
  "seed": 42
}
```

The target above is an illustrative test input. It is not a measured prediction or a guarantee of feasibility.

### Predict the bundled example cloud

For a request stored under the project's `examples/` directory, invoke `run.cmd predict --request examples/predict_benchmark.json` with:

```json
{
  "mode": "predict",
  "points": "../vendor/Predictor/Branchmark/ship1.csv",
  "point_scale": "model",
  "draft_ratio": 0.495283019,
  "speed": 0.8,
  "speed_unit": "m/s",
  "speed_scale": "model"
}
```

The relative point-cloud path is resolved from the JSON file's directory, so this example is independent of the invocation working directory. Preserve the upstream spelling `Branchmark`. Command-line `--points` paths instead resolve from the invocation working directory.

## Point-cloud validation

Require a comma-delimited file with exactly 1000 rows and 3 numeric columns, in XYZ order, without a header. Require finite values. Expect half-hull coordinates with X from bow toward stern, Y from the centre plane toward one side, and Z from bottom toward deck. Coordinates use metres, and the origin must agree with the supplied convention.

The predictor takes a full-depth half-hull cloud and a separate `T/D` condition. It does not require the input to be cropped below the waterline. The structured 20-by-50 grid is used for generated geometry; an uploaded predictor input is not rejected solely because its points have a different row ordering.

For `point_scale=model`, require `Xmax` within 0.2% of 3 m, then use the uniform coordinate factor `3/Xmax`. A full-scale cloud uses its measured `Xmax` as the reference length; if `full_length` is also provided, it must agree within 0.2%. A model-scale cloud may omit `full_length` for a model-scale speed, in which case no full-to-model length ratio is claimed.

Numerical tolerance for a nearly zero origin or a nearly 3 m example cloud is not permission to repair a malformed shape. Apply only the documented, uniform physical-scale conversion. If a cloud has the wrong point count, extra columns, missing values, a header or an inconsistent origin, report the failing requirement and ask for a corrected file. Reuse generated-design draft metadata only when the adjacent result record's stored point-cloud SHA-256 matches the actual input file.
