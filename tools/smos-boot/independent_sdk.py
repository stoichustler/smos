#!/usr/bin/env python3

"""Create and validate manifests for a self-contained SMOS SDK."""

import argparse
import ast
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import tempfile
from typing import Iterable


MANIFEST_NAME = "sdk-manifest.json"
_DIRFD_RE = re.compile(r"(?:AT_FDCWD|-?\d+)<([^>]+)>")
_QUOTED_RE = re.compile(r'"(?:\\.|[^"\\])*"')


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained_link_target(root: pathlib.Path, path: pathlib.Path) -> str:
    target = os.readlink(path)
    if pathlib.Path(target).is_absolute():
        raise ValueError(f"published SDK contains absolute symlink: {path}")
    try:
        path.resolve(strict=True).relative_to(root)
    except (FileNotFoundError, ValueError) as error:
        raise ValueError(f"published SDK contains escaping symlink: {path}") from error
    return target


def _sdk_entries(root: pathlib.Path) -> list[tuple[str, pathlib.Path, str]]:
    """Return contained files and internal links in manifest-path order."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"SDK root is not a directory: {root}")

    entries: list[tuple[str, pathlib.Path, str]] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        directory_path = pathlib.Path(directory)
        retained_dirs = []
        for name in sorted(dirnames):
            path = directory_path / name
            if path.is_symlink():
                _contained_link_target(root, path)
                entries.append((path.relative_to(root).as_posix(), path, "symlink"))
            else:
                retained_dirs.append(name)
        dirnames[:] = retained_dirs

        dirnames.sort()
        for name in sorted(filenames):
            path = directory_path / name
            relative = path.relative_to(root).as_posix()
            if relative == MANIFEST_NAME:
                continue
            if path.is_symlink():
                _contained_link_target(root, path)
                entries.append((relative, path, "symlink"))
                continue
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode):
                raise ValueError(f"published SDK contains non-regular file: {path}")
            entries.append((relative, path, "file"))

    entries.sort(key=lambda item: item[0])
    return entries


def create_manifest(
    root: pathlib.Path, architectures: tuple[str, ...]
) -> dict:
    root = pathlib.Path(root)
    entries = []
    total_bytes = 0
    resolved_root = pathlib.Path(root).resolve(strict=True)
    for relative, path, kind in _sdk_entries(resolved_root):
        if kind == "symlink":
            size = path.lstat().st_size
            entries.append({
                "path": relative,
                "kind": kind,
                "size": size,
                "target": _contained_link_target(resolved_root, path),
            })
        else:
            file_stat = path.stat()
            size = file_stat.st_size
            entries.append({
                "path": relative,
                "kind": kind,
                "size": size,
                "sha256": sha256_file(path),
                "executable": bool(file_stat.st_mode & 0o111),
            })
        total_bytes += size

    return {
        "version": 1,
        "architectures": list(architectures),
        "files": entries,
        "total_bytes": total_bytes,
    }


def write_manifest(
    root: pathlib.Path, architectures: tuple[str, ...]
) -> pathlib.Path:
    root = pathlib.Path(root)
    manifest_path = root / MANIFEST_NAME
    manifest = create_manifest(root, architectures)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path


def _safe_manifest_path(root: pathlib.Path, value: object) -> pathlib.Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"unsafe manifest path: {value!r}")
    relative = pathlib.PurePosixPath(value)
    if relative.is_absolute() or relative == pathlib.PurePosixPath("."):
        raise ValueError(f"unsafe manifest path: {value!r}")
    if any(part in ("", ".", "..") for part in relative.parts):
        raise ValueError(f"unsafe manifest path: {value!r}")

    candidate = root.joinpath(*relative.parts)
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError as error:
        raise ValueError(f"manifest path is not contained: {value!r}") from error
    return candidate


def validate_sdk(
    root: pathlib.Path, required_architectures: tuple[str, ...] = ()
) -> dict:
    root = pathlib.Path(root).resolve(strict=True)
    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_symlink():
        raise ValueError(f"published SDK contains symlink: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text())
    except FileNotFoundError as error:
        raise ValueError(f"SDK manifest is missing: {manifest_path}") from error

    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("unsupported SDK manifest version")
    architectures = manifest.get("architectures")
    if not isinstance(architectures, list) or not all(
        isinstance(architecture, str) for architecture in architectures
    ):
        raise ValueError("invalid SDK architectures")
    missing = [
        architecture
        for architecture in required_architectures
        if architecture not in architectures
    ]
    if missing:
        raise ValueError(f"SDK is missing required architectures: {', '.join(missing)}")

    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("invalid SDK file list")

    actual_files = _sdk_entries(root)
    actual_paths = [(relative, kind) for relative, _, kind in actual_files]
    manifest_paths = []
    total_bytes = 0
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("invalid SDK file entry")
        path = _safe_manifest_path(root, entry.get("path"))
        relative = path.relative_to(root).as_posix()
        manifest_paths.append(relative)

        kind = entry.get("kind", "file")
        if kind == "symlink":
            if not path.is_symlink():
                raise ValueError(f"manifest symlink is missing: {relative}")
            target = _contained_link_target(root, path)
            if entry.get("target") != target:
                raise ValueError(f"symlink target mismatch for {relative}")
            size = path.lstat().st_size
        elif kind == "file":
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"manifest file is missing: {relative}")
            file_stat = path.stat()
            size = file_stat.st_size
            if entry.get("sha256") != sha256_file(path):
                raise ValueError(f"hash mismatch for {relative}")
            if entry.get("executable") is not bool(file_stat.st_mode & 0o111):
                raise ValueError(f"executable mode mismatch for {relative}")
        else:
            raise ValueError(f"unknown SDK entry kind: {kind!r}")
        if entry.get("size") != size:
            raise ValueError(f"size mismatch for {relative}")
        total_bytes += size

    if manifest_paths != sorted(manifest_paths) or len(set(manifest_paths)) != len(
        manifest_paths
    ):
        raise ValueError("SDK manifest paths must be sorted and unique")
    manifest_path_kinds = [
        (entry["path"], entry.get("kind", "file")) for entry in files
    ]
    if manifest_path_kinds != actual_paths:
        raise ValueError("SDK manifest file list does not match published files")
    if manifest.get("total_bytes") != total_bytes:
        raise ValueError("SDK manifest total_bytes mismatch")
    return manifest


def _within(path: pathlib.Path, directory: pathlib.Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _lexical(path: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.path.abspath(os.path.normpath(path)))


def trace_paths(
    lines: Iterable[str],
    source_root: pathlib.Path,
    prebuilt_root: pathlib.Path,
) -> set[pathlib.Path]:
    """Return prebuilt-relative regular files observed in strace file calls."""
    source = pathlib.Path(source_root).resolve()
    prebuilt = pathlib.Path(prebuilt_root).resolve(strict=True)
    mounted = _lexical(source / "prebuilt")
    found: set[pathlib.Path] = set()

    for line in lines:
        cwd_match = _DIRFD_RE.search(line)
        cwd = pathlib.Path(cwd_match.group(1)) if cwd_match else source
        for encoded in _QUOTED_RE.findall(line):
            try:
                raw = ast.literal_eval(encoded)
            except (SyntaxError, ValueError):
                continue
            if not isinstance(raw, str) or not raw or "\0" in raw:
                continue
            value = pathlib.Path(raw)
            if not value.is_absolute() and "/" not in raw and cwd_match is None:
                continue
            candidate = _lexical(value if value.is_absolute() else cwd / value)

            relative = None
            for prefix in (mounted, _lexical(prebuilt)):
                if _within(candidate, prefix):
                    relative = candidate.relative_to(prefix)
                    break
            if relative is None:
                canonical = candidate.resolve(strict=False)
                if _within(canonical, prebuilt):
                    relative = canonical.relative_to(prebuilt)
            if relative is None or relative == pathlib.Path("."):
                continue

            accessed = prebuilt / relative
            try:
                resolved = accessed.resolve(strict=True)
            except FileNotFoundError:
                continue
            if _within(resolved, prebuilt) and resolved.is_file():
                found.add(relative)
    return found


def _safe_relative(path: pathlib.Path) -> pathlib.Path:
    value = pathlib.PurePosixPath(path.as_posix())
    if value.is_absolute() or value == pathlib.PurePosixPath(".") or any(
        part in ("", ".", "..") for part in value.parts
    ):
        raise ValueError(f"unsafe SDK input path: {path}")
    return pathlib.Path(*value.parts)


def extract_sdk(
    source_prebuilt: pathlib.Path,
    destination: pathlib.Path,
    relative_paths: Iterable[pathlib.Path],
    architectures: tuple[str, ...],
    replace: bool = False,
) -> dict:
    """Materialize a traced prebuilt closure and atomically publish it."""
    source = pathlib.Path(source_prebuilt).resolve(strict=True)
    if not source.is_dir():
        raise ValueError(f"prebuilt source is not a directory: {source}")
    target = pathlib.Path(destination).absolute()
    if target.exists() and not target.is_dir():
        raise ValueError(f"SDK destination is not a directory: {target}")
    if target.exists() and not replace:
        raise FileExistsError(f"SDK destination already exists: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = pathlib.Path(
        tempfile.mkdtemp(prefix=f".{target.name}.tmp.", dir=target.parent)
    )
    backup: pathlib.Path | None = None
    try:
        for raw in sorted(set(pathlib.Path(path) for path in relative_paths)):
            relative = _safe_relative(raw)
            original = source / relative
            try:
                resolved = original.resolve(strict=True)
            except FileNotFoundError as error:
                raise FileNotFoundError(f"traced SDK input is absent: {relative}") from error
            if not _within(resolved, source):
                raise ValueError(f"SDK input escapes prebuilt root: {relative}")
            if not resolved.is_file():
                continue
            published = staging / "prebuilt" / relative
            published.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolved, published)

        write_manifest(staging, architectures)
        validate_sdk(staging, architectures)

        if target.exists():
            backup = target.parent / f".{target.name}.old.{os.getpid()}"
            if backup.exists():
                raise FileExistsError(f"SDK backup path already exists: {backup}")
            os.replace(target, backup)
        try:
            os.replace(staging, target)
        except BaseException:
            if backup is not None:
                os.replace(backup, target)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
            backup = None
        return validate_sdk(target, architectures)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--sdk", type=pathlib.Path, required=True)
    validate.add_argument("--architecture", action="append", default=[])

    extract = subparsers.add_parser("extract")
    extract.add_argument("--source-root", type=pathlib.Path, required=True)
    extract.add_argument("--source-prebuilt", type=pathlib.Path, required=True)
    extract.add_argument("--destination", type=pathlib.Path, required=True)
    extract.add_argument("--trace", type=pathlib.Path, required=True)
    extract.add_argument("--architecture", action="append", default=[])
    extract.add_argument("--replace", action="store_true")

    args = parser.parse_args()
    architectures = tuple(args.architecture)
    if args.command == "validate":
        manifest = validate_sdk(args.sdk, architectures)
        print(
            f"SMOS_SDK_FILES={len(manifest['files'])} "
            f"SMOS_SDK_BYTES={manifest['total_bytes']}"
        )
        return 0

    lines = args.trace.read_text(errors="replace").splitlines()
    paths = trace_paths(lines, args.source_root, args.source_prebuilt)
    if not paths:
        raise ValueError("trace contains no prebuilt file accesses")
    manifest = extract_sdk(
        args.source_prebuilt,
        args.destination,
        paths,
        architectures,
        args.replace,
    )
    print(
        f"SMOS_SDK_FILES={len(manifest['files'])} "
        f"SMOS_SDK_BYTES={manifest['total_bytes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
