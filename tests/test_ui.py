import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import package_backend as backend
from package_uninstaller import PackageUninstaller, UninstallWorker, ScanWorker, RemovalDialog, apply_theme
from test_backend import package, inventory


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setApplicationName("PackageUninstallerTests")
        apply_theme(cls.app)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = PackageUninstaller(autoload=False, storage=self.directory.name, persist=False)
        self.data = inventory([package("alpha", requires=["beta"]), package("beta"), package("pip"), package("PyQt6"), package("version-two", version="2"), package("version-ten", version="10")])
        self.window.on_packages_loaded(self.data)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def check(self, name):
        for row in range(self.window.package_table.rowCount()):
            item = self.window.package_table.item(row, 0)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                item.setCheckState(Qt.CheckState.Checked)
                return row
        self.fail("Package missing")

    def test_selection_survives_sort_refresh_and_clear(self):
        self.check("beta")
        self.window.sort_combo.setCurrentText("Size")
        self.window.toggle_sort_order()
        self.assertEqual(self.window.selected_packages, {"beta"})
        self.window.on_packages_loaded(self.data)
        checked = {self.window.package_table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in range(self.window.package_table.rowCount()) if self.window.package_table.item(row, 0).checkState() == Qt.CheckState.Checked}
        self.assertEqual(checked, {"beta"})
        self.window.deselect_all_packages()
        self.assertEqual(self.window.selected_packages, set())

    def test_filter_selects_only_visible_removable_packages(self):
        self.window.search_box.setText("alpha")
        self.window.select_all_packages()
        self.assertEqual(self.window.selected_packages, {"alpha"})
        self.window.search_box.setText("beta")
        self.assertIn("1 hidden", self.window.selected_info.text())
        self.window.search_box.clear()
        self.window.select_all_packages()
        self.assertNotIn("pip", self.window.selected_packages)
        self.assertNotIn("pyqt6", self.window.selected_packages)

    def test_no_control_reenables_removal_while_busy(self):
        self.check("alpha")
        self.window.set_busy("uninstall")
        self.window.update_selected_info()
        self.window.search_box.setText("beta")
        self.window.update_selected_info()
        self.assertFalse(self.window.uninstall_btn.isEnabled())
        self.assertFalse(self.window.refresh_btn.isEnabled())
        self.assertFalse(self.window.package_table.isEnabled())
        self.assertFalse(self.window.select_all_btn.isEnabled())
        self.window.set_busy("")
        self.assertTrue(self.window.uninstall_btn.isEnabled())

    def test_versions_sort_semantically(self):
        self.window.sort_combo.setCurrentText("Version")
        names = [self.window.package_table.item(row, 1).text() for row in range(self.window.package_table.rowCount())]
        self.assertLess(names.index("version-two"), names.index("version-ten"))

    def paginated_inventory(self):
        self.window.page_size_combo.setCurrentIndex(1)
        self.window.on_packages_loaded(inventory([package(f"package-{index:03d}") for index in range(73)]))

    def test_numbered_pages_preserve_selection_and_clamp_last_page(self):
        self.paginated_inventory()
        self.assertEqual(self.window.package_table.rowCount(), 25)
        self.assertEqual(self.window.page_count(), 3)
        self.check("package-000")
        self.window.go_to_page(1)
        self.assertEqual(self.window.package_table.item(0, 1).text(), "package-025")
        self.assertIn("1 on other pages", self.window.selected_info.text())
        self.check("package-025")
        self.window.go_to_page(99)
        self.assertEqual(self.window.current_page, 2)
        self.assertEqual(self.window.package_table.rowCount(), 23)
        self.assertFalse(self.window.next_btn.isEnabled())
        self.window.go_to_page(0)
        self.assertEqual(self.window.package_table.item(0, 0).checkState(), Qt.CheckState.Checked)
        self.assertEqual(self.window.selected_packages, {"package-000", "package-025"})

    def test_search_covers_all_pages_and_empty_results_reset_navigation(self):
        self.paginated_inventory()
        self.window.go_to_page(1)
        self.window.search_box.setText("package-072")
        self.assertEqual(self.window.current_page, 0)
        self.assertEqual(self.window.package_table.rowCount(), 1)
        self.assertEqual(self.window.package_table.item(0, 1).text(), "package-072")
        self.window.search_box.setText("no-such-package")
        self.assertEqual(self.window.package_table.rowCount(), 0)
        self.assertFalse(self.window.next_btn.isEnabled())
        self.assertFalse(self.window.previous_btn.isEnabled())
        self.assertFalse(self.window.select_all_btn.isEnabled())
        self.window.search_box.clear()
        self.assertEqual(self.window.page_count(), 3)

    def test_select_page_does_not_select_other_pages_and_clear_is_global(self):
        self.paginated_inventory()
        self.window.select_all_packages()
        self.assertEqual(len(self.window.selected_packages), 25)
        self.window.go_to_page(1)
        self.window.select_all_packages()
        self.assertEqual(len(self.window.selected_packages), 50)
        self.window.deselect_all_packages()
        self.assertEqual(self.window.selected_packages, set())

    def test_pagination_cannot_change_during_removal(self):
        self.paginated_inventory()
        self.window.set_busy("uninstall")
        self.window.go_to_page(1)
        self.assertEqual(self.window.current_page, 0)
        self.assertFalse(self.window.next_btn.isEnabled())
        self.assertFalse(self.window.page_size_combo.isEnabled())
        self.assertTrue(all(not control.isEnabled() for control in self.window.page_buttons))
        self.window.set_busy("")

    def test_refresh_clamps_page_when_inventory_shrinks(self):
        self.paginated_inventory()
        self.window.go_to_page(2)
        self.window.on_packages_loaded(inventory([package("remaining")]))
        self.assertEqual(self.window.current_page, 0)
        self.assertEqual(self.window.package_table.rowCount(), 1)

    def test_html_metadata_and_output_display_as_plain_text(self):
        self.data["packages"][0]["description"] = "<img src='file:///secret'> <b>hello</b>"
        self.window.on_packages_loaded(self.data)
        row = self.check("alpha")
        self.window.package_table.setCurrentCell(row, 1)
        self.window.on_package_selected_details()
        self.assertIn("<b>hello</b>", self.window.details_text.toPlainText())
        self.window.log_message("<b>unsafe</b>")
        self.assertIn("<b>unsafe</b>", self.window.log_text.toPlainText())
        self.assertNotIn("[-1]", self.window.log_text.toPlainText())

    def test_review_displays_dependents_and_requires_acknowledgement(self):
        dialog = RemovalDialog(self.window, {"beta"})
        self.assertFalse(dialog.remove_button.isEnabled())
        from PyQt6.QtWidgets import QTextEdit
        content = dialog.findChild(QTextEdit).toPlainText()
        self.assertIn("alpha", content)
        self.assertIn("REQUIRED DEPENDENCY", content)
        dialog.acknowledge.setChecked(True)
        self.assertTrue(dialog.remove_button.isEnabled())
        dialog.close()

    def test_duplicate_metadata_and_non_pip_conda_are_protected(self):
        data = inventory([package("duplicate"), package("duplicate"), package("numpy", installer="unknown")])
        data["environment"]["is_conda"] = True
        self.window.on_packages_loaded(data)
        self.window.select_all_packages()
        self.assertEqual(self.window.selected_packages, set())

    def test_missing_pip_disables_mutations_but_allows_inspection(self):
        self.data["environment"]["has_pip"] = False
        self.window.on_packages_loaded(self.data)
        self.check("alpha")
        self.assertFalse(self.window.export_btn.isEnabled())
        self.assertFalse(self.window.uninstall_btn.isEnabled())
        self.assertTrue(self.window.package_table.isEnabled())

    def test_failed_discovery_recovers_controls_and_clears_stale_inventory(self):
        self.window.inventory = None
        self.window.set_busy("scan")
        self.window.pending_error = "Invalid interpreter"
        self.window.worker_finished()
        self.assertTrue(self.window.refresh_btn.isEnabled())
        self.assertFalse(self.window.uninstall_btn.isEnabled())
        self.assertEqual(self.window.package_table.rowCount(), 0)

    def test_async_scan_failure_and_close_are_safe(self):
        self.window.environment_combo.blockSignals(True)
        self.window.environment_combo.addItem("Missing Python", str(Path(self.directory.name) / "missing.exe"))
        self.window.environment_combo.setCurrentIndex(self.window.environment_combo.count() - 1)
        self.window.environment_combo.blockSignals(False)
        self.window.load_packages()
        deadline = time.monotonic() + 5
        while self.window.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertFalse(self.window.busy)
        self.assertTrue(self.window.refresh_btn.isEnabled())
        self.assertIsNone(self.window.inventory)

    def test_scan_can_be_cancelled_without_emitting_inventory(self):
        worker = ScanWorker(sys.executable)
        results = []
        worker.loaded.connect(results.append)
        # Replace only the launched command with a harmless slow subprocess.
        with patch.object(backend, "python_command", return_value=[sys.executable, "-c", "import time; time.sleep(5)"]):
            worker.start()
            worker.requestInterruption()
            self.assertTrue(worker.wait(3000))
        self.app.processEvents()
        self.assertEqual(results, [])

    def test_close_waits_for_discovery_thread_before_destroying_window(self):
        self.window.show()
        self.window.set_busy("scan")
        self.window.inventory = None
        self.window.pending_inventory = None
        self.window.worker = ScanWorker(sys.executable)
        self.window.worker.finished.connect(self.window.worker_finished)
        with patch.object(backend, "python_command", return_value=[sys.executable, "-c", "import time; time.sleep(5)"]):
            self.window.worker.start()
            self.window.close()
            self.assertTrue(self.window.closing)
            self.assertIsNotNone(self.window.worker)
            deadline = time.monotonic() + 5
            while self.window.worker is not None and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
        self.assertIsNone(self.window.worker)
        self.assertFalse(self.window.isVisible())


class RemovalWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def run_worker(self, data, selected, failure=False, stop_after_first=False, snapshot_error=False):
        with tempfile.TemporaryDirectory() as directory:
            worker = UninstallWorker("/test/python", data, selected, directory)
            reports = []
            worker.completed.connect(reports.append)
            calls = []

            def remove(executable, name):
                calls.append(name)
                if stop_after_first:
                    worker.requestInterruption()
                return (not failure), "pip output"

            with patch.object(backend, "read_environment", return_value=data), patch.object(backend, "run_python", return_value=subprocess.CompletedProcess([], 0, "", "")), patch.object(backend, "perform_uninstall", side_effect=remove), patch.object(backend, "create_snapshot", side_effect=RuntimeError("Disk full") if snapshot_error else None, return_value=Path(directory) / "backup"):
                # requestInterruption only works on an actual running QThread.
                worker.start()
                self.assertTrue(worker.wait(5000))
                QApplication.instance().processEvents()
            return calls, reports[-1]

    def test_cancellation_stops_between_packages(self):
        data = inventory([package("alpha", requires=["beta"]), package("beta")])
        calls, report = self.run_worker(data, {"alpha", "beta"}, stop_after_first=True)
        self.assertEqual(calls, ["alpha"])
        self.assertTrue(report["cancelled"])
        self.assertEqual(report["removed"], ["alpha"])
        self.assertEqual(report["skipped"], ["beta"])

    def test_failure_stops_remaining_queue(self):
        data = inventory([package("alpha", requires=["beta"]), package("beta")])
        calls, report = self.run_worker(data, {"alpha", "beta"}, failure=True)
        self.assertEqual(calls, ["alpha"])
        self.assertEqual(report["failed"], ["alpha"])
        self.assertEqual(report["skipped"], ["beta"])

    def test_snapshot_failure_means_nothing_removed(self):
        calls, report = self.run_worker(inventory([package("alpha")]), {"alpha"}, snapshot_error=True)
        self.assertEqual(calls, [])
        self.assertIn("Disk full", report["error"])
        self.assertEqual(report["skipped"], ["alpha"])

    def test_protected_package_is_also_blocked_inside_worker(self):
        calls, report = self.run_worker(inventory([package("pip")]), {"pip"})
        self.assertEqual(calls, [])
        self.assertIn("blocked", report["error"])


if __name__ == "__main__":
    unittest.main()
