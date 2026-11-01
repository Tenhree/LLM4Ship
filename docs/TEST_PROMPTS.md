# Conversational test prompts

These prompts test Pi-agent's routing, parameter collection, unit handling and delivery behavior. Replace sample paths with real paths on the test machine. Numerical resistance targets below are test inputs; no resistance prediction is asserted in this document.

Use `/skill:llm4ship` before a prompt if automatic skill selection does not occur. Start from a working directory where case outputs may be created. Check the environment with `--check --require-gpu --json` and exercise the models with `doctor --models` before GPU inference tests. CPU checks cannot establish predictor execution on the target NVIDIA machine.

## 1. Generate geometry in Chinese

```text
请使用 LLM4Ship 帮我设计一艘船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 3.75 m、排水量 3000 t 的船舶。按海水密度 1025 kg/m³ 计算，随机种子使用 42，并提供全船三维预览。
```

Expected behavior: use `generate` without resistance prediction, create the next `DesignCase-YYYYMMDD-x` folder in the invocation working directory, and deliver `DesignCaseShip.csv`, `DesignCaseShip.stl`, `DesignCaseShip.png` and `DesignCaseShip.html`. The previews must use the actual exported half hull and its mirror. Report the actual displacement estimate and acceptance result from `result.json`. A search failure must be reported honestly.

## 2. Generate geometry in English

```text
Use LLM4Ship to design a ship with length 90 m, full beam 15.6 m, molded depth 7.5 m, draft 3.75 m and displacement mass 3000 metric tonnes. Use seawater density 1025 kg/m^3 and seed 42. Export the half-hull CSV, full-hull STL and a full-hull point-cloud preview.
```

Expected behavior: the same workflow and units as Test 1, with an English response. Full beam must be interpreted as 15.6 m, giving a half-hull breadth of 7.8 m.

## 3. Generate and predict at a model speed

```text
请使用 LLM4Ship 设计一艘船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 3.75 m、排水量 3000 t 的船舶，并估算其在船长 3 m 的模型尺度、航速 1.2 m/s 时的总阻力。随机种子使用 42。
```

Expected behavior: generate at the requested ship dimensions, then uniformly scale XYZ for prediction. Report resistance in N for a 3 m model at 1.2 m/s and state the length ratio as full ship : model = 30:1. Keep the main CSV and STL at the requested ship scale and save `DesignCaseShip_model_3m.csv` as the auxiliary prediction input.

## 4. Generate and predict from an English request

```text
Use LLM4Ship to generate a hull with L=90 m, B=15.6 m, D=7.5 m, T=3.75 m and displacement=3000 tonnes. Estimate its total resistance at a model-scale speed of 1.2 m/s for a 3 m model. Save the outputs to D:/Hull Cases/English Design A.
```

Expected behavior: route to generation with prediction, preserve the selected output directory, and make the model scale and units explicit in English. Protect any existing files at that destination.

## 5. Convert a full-scale speed in knots

```text
请使用 LLM4Ship 设计一艘船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 3.75 m、排水量 3000 t 的船。它的实船航速为 12 kn，请按弗劳德相似换算到船长 3 m 的模型尺度，再预报该模型尺度下的总阻力。
```

Expected behavior: use `lambda=30` and convert 12 kn to approximately 1.1270913 m/s before prediction. The resistance remains a model-scale value in N.

## 6. Convert a full-scale speed in km/h

```text
Use LLM4Ship to generate a 90 m by 15.6 m hull with depth 7.5 m, draft 3.75 m and displacement 3000 tonnes. Its full-scale speed is 22.224 km/h. Convert this to the corresponding 3 m model speed and predict model-scale total resistance.
```

Expected behavior: recognize that 22.224 km/h is the same physical speed as 12 kn, so the analytical conversion agrees with Test 5. Do not compare stochastic resistance outputs as if identical geometry had necessarily been generated unless the same seed and settings are also used.

## 7. Explore a direct resistance target in Chinese

```text
请使用 LLM4Ship 设计一艘船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 3.75 m、排水量 3000 t 的船舶。要求其在船长 3 m 的模型尺度、航速 1.2 m/s 时，总阻力低于 15 N。最多搜索 100 个回合，随机种子为 42；如果未达到目标，请输出本次搜索中阻力最低的可行方案，并明确说明未达标。
```

Expected behavior: use the trained TD3 workflow with a direct strict upper target of 15 N. Create an `OPTDesignCase-YYYYMMDD-x` folder and the `OPTDesignCaseShip.csv`, `.stl`, `.png`, `.html` and `_model_3m.csv` files when a valid candidate is exported. The comparison is strictly less than 15 N; equality is not success. The target is not a promised result.

## 8. Explore a direct resistance target in English

```text
Use LLM4Ship to explore a ship with length 90 m, full beam 15.6 m, depth 7.5 m, draft 3.75 m and displacement mass 3000 tonnes. At a 3 m model-scale speed of 1.2 m/s, seek total resistance strictly below 15 N. Use at most 100 episodes and seed 42. If the target is missed, return the lowest-resistance feasible hull actually found and report the target miss.
```

