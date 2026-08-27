#!/usr/bin/env python3
"""Reject generated build graphs that route tools through source prebuilt."""

import argparse
import os
import pathlib
import re
from collections.abc import Iterable


_RELATIVE_PREBUILT = re.compile(r"(?<![A-Za-z0-9_.-])(?:\.\./)+prebuilt/")


def forbidden_references(text: str, root: pathlib.Path) -> list[str]:
    markers = []
    absolute = f"{root.resolve().as_posix()}/prebuilt/"
    if absolute in text:
        markers.append(absolute)
    markers.extend(dict.fromkeys(_RELATIVE_PREBUILT.findall(text)))
    if "//prebuilt/" in text:
        markers.append("//prebuilt/")
    return markers


def check_graph(
    root: pathlib.Path, sdk: pathlib.Path, out_dirs: Iterable[pathlib.Path]
) -> None:
    root = root.resolve()
    sdk = sdk.resolve()
    sdk_prebuilt = sdk / "prebuilt"
    if not sdk_prebuilt.is_dir():
        raise ValueError(f"SDK prebuilt payload is absent: {sdk_prebuilt}")

    for out_dir in out_dirs:
        out_dir = out_dir.resolve()
        external_relative = pathlib.Path(
            os.path.relpath(sdk_prebuilt, out_dir)
        ).as_posix()
        external_markers = (f"{external_relative}/", f"{sdk_prebuilt.as_posix()}/")
        found_external = False
        for ninja in sorted(out_dir.rglob("*.ninja")):
            text = ninja.read_text(errors="replace")
            forbidden = forbidden_references(text, root)
            if forbidden:
                raise ValueError(
                    f"source prebuilt reference in {ninja}: {forbidden[0]}"
                )
            if any(marker in text for marker in external_markers):
                found_external = True
        if not found_external:
            raise ValueError(f"external SDK path is absent from Ninja graph: {out_dir}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--sdk", required=True, type=pathlib.Path)
    parser.add_argument("--out-dir", action="append", required=True, type=pathlib.Path)
    args = parser.parse_args()
    check_graph(args.root, args.sdk, args.out_dir)
    print("SMOS external SDK graph: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
