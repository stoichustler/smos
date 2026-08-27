#!/usr/bin/env python3

import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import inventory


class InventoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name).resolve()
        (self.root / "src/core").mkdir(parents=True)
        (self.root / "src/core/BUILD.gn").write_text("# build\n")
        (self.root / "src/core/main.cc").write_text("int main() {}\n")
        (self.root / "release").mkdir()
        (self.root / "release/rules.gni").write_text("# rule\n")
        (self.root / "docs/plans").mkdir(parents=True)
        (self.root / "docs/plans/plan.md").write_text("plan\n")
        (self.root / "tools/smos-boot").mkdir(parents=True)
        (self.root / "tools/smos-boot/check.sh").write_text("#!/bin/sh\n")
        (self.root / "LICENSE").write_text("license\n")
        (self.root / "README.md").write_text("readme\n")
        (self.root / ".gitignore").write_text("out/\n")
        (self.root / "real.txt").write_text("real\n")
        (self.root / "linked.txt").symlink_to("real.txt")

    def test_unions_arches_and_adds_parent_build_files(self) -> None:
        records = {
            "arm64": ["../../src/core/main.cc", "../../linked.txt"],
            "riscv64": ["../../release/rules.gni"],
        }
        out_dirs = {
            arch: self.root / "out" / f"smos-boot-{arch}" for arch in records
        }
        found = inventory.collect_records(self.root, out_dirs, records)
        paths = {entry.path: entry for entry in found}
        self.assertIn("src/core/main.cc", paths)
        self.assertIn("src/core/BUILD.gn", paths)
        self.assertEqual(("arm64",), paths["src/core/main.cc"].architectures)
        self.assertIn("release/rules.gni", paths)
        self.assertIn("linked.txt", paths)
        self.assertIn("real.txt", paths)

    def test_rejects_escape_and_unapproved_absolute_path(self) -> None:
        out = self.root / "out/smos-boot-arm64"
        with self.assertRaisesRegex(ValueError, "escapes source root"):
            inventory.normalize_input("../../../../escape", out, self.root, ())
        with self.assertRaisesRegex(ValueError, "unapproved external"):
            inventory.normalize_input("/etc/passwd", out, self.root, ())

    def test_approved_external_and_generated_paths_are_not_copied(self) -> None:
        external = self.root.parent / "external"
        external.mkdir(exist_ok=True)
        (external / "tool").write_text("tool\n")
        out = self.root / "out/smos-boot-arm64"
        self.assertIsNone(
            inventory.normalize_input(str(external / "tool"), out, self.root, (external,))
        )
        self.assertIsNone(
            inventory.normalize_input("generated.o", out, self.root, (external,))
        )

    def test_extracts_dynamic_dependencies_and_command_scripts(self) -> None:
        deps = inventory.dependency_inputs(
            ["obj/main.o: #deps 1", "    ../../src/core/main.cc", "", "bad"]
        )
        self.assertEqual(["../../src/core/main.cc"], deps)
        command = (
            "../../prebuilt/python ../../release/rules.py --source="
            "../../src/core/main.cc -I../../src/core"
        )
        self.assertEqual(
            [
                "../../prebuilt/python",
                "../../release/rules.py",
                "../../src/core/main.cc",
                "../../src/core",
            ],
            inventory.command_inputs(command),
        )

    @mock.patch("inventory.subprocess.run")
    def test_runtime_dependency_query_is_optional(self, run: mock.Mock) -> None:
        run.side_effect = subprocess.CalledProcessError(
            1, ["gn", "desc"], stderr="toolchain path is unavailable"
        )
        self.assertEqual(
            [],
            inventory.runtime_dependency_inputs(
                self.root, self.root / "out", "//userspace/core:core", pathlib.Path("gn")
            ),
        )

    def test_protected_tree_and_stable_manifests(self) -> None:
        (self.root / "src/.git").mkdir()
        entries = inventory.collect_records(
            self.root,
            {"arm64": self.root / "out/smos-boot-arm64"},
            {"arm64": ["../../src/core/main.cc"]},
        )
        inventory.add_protected(self.root, entries)
        paths = {entry.path for entry in entries}
        for required in (
            ".gitignore",
            "LICENSE",
            "README.md",
            "docs/plans/plan.md",
            "tools/smos-boot/check.sh",
        ):
            self.assertIn(required, paths)
        one = self.root / "one.json"
        two = self.root / "two.json"
        inventory.write_json(one, self.root, entries, {"arm64": ["target"]})
        inventory.write_json(two, self.root, entries, {"arm64": ["target"]})
        self.assertEqual(one.read_bytes(), two.read_bytes())
        data = json.loads(one.read_text())
        self.assertNotIn("external_git_links", data)
        self.assertEqual(sorted(item["path"] for item in data["paths"]),
                         [item["path"] for item in data["paths"]])


if __name__ == "__main__":
    unittest.main()