Expected behavior: the same interpretation as Test 7. Do not ask for an unrelated baseline resistance or target percentage.

## 9. Exercise the best-feasible fallback

```text
请使用 LLM4Ship 对船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 3.75 m、排水量 3000 t 的船舶进行探索设计。在 3 m 模型尺度、航速 1.2 m/s 下，目标总阻力低于 0.001 N。仅搜索 5 个回合，随机种子为 42。若无法达到目标，请保留并输出本次搜索中阻力最低的可行方案。
```

Expected behavior: treat this deliberately extreme target as a fallback-path test. If at least one feasible candidate is found, report `target_not_met`, retain its files and interpret exit code `2` as the target miss with a useful fallback. The implementation rejects predictions at or below 0.001 N; it must not use such a prediction as evidence that this target was achieved. If no feasible candidate is found, report that distinct failure with exit code `1` and inspect any recorded history and `failure.json`.

## 10. Predict the bundled point cloud

```text
请使用 LLM4Ship 预测 D:/Tools/LLM4Ship/vendor/Predictor/Branchmark/ship1.csv 的总阻力。该点云是约 3 m 船长的模型尺度半船点云，吃水型深比为 0.495283019，模型尺度航速为 0.8 m/s。
```

Expected behavior: validate the actual file, normalize only the permitted scale tolerance to the exact required model length, and run the predictor with the specified draft ratio and model speed. Create a `PredictionCase-YYYYMMDD-x` folder containing `ResistancePrediction_model_3m.csv`, `request.json` and `result.json`. Since this prompt does not supply a corresponding full-scale length, state that its full-to-model length ratio is unspecified. Do not generate a replacement hull or claim that the ratio is 30:1.

## 11. Predict a full-scale cloud from an English request

```text
Use LLM4Ship to predict total resistance for D:/Hull Cases/Design A/DesignCaseShip.csv. This is a full-scale half-hull cloud in metres for a 90 m ship. Its operating draft is 3.75 m and its full-scale speed is 12 kn. Scale the cloud uniformly to a 3 m model and report the corresponding model-scale speed and resistance.
```

Expected behavior: validate the existing cloud, derive the draft ratio in a consistent scale, convert XYZ with one factor and convert speed by Froude similarity. The path must refer to a real output file from the test machine.

## 12. Use a model cloud with a full-scale speed

```text
请使用 LLM4Ship 预测这个 3 m 模型尺度半船点云在对应实船航速 12 kn 时的模型总阻力。对应实船船长为 90 m，吃水型深比为 0.5。点云路径为 D:/Hull Cases/model_cloud.csv。
```

Expected behavior: use the explicitly supplied 90 m full-scale length for speed conversion. Do not infer real ship length from an already normalized cloud. Use `T/D=0.5` without mixing full-scale draft and model depth.

## 13. Reuse a generated design's draft metadata

After a successful geometry-only run, send:

```text
请继续使用刚才生成的方案，按照刚才的吃水条件，预测其在 3 m 模型尺度、航速 1.2 m/s 下的总阻力。
```

Expected behavior: reuse the known file and same-hull draft metadata if available. Automatic metadata reuse requires the adjacent `result.json` to describe full-scale geometry and its stored cloud hash to match the actual input file. Ask for missing information only if the preceding result does not establish it. Do not generate an unrelated design.

## 14. Request missing draft information

Attach a valid CSV and send:

```text
请使用 LLM4Ship 预测这个模型尺度点云在模型航速 1.2 m/s 时的总阻力。
```

Expected behavior: ask for draft or `T/D` if it is not already known for this hull. A full-depth point cloud alone does not define operating draft.

## 15. Request missing speed-scale information

```text
请使用 LLM4Ship 预测 D:/Hull Cases/Design A/DesignCaseShip.csv 在航速 5 m/s 时的总阻力。点云为实船尺度，吃水 3.75 m。
```

Expected behavior: if the surrounding conversation does not establish the speed scale, ask whether 5 m/s is a full-scale or model-scale speed. Do not choose a scale solely because the unit is m/s.

## 16. Reject a malformed cloud

Provide a CSV with a header, 999 rows, four columns or a non-finite value and send:

```text
请使用 LLM4Ship 预测这个点云的总阻力。点云为模型尺度，吃水型深比 0.5，模型航速 1.2 m/s。
```

Expected behavior: identify the failed format requirement and ask for a corrected file. Do not silently remove columns, invent missing points, replace non-finite values or resample the cloud.

## 17. Resolve an inconsistent inequality

```text
请使用 LLM4Ship 设计一艘船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 3.75 m、排水量 3000 t 的船，在 3 m 模型尺度航速 1.2 m/s 时，阻力不低于 15 N；如果不能降到 15 N 以下，就给出最低阻力方案。
```

Expected behavior: ask which inequality the user intends. The lower-bound phrase conflicts with the later reduction objective. Do not silently change an explicit condition.

## 18. Preserve a selected Chinese output path

