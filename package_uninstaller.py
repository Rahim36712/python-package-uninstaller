"""A local, environment-aware Python package uninstaller."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

from packaging.version import Version, InvalidVersion
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QSettings, QStandardPaths, QEvent
from PyQt6.QtGui import QColor, QFont, QPalette, QDesktopServices, QGuiApplication, QTextCursor
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QLayout,
    QTextEdit, QVBoxLayout, QWidget,
)

import package_backend as backend


STYLE = """
QWidget { color: #202127; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QDialog { background: #f5f5f6; }
QFrame#card { background: #ffffff; border: 1px solid #dedfe3; border-radius: 12px; }
QLabel#muted { color: #676a74; }
QLabel#heading { font-size: 22px; font-weight: 700; }
QLabel#section { font-size: 14px; font-weight: 600; }
QLabel#badge { color: #4b4e58; background: #e9eaed; border-radius: 8px; padding: 4px 10px; font-size: 11px; }
QLabel#warning { color: #775120; background: #fff6e7; border: 1px solid #eedab8; border-radius: 8px; padding: 6px 10px; font-size: 12px; }
QLabel#error { color: #972b3d; background: #fff0f2; border: 1px solid #eec5ce; border-radius: 8px; padding: 8px 10px; }
QLabel#status { color: #676a74; padding: 2px 0; font-size: 12px; }
QLineEdit, QComboBox { background: #ffffff; border: 1px solid #ced0d7; border-radius: 8px; padding: 6px 10px; min-height: 18px; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #555966; }
QComboBox::drop-down { border: none; width: 27px; }
QComboBox::down-arrow { image: url("__CHEVRON__"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #c8cbd3; selection-background-color: #e8e9ed; selection-color: #202127; padding: 5px; }
QPushButton { background: #ffffff; border: 1px solid #d2d4db; border-radius: 8px; padding: 6px 11px; min-height: 18px; font-weight: 600; }
QPushButton:hover { background: #f0f1f3; border-color: #a7aab4; }
QPushButton:pressed { background: #e6e7ec; }
QPushButton:focus { border: 1px solid #555966; }
QPushButton:disabled { background: #f8f8f9; color: #999ca6; border-color: #e5e6eb; }
QPushButton#primary { background: #25262d; border-color: #25262d; color: white; }
QPushButton#primary:hover { background: #41434c; }
QPushButton#primary:disabled { background: #e8e9ed; color: #92959f; border-color: #e0e1e6; }
QPushButton#quiet { background: transparent; border-color: #d2d4db; }
QPushButton#quiet:hover { background: #f0f1f3; }
QPushButton#page { padding: 2px; min-height: 22px; border-radius: 6px; font-size: 12px; }
QPushButton#page:checked { background: #25262d; border-color: #25262d; color: #ffffff; }
QTableWidget { background: #ffffff; alternate-background-color: #fafafb; border: none; outline: none; gridline-color: transparent; selection-background-color: #e9eaf0; selection-color: #202127; }
QTableWidget::item { padding: 3px 6px; border-bottom: 1px solid #eeeef1; }
QTableWidget::item:focus { border: 1px solid #a5a9b7; }
QHeaderView::section { background: #f6f6f8; color: #60636f; font-size: 11px; border: none; border-bottom: 1px solid #dedfe5; padding: 5px 6px; font-weight: 600; }
QTableCornerButton::section { background: #f6f6f8; border: none; }
QTextEdit { background: #fbfbfc; border: 1px solid #dfe1e7; border-radius: 8px; padding: 8px; selection-background-color: #e0e2e9; selection-color: #202127; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator, QTableView::indicator { width: 15px; height: 15px; border: 1px solid #a2a6b2; border-radius: 4px; background: #ffffff; }
QCheckBox::indicator:checked, QTableView::indicator:checked { image: url("__CHECK__"); background: #25262d; border-color: #25262d; }
QTableView::indicator:disabled { border-color: #d8dae2; background: #f2f3f6; }
QProgressBar { background: #e8e9ee; border: none; border-radius: 4px; height: 6px; text-align: center; }
QProgressBar::chunk { background: #565963; border-radius: 4px; }
QSplitter::handle { background: transparent; width: 10px; }
QSplitter::handle:hover { background: #dedfe6; border-radius: 4px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 3px; }
QScrollBar::handle:vertical { background: #c1c4ce; min-height: 28px; border-radius: 4px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 3px; }
QScrollBar::handle:horizontal { background: #c1c4ce; min-width: 28px; border-radius: 4px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { background: #25262d; color: #ffffff; border: 1px solid #41434c; padding: 7px; }
"""


def label(text, role=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if role:
        widget.setObjectName(role)
    return widget


def button(text, callback, role=None, tooltip=None):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if role:
        widget.setObjectName(role)
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def card():
    widget = QFrame()
    widget.setObjectName("card")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)
    return widget, layout


class ScanWorker(QThread):
    loaded = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, executable):
        super().__init__()
        self.executable = executable

    def run(self):
        process = None
        try:
            process = subprocess.Popen(
                backend.python_command(self.executable, Path(backend.__file__).resolve(), "--scan"),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, **backend.process_options(),
            )
            deadline = time.monotonic() + 120
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    if self.isInterruptionRequested():
                        process.kill()
                        process.communicate()
                        return
                    if time.monotonic() > deadline:
                        raise RuntimeError("Discovery exceeded two minutes. Check the interpreter and file access.")
            if self.isInterruptionRequested():
                return
            if process.returncode:
                raise RuntimeError(stderr.strip() or "The selected Python interpreter could not be inspected.")
            self.loaded.emit(json.loads(stdout))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()


class ExportWorker(QThread):
    exported = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, executable, destination):
        super().__init__()
        self.executable, self.destination = executable, Path(destination)

    def run(self):
        try:
            result = backend.run_python(self.executable, ["-m", "pip", "freeze", "--all"], timeout=60)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "Pip could not export this environment.")
            self.destination.write_text(result.stdout, encoding="utf-8")
            self.exported.emit(str(self.destination))
        except Exception as exc:
            self.failed.emit(str(exc))


class UninstallWorker(QThread):
    message = pyqtSignal(str)
    package_done = pyqtSignal(str, bool, str)
    completed = pyqtSignal(dict)

    def __init__(self, executable, inventory, selected, storage):
        super().__init__()
        self.executable, self.inventory = executable, inventory
        self.selected, self.storage = set(selected), Path(storage)

    def run(self):
        summary = {"removed": [], "failed": [], "skipped": sorted(self.selected), "cancelled": False, "snapshot": "", "error": ""}
        try:
            self.message.emit("Checking that the environment still matches your removal plan…")
            current = backend.read_environment(self.executable)
            backend.validate_plan(self.inventory["packages"], current["packages"], self.selected)
            by_key = {package["key"]: package for package in current["packages"]}
            for key in self.selected:
                reason = backend.protection_reason(by_key[key], self.executable, sys.executable, current["environment"])
                if sum(p["key"] == key for p in current["packages"]) > 1:
                    reason = "Duplicate distribution metadata"
                if reason:
                    raise RuntimeError(f"Removal blocked for {by_key[key]['name']}: {reason}.")
            if self.isInterruptionRequested():
                summary["cancelled"] = True
                return
            self.message.emit("Saving a recovery snapshot before making changes…")
            folder = backend.create_snapshot(self.executable, current, self.selected, self.storage / "snapshots")
            summary["snapshot"] = str(folder)
            backend.append_history(self.storage, {
                "action": "planned", "executable": self.executable,
                "packages": sorted(self.selected), "snapshot": str(folder),
            })
            self.message.emit(f"Recovery files saved to {folder}")
            check = backend.run_python(self.executable, ["-m", "pip", "check"], timeout=60)
            if check.returncode:
                self.message.emit("Existing dependency issues before removal:\n" + (check.stdout + check.stderr).strip())
            graph, _, _ = backend.dependency_graph(current["packages"], current["environment"])
            ordered = backend.removal_order(self.selected, graph)
            for index, key in enumerate(ordered):
                if self.isInterruptionRequested():
                    summary["cancelled"] = True
                    summary["skipped"] = ordered[index:]
                    break
                name = by_key[key]["name"]
                self.message.emit(f"Removing {name} ({index + 1}/{len(ordered)})…")
                summary["skipped"] = ordered[index + 1:]
                try:
                    # Commit a journal entry before each individual pip invocation.
                    backend.append_history(self.storage, {"action": "started", "package": name, "snapshot": str(folder), "executable": self.executable})
                    success, output = backend.perform_uninstall(self.executable, name)
                except Exception as exc:
                    success, output = False, str(exc)
                summary["removed" if success else "failed"].append(name)
                self.message.emit(output)
                self.package_done.emit(key, success, output)
                backend.append_history(self.storage, {
                    "action": "removed" if success else "failed", "package": name,
                    "executable": self.executable, "snapshot": str(folder), "output": output,
                })
                if not success:
                    # A failure may mean pip partially changed the environment.
                    summary["skipped"] = ordered[index + 1:]
                    self.message.emit("Stopped the queue after a failure. Refresh before retrying.")
                    break
            if summary["removed"] or summary["failed"]:
                self.message.emit("Checking remaining dependency consistency…")
                check = backend.run_python(self.executable, ["-m", "pip", "check"], timeout=60)
                self.message.emit((check.stdout + check.stderr).strip() or "Dependency check finished.")
        except Exception as exc:
            summary["error"] = str(exc)
            self.message.emit(f"Stopped: {exc}")
        finally:
            self.completed.emit(summary)


class RemovalDialog(QDialog):
    def __init__(self, parent, selected):
        super().__init__(parent)
        self.setWindowTitle("Review package removal")
        self.resize(600, 580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(15)
        layout.addWidget(label("Review removal", "heading"))
        layout.addWidget(label(f"{len(selected)} package(s) · Python {parent.environment['version']}", "muted"))
        layout.addWidget(label(parent.loaded_executable, "muted", True))
        required, possible = backend.removal_warnings(selected, parent.graph, parent.optional_graph)
        names = parent.packages_by_key
        lines = ["PACKAGES TO REMOVE"]
        for key in sorted(selected):
            package = names[key]
            lines.append(f"• {package['name']}  {package['version']}")
            if package.get("editable"):
                lines.append("  Editable install: source files will remain on disk.")
        if required:
            lines += ["", "REMAINING PACKAGES THAT WILL LOSE A REQUIRED DEPENDENCY"]
            for key, dependents in sorted(required.items()):
                lines.append(f"• {names[key]['name']} is required by: {', '.join(sorted(dependents))}")
        if possible:
            lines += ["", "POSSIBLE OPTIONAL FEATURE IMPACT"]
            for key, dependents in sorted(possible.items()):
                lines.append(f"• {names[key]['name']} appears in extras for: {', '.join(sorted(dependents))}")
        if parent.dependency_errors:
            lines += ["", "DEPENDENCY METADATA COULD NOT BE FULLY EVALUATED", *parent.dependency_errors]
        if not parent.environment["is_venv"]:
            lines += ["", "This is a shared/global Python installation. Other projects may use these packages."]
        if parent.environment.get("is_conda"):
            lines += ["", "Conda environment: only pip-managed packages should be removed here."]
        review = QTextEdit()
        review.setReadOnly(True)
        review.setPlainText("\n".join(lines))
        layout.addWidget(review, 1)
        layout.addWidget(label("A requirements snapshot is saved first. Recovery requires reinstalling; it cannot guarantee an exact rollback.", "muted", True))
        self.acknowledge = QCheckBox("I reviewed the packages and understand the impact")
        layout.addWidget(self.acknowledge)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.remove_button = controls.addButton(f"Remove {len(selected)} package(s)", QDialogButtonBox.ButtonRole.AcceptRole)
        self.remove_button.setObjectName("primary")
        self.remove_button.setEnabled(False)
        self.acknowledge.toggled.connect(self.remove_button.setEnabled)
        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)
        controls.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)


class PackageUninstaller(QMainWindow):
    def __init__(self, autoload=True, storage=None, persist=True):
        super().__init__()
        self.settings = QSettings("LocalTools", "PythonPackageUninstaller") if persist else None
        default_storage = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        self.storage = Path(storage) if storage else default_storage
        self.packages, self.packages_by_key, self.selected_packages = [], {}, set()
        self.environment, self.graph, self.optional_graph = {}, {}, {}
        self.dependency_errors = []
        self.loaded_executable = ""
        self.inventory = None
        self.busy = False
        self.operation = ""
        self.building = False
        self.worker = None
        self.pending_inventory = None
        self.pending_error = ""
        self.pending_summary = None
        self.closing = False
        self.current_page = 0
        self.page_capacity = 15
        self.filtered_packages = []
        self.page_buttons = []
        self.fit_update_pending = False
        self.init_ui()
        if autoload:
            QTimer.singleShot(0, self.load_packages)

    def init_ui(self):
        self.setWindowTitle("Python Package Uninstaller")
        self.resize(1240, 820)
        self.setMinimumSize(960, 680)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)
        header = QHBoxLayout()
        header.addWidget(label("Package Uninstaller", "heading"), 1)
        header.addWidget(label("Python packages", "badge"))
        layout.addLayout(header)

        environment_card, env_layout = card()
        env_layout.setContentsMargins(14, 10, 14, 10)
        env_layout.setSpacing(5)
        env_row = QHBoxLayout()
        env_row.addWidget(label("Environment", "section"))
        self.environment_combo = QComboBox()
        self.environment_combo.setAccessibleName("Python environment")
        self.environment_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.environment_combo.setMinimumWidth(250)
        self.environment_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.environment_combo.setMinimumContentsLength(30)
        candidates = [sys.executable]
        if self.settings:
            candidates += self.settings.value("environments", [], type=list)
        for candidate in [Path.cwd() / ".venv" / "Scripts" / "python.exe", Path.cwd() / "venv" / "Scripts" / "python.exe"]:
            if candidate.is_file():
                candidates.append(str(candidate))
        for candidate in dict.fromkeys(candidates):
            if Path(candidate).is_file():
                self.environment_combo.addItem(candidate, candidate)
        env_row.addWidget(self.environment_combo, 1)
        self.add_environment_btn = button("Browse…", self.browse_environment, "quiet", "Choose another Python interpreter or virtual environment")
        env_row.addWidget(self.add_environment_btn)
        self.export_btn = button("Export requirements", self.export_requirements, "quiet", "Save pip freeze output for the selected environment")
        env_row.addWidget(self.export_btn)
        env_layout.addLayout(env_row)
        self.environment_info = label("Choose a Python interpreter to inspect its installed packages.", "muted", True)
        env_layout.addWidget(self.environment_info)
        self.environment_combo.currentIndexChanged.connect(self.load_packages)
        layout.addWidget(environment_card)

        self.banner = label("", "warning", True)
        self.banner.hide()
        layout.addWidget(self.banner)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, 1)

        inventory_card, inventory_layout = card()
        inventory_layout.setContentsMargins(12, 12, 12, 10)
        inventory_layout.setSpacing(8)
        toolbar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search packages…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setAccessibleName("Search packages by name or description")
        self.search_box.setToolTip("Search package names and descriptions · Ctrl+F")
        self.search_box.textChanged.connect(self.filter_packages)
        toolbar.addWidget(self.search_box, 1)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Name", "Size", "Version"])
        self.sort_combo.setAccessibleName("Sort packages")
        self.sort_combo.currentTextChanged.connect(self.populate_table)
        toolbar.addWidget(self.sort_combo)
        self.sort_order_btn = button("↑", self.toggle_sort_order, tooltip="Ascending order; click for descending")
        self.sort_order_btn.setAccessibleName("Toggle sort direction")
        self.sort_order_btn.setFixedWidth(32)
        self.descending = False
        toolbar.addWidget(self.sort_order_btn)
        self.refresh_btn = button("Refresh", self.load_packages, "quiet", "Rediscover packages and recorded file sizes · F5")
        toolbar.addWidget(self.refresh_btn)
        inventory_layout.addLayout(toolbar)
        selection_row = QHBoxLayout()
        self.select_all_btn = button("Select page", self.select_all_packages, "quiet", "Select removable packages on this page only")
        self.deselect_all_btn = button("Clear selection", self.deselect_all_packages, "quiet")
        selection_row.addWidget(self.select_all_btn)
        selection_row.addWidget(self.deselect_all_btn)
        selection_row.addStretch()
        self.result_count = label("0 packages", "muted")
        selection_row.addWidget(self.result_count)
        self.page_size_combo = QComboBox()
        for text, size in [("Auto rows", 0), ("25 rows", 25), ("50 rows", 50), ("100 rows", 100)]:
            self.page_size_combo.addItem(text, size)
        self.page_size_combo.setAccessibleName("Packages per page")
        self.page_size_combo.setToolTip("Auto rows fits each page to the window without vertical scrolling")
        self.page_size_combo.currentIndexChanged.connect(self.change_page_size)
        selection_row.addWidget(self.page_size_combo)
        inventory_layout.addLayout(selection_row)

        self.table_stack = QStackedWidget()
        self.package_table = QTableWidget(0, 4)
        self.package_table.setHorizontalHeaderLabels(["", "PACKAGE", "VERSION", "RECORDED SIZE"])
        self.package_table.setAccessibleName("Installed packages; check a box to include a package in removal")
        self.package_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.package_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.package_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.package_table.setAlternatingRowColors(True)
        self.package_table.setShowGrid(False)
        self.package_table.verticalHeader().hide()
        self.package_table.verticalHeader().setMinimumSectionSize(26)
        self.package_table.verticalHeader().setDefaultSectionSize(26)
        self.package_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.package_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        head = self.package_table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        head.resizeSection(0, 34)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        head.resizeSection(2, 105)
        head.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        head.resizeSection(3, 130)
        self.package_table.itemChanged.connect(self.on_item_changed)
        self.package_table.itemSelectionChanged.connect(self.on_package_selected_details)
        self.package_table.viewport().installEventFilter(self)
        self.table_stack.addWidget(self.package_table)
        self.empty_state = label("Discovering installed packages…", "muted", True)
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_stack.addWidget(self.empty_state)
        inventory_layout.addWidget(self.table_stack, 1)
        pagination = QHBoxLayout()
        pagination.setSpacing(4)
        self.page_info = label("0 packages", "muted")
        pagination.addWidget(self.page_info)
        pagination.addStretch()
        self.previous_btn = button("‹", lambda: self.go_to_page(self.current_page - 1), "page", "Previous page")
        self.previous_btn.setFixedWidth(28)
        self.previous_btn.setAccessibleName("Previous package page")
        pagination.addWidget(self.previous_btn)
        self.number_layout = QHBoxLayout()
        self.number_layout.setSpacing(4)
        pagination.addLayout(self.number_layout)
        self.next_btn = button("›", lambda: self.go_to_page(self.current_page + 1), "page", "Next page")
        self.next_btn.setFixedWidth(28)
        self.next_btn.setAccessibleName("Next package page")
        pagination.addWidget(self.next_btn)
        inventory_layout.addLayout(pagination)
        self.splitter.addWidget(inventory_card)

        side_card, side_layout = card()
        side_card.setMinimumWidth(270)
        side_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(8)
        details_header = QHBoxLayout()
        details_header.addWidget(label("Package details", "section"), 1)
        self.copy_location_btn = button("Copy path", self.copy_location, "quiet")
        self.copy_location_btn.setStyleSheet("padding: 4px 8px; min-height: 16px; font-size: 11px;")
        self.copy_location_btn.setEnabled(False)
        details_header.addWidget(self.copy_location_btn)
        side_layout.addLayout(details_header)
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setAccessibleName("Focused package details and dependency information")
        self.details_text.setMinimumHeight(60)
        self.details_text.setPlainText("Click a package to see its description, location and dependencies.")
        side_layout.addWidget(self.details_text, 3)
        self.selected_info = label("Removal selection · none", "muted", True)
        side_layout.addWidget(self.selected_info)
        self.selection_preview = QTextEdit()
        self.selection_preview.setReadOnly(True)
        self.selection_preview.setAccessibleName("All packages selected for removal across every page and search")
        self.selection_preview.setMinimumHeight(40)
        self.selection_preview.setMaximumHeight(110)
        self.selection_preview.setPlainText("Your selected packages will appear here.")
        side_layout.addWidget(self.selection_preview, 1)
        self.uninstall_btn = button("Review removal", self.uninstall_selected, "primary")
        self.uninstall_btn.setEnabled(False)
        side_layout.addWidget(self.uninstall_btn)
        self.recovery_btn = button("Recovery && history", self.show_recovery, "quiet")
        self.splitter.addWidget(side_card)
        self.splitter.setSizes([900, 300])

        footer = QHBoxLayout()
        self.status_label = label("Ready", "status", True)
        footer.addWidget(self.status_label, 1)
        self.cancel_btn = button("Cancel", self.cancel_operation, "quiet")
        self.cancel_btn.hide()
        footer.addWidget(self.cancel_btn)
        self.log_toggle = button("Show activity", self.toggle_log, "quiet")
        footer.addWidget(self.recovery_btn)
        footer.addWidget(self.log_toggle)
        layout.addLayout(footer)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setAccessibleName("Activity log")
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setMinimumHeight(110)
        self.log_text.setMaximumHeight(180)
        self.log_text.document().setMaximumBlockCount(2500)
        self.log_text.hide()
        layout.addWidget(self.log_text)

        from PyQt6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search_box.setFocus)
        QShortcut(QKeySequence("F5"), self, activated=self.load_packages)
        QShortcut(QKeySequence("Escape"), self, activated=self.cancel_operation)
        if self.settings:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
            # The denser layout gets its own proportions; old dark-layout widths
            # must not crowd the package list after this redesign.
            splitter = self.settings.value("splitter_compact")
            if splitter:
                self.splitter.restoreState(splitter)
        self.update_controls()

    def eventFilter(self, watched, event):
        if hasattr(self, "package_table") and watched is self.package_table.viewport() and event.type() == QEvent.Type.Resize:
            if not self.fit_update_pending:
                self.fit_update_pending = True
                QTimer.singleShot(0, self.sync_page_capacity)
        return super().eventFilter(watched, event)

    def sync_page_capacity(self):
        self.fit_update_pending = False
        if self.closing or not hasattr(self, "page_size_combo") or self.page_size_combo.currentData() != 0:
            return
        height = self.package_table.viewport().height()
        capacity = max(1, height // self.package_table.verticalHeader().defaultSectionSize())
        if capacity != self.page_capacity:
            # Preserve the first visible package as closely as possible on resize.
            first_index = self.current_page * self.page_capacity
            self.page_capacity = capacity
            self.current_page = first_index // capacity
            if self.inventory is not None:
                self.populate_table()

    def rows_per_page(self):
        return self.page_size_combo.currentData() or self.page_capacity

    def change_page_size(self, *_):
        self.current_page = 0
        automatic = self.page_size_combo.currentData() == 0
        self.package_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if automatic else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        if automatic:
            self.sync_page_capacity()
        self.populate_table()

    def page_count(self):
        return max(1, (len(self.filtered_packages) + self.rows_per_page() - 1) // self.rows_per_page())

    def go_to_page(self, page):
        if self.busy or not self.inventory:
            return
        self.current_page = min(max(page, 0), self.page_count() - 1)
        self.populate_table()

    def update_pagination(self):
        while self.number_layout.count():
            item = self.number_layout.takeAt(0)
            item.widget().deleteLater()
        self.page_buttons = []
        count = self.page_count()
        start = max(0, min(self.current_page - 1, count - 3))
        pages = sorted({0, count - 1} | set(range(start, min(count, start + 3))))
        previous = -1
        for page in pages:
            if page > previous + 1:
                self.number_layout.addWidget(label("…", "muted"))
            control = button(str(page + 1), lambda _=False, p=page: self.go_to_page(p), "page")
            control.setFixedWidth(max(28, 12 + len(str(page + 1)) * 8))
            control.setCheckable(True)
            control.setChecked(page == self.current_page)
            control.setAccessibleName(f"Package page {page + 1}")
            self.number_layout.addWidget(control)
            self.page_buttons.append(control)
            previous = page
        total = len(self.filtered_packages)
        first = self.current_page * self.rows_per_page() + 1 if total else 0
        last = min(total, (self.current_page + 1) * self.rows_per_page())
        self.page_info.setText(f"{first}–{last} of {total}")
        self.page_info.setToolTip(f"Page {self.current_page + 1} of {count}")
        self.update_controls()

    def chosen_executable(self):
        return self.environment_combo.currentData() or sys.executable

    def set_busy(self, operation):
        self.busy = bool(operation)
        self.operation = operation
        self.progress_bar.setVisible(self.busy)
        if self.busy:
            self.progress_bar.setRange(0, 0)
        self.cancel_btn.setVisible(operation in {"scan", "uninstall"})
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Stop after current" if operation == "uninstall" else "Cancel")
        self.cancel_btn.setToolTip("Finishes the current pip operation before stopping the queue" if operation == "uninstall" else "Stop package discovery")
        self.update_controls()

    def update_controls(self):
        usable = not self.busy and self.inventory is not None
        has_pip = usable and self.environment.get("has_pip", False)
        self.search_box.setEnabled(not self.busy)
        for control in (self.environment_combo, self.add_environment_btn, self.refresh_btn):
            control.setEnabled(not self.busy)
        for control in (self.sort_combo, self.sort_order_btn, self.package_table, self.select_all_btn, self.page_size_combo):
            control.setEnabled(usable)
        self.select_all_btn.setEnabled(usable and any(not self.package_table.isRowHidden(row) for row in range(self.package_table.rowCount())))
        self.deselect_all_btn.setEnabled(usable and bool(self.selected_packages))
        self.export_btn.setEnabled(bool(has_pip))
        self.uninstall_btn.setEnabled(bool(has_pip and self.selected_packages))
        self.previous_btn.setEnabled(usable and self.current_page > 0)
        self.next_btn.setEnabled(usable and self.current_page < self.page_count() - 1)
        for control in self.page_buttons:
            control.setEnabled(usable)

    def browse_environment(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a Python interpreter", str(Path(sys.executable).parent), "Python interpreter (python.exe python3.exe python python3);;All files (*)")
        if not path:
            return
        path = str(Path(path).resolve())
        existing = self.environment_combo.findData(path)
        if existing == -1:
            self.environment_combo.addItem(path, path)
            existing = self.environment_combo.count() - 1
        self.environment_combo.setCurrentIndex(existing)

    def load_packages(self, *_):
        if self.busy or self.closing:
            return
        executable = self.chosen_executable()
        if self.loaded_executable and executable != self.loaded_executable:
            self.selected_packages.clear()
            self.current_page = 0
            self.search_box.clear()
        self.inventory = None
        self.banner.hide()
        self.status_label.setText("Discovering packages and checking their recorded files…")
        self.table_stack.setCurrentWidget(self.empty_state)
        self.empty_state.setText("Discovering packages…\nReading metadata and recorded files in the selected environment.")
        self.pending_inventory, self.pending_error = None, ""
        self.set_busy("scan")
        self.log_message(f"Scanning {executable}")
        self.worker = ScanWorker(executable)
        self.worker.loaded.connect(self.receive_inventory)
        self.worker.failed.connect(self.receive_error)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def receive_inventory(self, inventory):
        self.pending_inventory = inventory

    def receive_error(self, message):
        self.pending_error = message

    def worker_finished(self):
        operation = self.operation
        worker = self.worker
        self.worker = None
        self.set_busy("")
        if worker:
            worker.deleteLater()
        if self.closing:
            self.close()
            return
        if operation == "scan":
            if self.pending_inventory is not None:
                self.on_packages_loaded(self.pending_inventory)
            else:
                self.packages, self.packages_by_key = [], {}
                self.filtered_packages = []
                self.current_page = 0
                self.selected_packages.clear()
                self.package_table.setRowCount(0)
                self.details_text.setPlainText("No inventory loaded. Refresh to try again.")
                self.copy_location_btn.setEnabled(False)
                self.update_selected_info()
                self.result_count.setText("0 packages")
                self.update_pagination()
                message = self.pending_error or "Discovery cancelled. Refresh to try again."
                self.empty_state.setText(message)
                self.status_label.setText("Discovery failed" if self.pending_error else "Discovery cancelled")
                if self.pending_error:
                    self.show_banner(message, error=True)
                self.log_message(message)
        elif operation == "export":
            if self.pending_error:
                self.show_banner("Export failed: " + self.pending_error, error=True)
                self.status_label.setText("Export failed")
        elif operation == "uninstall":
            summary = self.pending_summary or {"error": "Worker stopped unexpectedly", "removed": [], "failed": [], "skipped": [], "snapshot": "", "cancelled": False}
            self.show_summary(summary)
            self.load_packages()

    def on_packages_loaded(self, inventory):
        self.inventory = inventory
        self.environment = inventory["environment"]
        self.loaded_executable = self.chosen_executable()
        packages = inventory["packages"]
        counts = {}
        for package in packages:
            counts[package["key"]] = counts.get(package["key"], 0) + 1
        self.packages = packages
        self.packages_by_key = {package["key"]: package for package in packages}
        for package in self.packages:
            package["protected"] = backend.protection_reason(package, self.loaded_executable, sys.executable, self.environment)
            if counts[package["key"]] > 1:
                package["protected"] = "Duplicate distribution metadata; repair this environment before removal"
        available = {p["key"] for p in self.packages if not p["protected"]}
        self.selected_packages.intersection_update(available)
        self.graph, self.optional_graph, self.dependency_errors = backend.dependency_graph(packages, self.environment)
        kind = "Virtual environment" if self.environment["is_venv"] else "Shared / global installation"
        if self.environment.get("is_conda"):
            kind = "Conda environment"
        self.environment_info.setText(f"Python {self.environment['version']}  ·  {kind}  ·  {len(packages)} installed packages")
        self.environment_combo.setToolTip(self.loaded_executable)
        messages = []
        if not self.environment["is_venv"]:
            messages.append("Shared Python installation. Removing packages may affect other projects.")
        if not self.environment["has_pip"]:
            messages.append("Pip is unavailable in this environment. Inspection works; removal and requirements export are disabled.")
        if inventory.get("warnings") or self.dependency_errors:
            messages.append("Some metadata could not be read. See activity for details.")
        if messages:
            self.show_banner(" ".join(messages))
        else:
            self.banner.hide()
        for warning in inventory.get("warnings", []) + self.dependency_errors:
            self.log_message(warning)
        self.populate_table()
        self.update_selected_info()
        self.on_package_selected_details()
        self.status_label.setText("Check boxes to select packages. Click a name for details.")
        self.log_message(f"Discovery complete: {len(packages)} packages")
        self.update_controls()

    def sort_key(self, package):
        mode = self.sort_combo.currentText()
        if mode == "Size":
            return (package["size"] if package["size"] is not None else -1, package["key"])
        if mode == "Version":
            try:
                return (1, Version(package["version"]), package["key"])
            except InvalidVersion:
                return (0, Version("0"), package["version"])
        return package["key"]

    def focused_key(self):
        row = self.package_table.currentRow()
        item = self.package_table.item(row, 1) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def populate_table(self, *_):
        if not hasattr(self, "package_table"):
            return
        focused = self.focused_key()
        self.building = True
        self.package_table.blockSignals(True)
        try:
            self.packages.sort(key=self.sort_key, reverse=self.descending)
            text = self.search_box.text().strip().casefold()
            self.filtered_packages = [p for p in self.packages if text in (p["name"] + " " + p["description"]).casefold()]
            self.current_page = min(self.current_page, self.page_count() - 1)
            start = self.current_page * self.rows_per_page()
            page = self.filtered_packages[start:start + self.rows_per_page()]
            self.package_table.setCurrentCell(-1, -1)
            self.package_table.clearContents()
            self.package_table.setRowCount(len(page))
            for row, package in enumerate(page):
                self.package_table.setRowHidden(row, False)
                check = QTableWidgetItem()
                check.setData(Qt.ItemDataRole.UserRole, package["key"])
                check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if not package["protected"]:
                    check.setFlags(check.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                check.setCheckState(Qt.CheckState.Checked if package["key"] in self.selected_packages else Qt.CheckState.Unchecked)
                check.setToolTip(package["protected"] or "Include in removal selection (Space to toggle)")
                self.package_table.setItem(row, 0, check)
                size = backend.format_size(package["size"])
                if package["size_kind"] == "partial":
                    size += " *"
                if package.get("editable"):
                    size += " †"
                for column, text in enumerate([package["name"], package["version"], size], 1):
                    item = QTableWidgetItem(text)
                    item.setData(Qt.ItemDataRole.UserRole, package["key"])
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    item.setToolTip(package["protected"] or package["description"])
                    if package["protected"]:
                        item.setForeground(QColor("#767985"))
                    if column == 3:
                        item.setToolTip("Bytes in this distribution’s recorded files; not guaranteed reclaimed space. * Partial metadata / missing files. † Editable source is excluded.")
                    self.package_table.setItem(row, column, item)
                if package["key"] == focused:
                    self.package_table.setCurrentCell(row, 1)
        finally:
            self.package_table.blockSignals(False)
            self.building = False
        self.package_table.scrollToTop()
        self.result_count.setText(f"{len(self.filtered_packages)} packages")
        if self.filtered_packages:
            self.table_stack.setCurrentWidget(self.package_table)
        else:
            self.empty_state.setText("No matching packages. Try another search." if self.packages else "This environment has no discoverable packages.")
            self.table_stack.setCurrentWidget(self.empty_state)
        self.update_pagination()
        self.update_selected_info()
        self.on_package_selected_details()

    def filter_packages(self, *_):
        self.current_page = 0
        if not self.busy:
            self.populate_table()

    def on_item_changed(self, item):
        if self.building or self.busy or item.column() != 0:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.selected_packages.add(key)
        else:
            self.selected_packages.discard(key)
        self.update_selected_info()

    def select_all_packages(self):
        if self.busy:
            return
        for row in range(self.package_table.rowCount()):
            if not self.package_table.isRowHidden(row):
                item = self.package_table.item(row, 0)
                if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    self.selected_packages.add(item.data(Qt.ItemDataRole.UserRole))
        self.populate_table()

    def deselect_all_packages(self):
        if self.busy:
            return
        self.selected_packages.clear()
        self.populate_table()

    def update_selected_info(self):
        count = len(self.selected_packages)
        visible = {self.package_table.item(row, 1).data(Qt.ItemDataRole.UserRole) for row in range(self.package_table.rowCount()) if not self.package_table.isRowHidden(row)}
        matched = {p["key"] for p in self.filtered_packages}
        hidden = len(self.selected_packages - matched)
        elsewhere = len((self.selected_packages & matched) - visible)
        details = [f"{count} selected"]
        if elsewhere:
            details.append(f"{elsewhere} on other pages")
        if hidden:
            details.append(f"{hidden} hidden by search")
        self.selected_info.setText(" · ".join(details))
        entries = [self.packages_by_key[key] for key in sorted(self.selected_packages) if key in self.packages_by_key]
        self.selection_preview.setPlainText("\n".join(f"{p['name']}  {p['version']}" for p in entries) or "Your selected packages will appear here.")
        self.uninstall_btn.setText(f"Review removal ({count})" if count else "Review removal")
        self.update_controls()

    def toggle_sort_order(self):
        if self.busy:
            return
        self.descending = not self.descending
        self.sort_order_btn.setText("↓" if self.descending else "↑")
        self.sort_order_btn.setToolTip("Descending order; click for ascending" if self.descending else "Ascending order; click for descending")
        self.populate_table()

    def on_package_selected_details(self):
        key = self.focused_key()
        package = self.packages_by_key.get(key)
        self.copy_location_btn.setEnabled(bool(package))
        if not package:
            self.details_text.setPlainText("Click a package to see its description, location and dependencies.")
            return
        dependents = sorted(k for k, values in self.graph.items() if key in values)
        lines = [f"{package['name']}  {package['version']}", "", package["description"], "", "RECORDED FILE SIZE", backend.format_size(package["size"])]
        if package["size_kind"] == "unknown":
            lines.append("No file inventory available; size cannot be measured.")
        elif package["size_kind"] == "partial":
            lines.append(f"Partial: {package['missing_files']} file(s) missing or inaccessible.")
        if package.get("editable"):
            lines.append("Editable install: source tree is excluded and will not be deleted.")
        lines += ["Not a guarantee of reclaimed disk space.", "", "INSTALL LOCATION", package["location"], "", "INSTALLER", package["installer"], "", "REQUIRES"]
        lines += package["requires"] or ["No dependencies declared."]
        lines += ["", "REQUIRED BY", ", ".join(dependents) or "No required dependents found in this environment."]
        if package["protected"]:
            lines += ["", "PROTECTED", package["protected"]]
        self.details_text.setPlainText("\n".join(lines))

    def copy_location(self):
        package = self.packages_by_key.get(self.focused_key())
        if package:
            QGuiApplication.clipboard().setText(package["location"])
            self.status_label.setText("Package location copied")

    def uninstall_selected(self):
        if self.busy or not self.inventory or not self.selected_packages or not self.environment.get("has_pip"):
            return
        selected = set(self.selected_packages)
        dialog = RemovalDialog(self, selected)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.pending_summary = None
        self.banner.hide()
        self.set_busy("uninstall")
        self.progress_bar.setRange(0, len(selected))
        self.progress_bar.setValue(0)
        self.status_label.setText("Preparing removal and saving recovery files…")
        self.worker = UninstallWorker(self.loaded_executable, self.inventory, selected, self.storage)
        self.worker.message.connect(self.log_message)
        self.worker.package_done.connect(self.on_uninstall_finished)
        self.worker.completed.connect(self.receive_summary)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def on_uninstall_finished(self, key, success, output):
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        if success:
            self.selected_packages.discard(key)
        self.status_label.setText(f"{'Removed' if success else 'Failed'}: {key}")
        self.update_selected_info()

    def receive_summary(self, summary):
        self.pending_summary = summary

    def show_summary(self, summary):
        text = f"Removed: {len(summary['removed'])}\nFailed: {len(summary['failed'])}\nNot attempted: {len(summary['skipped'])}"
        if summary["cancelled"]:
            text += "\n\nQueue cancelled between packages. Completed removals remain in effect."
        if summary["error"]:
            text += "\n\n" + summary["error"]
        if summary["snapshot"]:
            text += "\n\nRecovery files:\n" + summary["snapshot"]
        self.log_message(text)
        message = QMessageBox(self)
        message.setWindowTitle("Removal results")
        message.setIcon(QMessageBox.Icon.Warning if summary["failed"] or summary["error"] else QMessageBox.Icon.Information)
        message.setText(text)
        message.setDetailedText("Removed:\n" + "\n".join(summary["removed"]) + "\n\nFailed:\n" + "\n".join(summary["failed"]) + "\n\nNot attempted:\n" + "\n".join(summary["skipped"]))
        message.exec()

    def cancel_operation(self):
        if self.worker and self.operation in {"scan", "uninstall"}:
            self.worker.requestInterruption()
            self.cancel_btn.setEnabled(False)
            message = "Stopping discovery…" if self.operation == "scan" else "Stop requested. Waiting for the current pip operation to finish…"
            self.status_label.setText(message)
            self.log_message(message)

    def export_requirements(self):
        if self.busy or not self.environment.get("has_pip"):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export environment requirements", "requirements-backup.txt", "Requirements (*.txt)")
        if not path:
            return
        self.pending_error = ""
        self.set_busy("export")
        self.status_label.setText("Exporting environment requirements…")
        self.worker = ExportWorker(self.loaded_executable, path)
        self.worker.exported.connect(self.on_exported)
        self.worker.failed.connect(self.receive_error)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def on_exported(self, path):
        self.status_label.setText("Requirements exported")
        self.log_message(f"Requirements exported to {path}")

    def toggle_log(self):
        visible = not self.log_text.isVisible()
        self.log_text.setVisible(visible)
        self.log_toggle.setText("Hide activity" if visible else "Show activity")

    def log_message(self, message):
        if not message:
            return
        # Always insert plain text: metadata and pip output are untrusted display text.
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.insertPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.ensureCursorVisible()

    def show_banner(self, message, error=False):
        self.banner.setObjectName("error" if error else "warning")
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner.setText(message)
        self.banner.show()

    def show_recovery(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Recovery & history")
        dialog.resize(720, 560)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(label("Recovery & history", "heading"))
        layout.addWidget(label("Snapshots are saved before every removal. They contain requirements.txt and inventory.json. Reinstall from a snapshot using the same interpreter; packages or local source paths may no longer be available.", "muted", True))
        location = QLineEdit(str(self.storage))
        location.setReadOnly(True)
        layout.addWidget(location)
        records = QTextEdit()
        records.setReadOnly(True)
        lines = []
        try:
            history = self.storage / "history.jsonl"
            if history.exists():
                with history.open(encoding="utf-8") as stream:
                    from collections import deque
                    for line in deque(stream, maxlen=200):
                        try:
                            event = json.loads(line)
                            lines.append(f"{event['time']}  ·  {event['action']}  ·  {event.get('package', ', '.join(event.get('packages', [])))}\n{event.get('executable', '')}\n{event.get('snapshot', '')}\n{event.get('output', '')}\n")
                        except (ValueError, KeyError):
                            lines.append("Unreadable history entry.")
        except OSError as exc:
            lines.append(f"History could not be read: {exc}")
        records.setPlainText("\n".join(reversed(lines)) or "No removals recorded yet.")
        layout.addWidget(records, 1)
        actions = QHBoxLayout()
        actions.addWidget(button("Open recovery folder", self.open_recovery_folder))
        actions.addStretch()
        actions.addWidget(button("Close", dialog.accept))
        layout.addLayout(actions)
        dialog.exec()

    def open_recovery_folder(self):
        try:
            self.storage.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.storage.resolve())))
        except OSError as exc:
            self.show_banner(str(exc), error=True)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            if self.operation == "uninstall" and not self.closing:
                reply = QMessageBox.question(self, "Removal in progress", "Stop the queue and close after the current pip operation finishes?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if reply != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
            self.closing = True
            if self.operation in {"scan", "uninstall"}:
                self.worker.requestInterruption()
            self.status_label.setText("Waiting for background work to finish before closing…")
            event.ignore()
            return
        if self.settings:
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("splitter_compact", self.splitter.saveState())
            self.settings.setValue("environments", [self.environment_combo.itemData(i) for i in range(self.environment_combo.count())])
        event.accept()


def apply_theme(app):
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: "#f5f5f6", QPalette.ColorRole.WindowText: "#202127",
        QPalette.ColorRole.Base: "#ffffff", QPalette.ColorRole.AlternateBase: "#fafafb",
        QPalette.ColorRole.Text: "#202127", QPalette.ColorRole.Button: "#ffffff",
        QPalette.ColorRole.ButtonText: "#202127", QPalette.ColorRole.Highlight: "#e9eaf0",
        QPalette.ColorRole.HighlightedText: "#202127", QPalette.ColorRole.PlaceholderText: "#777b87",
    }.items():
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    assets = Path(__file__).resolve().parent / "assets"
    app.setStyleSheet(STYLE.replace("__CHEVRON__", (assets / "chevron.svg").as_posix()).replace("__CHECK__", (assets / "check.svg").as_posix()))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PythonPackageUninstaller")
    app.setOrganizationName("LocalTools")
    apply_theme(app)
    window = PackageUninstaller()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
