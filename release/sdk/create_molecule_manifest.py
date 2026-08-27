#!/usr/bin/env fuchsia-vendored-python
# Copyright 2017 The Fuchsia Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import json
import os
import pathlib
import sys

from sdk_common import Validator, gather_dependencies


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="Path to the output file", required=True)
    parser.add_argument(
        "--deps",
        help="List of manifest paths for the included elements",
        nargs="*",
    )
    parser.add_argument(
        "--category", help="Minimum publication level", required=True
    )
    parser.add_argument(
        "--areas-file-path",
        type=pathlib.Path,
        help="Path to docs/contribute/governance/areas/_areas.yaml",
    )
    args = parser.parse_args()

    (direct_deps, atoms) = gather_dependencies(args.deps)

    validator = (
        Validator.from_areas_file_path(areas_file=args.areas_file_path)
        if args.areas_file_path
        else Validator([])
    )
    violations = [
        *validator.detect_violations(
            args.category,
            list(atoms),
            validate_areas=args.areas_file_path is not None,
        )
    ]
    if violations:
        print("Errors detected!")
        for msg in violations:
            print(msg)
        return 1

    manifest = {
        "ids": [],
        "atoms": [a.json for a in sorted(list(atoms))],
        "root": "..",
    }
    with open(os.path.abspath(args.out), "w") as out:
        json.dump(
            manifest, out, indent=2, sort_keys=True, separators=(",", ": ")
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
