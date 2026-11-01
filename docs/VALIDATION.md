# Release validation record

Release: **1.0.1**. Checks completed on **2026-10-21**.

This release moves the four child-skill directories into `skills/` and updates the affected registration, launch, model-root, test, packaging and documentation paths. It preserves the model weights, hull algorithms, request schema and output contracts.

## Checks performed for this revision

| Check | Result |
| --- | --- |
| Existing automated suite | **74 tests: 72 passed, 2 skipped, 0 failures, 0 errors** |
| Root launcher and request routing | All five bundled JSON examples passed as dry runs from an external working directory containing spaces; no case folders were created |
| Runtime version | Root launcher reports `1.0.1` |
| Model location | The moved adapter resolves the folder containing `package.json` and `models-manifest.json` as the project root |
| Checkpoint integrity | Generator, Predictor and TD3 archive match all three SHA-256 values in `models-manifest.json` |
| Skill format | Both active `SKILL.md` files pass the Skill format validator |
| Resource layout | Root router plus `./skills`; three reserved child directories are empty |
| Archive packaging | Includes all three weights, the implemented child and explicit empty-directory entries; excludes old top-level child directories and runtime caches |
| Portable shell launchers | The ZIP records executable permissions for `run.sh` and `environment/start.sh`, including builds made on a filesystem without POSIX permission support |

The packaging command verifies the completed ZIP's CRC and reports its checksum. A final archive inspection checks the new layout and launcher metadata before delivery.

See [validation-summary-v1.0.1.json](validation-summary-v1.0.1.json), [validation-tests-v1.0.1.txt](validation-tests-v1.0.1.txt) and [migration-dry-runs-v1.0.1.json](migration-dry-runs-v1.0.1.json) for the recorded results. See [MIGRATION.md](MIGRATION.md) for installing this layout.

## Test environment and skipped checks

The revision checks ran on Linux x86-64, Python 3.12.14, NumPy 2.3.5 and Matplotlib 3.10.8. PyTorch and Stable-Baselines3 were not installed in this revision's validation runtime. This runtime is separate from the preferred deployment environment, `D:\anaconda3\envs\mypythorch\python.exe`.

Two existing tests were skipped:

1. The comparison between the saved real TD3 actor and Stable-Baselines3, because its PyTorch/Stable-Baselines3 dependencies were unavailable.
2. Native Windows launcher execution, because this runtime is Linux.

Synthetic model doubles in the workflow tests verify control flow, export consistency and error handling. Their resistance values are fixtures and are not predictions from the trained Predictor.

This revision did not rerun real Generator inference, the GPU Predictor, complete TD3 optimization, automatic CUDA environment installation, an authenticated Pi session, CFD or towing-tank validation. Hash validation proves checkpoint identity; it does not execute a model or establish hydrodynamic accuracy.

## Previous model-execution evidence

The complete [version 1.0.0 validation record](VALIDATION-v1.0.0.md), [original suite summary](validation-summary.json) and [original suite log](validation-tests.txt) are retained as historical evidence. That release executed the real Generator on CPU and compared real TD3 actor actions with Stable-Baselines3. Those results are not presented as new 1.0.1 executions. The included [generated example](../examples/generated_sample/README.md) is the same previously validated sample.

## Checks on the Windows NVIDIA machine

From the new project root, use PowerShell:

```powershell
.\run.cmd --check --require-gpu --json
.\run.cmd generate --request .\examples\generate.json --dry-run
.\run.cmd doctor --models --device cuda
```

The first command checks the selected environment. The second performs request validation without inference. The third actually loads and checks model execution on the selected CUDA environment. Run [tests/run_gpu_smoke.py](../tests/run_gpu_smoke.py) using the verified interpreter for real generation, resistance prediction and bounded optimization checks; the [README](../README.md#testing-and-limitations) gives the exact invocation.

## Source history and rebuilding

The source changes are recorded in Git and exported in `docs/source-history.bundle`. Trained weights are included in the full release ZIP and excluded from source Git history. The packager retains the three required empty skill folders even though Git cannot track empty directories.

Rebuild with a prepared Python interpreter:

```powershell
& 'D:\anaconda3\envs\mypythorch\python.exe' tools/package_project.py --output '..\WhutOceanShip-Skills-rebuilt.zip'
```

The command checks the weights, rejects symlinks, excludes caches and refuses to overwrite an existing ZIP.
