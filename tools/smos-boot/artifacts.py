#!/usr/bin/env python3
"""Resolve the compact image artifacts from generated GN metadata."""

import argparse
import dataclasses
import json
import os
import pathlib
import shlex
import subprocess
import tempfile


ASSEMBLY_TARGETS = {
    "bringup": (
        "//release/images/bringup:bringup.copy_zbi",
        "//release/images/bringup:bringup.product_assembler",
    ),
    "fuchsia": (
        "//release/images/fuchsia:fuchsia.copy_zbi",
        "//release/images/fuchsia:fuchsia.product_assembler",
    ),
}


@dataclasses.dataclass(frozen=True)
class Artifacts:
    qemu_kernel: pathlib.Path
    zbi: pathlib.Path


def _described_outputs(
    root: pathlib.Path, out_dir: pathlib.Path, gn: pathlib.Path, target: str
) -> list[pathlib.Path]:
    result = subprocess.run(
        [str(gn), "desc", str(out_dir), target, "outputs"],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    paths = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("//"):
            paths.append((root / line[2:]).resolve())
    return paths


def _inside(path: pathlib.Path, directory: pathlib.Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _one_output(
    outputs: list[pathlib.Path], suffix: str, out_dir: pathlib.Path, description: str
) -> pathlib.Path:
    matches = [path for path in outputs if path.name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {description}, found {len(matches)}")
    path = matches[0]
    if not _inside(path, out_dir):
        raise ValueError(f"{description} is outside output directory: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"missing {description}: {path}")
    return path


def resolve_artifacts(
    source_root: pathlib.Path,
    out_dir: pathlib.Path,
    gn: pathlib.Path,
    assembly: str = "fuchsia",
) -> Artifacts:
    root = source_root.resolve()
    output = out_dir.resolve()
    if not _inside(output, root):
        raise ValueError(f"output directory is outside source tree: {output}")

    try:
        copy_zbi_target, product_assembler_target = ASSEMBLY_TARGETS[assembly]
    except KeyError as error:
        raise ValueError(f"unknown assembly: {assembly}") from error

    zbi = _one_output(
        _described_outputs(root, output, gn, copy_zbi_target),
        ".zbi",
        output,
        "ZBI",
    )
    metadata = _one_output(
        _described_outputs(root, output, gn, product_assembler_target),
        "image_assembly.json",
        output,
        "image assembly metadata",
    )
    config = json.loads(metadata.read_text())
    qemu_kernel_value = config.get("qemu_kernel")
    if not isinstance(qemu_kernel_value, str) or not qemu_kernel_value:
        raise ValueError(f"missing qemu_kernel in {metadata}")
    qemu_kernel = (output / qemu_kernel_value).resolve()
    if not _inside(qemu_kernel, output):
        raise ValueError(f"QEMU kernel is outside output directory: {qemu_kernel}")
    if not qemu_kernel.is_file():
        raise FileNotFoundError(f"missing QEMU kernel: {qemu_kernel}")
    return Artifacts(qemu_kernel=qemu_kernel, zbi=zbi)


def _write_env(path: pathlib.Path, found: Artifacts) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(f"QEMU_KERNEL={shlex.quote(str(found.qemu_kernel))}\n")
            stream.write(f"ZBI={shlex.quote(str(found.zbi))}\n")
        os.replace(temporary, path)
    except BaseException:
        pathlib.Path(temporary).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=pathlib.Path)
    parser.add_argument("--out-dir", required=True, type=pathlib.Path)
    parser.add_argument("--gn", required=True, type=pathlib.Path)
    parser.add_argument("--assembly", choices=sorted(ASSEMBLY_TARGETS), default="fuchsia")
    parser.add_argument("--write", required=True, type=pathlib.Path)
    args = parser.parse_args()
    found = resolve_artifacts(args.source_root, args.out_dir, args.gn, args.assembly)
    _write_env(args.write, found)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
