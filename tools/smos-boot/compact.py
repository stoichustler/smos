#!/usr/bin/env python3
"""Stage and measure a physically compact SMOS source tree."""

import argparse
import json
import os
import pathlib
import shutil


DEFAULT_MAX_BYTES = 524_288_000
MEASURE_EXCLUDED = {".git", "out", "prebuilt", ".cipd"}


def _within(path: pathlib.Path, directory: pathlib.Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _validate_relative(value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    if path.is_absolute() or ".." in path.parts or path == pathlib.Path("."):
        raise ValueError(f"unsafe manifest path: {value}")
    return path


def measure_tree(root: pathlib.Path) -> int:
    source = root.resolve()
    total = 0
    for directory, names, files in os.walk(source, followlinks=False):
        relative_dir = pathlib.Path(directory).relative_to(source)
        if relative_dir == pathlib.Path("."):
            names[:] = sorted(name for name in names if name not in MEASURE_EXCLUDED)
        else:
            names[:] = sorted(names)
        retained_names = []
        for name in names:
            path = pathlib.Path(directory) / name
            if path.is_symlink():
                total += path.lstat().st_size
            else:
                retained_names.append(name)
        names[:] = retained_names
        for name in sorted(files):
            total += (pathlib.Path(directory) / name).lstat().st_size
    return total


def enforce_size(size: int, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    if size >= max_bytes:
        raise ValueError(f"size gate failed: {size} bytes is not below {max_bytes}")


def _prepare_destination(destination: pathlib.Path, replace: bool) -> None:
    if destination.exists():
        if not destination.is_dir():
            raise ValueError(f"destination is not a directory: {destination}")
        if any(destination.iterdir()):
            if not replace:
                raise ValueError(f"refusing nonempty destination: {destination}")
            shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)


def _copy_entry(source: pathlib.Path, destination: pathlib.Path, item: dict) -> None:
    relative = _validate_relative(item["path"])
    original = source / relative
    staged = destination / relative
    try:
        original.lstat()
    except FileNotFoundError as error:
        raise FileNotFoundError(f"manifest input is absent: {relative}") from error
    staged.parent.mkdir(parents=True, exist_ok=True)
    kind = item.get("kind")
    if kind == "symlink":
        if not original.is_symlink():
            raise ValueError(f"manifest expected a symlink: {relative}")
        staged.symlink_to(os.readlink(original))
    elif kind == "file":
        if original.is_symlink() or not original.is_file():
            raise ValueError(f"manifest expected a regular file: {relative}")
        shutil.copy2(original, staged, follow_symlinks=False)
    else:
        raise ValueError(f"unknown manifest entry kind {kind!r}: {relative}")


def _copy_git(source: pathlib.Path, destination: pathlib.Path) -> None:
    git = source / ".git"
    if git.is_dir():
        shutil.copytree(git, destination / ".git", symlinks=True)
    elif git.is_file():
        shutil.copy2(git, destination / ".git", follow_symlinks=False)


def _external_links(
    destination: pathlib.Path, external: pathlib.Path, names: list[str]
) -> dict[str, str]:
    links = {}
    for name in names:
        relative = _validate_relative(name)
        if len(relative.parts) != 1:
            raise ValueError(f"external link must be top-level: {name}")
        target = external / relative
        if not target.is_dir():
            raise FileNotFoundError(f"external payload is absent: {target}")
        link = destination / relative
        link_target = os.path.relpath(target, link.parent)
        link.symlink_to(link_target)
        links[name] = link_target
    return links


def stage_tree(
    source: pathlib.Path,
    destination: pathlib.Path,
    manifest_path: pathlib.Path,
    external_toolchain: pathlib.Path,
    replace: bool = False,
) -> dict:
    source_root = source.resolve()
    destination_root = destination.resolve()
    external = external_toolchain.resolve()
    if _within(destination_root, source_root) or _within(source_root, destination_root):
        raise ValueError("source and destination overlap")
    if not source_root.is_dir():
        raise FileNotFoundError(f"source is absent: {source_root}")
    manifest = json.loads(manifest_path.read_text())
    paths = manifest.get("paths")
    if not isinstance(paths, list):
        raise ValueError("manifest paths must be a list")
    ordered = sorted(paths, key=lambda item: item["path"])
    if len({item["path"] for item in ordered}) != len(ordered):
        raise ValueError("manifest contains duplicate paths")

    _prepare_destination(destination_root, replace)
    try:
        for item in ordered:
            _copy_entry(source_root, destination_root, item)
        _copy_git(source_root, destination_root)
        links = _external_links(
            destination_root, external, list(manifest.get("external_links", []))
        )
        source_bytes = sum(int(item.get("size", 0)) for item in ordered)
        record = {
            "version": manifest.get("version", 1),
            "copied_paths": len(ordered),
            "source_bytes": source_bytes,
            "staged_bytes": measure_tree(destination_root),
            "max_bytes": DEFAULT_MAX_BYTES,
            "external_links": links,
            "size_excludes": sorted(MEASURE_EXCLUDED),
        }
        enforce_size(record["staged_bytes"], DEFAULT_MAX_BYTES)
        return record
    except BaseException:
        # A failed stage is never a valid deliverable.  Leave an existing
        # caller-owned destination untouched unless this call created/replaced it.
        if destination_root.exists():
            shutil.rmtree(destination_root)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measure", type=pathlib.Path)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--source", type=pathlib.Path)
    parser.add_argument("--destination", type=pathlib.Path)
    parser.add_argument("--external-toolchain", type=pathlib.Path)
    parser.add_argument("--replace-staging", action="store_true")
    args = parser.parse_args()

    if args.measure is not None:
        size = measure_tree(args.measure)
        enforce_size(size, args.max_bytes)
        print(f"SMOS_SIZE_BYTES={size}")
        return 0
    required = (args.manifest, args.source, args.destination, args.external_toolchain)
    if any(value is None for value in required):
        parser.error(
            "staging requires --manifest, --source, --destination, and --external-toolchain"
        )
    result = stage_tree(
        args.source,
        args.destination,
        args.manifest,
        args.external_toolchain,
        args.replace_staging,
    )
    print(f"SMOS_STAGE_BYTES={result['staged_bytes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
