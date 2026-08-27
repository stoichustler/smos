#!/usr/bin/env python3
"""Compute the reproducible source closure of the compact SMOS targets."""

import argparse
import dataclasses
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
from collections import defaultdict
from typing import Iterable


@dataclasses.dataclass(frozen=True, order=True)
class Entry:
    path: str
    kind: str
    size: int
    architectures: tuple[str, ...] = ()
    protected: bool = False


def _is_within(path: pathlib.Path, directory: pathlib.Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def normalize_input(
    raw: str,
    base: pathlib.Path,
    root: pathlib.Path,
    external_roots: tuple[pathlib.Path, ...],
    excluded_prefixes: tuple[str, ...] = (".git", "out", "prebuilt", ".cipd", "beau"),
) -> pathlib.Path | None:
    """Return a lexical repository-relative path without following symlinks."""
    source_root = root.resolve()
    path = pathlib.Path(raw)
    if not path.is_absolute():
        path = base / path
    path = pathlib.Path(os.path.abspath(os.path.normpath(path)))
    if _is_within(path, source_root):
        relative = path.relative_to(source_root)
        if relative.parts and relative.parts[0] in excluded_prefixes:
            return None
        return relative
    for external in external_roots:
        if _is_within(path, external.resolve()):
            return None
    if pathlib.Path(raw).is_absolute():
        raise ValueError(f"unapproved external input: {raw}")
    raise ValueError(f"input escapes source root: {raw}")


def _entry_for(root: pathlib.Path, relative: pathlib.Path, architectures: set[str], protected: bool) -> Entry:
    path = root / relative
    info = path.lstat()
    kind = "symlink" if path.is_symlink() else "file"
    return Entry(
        path=relative.as_posix(),
        kind=kind,
        size=info.st_size,
        architectures=tuple(sorted(architectures)),
        protected=protected,
    )


def _merge_entry(entries: dict[str, Entry], new: Entry) -> None:
    old = entries.get(new.path)
    if old is None:
        entries[new.path] = new
        return
    entries[new.path] = dataclasses.replace(
        old,
        architectures=tuple(sorted(set(old.architectures) | set(new.architectures))),
        protected=old.protected or new.protected,
    )


def _add_path(
    root: pathlib.Path,
    relative: pathlib.Path,
    architectures: set[str],
    entries: dict[str, Entry],
    external_roots: tuple[pathlib.Path, ...],
    protected: bool = False,
) -> None:
    """Add a path, retaining each in-tree symlink and its final target."""
    if relative == pathlib.Path("."):
        return
    cursor = root
    parts = relative.parts
    for index, part in enumerate(parts):
        cursor = cursor / part
        try:
            cursor.lstat()
        except FileNotFoundError as error:
            raise FileNotFoundError(f"missing inventory input: {relative}") from error
        if cursor.is_symlink():
            link_relative = pathlib.Path(*parts[: index + 1])
            _merge_entry(entries, _entry_for(root, link_relative, architectures, protected))
            target = pathlib.Path(os.readlink(cursor))
            if not target.is_absolute():
                target = cursor.parent / target
            target = pathlib.Path(os.path.abspath(os.path.normpath(target)))
            suffix = pathlib.Path(*parts[index + 1 :])
            final = target / suffix
            normalized = normalize_input(str(final), root, root, external_roots)
            if normalized is not None:
                _add_path(root, normalized, architectures, entries, external_roots, protected)
            return
    if cursor.is_dir():
        return
    _merge_entry(entries, _entry_for(root, relative, architectures, protected))


def _add_parent_build_files(
    root: pathlib.Path,
    entries: dict[str, Entry],
    external_roots: tuple[pathlib.Path, ...],
) -> None:
    pending = list(entries.values())
    for entry in pending:
        parent = pathlib.Path(entry.path).parent
        architectures = set(entry.architectures)
        while parent != pathlib.Path("."):
            build_file = parent / "BUILD.gn"
            if (root / build_file).is_file() or (root / build_file).is_symlink():
                _add_path(root, build_file, architectures, entries, external_roots)
            parent = parent.parent
        if (root / "BUILD.gn").is_file():
            _add_path(root, pathlib.Path("BUILD.gn"), architectures, entries, external_roots)


def collect_records(
    root: pathlib.Path,
    out_dirs: dict[str, pathlib.Path],
    records: dict[str, Iterable[str]],
    external_roots: tuple[pathlib.Path, ...] = (),
    excluded_prefixes: tuple[str, ...] = (".git", "out", "prebuilt", ".cipd", "beau"),
) -> list[Entry]:
    source_root = root.resolve()
    entries: dict[str, Entry] = {}
    for arch in sorted(records):
        base = out_dirs[arch].resolve()
        for raw in records[arch]:
            raw = raw.strip()
            if not raw:
                continue
            relative = normalize_input(
                raw, base, source_root, external_roots, excluded_prefixes
            )
            if relative is not None:
                candidate = source_root / relative
                if candidate.is_dir() and not candidate.is_symlink():
                    # Compiler commands commonly name only an include
                    # directory.  A previous build may not have a complete
                    # .ninja_deps record for every header in that directory,
                    # so retain the in-tree header tree rather than relying
                    # on stale outputs.  This makes a staged fresh checkout
                    # equivalent to the source used to derive the inventory.
                    for directory, names, files in os.walk(candidate):
                        names[:] = sorted(names)
                        for name in sorted(files):
                            _add_path(
                                source_root,
                                (pathlib.Path(directory) / name).relative_to(source_root),
                                {arch},
                                entries,
                                external_roots,
                            )
                else:
                    _add_path(source_root, relative, {arch}, entries, external_roots)
    _add_parent_build_files(source_root, entries, external_roots)
    return sorted(entries.values())


def _protected_paths(root: pathlib.Path, policy: dict) -> Iterable[pathlib.Path]:
    for value in policy.get("protected_files", []):
        path = pathlib.Path(value)
        if (root / path).is_file() or (root / path).is_symlink():
            yield path
    for value in policy.get("protected_trees", []):
        tree = root / value
        if not tree.is_dir():
            continue
        for directory, names, files in os.walk(tree):
            names[:] = sorted(name for name in names if name not in {".git", "__pycache__"})
            for name in sorted(files):
                if name.endswith((".pyc", ".pyo")):
                    continue
                yield (pathlib.Path(directory) / name).relative_to(root)


def add_protected(
    root: pathlib.Path,
    entries: list[Entry],
    policy: dict | None = None,
    external_roots: tuple[pathlib.Path, ...] = (),
) -> None:
    if policy is None:
        policy = {
            "protected_files": [".gn", ".gitignore", "LICENSE", "PATENTS", "README.md"],
            "protected_trees": ["docs/plans", "tools/smos-boot"],
        }
    merged = {entry.path: entry for entry in entries}
    for relative in _protected_paths(root, policy):
        _add_path(root, relative, set(), merged, external_roots, protected=True)
    _add_parent_build_files(root, merged, external_roots)
    entries[:] = sorted(merged.values())


def _manifest(root: pathlib.Path, entries: list[Entry], targets: dict[str, list[str]], policy: dict) -> dict:
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
    for entry in entries:
        top = entry.path.split("/", 1)[0]
        grouped[top]["files"] += 1
        grouped[top]["bytes"] += entry.size
    host_prefixes = tuple(policy.get("host_build_only_prefixes", []))
    host_only = [entry.path for entry in entries if entry.path.startswith(host_prefixes)]
    return {
        "version": policy.get("version", 1),
        "source_root": ".",
        "targets": {arch: list(targets[arch]) for arch in sorted(targets)},
        "external_links": list(policy.get("external_links", ["prebuilt"])),
        "summary": {
            "files": len(entries),
            "bytes": sum(entry.size for entry in entries),
            "by_top_level": {name: grouped[name] for name in sorted(grouped)},
            "host_build_only_files": len(host_only),
            "host_build_only_bytes": sum((root / path).lstat().st_size for path in host_only),
        },
        "host_build_only_paths": host_only,
        "paths": [dataclasses.asdict(entry) for entry in sorted(entries)],
    }


def write_json(
    output: pathlib.Path,
    root: pathlib.Path,
    entries: list[Entry],
    targets: dict[str, list[str]],
    policy: dict | None = None,
) -> None:
    if policy is None:
        policy = {"version": 1}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(_manifest(root, entries, targets, policy), indent=2, sort_keys=True) + "\n")