```text
请使用 LLM4Ship 生成船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 3.75 m、排水量 3000 t 的船型，将文件保存在 D:/船型设计/方案 A，并给出全船预览。随机种子为 42。
```

Expected behavior: preserve the path and quote or serialize it correctly. Output filenames remain `DesignCaseShip.csv` and `DesignCaseShip.stl`. Protect prior files if this destination has already been used.

## 19. Inspect conversion without running models

```text
请使用 LLM4Ship 对船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 3.75 m、排水量 3000 t、实船航速 12 kn 的请求执行 dry-run。只检查参数和 3 m 模型尺度换算，暂不执行模型。
```

Expected behavior: use the application's dry-run path, report normalized parameters and scale conversion, and perform no model inference or case-folder allocation.

## 20. Exercise the original draft-ratio extrapolation example

```text
请使用 LLM4Ship 设计一艘船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 5.6 m、排水量 5000 t 的船。在 3 m 模型尺度航速 1.2 m/s 下探索总阻力低于 15 N 的方案。请明确报告输入是否超出现有 TD3 配置的采样范围，以及本次实际搜索结果。
```

Expected behavior: identify `T/D≈0.7467` as outside the TD3 configured range `0.35–0.60`, keep the requested dimensions unchanged, and report the actual outcome with that domain note. Do not claim an accuracy guarantee or silently change the draft.

## 21. Verify dated folder numbering

Run Test 1 twice from the same working directory without specifying an output folder. Alternatively, in a dedicated test directory, retain existing same-date folders ending in `-1` and `-3`, then run once.

Expected behavior: allocate the next available numeric suffix for the same prefix and date. For the `-1`, `-3` setup, choose `-4`. Confirm that prior result files remain present. The actual date comes from the executing device, not from the examples in the original request.

## 22. Verify unsupported-task behavior

```text
请使用 LLM4Ship 帮我设计客舱布局。
```

Expected behavior: LLM4Ship explains that cabin-layout design is outside its implemented hull-exploration workflows. It must not claim that this standalone skill implements cabin design or invoke an unimplemented child skill.

## 23. Inspect the original 90 m case at 18 kn

```text
请使用 LLM4Ship 对船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 5.6 m、排水量 5000 t、实船航速 18 kn、模型尺度总阻力目标低于 15 N 的探索请求执行 dry-run。请检查尺度换算和 TD3 输入范围，不执行生成或预测模型。
```

Expected behavior: report `lambda=30`, model speed approximately `1.6906369 m/s`, model beam `0.52 m`, model depth `0.25 m`, model draft approximately `0.1866667 m`, and the out-of-range TD3 draft ratio `0.7466667`. The 15 N target is only an input. No model is loaded, no case folder is created, and no resistance prediction is asserted.

## Executable JSON counterparts

These files use the actual application's request schema. None fixes an output directory:

| JSON request | Corresponding test |
| --- | --- |
| [generate.json](../examples/generate.json) | Test 1 or 2 |
| [generate_resistance.json](../examples/generate_resistance.json) | Test 3 or 4 without the fixed output path |
| [optimize.json](../examples/optimize.json) | Test 7 or 8 |
| [predict_benchmark.json](../examples/predict_benchmark.json) | Test 10 |
| [user90m5000t_dry_run.json](../examples/user90m5000t_dry_run.json) | Test 23 |

For example, from any chosen working directory:

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' --request 'D:\Tools\LLM4Ship\examples\generate.json' --dry-run
& 'D:\Tools\LLM4Ship\run.cmd' --request 'D:\Tools\LLM4Ship\examples\predict_benchmark.json' --dry-run
& 'D:\Tools\LLM4Ship\run.cmd' --request 'D:\Tools\LLM4Ship\examples\user90m5000t_dry_run.json'
```

The benchmark's relative `points` path resolves from its JSON file, so the bundled example can be found from another invocation directory. A relative `output` path, if added, resolves from the invocation working directory. The first four files need `--dry-run` for an inspection-only run; the fifth already contains `dry_run: true`. A prediction dry run reads the actual CSV and requires NumPy.

## Acceptance notes

For a valid inference run, inspect actual program outputs instead of comparing the response against a made-up resistance number. Verify principal dimensions, half/full-hull distinction, model speed, scale ratio, units, declared displacement tolerance, file paths and target status. Review the mesh and point-cloud previews from the exported files.

A fixed seed is useful for repeat runs in the same environment. Cross-device floating-point behavior and search outcomes can differ. Format tests and analytical scale-conversion checks can be evaluated independently of the learned model's numerical resistance output.

Consult [VALIDATION-LLM4Ship.md](VALIDATION-LLM4Ship.md) for tests executed after the standalone refactor; [VALIDATION.md](VALIDATION.md) preserves the earlier collection's validation record. The [README GPU-check instructions](../README.md#testing-and-limitations) run `tests/run_gpu_smoke.py` with the environment doctor's selected Python. That script checks actual generation with prediction, re-prediction of exported geometry and a two-episode TD3 fallback; it has not been executed in the CPU-only build environment. The [included 5000 t sample](../examples/generated_sample/README.md) is a preserved real CPU geometry result with no resistance value.
