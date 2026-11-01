# Output and result interpretation

## Directory allocation

Honor an explicit output directory. Otherwise allocate a new folder below the invocation working directory using the executing device's local date:

| Workflow | Default directory |
| --- | --- |
| Geometry generation | `DesignCase-YYYYMMDD-x` |
| Generation with prediction | `DesignCase-YYYYMMDD-x` |
| TD3 exploration | `OPTDesignCase-YYYYMMDD-x` |
| Existing-cloud prediction | `PredictionCase-YYYYMMDD-x` |

Choose `x` as one more than the largest existing numeric suffix for the same prefix and date. Existing folders `-1` and `-3` produce the next index `-4`. Keep all three prefixes independent. Do not use the skill installation directory as the default output location unless it is also the user's invocation working directory. Relative output paths, including those inside JSON requests, resolve from the invocation working directory.

Preserve prior results when a user-selected directory would cause a filename collision. Inspect the application's error and resolve the destination; do not delete an existing case automatically.

## Principal artifacts

| Artifact | Generation | Optimization |
| --- | --- | --- |
| Half-hull point cloud | `DesignCaseShip.csv` | `OPTDesignCaseShip.csv` |
| Full-hull STL | `DesignCaseShip.stl` | `OPTDesignCaseShip.stl` |
| Static preview | `DesignCaseShip.png` | `OPTDesignCaseShip.png` |
| Interactive preview | `DesignCaseShip.html` | `OPTDesignCaseShip.html` |
| Model-scale prediction input | `DesignCaseShip_model_3m.csv`, when predicting | `OPTDesignCaseShip_model_3m.csv` |

The CSV contains 1000 numeric XYZ rows without a header. Coordinates are in metres at the requested ship scale and are written with `%.17g` precision to preserve the search geometry through the file round trip. Y represents half breadth. The STL contains the mirrored full hull and its closure surfaces. STL itself has no unit field; interpret its coordinates as metres as documented in the result.

The PNG and self-contained HTML show the actual half-hull cloud and its mirror. The HTML includes its Plotly JavaScript, so viewing it does not require a CDN. Use the exact paths reported by the application; preview filenames have `.png` and `.html` extensions with no `_preview` suffix.

When predicting, retain the documented relationship between principal geometry and the uniformly scaled 3 m predictor input. The model-scale cloud is an auxiliary prediction input, not a replacement for the requested full-scale design CSV.

Standalone prediction writes `ResistancePrediction_model_3m.csv`, `request.json` and `result.json` to its prediction case. It preserves the supplied source CSV and does not generate a new STL or preview.

## Structured records

Every completed case includes `request.json` and `result.json`. Generation and optimization also include `search_history.csv`. The design history records each evaluation's latent values, raw conditioning value, raw and physical volume errors, resistance when evaluated, status and detail. Search history may contain rejected candidates; only the exported result is the selected design.

For design results, useful `result.json` fields include:

| Field | Meaning |
| --- | --- |
| `status`, `mode`, `output_directory` | Run outcome, requested workflow and absolute destination. |
| `design` | Normalized main dimensions, displacement, density and tolerance. |
| `actual_displacement_volume_m3`, `actual_displacement_tonnes`, `physical_volume_relative_error` | Final point cloud's estimated submerged displacement and its error. |
| `candidate` | Selected latent values, calibrated condition, feasibility data and episode/step when applicable. |
| `speed` | Input speed and units, input scale, model speed and length ratio. |
| `model_total_resistance_N`, `resistance_scale` | Model prediction and its 3 m scale; null for generation without prediction. |
| `target_resistance_N`, `target_operator`, `target_met`, `selection` | Strict comparison and the selected candidate's search outcome. |
| `warnings`, `limitations`, `mesh_quality` | Applicable training-domain notes and verification boundaries. |
| `artifacts` | Absolute paths for the main cloud, STL, previews and model cloud when present. |
| `point_cloud_sha256` | Hash connecting the final CSV to this design metadata. |

Standalone prediction uses an `input` record for source-cloud, point-scale and draft metadata, plus `speed`, `model_total_resistance_N` and `artifacts.model_point_cloud`. The length ratio is stored in `speed.length_scale_ratio_full_to_model`. It does not claim the uploaded hull satisfies a newly requested displacement.

If a design fails after a case folder has been allocated, inspect `failure.json` and the available `search_history.csv`. Failures during input validation or runtime/model preflight may occur before a folder is allocated. Do not claim those failures produced a completed design.

## Status and threshold handling

Distinguish successful target satisfaction, useful fallback output and failure:

| Outcome | Exit code | Required user-facing interpretation |
| --- | --- | --- |
| `completed`: valid design exported | `0` | Creation completed; provide the absolute output folder and artifact paths. |
| `completed`: resistance target achieved | `0` | Report the verified model resistance, target, model speed and scale ratio. |
| `completed`: standalone prediction | `0` | Report the actual prediction conditions, result and saved model input. |
| `target_not_met` | `2` | Deliver the best feasible design found and explain that it remains above or equal to the strict target. |
| `error`: no feasible candidate | `1` | Report that no acceptable design was found within the budget and include the recorded reason. |
| `error`: invalid input, environment or model failure | `1` | State the actual error; do not claim that design or prediction finished. |
| `interrupted` | `130` | State that execution was interrupted; inspect available files before describing any result as complete. |

For the documented `target_not_met` outcome, exit code `2` accompanies an exported feasible fallback. Read the structured result and retain those files. Do not discard them or report the entire run as an unqualified failure solely because the exit code is nonzero.

The comparison is strictly `R_model < R_target`, saved as `target_operator: "lt"`. Equality does not satisfy the target. On design export, the final prediction is evaluated again from the saved cloud and compared with the search prediction. A difference outside the implementation's numerical tolerance, or any crossing of the strict target boundary, causes an explicit failure before delivery of a successful design; the application cannot verify the ranking or target satisfaction in that situation.

Do not call the best observed candidate a globally optimal hull. State the actual search budget and evaluated-result scope.

## Minimum result content

For generation, report requested main dimensions, density assumption if used, requested displacement and the final estimated displacement with its relative error. Include the output location and preview.

For a resistance result, also report:

1. **Scale:** 3 m model length, `Xmax=3 m` predictor geometry.
2. **Speed:** actual model speed in m/s, plus the original speed and its scale if converted.
3. **Resistance:** predicted total resistance in N.
4. **Length ratio:** `lambda=L_full/3`, written unambiguously as full scale : model. If only a model-scale input was supplied and its full-scale length is unknown, say that the corresponding full-scale ratio is unspecified.
5. **Conditions:** draft or `T/D`, applicable domain notes and target comparison if used.

For example, a Chinese response may say that the total resistance is for the 3 m model at the stated model speed and that the ship-to-model length ratio is 30:1. Fill in the resistance only from the actual model result.

## Verification boundaries

File existence, finite point values, dimensions, physical-volume tolerance, mesh closure and orientation checks, and repeat prediction from the exported geometry provide consistency evidence. The mesh checks do not perform a general self-intersection test. These checks do not establish prediction accuracy against CFD or a towing-tank experiment. Consult the release's actual validation record for which checks were run on CPU and which require the supported NVIDIA environment.
