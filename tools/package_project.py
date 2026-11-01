"""Build the standalone LLM4Ship release ZIP, including all supplied model weights."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", "SKILL.md", "package.json", "models-manifest.json",
              "run.cmd", "run.sh", ".gitignore", ".gitattributes"}
DIRECTORIES = {"scripts", "references", "agents", "environment", "vendor", "tests", "docs", "examples", "tools"}
EXECUTABLE_SCRIPTS = {"run.sh", "environment/start.sh"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT.parent / "LLM4Ship-v1.0.1.zip")
    args = parser.parse_args()
    destination = args.output.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    for item in json.loads((ROOT / "models-manifest.json").read_text())["models"]:
        with (ROOT / item["path"]).open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"Weight integrity check failed: {item['path']}")
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    if package.get("name") != "llm4ship" or package.get("pi", {}).get("skills") != ["./SKILL.md"]:
        raise ValueError("LLM4Ship must register exactly one root skill in package.json")
    skill_files = sorted(path.relative_to(ROOT).as_posix() for path in ROOT.rglob("SKILL.md")
                         if ".git" not in path.relative_to(ROOT).parts)
    if skill_files != ["SKILL.md"]:
        raise ValueError(f"Expected one standalone SKILL.md, found: {skill_files}")
    for name in ("scripts/hull_explore.py", "scripts/hullexplore/models.py",
                 "references/REQUEST_SCHEMA.md", "environment/bootstrap.py"):
        if not (ROOT / name).is_file():
            raise FileNotFoundError(f"Missing standalone skill resource: {name}")
    files = []
    directories = set()
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(part.startswith(".") for part in relative.parts) and relative.as_posix() not in ROOT_FILES:
            continue
        if any(part in {"__pycache__", ".git", ".pytest_cache"} for part in relative.parts):
            continue
        if relative.parts[0] not in DIRECTORIES and relative.as_posix() not in ROOT_FILES:
            continue
        if path.is_symlink():
            raise ValueError(f"Release archives do not include symbolic links: {relative}")
        if path.is_dir():
            directories.add(relative.as_posix())
        elif path.suffix not in {".pyc", ".pyo"}:
            files.append(path)
    try:
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            archive.write(ROOT, ROOT.name + "/")
            for name in sorted(directories):
                archive.write(ROOT / name, ROOT.name + "/" + name + "/")
            for path in files:
                relative = path.relative_to(ROOT).as_posix()
                archive_name = ROOT.name + "/" + relative
                if relative in EXECUTABLE_SCRIPTS:
                    # Preserve executable launchers even when packaged on Windows.
                    info = zipfile.ZipInfo.from_file(path, archive_name)
                    info.create_system = 3
                    info.external_attr = (0o100755 << 16) | (info.external_attr & 0xFFFF)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, path.read_bytes())
                else:
                    archive.write(path, archive_name)
        with zipfile.ZipFile(destination) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"ZIP CRC check failed: {bad}")
        with destination.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    print(json.dumps({"archive": str(destination), "bytes": destination.stat().st_size,
                      "sha256": digest, "files": len(files), "skill": "llm4ship",
                      "registered_skills": ["./SKILL.md"],
                      "weight_integrity": "passed", "zip_crc": "passed"}, indent=2))


if __name__ == "__main__":
    main()
