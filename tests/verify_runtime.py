"""Read-only runtime smoke check and offscreen screenshots; no uninstall calls."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase
from package_uninstaller import PackageUninstaller, RemovalDialog, apply_theme


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("verification")
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setApplicationName("PackageUninstallerVerification")
    if app.platformName() == "offscreen" and os.name == "nt":
        # Qt's offscreen plugin does not discover Windows system fonts itself.
        for filename in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename))
    apply_theme(app)
    with tempfile.TemporaryDirectory() as directory:
        window = PackageUninstaller(storage=directory, persist=False)
        window.show()
        deadline = time.monotonic() + 125
        app.processEvents()
        while window.busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        # Showing the loaded table queues a resize and then the auto-fit update.
        for _ in range(5):
            app.processEvents()
        assert window.inventory, "Live discovery failed: " + window.pending_error
        assert window.worker is None and not window.busy
        assert window.refresh_btn.isEnabled()
        assert 0 < window.package_table.rowCount() <= window.rows_per_page()
        assert window.page_count() > 1
        row_height = window.package_table.verticalHeader().defaultSectionSize()
        assert window.package_table.rowCount() * row_height <= window.package_table.viewport().height(), (window.package_table.rowCount(), window.package_table.viewport().height(), window.page_capacity)
        full_rows = window.package_table.rowCount()
        # Exercise selection and details on real metadata without executing pip.
        for row in range(window.package_table.rowCount()):
            item = window.package_table.item(row, 0)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(Qt.CheckState.Checked)
                window.package_table.setCurrentCell(row, 1)
                if len(window.selected_packages) == 2:
                    break
        app.processEvents()
        assert window.grab().save(str(output / "main-window.png"))
        dialog = RemovalDialog(window, set(window.selected_packages))
        dialog.show()
        app.processEvents()
        assert dialog.grab().save(str(output / "removal-review.png"))
        dialog.reject()
        window.resize(960, 680)
        for _ in range(4):
            app.processEvents()
        assert window.package_table.rowCount() * row_height <= window.package_table.viewport().height()
        assert window.package_table.rowCount() >= 10, "Compact layout should expose at least ten complete package rows"
        compact_rows = window.package_table.rowCount()
        assert window.grab().save(str(output / "compact-window.png"))
        window.go_to_page(1)
        app.processEvents()
        assert window.current_page == 1
        assert len(window.selected_packages) == 2
        assert window.grab().save(str(output / "second-page.png"))
        count = len(window.packages)
        window.close()
        app.processEvents()
    print(f"Runtime OK: {count} live packages; {full_rows} rows at 1240x820 and {compact_rows} at 960x680; numbered pages, selection, review and close passed. Screenshots: {output.resolve()}")


if __name__ == "__main__":
    main()