def write_nul(output: pathlib.Path, entries: list[Entry]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"".join(entry.path.encode() + b"\0" for entry in sorted(entries)))


def write_report(output: pathlib.Path, manifest: dict) -> None:
    summary = manifest["summary"]
    lines = [
        "# SMOS retained components",
        "",
        "This inventory is generated from the transitive Ninja inputs for both compact images,",
        "their boot shims and verification targets, plus the GN regeneration depfiles.",
        "",
        f"- Retained files: {summary['files']}",
        f"- Retained source bytes: {summary['bytes']} ({summary['bytes'] / 1048576:.2f} MiB)",
        f"- Host-build-only optional-domain files: {summary['host_build_only_files']} "
        f"({summary['host_build_only_bytes'] / 1048576:.2f} MiB)",
        "- Runtime graphics, networking, WLAN, Bluetooth, audio, camera, update and recovery packages: none",
        "- Virtualization exception: virtio socket is retained without netstack or physical network drivers",
        "- External payload: `$SMOS_SDK_ROOT/prebuilt` (not linked or counted)",
        "",
        "## Size by top-level path",
        "",
        "| Path | Files | Bytes | MiB |",
        "|---|---:|---:|---:|",
    ]
    for name, values in manifest["summary"]["by_top_level"].items():
        lines.append(
            f"| `{name}` | {values['files']} | {values['bytes']} | "
            f"{values['bytes'] / 1048576:.2f} |"
        )
    lines += [
        "",
        "## Host-build-only compatibility inputs",
        "",
        "The paths recorded in `host_build_only_paths` are transitive inputs of host assembly",
        "tooling or common protocol libraries.",
        "They do not add packages, drivers, services, or files to the SMOS BootFS.",
        "Their exact file list is recorded in `out/smos-keep.json`.",
        "",
    ]
    output.write_text("\n".join(lines))


