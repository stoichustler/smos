#!/usr/bin/env python3

import json
import os
import pathlib
import stat
import tempfile
import unittest

import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))

import compact


class CompactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = pathlib.Path(self.temp.name)
        self.source = base / "source"
        self.destination = base / "stage"
        self.external = base / "external"
        self.source.mkdir()
        (self.external / "prebuilt").mkdir(parents=True)
        (self.external / "vendor/.git").mkdir(parents=True)
        (self.source / "dir").mkdir()
        self.executable = self.source / "dir/tool.sh"
        self.executable.write_text("#!/bin/sh\n")
        self.executable.chmod(0o751)
        (self.source / "target.txt").write_text("target\n")
        (self.source / "link.txt").symlink_to("target.txt")
        self.manifest = base / "keep.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "external_links": [],
                    "external_git_links": ["vendor/.git"],
                    "paths": [
                        {"path": "dir/tool.sh", "kind": "file", "size": 10},
                        {"path": "link.txt", "kind": "symlink", "size": 10},
                        {"path": "target.txt", "kind": "file", "size": 7},
                    ],
                }
            )
        )

    def test_copies_only_manifest_preserving_mode_and_symlink(self) -> None:
        (self.source / "unused").write_text("no\n")
        result = compact.stage_tree(
            self.source, self.destination, self.manifest, self.external
        )
        self.assertFalse((self.destination / "unused").exists())
        self.assertEqual(
            stat.S_IMODE(self.executable.stat().st_mode),
            stat.S_IMODE((self.destination / "dir/tool.sh").stat().st_mode),
        )
        self.assertEqual("target.txt", os.readlink(self.destination / "link.txt"))
        self.assertFalse((self.destination / "prebuilt").exists())
        self.assertFalse((self.destination / "vendor/.git").exists())
        self.assertNotIn("external_git_links", result)
        self.assertEqual(3, result["copied_paths"])
        self.assertEqual({}, result["external_links"])
        self.assertFalse((self.destination / "compact-manifest.json").exists())
        self.assertFalse((self.source / "compact-manifest.json").exists())

    def test_project_policy_has_no_external_source_links(self) -> None:
        policy = json.loads(
            (ROOT / "tools/smos-boot/compact-policy.json").read_text()
        )
        self.assertEqual([], policy["external_links"])

    def test_project_policy_keeps_both_supported_target_architectures(self) -> None:
        policy = json.loads(
            (ROOT / "tools/smos-boot/compact-policy.json").read_text()
        )
        self.assertEqual(["arm64", "riscv64"], sorted(policy["architectures"]))

    def test_refuses_nonempty_destination_without_replace(self) -> None:
        self.destination.mkdir()
        (self.destination / "user-data").write_text("keep\n")
        with self.assertRaisesRegex(ValueError, "nonempty destination"):
            compact.stage_tree(self.source, self.destination, self.manifest, self.external)
        self.assertTrue((self.destination / "user-data").is_file())

    def test_rejects_source_destination_overlap(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlap"):
            compact.stage_tree(
                self.source, self.source / "inside", self.manifest, self.external
            )

    def test_measure_fails_at_limit(self) -> None:
        measured = compact.measure_tree(self.source)
        with self.assertRaisesRegex(ValueError, "size gate"):
            compact.enforce_size(measured, measured)
        compact.enforce_size(measured, measured + 1)


if __name__ == "__main__":
    unittest.main()
