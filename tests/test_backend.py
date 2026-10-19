import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import package_backend as backend


def package(name, version="1.0", requires=(), **values):
    return {
        "name": name, "key": backend.canonical_name(name), "version": version,
        "location": "/test/site-packages", "requires": list(requires),
        "description": "Package description", "size": 100, "size_kind": "recorded",
        "missing_files": 0, "installer": "pip", "editable": False, **values,
    }


def inventory(packages):
    return {
        "packages": packages, "warnings": [],
        "environment": {
            "version": "3.14.2", "prefix": "/test", "executable": "/test/python",
            "is_venv": True, "is_conda": False, "has_pip": True,
            "markers": {**backend.marker_environment(), "python_version": "3.14"},
        },
    }


class FileDistribution:
    def __init__(self, root, files):
        self.root, self.files = Path(root), files

    def locate_file(self, file):
        return self.root / file

    def read_text(self, name):
        return "file inventory" if name == "RECORD" else None


class BackendTests(unittest.TestCase):
    def test_sizes_count_only_distribution_recorded_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "own.py").write_bytes(b"abc")
            (root / "other.py").write_bytes(b"x" * 400)
            first = FileDistribution(root, ["own.py", "own.py"])
            second = FileDistribution(root, ["other.py"])
            self.assertEqual(backend.package_size(first), (3, "recorded", 0))
            self.assertEqual(backend.package_size(second), (400, "recorded", 0))

    def test_missing_and_absent_file_records_are_honest(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(backend.package_size(FileDistribution(directory, None)), (None, "unknown", 0))
            self.assertEqual(backend.package_size(FileDistribution(directory, ["gone.py"])), (0, "partial", 1))

    def test_build_source_inventory_is_not_counted_as_installed_size(self):
        with tempfile.TemporaryDirectory() as directory:
            distribution = FileDistribution(directory, ["source.py"])
            with patch.object(distribution, "read_text", return_value=None):
                self.assertEqual(backend.package_size(distribution), (None, "unknown", 0))

    def test_target_markers_and_optional_dependencies(self):
        packages = [package("app", requires=["base>=1", "old; python_version < '3.12'", "win; sys_platform == 'win32'", "extra-lib; extra == 'plot'", "not a valid requirement !!"])]
        environment = inventory(packages)["environment"]
        environment["markers"]["sys_platform"] = "linux"
        graph, optional, errors = backend.dependency_graph(packages, environment)
        self.assertEqual(graph["app"], {"base"})
        self.assertEqual(optional["app"], {"extra-lib"})
        self.assertEqual(len(errors), 1)

    def test_reverse_warnings_exclude_packages_also_being_removed(self):
        required, possible = backend.removal_warnings({"base", "app"}, {"app": {"base"}, "other": {"base"}}, {"plugin": {"base"}})
        self.assertEqual(required, {"base": ["other"]})
        self.assertEqual(possible, {"base": ["plugin"]})

    def test_dependents_are_removed_first_and_cycles_terminate(self):
        self.assertEqual(backend.removal_order({"base", "app", "plugin"}, {"app": {"base"}, "plugin": {"app"}}), ["plugin", "app", "base"])
        self.assertEqual(set(backend.removal_order({"a", "b"}, {"a": {"b"}, "b": {"a"}})), {"a", "b"})

    def test_changed_inventory_blocks_removal(self):
        original = [package("base")]
        with self.assertRaises(RuntimeError):
            backend.validate_plan(original, [package("base", "2.0")], {"base"})
        with self.assertRaises(RuntimeError):
            backend.validate_plan(original, original + [package("new-dependent", requires=["base"])], {"base"})
        with self.assertRaises(RuntimeError):
            backend.validate_plan(original, [], {"base"})
        backend.validate_plan(original, original, {"base"})

    def test_runtime_and_foreign_manager_protection(self):
        self.assertTrue(backend.protection_reason(package("pip"), "/other/python", "/app/python"))
        self.assertTrue(backend.protection_reason(package("PyQt6"), "/app/python", "/app/python"))
        self.assertFalse(backend.protection_reason(package("PyQt6"), "/other/python", "/app/python"))
        self.assertTrue(backend.protection_reason(package("numpy", installer="conda"), "/other/python", "/app/python"))

    def test_inherited_packages_cannot_be_removed_from_wrong_venv(self):
        environment = inventory([])["environment"]
        inherited = package("numpy", location="/other/site-packages")
        self.assertIn("Inherited", backend.protection_reason(inherited, "/test/python", "/app/python", environment))
        self.assertFalse(backend.protection_reason({**inherited, "editable": True}, "/test/python", "/app/python", environment))

    def test_freeze_failure_prevents_snapshot(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backend, "run_python", return_value=subprocess.CompletedProcess([], 1, "", "failure")):
            with self.assertRaises(RuntimeError):
                backend.create_snapshot("python", inventory([]), {"base"}, Path(directory) / "snapshots")
            self.assertFalse((Path(directory) / "snapshots").exists())

    def test_snapshot_and_durable_history(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backend, "run_python", return_value=subprocess.CompletedProcess([], 0, "base==1.0\n", "")):
            folder = backend.create_snapshot("python", inventory([package("base")]), {"base"}, directory)
            self.assertEqual((folder / "requirements.txt").read_text(), "base==1.0\n")
            self.assertEqual(json.loads((folder / "inventory.json").read_text())["selected"], ["base"])
            backend.append_history(directory, {"action": "removed", "package": "base"})
            record = json.loads((Path(directory) / "history.jsonl").read_text())
            self.assertEqual(record["package"], "base")
            self.assertIn("time", record)

    def test_uninstall_checks_actual_absence(self):
        results = [subprocess.CompletedProcess([], 0, "Skipping not installed", ""), subprocess.CompletedProcess([], 0, "true\n", "")]
        with patch.object(backend, "run_python", side_effect=results):
            success, output = backend.perform_uninstall("python", "base")
        self.assertFalse(success)
        self.assertIn("could not be verified", output)

    def test_uninstall_success_and_failure(self):
        with patch.object(backend, "run_python", side_effect=[subprocess.CompletedProcess([], 0, "Removed", ""), subprocess.CompletedProcess([], 0, "false\n", "")]) as command:
            self.assertTrue(backend.perform_uninstall("python", "base")[0])
            self.assertEqual(command.call_args_list[0].args[1], ["-m", "pip", "uninstall", "-y", "base"])
        with patch.object(backend, "run_python", return_value=subprocess.CompletedProcess([], 1, "", "denied")):
            self.assertEqual(backend.perform_uninstall("python", "base"), (False, "denied"))

    def test_uninstall_rejects_options_and_handles_timeout(self):
        with patch.object(backend, "run_python") as command:
            self.assertFalse(backend.perform_uninstall("python", "--all")[0])
            command.assert_not_called()
        with patch.object(backend, "run_python", side_effect=subprocess.TimeoutExpired([], 300)):
            success, message = backend.perform_uninstall("python", "base")
            self.assertFalse(success)
            self.assertIn("Files may have changed", message)


if __name__ == "__main__":
    unittest.main()
