"""Package inspection and recovery helpers. The scan command needs only stdlib."""
from __future__ import annotations

import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import re
import site
import subprocess
import sys
from datetime import datetime, timezone


def canonical_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def format_size(size):
    if size is None:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024


def package_size(dist):
    """Count only files recorded for this distribution, never its shared location.

    Recorded bytes are not a promise of reclaimed space: shared files, editable
    source trees and unrecorded generated files can differ from pip's removal.
    """
    # SOURCES.txt describes build inputs, not installed files. Legacy editable
    # distributions must not have their source trees counted as removable bytes.
    if dist.read_text("RECORD") is None and dist.read_text("installed-files.txt") is None:
        return None, "unknown", 0
    files = dist.files
    if files is None:
        return None, "unknown", 0
    total, missing, seen = 0, 0, set()
    for entry in files:
        path = Path(dist.locate_file(entry))
        try:
            stat = path.stat(follow_symlinks=False)
            identity = (stat.st_dev, stat.st_ino) if stat.st_ino else str(path.absolute())
            if identity in seen:
                continue
            seen.add(identity)
            if path.is_file() or path.is_symlink():
                total += stat.st_size
        except OSError:
            missing += 1
    return total, "partial" if missing else "recorded", missing


def marker_environment():
    version = sys.implementation.version
    implementation_version = f"{version.major}.{version.minor}.{version.micro}"
    if version.releaselevel != "final":
        implementation_version += version.releaselevel[0] + str(version.serial)
    return {
        "implementation_name": sys.implementation.name,
        "implementation_version": implementation_version,
        "os_name": os.name,
        "platform_machine": platform.machine(),
        "platform_release": platform.release(),
        "platform_system": platform.system(),
        "platform_version": platform.version(),
        "python_full_version": platform.python_version(),
        "platform_python_implementation": platform.python_implementation(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "sys_platform": sys.platform,
        "extra": "",
    }


def scan_environment():
    packages, warnings = [], []
    for dist in metadata.distributions():
        try:
            name = dist.metadata.get("Name")
            if not name:
                warnings.append("Ignored a distribution with no package name.")
                continue
            size, size_kind, missing = package_size(dist)
            direct_url = {}
            try:
                direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
            except (ValueError, OSError):
                warnings.append(f"Could not read source metadata for {name}.")
            packages.append({
                "name": name, "key": canonical_name(name), "version": dist.version,
                "location": str(Path(dist.locate_file("")).absolute()),
                "description": dist.metadata.get("Summary") or "No description supplied by the package.",
                "requires": dist.requires or [], "size": size, "size_kind": size_kind,
                "missing_files": missing,
                "installer": (dist.read_text("INSTALLER") or "unknown").strip(),
                "editable": bool(direct_url.get("dir_info", {}).get("editable")),
            })
        except Exception as exc:
            warnings.append(f"Could not inspect a distribution: {exc}")
    packages.sort(key=lambda package: package["key"])
    return {
        "environment": {
            "executable": sys.executable, "prefix": sys.prefix,
            "version": platform.python_version(), "is_venv": sys.prefix != sys.base_prefix,
            "is_conda": (Path(sys.prefix) / "conda-meta").is_dir(),
            "user_site": site.getusersitepackages(), "markers": marker_environment(),
            "has_pip": any(package["key"] == "pip" for package in packages),
        },
        "packages": packages, "warnings": warnings,
    }


def python_command(executable, *arguments):
    return [str(executable), *map(str, arguments)]


def process_options():
    env = os.environ.copy()
    env.update(PYTHONIOENCODING="utf-8", PIP_NO_INPUT="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    return dict(
        encoding="utf-8", errors="replace", env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def run_python(executable, arguments, timeout=120):
    return subprocess.run(
        python_command(executable, *arguments), capture_output=True,
        timeout=timeout, **process_options(),
    )


def read_environment(executable):
    result = run_python(executable, [Path(__file__).resolve(), "--scan"])
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Python environment inspection failed.")
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError("The interpreter did not return a valid package inventory.") from exc


def dependency_graph(packages, environment):
    """Required dependencies and conservative optional-dependency warnings."""
    from packaging.requirements import Requirement, InvalidRequirement
    graph = {package["key"]: set() for package in packages}
    optional = {package["key"]: set() for package in packages}
    warnings = []
    for package in packages:
        for raw in package["requires"]:
            try:
                requirement = Requirement(raw)
                key = canonical_name(requirement.name)
                if requirement.marker and "extra" in str(requirement.marker):
                    # Installed metadata does not retain which extras were requested.
                    optional[package["key"]].add(key)
                elif not requirement.marker or requirement.marker.evaluate(environment=environment["markers"]):
                    graph[package["key"]].add(key)
            except (InvalidRequirement, ValueError, KeyError) as exc:
                warnings.append(f"Cannot evaluate {package['name']} dependency {raw!r}: {exc}")
    return graph, optional, warnings


def removal_warnings(selected, graph, optional):
    required, possible = {}, {}
    for dependent, dependencies in graph.items():
        if dependent not in selected:
            for dependency in dependencies & selected:
                required.setdefault(dependency, []).append(dependent)
    for dependent, dependencies in optional.items():
        if dependent not in selected:
            for dependency in dependencies & selected:
                possible.setdefault(dependency, []).append(dependent)
    return required, possible


def removal_order(selected, graph):
    """Remove dependents before dependencies; break dependency cycles stably."""
    remaining, ordered = set(selected), []
    while remaining:
        depended_on = set().union(*(graph.get(key, set()) & remaining for key in remaining))
        ready = sorted(remaining - depended_on) or [min(remaining)]
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered


def protection_reason(package, executable, runtime_executable, environment=None):
    if package["key"] in {"pip", "setuptools", "wheel"}:
        return "Protected Python packaging tool"
    if os.path.normcase(os.path.realpath(executable)) == os.path.normcase(os.path.realpath(runtime_executable)):
        if package["key"] in {"pyqt6", "pyqt6-qt6", "pyqt6-sip", "packaging"}:
            return "Required by this running application"
    if package.get("installer", "").lower() not in {"pip", "unknown", ""}:
        return f"Managed by {package['installer']}; use its own package manager"
    if environment:
        if environment.get("is_conda") and package["installer"] != "pip":
            return "Conda environment: removal is limited to explicitly pip-managed packages"
        if environment.get("is_venv") and not package.get("editable"):
            location = Path(package["location"]).resolve()
            prefix = Path(environment["prefix"]).resolve()
            if not location.is_relative_to(prefix):
                return "Inherited from another environment; switch to its interpreter to manage it"
    return ""


def validate_plan(original, current, selected):
    old = {package["key"]: package for package in original}
    new = {package["key"]: package for package in current}
    for key in selected:
        if key not in old or key not in new:
            raise RuntimeError(f"{key} is no longer installed. Refresh and review your selection.")
        if (old[key]["version"], old[key]["location"]) != (new[key]["version"], new[key]["location"]):
            raise RuntimeError(f"{key} changed since discovery. Refresh and review your selection.")
    # A newly installed dependent must be reviewed before any removal.
    def fingerprint(package):
        return (package["key"], package["version"], package["location"], tuple(package["requires"]), package.get("installer", "unknown"), package.get("editable", False))
    old_inventory = sorted(map(fingerprint, original))
    new_inventory = sorted(map(fingerprint, current))
    if old_inventory != new_inventory:
        raise RuntimeError("The environment changed since discovery. Refresh before uninstalling.")


def create_snapshot(executable, inventory, selected, directory):
    """Persist pip's own freeze output before allowing a destructive operation."""
    result = run_python(executable, ["-m", "pip", "freeze", "--all"], timeout=60)
    if result.returncode:
        raise RuntimeError(f"Recovery export failed; nothing was removed. {result.stderr.strip()}")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = directory / stamp
    folder.mkdir()
    (folder / "requirements.txt").write_text(result.stdout, encoding="utf-8")
    (folder / "inventory.json").write_text(json.dumps({
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": inventory["environment"], "packages": inventory["packages"],
        "selected": sorted(selected),
    }, indent=2), encoding="utf-8")
    return folder


def append_history(directory, event):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    event = {"time": datetime.now(timezone.utc).isoformat(), **event}
    with (directory / "history.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def perform_uninstall(executable, package_name):
    """Pip exit status alone does not prove a distribution was removed."""
    from packaging.utils import canonicalize_name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", package_name):
        return False, "Invalid package name; removal was blocked."
    try:
        result = run_python(executable, ["-m", "pip", "uninstall", "-y", package_name], timeout=300)
    except subprocess.TimeoutExpired:
        return False, "Pip exceeded five minutes. Files may have changed; refresh and inspect the environment."
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode:
        return False, output or f"Pip exited with code {result.returncode}."
    probe = run_python(executable, [Path(__file__).resolve(), "--installed", canonicalize_name(package_name)], timeout=30)
    if probe.returncode or probe.stdout.strip() != "false":
        return False, output + "\nRemoval could not be verified; the package may still be installed."
    return True, output


if __name__ == "__main__":
    if sys.argv[1:] == ["--scan"]:
        print(json.dumps(scan_environment()))
    elif len(sys.argv) == 3 and sys.argv[1] == "--installed":
        print(json.dumps(any(canonical_name(dist.metadata.get("Name", "")) == sys.argv[2] for dist in metadata.distributions())))
    else:
        raise SystemExit("Usage: package_backend.py --scan | --installed NAME")
