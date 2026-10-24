"""Parse lockfiles into exact resolved dependency versions.

Unlike manifests, lockfiles record the concrete version the resolver chose, so
results here can be treated as exact pins rather than ranges. They still don't
prove what is installed in a given environment.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import PurePath

MAX_LOCKFILE_BYTES = 1024 * 1024  # lockfiles are bigger than manifests

_SEMVER = re.compile(r"^\d+\.\d+\.\d+([-+].+)?$")


class LockfileError(ValueError):
    """Raised when a lockfile is malformed, unsupported, or too large."""


@dataclass(frozen=True)
class LockedDependency:
    name: str
    version: str
    ecosystem: str  # "python", "javascript" or "rust"


def _sorted(deps: set[LockedDependency]) -> list[LockedDependency]:
    return sorted(deps, key=lambda d: (d.name, d.version))


def _normalize_python_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()  # PEP 503


def _load_toml(text: str, label: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise LockfileError(f"Invalid {label}: {exc}") from exc


def parse_poetry_lock(text: str) -> list[LockedDependency]:
    data = _load_toml(text, "poetry.lock")
    found: set[LockedDependency] = set()
    for pkg in data.get("package", []):
        name, version = pkg.get("name"), pkg.get("version")
        if isinstance(name, str) and isinstance(version, str) and version:
            found.add(LockedDependency(_normalize_python_name(name), version, "python"))
    return _sorted(found)


def parse_cargo_lock(text: str) -> list[LockedDependency]:
    data = _load_toml(text, "Cargo.lock")
    found: set[LockedDependency] = set()
    # The same crate can legitimately appear at several versions; keep them all
    # and let the caller decide how to warn about duplicates.
    for pkg in data.get("package", []):
        name, version = pkg.get("name"), pkg.get("version")
        if isinstance(name, str) and isinstance(version, str) and version:
            found.add(LockedDependency(name, version, "rust"))
    return _sorted(found)


def _npm_from_packages(packages: dict) -> set[LockedDependency]:
    """lockfileVersion 2/3: flat "packages" map keyed by install path."""
    found: set[LockedDependency] = set()
    marker = "node_modules/"
    for path, meta in packages.items():
        if not path or not isinstance(meta, dict) or meta.get("link"):
            continue  # root project entry or workspace symlink
        idx = path.rfind(marker)
        if idx == -1:
            continue  # workspace member such as "packages/app"
        name = meta.get("name") if isinstance(meta.get("name"), str) else path[idx + len(marker):]
        version = meta.get("version")
        if isinstance(version, str) and _SEMVER.match(version):
            found.add(LockedDependency(name, version, "javascript"))
    return found


def _npm_from_v1(dependencies: dict) -> set[LockedDependency]:
    """lockfileVersion 1: nested "dependencies" tree."""
    found: set[LockedDependency] = set()
    for name, meta in dependencies.items():
        if not isinstance(meta, dict):
            continue
        version = meta.get("version")
        if isinstance(version, str) and _SEMVER.match(version):
            found.add(LockedDependency(name, version, "javascript"))
        nested = meta.get("dependencies")
        if isinstance(nested, dict):
            found |= _npm_from_v1(nested)
    return found


def parse_package_lock(text: str) -> list[LockedDependency]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LockfileError(f"Invalid package-lock.json: {exc}") from exc
    if not isinstance(data, dict):
        raise LockfileError("package-lock.json must contain a JSON object.")
    if isinstance(data.get("packages"), dict):
        return _sorted(_npm_from_packages(data["packages"]))
    if isinstance(data.get("dependencies"), dict):
        return _sorted(_npm_from_v1(data["dependencies"]))
    raise LockfileError("package-lock.json has no 'packages' or 'dependencies' section.")


_PARSERS = {
    "poetry.lock": parse_poetry_lock,
    "cargo.lock": parse_cargo_lock,
    "package-lock.json": parse_package_lock,
}

SUPPORTED_LOCKFILES = ("poetry.lock", "Cargo.lock", "package-lock.json")


def parse_lockfile(filename: str, content: bytes | str) -> list[LockedDependency]:
    parser = _PARSERS.get(PurePath(filename).name.lower())
    if parser is None:
        raise LockfileError(
            f"Unsupported lockfile '{filename}'. Supported: {', '.join(SUPPORTED_LOCKFILES)}."
        )
    if isinstance(content, bytes):
        if len(content) > MAX_LOCKFILE_BYTES:
            raise LockfileError("Lockfile exceeds the 1 MiB limit.")
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LockfileError("Lockfile must be UTF-8 text.") from exc
    elif len(content.encode("utf-8")) > MAX_LOCKFILE_BYTES:
        raise LockfileError("Lockfile exceeds the 1 MiB limit.")
    return parser(content)