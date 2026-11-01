# LLM4Ship standalone refactor validation

Package: **LLM4Ship 1.0.1**, derived from **WhutOceanShip-Skills 1.0.1**.
Checked on **2026-11-01**, using the user-facing Asia/Shanghai date.

This revision extracts the implemented hull-exploration skill into one standalone
package. It preserves the supplied model assets, inference algorithms, request
schema, case naming, output formats and environment dependency versions.

## Checks performed

| Check | Result |
| --- | --- |
| Existing automated suite | 74 tests: **72 passed, 2 skipped, 0 failures, 0 errors** |
| Source-file accounting | All 95 non-dot source-package files have a preserved or updated counterpart, including the former router and agent metadata as historical text |
| Original model resources | All 35 original `vendor/` files are byte-identical |
| Checkpoint integrity | All three SHA-256 hashes and sizes match the unchanged `models-manifest.json` |
| Core application | The request contracts, geometry, workflow, entry script and version module are byte-identical; the model adapter only changes root depth and the CLI only changes its description |
| Runtime compatibility | Preferred Windows interpreter, dependency specifications, legacy environment-variable names, cache locations and ownership markers are retained |
| Structured request equivalence | All five bundled examples produce the same normalized dry-run JSON as the source package, after accounting for the installed root path |
| Working directory handling | Dry runs succeed from an external path containing spaces and create no case-output folders |
| Python syntax | All 41 bundled Python files parse successfully |
| Active documentation | Local links resolve within the standalone tree |
| Skill metadata | Root `SKILL.md` passes the Skill Creator format validator with identifier `llm4ship` |
| Single-skill registration | `package.json` registers only `./SKILL.md`; no `skills/` collection directory remains |
| Runtime version | Root launcher still reports `1.0.1` |
| Independent instruction-driven check | A fresh agent followed the standalone skill to build and execute an external JSON optimization dry run; it returned `validated` with the expected scale conversion and explicit domain warning |

Detailed results are retained in
[validation-summary-LLM4Ship.json](validation-summary-LLM4Ship.json),
[validation-tests-LLM4Ship.txt](validation-tests-LLM4Ship.txt), and
[standalone-checks-LLM4Ship.json](standalone-checks-LLM4Ship.json).

## Preserved trained models

| Model | Bytes | SHA-256 |
| --- | ---: | --- |
| `vendor/Generator/stage2_final.pth` | 131772656 | `a7a42209dae1c580aea4a9b29b96edcd28265aeaad84b12321fc3b0bcd6d81d3` |
| `vendor/Predictor/prediction_best.pth` | 317996242 | `729d14baa36b0372aff228c130c2cb600e12a8cf1435eb244e89fbc18a0feeb5` |
| `vendor/Hull_RL_Optimization/runs/td3/models/td3_final.zip` | 3402953 | `d776176d07df4e4c6eddd689a5f3b7fa0a537f3aba9f4afbb9359610b0c137d7` |

## Validation limits

The refactor checks ran on Linux with Python 3.12.14 and the available NumPy and
Matplotlib packages. This is separate from the preferred Windows NVIDIA
deployment environment, `D:\anaconda3\envs\mypythorch\python.exe`.

Two existing tests were skipped: the real TD3 actor comparison requires PyTorch
and Stable-Baselines3, which are absent here; the native Windows launcher test
requires Windows. No dependencies were installed for this refactor.

No real Generator, GPU Predictor or complete TD3 search was executed in this
revision. Synthetic model doubles in the existing tests check control flow,
validation and artifact consistency, and their resistance values are fixtures.
Hash checks establish model-file identity, not predictive accuracy.
Automatic CUDA environment installation and an authenticated Pi session were
not exercised here.

The preserved [collection validation](VALIDATION.md) and
[earlier model-execution record](VALIDATION-v1.0.0.md) are historical evidence.
The bundled numerical sample files also remain historical and unchanged; they
are not new results from this refactor.

The source attributes explicitly preserve the generated sample CSV bytes,
including the historical search log's original line endings.

## Source history and release packaging

The source refactor is recorded in Git and exported to
`docs/source-history.bundle`. Weights are included in the release ZIP and remain
outside the source history. The packager verifies all three weights, enforces
one registered root skill, checks ZIP CRC, preserves executable shell-launcher
metadata and excludes local runtime and cache files.

Rebuild from the complete extracted package with a prepared interpreter:

```powershell
& 'D:\anaconda3\envs\mypythorch\python.exe' tools/package_project.py --output '..\LLM4Ship-rebuilt.zip'
```

The packager refuses to overwrite an existing ZIP. See
[MIGRATION.md](MIGRATION.md) for installation and the
[README](../README.md#testing-and-limitations) for actual GPU checks on the target
Windows machine.
