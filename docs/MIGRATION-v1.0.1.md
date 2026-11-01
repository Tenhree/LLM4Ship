> Historical collection document. This preserves the earlier WhutOceanShip-Skills version 1.0.1 migration instructions. Its old paths and skill names are not the standalone LLM4Ship installation procedure. See [MIGRATION.md](MIGRATION.md) for the current guide.

# Migrating to version 1.0.1

Version **1.0.1** groups all four child-skill directories under the project-root `skills/` directory. The collection router stays at the project root. This release preserves the existing four hull-exploration workflows, request schema, model weights, environment-selection policy, geometry and resistance units, and output naming conventions.

## Directory changes

Paths in this table are relative to the folder containing `package.json`:

| Version 1.0.0 | Version 1.0.1 |
| --- | --- |
| `Hullexploration-Skill/` | `skills/Hullexploration-Skill/` |
| `Hulldemonstration-Skill/` | `skills/Hulldemonstration-Skill/` |
| `Yachtformdesign-Skill/` | `skills/Yachtformdesign-Skill/` |
| `Cabindesign-Skill/` | `skills/Cabindesign-Skill/` |

`Hullexploration-Skill` contains the implemented skill, its scripts and its references. The other three directories remain empty placeholders. The project-root `SKILL.md`, `run.cmd`, `run.sh`, `environment/`, `vendor/`, `examples/` and `tests/` retain their roles.

The project root is now two levels above the child-skill directory. The application entry is `skills/Hullexploration-Skill/scripts/hull_explore.py`. The supplied launchers resolve that location; ordinary usage should continue through the root `run.cmd` or `run.sh`.

## Pi registration

The package manifest uses the following resource entries:

```json
{
  "pi": {
    "skills": ["./SKILL.md", "./skills"]
  }
}
```

Pi resolves package resource paths from the package root and recursively discovers directories containing `SKILL.md`. The first entry exposes the collection router. The second discovers the implemented child and any future valid child skills. Empty placeholder directories expose no commands. The active skill names remain `whutoceanship-skills` and `hullexploration-skill`.

These behaviors are documented in [Pi Packages](https://pi.dev/docs/latest/packages) and [Pi Skills](https://pi.dev/docs/latest/skills). Use [`/reload`](https://pi.dev/docs/latest/slash-commands) after changing registered skill resources in an active Pi session.

## Upgrade an existing installation

1. Keep the previous installation and any generated design cases available until the new installation is verified. Extract the complete version 1.0.1 archive into a **new empty directory**. Merging it over version 1.0.0 can leave the old top-level child directories alongside `skills/`.
2. Locate the newly extracted folder containing `package.json`, `SKILL.md`, `skills/`, `run.cmd` and `run.sh`. That folder is the new project root. In the following examples, it is `D:\Tools\WhutOceanShip-Skills-1.0.1`; substitute its actual path.
3. If Pi already has the old local package registered, inspect `pi list` and replace that registration with the new project path. Use the same personal or project scope as the existing installation. For a personal installation previously at `D:\Tools\WhutOceanShip-Skills`, the commands are:

   ```powershell
   pi list
   pi remove 'D:\Tools\WhutOceanShip-Skills'
   pi install 'D:\Tools\WhutOceanShip-Skills-1.0.1'
   ```

4. Run `/reload` in Pi, or restart it. Check that `/skill:whutoceanship-skills` and `/skill:hullexploration-skill` are available. Keep one active registration for the collection; registering both old and new copies introduces duplicate skill names.
5. Run the new root launcher from the working directory where future case folders should be created:

   ```powershell
   & 'D:\Tools\WhutOceanShip-Skills-1.0.1\run.cmd' --version
   & 'D:\Tools\WhutOceanShip-Skills-1.0.1\run.cmd' --check --json
   & 'D:\Tools\WhutOceanShip-Skills-1.0.1\run.cmd' --request 'D:\Tools\WhutOceanShip-Skills-1.0.1\examples\user90m5000t_dry_run.json'
   ```

The first command should identify version 1.0.1. The environment check reports the selected interpreter. The included request is a dry run and does not perform inference or create a design-case folder. See [VALIDATION.md](VALIDATION.md) for the release's executed checks and [the README](../README.md#testing-and-limitations) for actual GPU validation.

The preferred Windows interpreter remains `D:\anaconda3\envs\mypythorch\python.exe`. If a different environment is already prepared, select it with `--python` or `WHUTOCEANSHIP_PYTHON`. See [environment/README.md](../environment/README.md) for managed-environment setup when changing machines or installation locations.

## Existing requests and outputs

Existing Chinese and English prompts use the same skill names. For example:

```text
请使用 Hullexploration-Skill 对船长 90 m、船宽 15.6 m、型深 7.5 m、吃水 5.6 m、排水量 5000 t、实船航速 18 kn 的请求执行 dry-run，检查参数和 3 m 模型尺度换算。
```

Request JSON keys, root-launcher arguments and dated output folder names are preserved. Command-line paths and relative output paths resolve from the invocation working directory. A relative `points` value inside JSON resolves from that JSON file's directory. Update any external shortcut or automation that directly references the old child-script path to use the new location, preferably through the root launcher.

Keep existing design cases at their current location or transfer them as complete case folders when needed. Moving the skill's implementation directory does not require converting existing hull coordinates or changing their recorded model-scale interpretation.
