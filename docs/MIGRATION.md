# Migrating to standalone LLM4Ship

LLM4Ship packages the existing hull-exploration workflow as one standalone skill. Its display name and project folder are `LLM4Ship`, its registered identifier is `llm4ship`, and its package version remains **1.0.1**. The former collection also used version 1.0.1; the package name, root layout and active Skill identifier distinguish this distribution.

The four engineering workflows, trained model weights, request schema, default Python interpreter, physical units, acceptance rules and output filenames are preserved. This migration changes the package identity and locations of the active skill files.

## Directory and registration changes

The following paths are relative to the respective project roots:

| Earlier collection | Standalone LLM4Ship |
| --- | --- |
| `skills/Hullexploration-Skill/SKILL.md` | `SKILL.md` |
| `skills/Hullexploration-Skill/scripts/` | `scripts/` |
| `skills/Hullexploration-Skill/references/` | `references/` |
| `skills/Hullexploration-Skill/agents/` | `agents/` |
| Collection-router `SKILL.md` | Historical `docs/collection-router-v1.0.1.txt` |
| Collection-level `agents/openai.yaml` | Historical `docs/collection-agent-v1.0.1.txt` |

The former `skills/` directory and its empty placeholder modules are not part of the standalone active layout. The launchers, `environment/`, `vendor/`, `examples/` and `tests/` remain at the project root or their existing root-level locations. The directory containing the active `SKILL.md` is now the project root; the application entry is `scripts/hull_explore.py`.

The package manifest registers exactly one skill:

```json
{
  "pi": {
    "skills": ["./SKILL.md"]
  }
}
```

Use `/skill:llm4ship` in Pi. The historical collection identifiers `whutoceanship-skills` and `hullexploration-skill` are not registered by this package. The archived router and agent files are provenance records and do not expose additional skills.

Pi's [Packages](https://pi.dev/docs/latest/packages) documentation describes local package registration and package-relative resource paths. Its [Skills](https://pi.dev/docs/latest/skills) documentation describes lowercase Skill identifiers, and its [slash-command reference](https://pi.dev/docs/latest/slash-commands) describes `/reload`.

## Replace an earlier local installation

1. Keep the previous installation and any generated design cases available until the standalone package has been checked. Extract the complete `LLM4Ship-v1.0.1.zip` archive into a **new empty directory**. Overlaying it on the old collection can leave stale collection files beside the new root skill.
2. Locate the extracted directory containing `SKILL.md`, `package.json`, `scripts/`, `references/`, `run.cmd` and `run.sh`. The following commands assume that this directory is `D:\Tools\LLM4Ship`; substitute its actual path.
3. Use `pi list` to identify the previous registration. When replacing a personal local installation previously registered at `D:\Tools\WhutOceanShip-Skills`, use:

   ```powershell
   pi list
   pi remove 'D:\Tools\WhutOceanShip-Skills'
   pi install 'D:\Tools\LLM4Ship'
   ```

   Use the same personal or project scope as the installation being replaced. Adjust the old source path to match the existing registration.

4. Run `/reload` in Pi or restart it. Invoke `/skill:llm4ship`. If Pi still offers the earlier collection commands, inspect its package registrations and configured Skill locations for another copy of the old collection.
5. Run the standalone launcher from the working directory where new result folders should be created:

   ```powershell
   & 'D:\Tools\LLM4Ship\run.cmd' --version
   & 'D:\Tools\LLM4Ship\run.cmd' --check --json
   & 'D:\Tools\LLM4Ship\run.cmd' --request 'D:\Tools\LLM4Ship\examples\user90m5000t_dry_run.json'
   ```

The version remains 1.0.1. The environment check reports the selected interpreter. The included JSON request performs a dry run without model inference or design-case allocation. Consult [VALIDATION-LLM4Ship.md](VALIDATION-LLM4Ship.md) for checks performed after the standalone refactor and [the README](../README.md#testing-and-limitations) for the real GPU check procedure.

## Runtime compatibility

The preferred Windows interpreter remains `D:\anaconda3\envs\mypythorch\python.exe`. Existing `--python` overrides and `WHUTOCEANSHIP_PYTHON`, `WHUTOCEANSHIP_RUNTIME_ROOT` and `WHUTOCEANSHIP_CACHE` settings remain valid. The legacy `WhutOceanShip-Skills` cache-directory names and runtime ownership identifiers are intentionally preserved for compatibility. They do not determine the displayed skill name.

The standalone project still selects and checks its runtime through the supplied launchers. See [environment/README.md](../environment/README.md) when an environment must be selected or prepared at a different installation location.

## Existing requests and results

Change the skill name in natural-language requests to LLM4Ship. The engineering content of the requests is unchanged. For example:

```text
请使用 LLM4Ship 对船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 5.6 m、排水量 5000 t、实船航速 18 kn 的请求执行 dry-run，检查参数和 3 m 模型尺度换算。
```

```text
Use LLM4Ship to generate a ship with length 90 m, full beam 15.6 m, depth 7.5 m, draft 3.75 m and displacement 3000 tonnes. Predict its total resistance at a 3 m model-scale speed of 1.2 m/s.
```

JSON keys, root-launcher arguments and dated output-folder names are unchanged. Relative command-line paths and output paths resolve from the invocation working directory. A relative `points` value inside JSON resolves from that JSON file's directory. Update shortcuts or automation that directly references `skills/Hullexploration-Skill/scripts/hull_explore.py` to the new `scripts/hull_explore.py` location, preferably using the root launcher.

Existing case folders retain their geometry and scale interpretation. Keep complete case folders together when relocating them so that the CSV and its result metadata remain associated. The bundled generated sample's numerical files are preserved unchanged.

## Historical documents

The following records describe earlier collection releases, rather than new standalone validation:

- [MIGRATION-v1.0.1.md](MIGRATION-v1.0.1.md) preserves the original migration prose for the collection's `skills/` layout and is explicitly marked historical.
- [VALIDATION.md](VALIDATION.md) and the earlier validation records and logs remain unmodified historical evidence. Their old names, paths and test results describe the runs originally recorded.
- [collection-router-v1.0.1.txt](collection-router-v1.0.1.txt) and [collection-agent-v1.0.1.txt](collection-agent-v1.0.1.txt) preserve the former collection metadata without creating another callable Skill.

Use the active root `SKILL.md`, this migration guide and [VALIDATION-LLM4Ship.md](VALIDATION-LLM4Ship.md) for the standalone package.
