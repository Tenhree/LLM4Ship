"""Bootstrap contract tests. No installer, pip command, or user model is run."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_SPEC = importlib.util.spec_from_file_location("whut_test_bootstrap", ROOT / "environment/bootstrap.py")
bootstrap = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = bootstrap
MODULE_SPEC.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def test_explicit_interpreter_has_priority(self):
        with tempfile.TemporaryDirectory() as folder:
            selected = bootstrap.select_python(Path(folder), explicit=sys.executable, environ={"WHUTOCEANSHIP_PYTHON": "/missing/python"}, system="Linux")
            self.assertEqual(selected.executable, Path(sys.executable).resolve())
            self.assertEqual(selected.origin, "explicit interpreter")

    def test_missing_explicit_interpreter_does_not_fall_back(self):
        with self.assertRaisesRegex(bootstrap.BootstrapError, "Requested Python was not found"):
            bootstrap.select_python(ROOT, explicit="/not/a/whut/python", environ={}, system="Linux")

    def test_preferred_windows_interpreter_precedes_private_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            preferred = Path(folder) / "preferred.exe"
            preferred.touch()
            with patch.object(bootstrap, "PREFERRED_WINDOWS_PYTHON", preferred):
                selected = bootstrap.select_python(Path(folder), environ={}, system="Windows")
                self.assertEqual(selected.executable, preferred.resolve())
                self.assertIsNone(bootstrap.select_python(Path(folder), isolated=True, environ={}, system="Windows"))

    def test_runtime_cache_is_project_specific(self):
        env = {"WHUTOCEANSHIP_CACHE": str(ROOT / "test-user-cache")}
        first = bootstrap.runtime_candidates(Path("/project/one"), environ=env)
        second = bootstrap.runtime_candidates(Path("/project/two"), environ=env)
        self.assertEqual(first[0], Path("/project/one/runtime"))
        self.assertNotEqual(first[1], second[1])
        self.assertEqual(len(bootstrap.runtime_candidates(ROOT, "custom-runtime", environ=env)), 1)

    def test_foreign_and_symlink_environments_are_never_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "env").mkdir()
            with patch.object(bootstrap, "run_command") as run:
                with self.assertRaisesRegex(bootstrap.BootstrapError, "unowned environment"):
                    bootstrap.ensure_managed_environment(root)
                run.assert_not_called()
            (root / "managed-runtime.json").write_text(json.dumps({"owner": "another-project", "prefix": str(root / "env")}), encoding="utf-8")
            with self.assertRaisesRegex(bootstrap.BootstrapError, "ownership marker"):
                bootstrap.select_python(root.parent, isolated=True, runtime_override=str(root), environ={})
        if hasattr(os, "symlink") and os.name != "nt":
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / "real-env").mkdir()
                (root / "env").symlink_to(root / "real-env", target_is_directory=True)
                with self.assertRaisesRegex(bootstrap.BootstrapError, "symbolic-link"):
                    bootstrap.ensure_managed_environment(root)

    def test_owned_complete_runtime_is_reused_without_installing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = bootstrap.python_in_prefix(root / "env")
            executable.parent.mkdir(parents=True)
            executable.touch()
            bootstrap.write_marker(root / "managed-runtime.json", {"owner": bootstrap.OWNER, "prefix": str((root / "env").resolve()), "complete": True})
            with patch.object(bootstrap, "run_command") as run, patch.object(bootstrap, "install_miniforge") as install:
                selected = bootstrap.ensure_managed_environment(root)
                self.assertEqual(selected.executable, executable.resolve())
                run.assert_not_called()
                install.assert_not_called()

    def test_installer_checksum_rejects_corruption_before_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            payload = Path(folder) / "installer"
            payload.write_bytes(b"example installer bytes")
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            bootstrap.verify_sha256(payload, digest + "  installer")
            with self.assertRaisesRegex(bootstrap.BootstrapError, "not executed"):
                bootstrap.verify_sha256(payload, "0" * 64)
            with self.assertRaisesRegex(bootstrap.BootstrapError, "no SHA-256"):
                bootstrap.verify_sha256(payload, "not a checksum")

    def test_installation_pins_and_sources_are_consistent(self):
        spec = bootstrap.load_spec()
        commands = bootstrap.installation_commands(Path("/private/conda"), Path("/private/env/bin/python"), spec)
        self.assertIn("python=3.11.10", commands[0])
        self.assertIn("https://download.pytorch.org/whl/cu121", commands[1])
        self.assertIn("torch==2.5.1+cu121", commands[1])
        self.assertIn("https://pypi.org/simple", commands[2])
        self.assertTrue(all(command[0] == "/private/env/bin/python" for command in commands[1:]))
        self.assertTrue(all("--isolated" in command for command in commands[1:]))
        self.assertNotIn("--upgrade", sum(commands, []))
        constraints = set((ROOT / "environment/constraints.txt").read_text().splitlines())
        requirements = set((ROOT / "environment/requirements-runtime.txt").read_text().splitlines())
        for name, item in {**spec["torch_packages"], **spec["packages"]}.items():
            pin = f"{name}=={item['version']}"
            self.assertIn(pin, constraints)
            if name in spec["packages"]:
                self.assertIn(pin, requirements)

    def test_parser_preserves_application_arguments(self):
        options, arguments = bootstrap.parse_options(["--python", sys.executable, "generate", "--request", "input folder/request.json", "--out", "output! & data", "--dry-run"])
        self.assertEqual(options.python, sys.executable)
        self.assertEqual(arguments, ["generate", "--request", "input folder/request.json", "--out", "output! & data", "--dry-run"])
        self.assertTrue(bootstrap.is_lightweight_command(arguments))
        self.assertFalse(bootstrap.is_lightweight_command(["optimize", "--length", "90", "--beam", "15.6", "--depth", "7.5", "--draft", "3.75", "--displacement-tonnes", "3000", "--speed", "1.2", "--speed-unit", "m/s", "--speed-scale", "model", "--target-resistance", "50"]))

    def test_check_never_provisions_missing_runtime(self):
        report = {"python": "3.11.10", "errors": ["Missing package: spconv-cu121"], "warnings": []}
        with patch.object(bootstrap, "select_python", return_value=None), patch.object(bootstrap, "inspect_python", return_value=(2, report)) as inspect, patch.object(bootstrap, "ensure_managed_environment") as ensure, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bootstrap.main(["--check", "--json"]), 2)
            ensure.assert_not_called()
            inspect.assert_called_once()

    def test_existing_broken_environment_is_reported_without_installing(self):
        selected = bootstrap.PythonSelection(Path(sys.executable), "explicit interpreter")
        report = {"python": "3.11.10", "errors": ["Cannot import spconv.pytorch"], "warnings": []}
        with patch.object(bootstrap, "select_python", return_value=selected), patch.object(bootstrap, "inspect_python", return_value=(2, report)), patch.object(bootstrap, "ensure_managed_environment") as ensure, patch.object(bootstrap, "run_application") as app, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bootstrap.main(["generate", "--length", "90", "--beam", "15.6", "--depth", "7.5", "--draft", "3.75", "--displacement-tonnes", "3000"]), 2)
            ensure.assert_not_called()
            app.assert_not_called()

    def test_lightweight_commands_do_not_import_or_install_model_dependencies(self):
        for arguments in (["--help"], ["--version"], ["doctor", "--models"], ["validate", "data.txt"], ["generate", "--dry-run"]):
            with self.subTest(arguments=arguments), patch.object(bootstrap, "select_python", return_value=None), patch.object(bootstrap, "inspect_python") as inspect, patch.object(bootstrap, "ensure_managed_environment") as ensure, patch.object(bootstrap, "run_application", return_value=0) as app, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(bootstrap.main(list(arguments)), 0)
                inspect.assert_not_called()
                ensure.assert_not_called()
                self.assertEqual(app.call_args.args[1], list(arguments))

    def test_json_dry_run_and_explicit_cli_overrides_use_the_same_parser(self):
        data = {"mode": "generate", "length": 90, "beam": 15.6, "depth": 7.5,
                "draft": 3.75, "displacement_tonnes": 3000, "dry_run": True,
                "speed": 1.2, "speed_unit": "m/s", "speed_scale": "model"}
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / "request.json"
            request.write_text(json.dumps(data), encoding="utf-8")
            self.assertTrue(bootstrap.is_lightweight_command(["generate", "--request", str(request)]))
            self.assertTrue(bootstrap.is_lightweight_command(["--request=" + str(request)]))
            normalized = bootstrap.parse_request_for_routing(["generate", "--request", str(request), "--speed", "1.4"])
            self.assertEqual(normalized["speed"], 1.4)
            data["dry_run"] = False
            request.write_text(json.dumps(data), encoding="utf-8")
            # A valid full model request must still take the normal setup route.
            self.assertFalse(bootstrap.is_lightweight_command(["--request", str(request)]))
            self.assertTrue(bootstrap.is_lightweight_command(["--request", str(request), "--dry-run"]))
            self.assertTrue(bootstrap.parse_request_for_routing(["--request", str(request), "--dry-run"])["dry_run"])

    def test_json_mode_only_diagnostics_are_lightweight(self):
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / "request.json"
            for mode in ("doctor", "validate"):
                with self.subTest(mode=mode):
                    request.write_text(json.dumps({"mode": mode}), encoding="utf-8")
                    self.assertTrue(bootstrap.is_lightweight_command(["--request", str(request)]))

    def test_invalid_json_is_forwarded_unchanged_without_installing(self):
        design = {"mode": "generate", "length": 90, "beam": 15.6, "depth": 7.5,
                  "draft": 3.75, "displacement_tonnes": 3000}
        invalid_contents = [
            "{", "[]", json.dumps({**design, "unknown_field": 1}),
            json.dumps({**design, "request": "must-not-be-followed.json"}),
            json.dumps({**design, "help": True}),
            json.dumps({**design, "dry_run": "false"}),
            json.dumps({**design, "length": True}),
            json.dumps({**design, "draft": 20}),
        ]
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / "invalid.json"
            for content in invalid_contents:
                with self.subTest(content=content):
                    request.write_text(content, encoding="utf-8")
                    arguments = ["--request", str(request)]
                    with patch.object(bootstrap, "select_python", return_value=None), patch.object(bootstrap, "inspect_python") as inspect, patch.object(bootstrap, "ensure_managed_environment") as ensure, patch.object(bootstrap, "run_application", return_value=1) as app, contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(bootstrap.main(arguments), 1)
                        inspect.assert_not_called()
                        ensure.assert_not_called()
                        self.assertEqual(app.call_args.args[1], arguments)
            request.write_text(json.dumps({**design, "request": "must-not-be-followed.json"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unknown JSON request fields: request"):
                bootstrap.parse_request_for_routing(["--request", str(request)])
            request.unlink()
            self.assertTrue(bootstrap.is_lightweight_command(["--request", str(request)]))

    def test_request_routing_preserves_cwd_paths_without_optional_dependencies(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            request_dir = directory / "request folder"
            caller = directory / "caller"
            request_dir.mkdir()
            caller.mkdir()
            request = request_dir / "request.json"
            request.write_text(json.dumps({"mode": "predict", "points": "data.csv",
                                           "point_scale": "model", "draft_ratio": 0.5,
                                           "speed": 1.2, "speed_unit": "m/s", "speed_scale": "model",
                                           "output": "relative result", "dry_run": True}), encoding="utf-8")
            script = (
                "import json, os, sys; sys.path.insert(0, sys.argv[1]); import bootstrap; "
                "request = bootstrap.parse_request_for_routing(['--request', sys.argv[2]]); "
                "overridden = bootstrap.parse_request_for_routing(['--request', sys.argv[2], '--points', 'caller.csv']); "
                "heavy = [name for name in sys.modules if name in ('torch','numpy') or name.endswith(('.models','.workflow','.geometry'))]; "
                "print(json.dumps({'request': request, 'overridden_points': overridden['points'], 'heavy': heavy, 'cwd': os.getcwd()}))"
            )
            # -S removes third-party site packages; parsing must remain stdlib-only.
            result = subprocess.run([sys.executable, "-B", "-S", "-c", script, str(ROOT / "environment"), str(request)], cwd=caller, capture_output=True, encoding="utf-8", timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["request"]["points"], str(request_dir / "data.csv"))
            self.assertEqual(report["request"]["output"], "relative result")
            self.assertEqual(report["overridden_points"], "caller.csv")
            self.assertEqual(report["heavy"], [])
            self.assertEqual(report["cwd"], str(caller))

    def test_json_only_dry_run_and_unknown_field_through_real_bootstrap(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            request = directory / "request.json"
            data = {"mode": "generate", "length": 90, "beam": 15.6, "depth": 7.5,
                    "draft": 3.75, "displacement_tonnes": 3000, "dry_run": True,
                    "output": "relative result"}
            request.write_text(json.dumps(data), encoding="utf-8")
            command = [sys.executable, "-B", str(ROOT / "environment/bootstrap.py"),
                       "--python", sys.executable, "--request", str(request)]
            # Explicit Python guarantees this integration test can never install
            # an environment, even if lightweight routing regresses.
            result = subprocess.run(command, cwd=directory, capture_output=True, encoding="utf-8", timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["dry_run"])
            self.assertFalse(report["models_loaded"])
            self.assertFalse(report["files_written"])
            self.assertEqual(report["output_directory"], "relative result")
            self.assertFalse((directory / "relative result").exists())
            # No CLI --dry-run is supplied in either case.
            data.pop("dry_run")
            data["unknown_field"] = True
            request.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run(command, cwd=directory, capture_output=True, encoding="utf-8", timeout=30, check=False)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual((result.stdout + result.stderr).count("Unknown JSON request fields: unknown_field"), 1)
            self.assertNotIn("Checking ", result.stderr)

    @unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "Requires a POSIX shell for launcher execution.")
    def test_shell_launcher_preserves_unicode_arguments_and_callers_cwd(self):
        with tempfile.TemporaryDirectory(prefix="whut-launch-") as folder:
            directory = Path(folder)
            # Construct non-ASCII test paths without embedding localized product copy.
            unicode_name = chr(0x8239) + chr(0x578b)
            project = directory / (unicode_name + " project & data!")
            caller = directory / (unicode_name + " caller")
            (project / "environment").mkdir(parents=True)
            caller.mkdir()
            shutil.copy2(ROOT / "run.sh", project / "run.sh")
            shutil.copy2(ROOT / "environment/start.sh", project / "environment/start.sh")
            (project / "environment/bootstrap.py").write_text("import json, os, sys\nprint(json.dumps({'cwd': os.getcwd(), 'args': sys.argv[1:]}, ensure_ascii=False))\n", encoding="utf-8")
            arguments = ["generate", "--request", unicode_name + " input &!.json", "--out", "folder with spaces/", "literal;$`value", "", 'quoted"value', "--dry-run"]
            env = os.environ.copy()
            env["WHUTOCEANSHIP_PYTHON"] = sys.executable
            result = subprocess.run(["bash", str(project / "run.sh"), *arguments], cwd=caller, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            response = json.loads(result.stdout)
            self.assertEqual(response["args"], arguments)
            self.assertEqual(response["cwd"], str(caller))

    @unittest.skipUnless(os.name == "nt", "Windows native launcher is checked on the target machine.")
    def test_windows_launcher_preserves_arguments_and_callers_cwd(self):
        with tempfile.TemporaryDirectory(prefix="whut-launch-") as folder:
            directory = Path(folder)
            unicode_name = chr(0x8239) + chr(0x578b)
            project = directory / (unicode_name + " project & data!")
            caller = directory / (unicode_name + " caller")
            (project / "environment").mkdir(parents=True)
            caller.mkdir()
            shutil.copy2(ROOT / "run.cmd", project / "run.cmd")
            shutil.copy2(ROOT / "environment/start.ps1", project / "environment/start.ps1")
            (project / "environment/bootstrap.py").write_text("import json, os, sys\nprint(json.dumps({'cwd': os.getcwd(), 'args': sys.argv[1:]}, ensure_ascii=False))\n", encoding="utf-8")
            arguments = ["generate", "--request", unicode_name + " input &!.json", "--out", "folder with spaces/", "--dry-run"]
            env = os.environ.copy()
            env["WHUTOCEANSHIP_PYTHON"] = sys.executable
            # A static, correctly quoted command is evaluated once by cmd.exe.
            command_line = subprocess.list2cmdline([str(project / "run.cmd"), *arguments])
            result = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", '"' + command_line + '"'], cwd=caller, env=env, capture_output=True, encoding="utf-8", timeout=45, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            response = json.loads(result.stdout)
            self.assertEqual(response["args"], arguments)
            self.assertEqual(response["cwd"], str(caller))


if __name__ == "__main__":
    unittest.main()