def _tool(root: pathlib.Path, name: str, external: pathlib.Path | None) -> pathlib.Path:
    candidates = []
    for base in (root, external):
        if base is None:
            continue
        if name == "ninja":
            candidates += [base / "prebuilt/third_party/ninja/linux-x64/ninja"]
        elif name == "gn":
            candidates += [base / "prebuilt/third_party/gn/linux-x64/gn"]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which(name)
    if found:
        return pathlib.Path(found)
    raise FileNotFoundError(f"missing tool: {name}")


def _depfile_inputs(path: pathlib.Path) -> list[str]:
    text = path.read_text(errors="replace").replace("\\\n", "")
    if ":" not in text:
        raise ValueError(f"malformed depfile: {path}")
    return shlex.split(text.split(":", 1)[1])


def dependency_inputs(lines: Iterable[str]) -> list[str]:
    return [line.strip() for line in lines if line.startswith("    ") and line.strip()]


_COMMAND_PATH = re.compile(r"(?<![./])\.\./\.\./(?!\.\./)[^\s\"';&|()<>]+")


def command_inputs(command: str) -> list[str]:
    found = []
    for match in _COMMAND_PATH.findall(command):
        value = match.rstrip(",]}:")
        if value not in found:
            found.append(value)
    return found


def runtime_dependency_inputs(
    root: pathlib.Path,
    out: pathlib.Path,
    label: str,
    gn: pathlib.Path,
) -> list[str]:
    """Return GN runtime inputs when the optional desc query is available."""
    try:
        described = subprocess.run(
            [str(gn), "desc", str(out), label, "runtime_deps", "--all"],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip().splitlines()
        suffix = f": {detail[0]}" if detail else ""
        print(f"warning: skipping optional runtime_deps for {label}{suffix}", file=sys.stderr)
        return []
    return described.stdout.splitlines()


def collect_generated(
    root: pathlib.Path,
    out_dirs: dict[str, pathlib.Path],
    targets: dict[str, list[str]],
    ninja: pathlib.Path,
    gn: pathlib.Path,
    external_roots: tuple[pathlib.Path, ...],
    excluded_prefixes: tuple[str, ...],
) -> list[Entry]:
    records: dict[str, set[str]] = {}
    for arch in sorted(targets):
        out = out_dirs[arch]
        command = [str(ninja), "-C", str(out), "-t", "inputs", *targets[arch]]
        result = subprocess.run(command, cwd=root, check=True, text=True, stdout=subprocess.PIPE)
        input_lines = result.stdout.splitlines()
        records[arch] = set(input_lines)
        records[arch].update(_depfile_inputs(out / "build.ninja.d"))

        # Query compiler-discovered headers only for outputs in the selected
        # graph.  An unfiltered `-t deps` also reports stale outputs left in
        # .ninja_deps after a dependency is removed.
        generated_outputs = sorted(
            {
                value
                for value in input_lines
                if value
                and not value.startswith(("../../", "/"))
                and (out / value).exists()
            }
        )
        for start in range(0, len(generated_outputs), 400):
            batch = generated_outputs[start : start + 400]
            deps = subprocess.Popen(
                [str(ninja), "-C", str(out), "-t", "deps", *batch],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
            )
            assert deps.stdout is not None
            for value in dependency_inputs(deps.stdout):
                records[arch].add(value)
            if deps.wait() != 0:
                raise subprocess.CalledProcessError(deps.returncode, deps.args)

        commands = subprocess.run(
            [str(ninja), "-C", str(out), "-t", "commands", *targets[arch]],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        for line in commands.stdout.splitlines():
            for value in command_inputs(line):
                try:
                    relative = normalize_input(
                        value,
                        out,
                        root,
                        external_roots,
                        excluded_prefixes,
                    )
                except ValueError:
                    # Some environment variables contain paths interpreted
                    # relative to a crate rather than the Ninja working dir.
                    continue
                if relative is not None:
                    candidate = root / relative
                    if candidate.is_file() or candidate.is_symlink() or candidate.is_dir():
                        records[arch].add(value)

        gn_labels = []
        for target in targets[arch]:
            if target.startswith(("release/", "platform/products/", "userspace/")) and ":" in target:
                gn_labels.append(f"//{target}")
        for label in gn_labels:
            records[arch].update(runtime_dependency_inputs(root, out, label, gn))
    return collect_records(
        root, out_dirs, records, external_roots, excluded_prefixes
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--nul-output", type=pathlib.Path)
    parser.add_argument("--report", type=pathlib.Path)
    parser.add_argument("--policy", type=pathlib.Path)
    parser.add_argument("--external-toolchain", type=pathlib.Path)
    args = parser.parse_args()

    script = pathlib.Path(__file__).resolve()
    root = (args.root or script.parents[2]).resolve()
    policy_path = args.policy or script.with_name("compact-policy.json")
    policy = json.loads(policy_path.read_text())
    external_value = args.external_toolchain or (
        pathlib.Path(os.environ["SMOS_TOOLCHAIN_ROOT"])
        if "SMOS_TOOLCHAIN_ROOT" in os.environ
        else None
    )
    external = None
    if external_value is not None:
        external = external_value
        if not external.is_absolute():
            external = root / external
        external = external.resolve()
    external_roots = (external,) if external is not None else ()
    targets = {arch: list(values) for arch, values in policy["architectures"].items()}
    out_dirs = {arch: root / "out" / f"smos-boot-{arch}" for arch in targets}
    entries = collect_generated(
        root,
        out_dirs,
        targets,
        _tool(root, "ninja", external),
        _tool(root, "gn", external),
        external_roots,
        tuple(policy["excluded_prefixes"]),
    )
    add_protected(root, entries, policy, external_roots)
    write_json(args.output, root, entries, targets, policy)
    if args.nul_output:
        write_nul(args.nul_output, entries)
    manifest = json.loads(args.output.read_text())
    if args.report:
        write_report(args.report, manifest)
    print(
        f"SMOS inventory: {manifest['summary']['files']} files, "
        f"{manifest['summary']['bytes']} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
