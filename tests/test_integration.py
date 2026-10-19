"""Exercise real pip only inside a disposable, isolated virtual environment."""
import csv
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import venv

from PyQt6.QtWidgets import QApplication
import package_backend as backend
from package_uninstaller import UninstallWorker


class IsolatedPipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_real_removal_snapshot_and_history_in_disposable_venv(self):
        # Local ensurepip bootstrap; no network or existing environment writes.
        with tempfile.TemporaryDirectory(prefix="package-uninstaller-test-") as directory:
            root = Path(directory).resolve()
            environment = root / "isolated"
            self.assertEqual(environment.parent, root)
            venv.EnvBuilder(with_pip=True).create(environment)
            executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            result = backend.run_python(executable, ["-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"])
            self.assertEqual(result.returncode, 0)
            site_packages = Path(result.stdout.strip()).resolve()
            self.assertTrue(site_packages.is_relative_to(environment.resolve()))
            names = ["codex_uninstaller_fixture_leaf", "codex_uninstaller_fixture_app"]
            for name in names:
                info = site_packages / f"{name}-0.0.1.dist-info"
                info.mkdir()
                (site_packages / f"{name}.py").write_text("VALUE = 1\n", encoding="utf-8")
                requires = "Requires-Dist: codex-uninstaller-fixture-leaf>=0.0.1\n" if name.endswith("app") else ""
                (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.0.1\nSummary: Disposable verification fixture\n{requires}", encoding="utf-8")
                (info / "INSTALLER").write_text("pip\n", encoding="utf-8")
                (info / "WHEEL").write_text("Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n", encoding="utf-8")
                recorded = [f"{name}.py"] + [f"{info.name}/{file}" for file in ["METADATA", "INSTALLER", "WHEEL", "RECORD"]]
                with (info / "RECORD").open("w", newline="", encoding="utf-8") as stream:
                    csv.writer(stream).writerows((path, "", "") for path in recorded)
            inventory = backend.read_environment(executable)
            self.assertTrue(inventory["environment"]["is_venv"])
            self.assertTrue(inventory["environment"]["has_pip"])
            self.assertLess(len(inventory["packages"]), 10, "Fixture must not expose the user's packages")
            selected = {backend.canonical_name(name) for name in names}
            reports = []
            worker = UninstallWorker(str(executable), inventory, selected, root / "recovery")
            worker.completed.connect(reports.append)
            worker.start()
            self.assertTrue(worker.wait(60000))
            self.app.processEvents()
            report = reports[-1]
            self.assertEqual(report["error"], "")
            self.assertEqual(report["failed"], [])
            self.assertEqual(report["skipped"], [])
            self.assertEqual(report["removed"], [names[1], names[0]])
            current = backend.read_environment(executable)
            self.assertFalse(selected & {p["key"] for p in current["packages"]})
            self.assertTrue(current["environment"]["has_pip"])
            for name in names:
                self.assertFalse((site_packages / f"{name}.py").exists())
                self.assertFalse((site_packages / f"{name}-0.0.1.dist-info").exists())
            snapshot = Path(report["snapshot"])
            self.assertTrue(snapshot.is_relative_to(root))
            freeze = (snapshot / "requirements.txt").read_text(encoding="utf-8")
            self.assertIn("codex", freeze)
            self.assertEqual(set(json.loads((snapshot / "inventory.json").read_text(encoding="utf-8"))["selected"]), selected)
            history = [json.loads(line) for line in (root / "recovery" / "history.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([event["action"] for event in history], ["planned", "started", "removed", "started", "removed"])


if __name__ == "__main__":
    unittest.main()
