# Python Package Uninstaller

A local PyQt6 desktop app for inspecting and removing packages from a selected
Python interpreter. It does not uninstall Windows applications or find unused
packages across your projects.

## Run

Requires Python 3.10 or later. From this directory:

```powershell
python -m pip install -r requirements.txt
python package_uninstaller.py
```

The app uses `importlib.metadata`, so it does not need `pkg_resources` or
setuptools to start. The interpreter being inspected needs Python 3.10+;
it does not need PyQt6 or packaging installed. Removal and requirements export
require pip in that interpreter.

## Use

- Choose an environment, or use **Browse…** to select its Python executable.
- The interface uses white surfaces, obsidian text and compact 26-pixel rows.
  **Auto rows** fits each numbered page to the window without vertical scrolling.
  You can also choose **25**, **50** or **100 rows** per page (larger pages may scroll).
- Search names/descriptions across all pages, sort by name/size/version, and check packages.
  Clicking a row shows details; checking its box adds it to the removal plan.
- **Select page** includes only removable packages on the current page. **Clear selection**
  clears all selections, including other pages and hidden results. Selection survives page changes, sorting
  and refresh, and is cleared when switching interpreters.
- **Refresh** / F5 rediscovers metadata and rescans recorded files in a worker.
- **Review removal** lists required dependents, possible extras and shared
  environment impact. Review and acknowledge the list before removal.
- **Stop after current** cancels the queue between pip operations. Completed
  removals remain in effect. A failed removal stops the queue for review.
- **Export requirements** saves that interpreter's `pip freeze --all` output.
- **Recovery & history** displays recent removals and opens the recovery folder.
  **Show activity** expands the current session log. Ctrl+F focuses search.

## Size and dependency limits

Sizes count each distribution's recorded files, including recorded scripts and
metadata, instead of scanning the shared `site-packages` directory. Unknown
inventories show **Unknown**; missing/inaccessible files show a partial size
marked `*`. Editable installations show `†` and exclude external source trees.
Recorded sizes are not guaranteed reclaimed space: shared files, generated
files, filesystem allocation and editable sources can differ.

Dependency warnings use the selected interpreter's environment markers.
Extras are conservative warnings because installed metadata does not preserve
which extras were requested. The app cannot prove a package is unused by other
projects. Pip/setuptools/wheel and this running app's dependencies are protected.
Duplicate package metadata, packages managed by another installer, and packages
inherited from outside a virtual environment are blocked. Build-source lists
without installed file records are not counted as installed sizes.
In Conda environments, only explicitly pip-managed packages are removable.

## Recovery

Before any removal, the app rechecks the inventory and saves a timestamped folder
containing `requirements.txt` and `inventory.json`. If exporting or journaling
fails before a removal starts, that removal is blocked. On Windows, recovery
data normally lives under `%LOCALAPPDATA%\LocalTools\PythonPackageUninstaller`;
the exact path is shown in **Recovery & history**. History is recorded in
`history.jsonl` and no data is uploaded.

To reinstall from a snapshot, use the same interpreter:

```powershell
& 'C:\path\to\python.exe' -m pip install -r 'C:\path\to\snapshot\requirements.txt'
```

This is a reinstall aid, not transactional undo. Reinstallation may need network
access; removed versions, private indexes and original editable/local sources
may be unavailable. The app does not automatically install or restore anything.
Avoid modifying the same environment from another process during removal.

## Verification

```powershell
python -m unittest discover -s tests -v
```

Tests cover recorded sizes, target markers, dependency impact, protection,
selection preservation, busy-state locks, safe text rendering, discovery failure,
cancellation, recovery failures and removal verification. Most removal tests mock
pip. An integration test bootstraps pip locally in a disposable, isolated virtual
environment and removes two synthetic fixture packages. It never removes packages
from your working Python environment or downloads dependencies.

For a read-only live discovery check and rendered screenshots:

```powershell
python tests/verify_runtime.py verification
```

Verified on 2026-10-09 with Python 3.14.2, PyQt6 6.10.2 and packaging 26.0:
36 tests passed, including real removal of disposable fixture packages and
pagination/selection checks. Live read-only discovery found 311 packages. The
white/obsidian interface shows 15 complete rows at 1240x820 and 10 at 960x680,
with numbered pages and no vertical scrolling in Auto rows mode. The main window,
compact layout, second page and removal review were rendered and inspected. Existing installed packages were
not removed. Screenshots are generated under `verification/` (git-ignored).
