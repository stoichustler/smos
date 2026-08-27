#!/usr/bin/env python3

import json
import pathlib
import tempfile
import unittest
from unittest import mock

import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import artifacts


class ArtifactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name).resolve()
        self.out = self.root / "out" / "smos-boot-arm64"
        self.metadata = self.out / "obj/release/images/fuchsia/fuchsia/image_assembly.json"
        self.metadata.parent.mkdir(parents=True)
        self.kernel = self.out / "kernel.phys_arm64/linux-arm64-boot-shim.bin"
        self.kernel.parent.mkdir(parents=True)
        self.kernel.touch()
        self.zbi = self.out / "smos.zbi"
        self.zbi.touch()
        self.metadata.write_text(json.dumps({"qemu_kernel": str(self.kernel.relative_to(self.out))}))

    @mock.patch("artifacts.subprocess.run")
    def test_resolves_gn_zbi_and_assembly_qemu_kernel(self, run: mock.Mock) -> None:
        run.side_effect = [
            mock.Mock(stdout="//out/smos-boot-arm64/smos.zbi\n"),
            mock.Mock(
                stdout="//out/smos-boot-arm64/obj/release/images/fuchsia/fuchsia/"
                "image_assembly.json\n"
            ),
        ]
        found = artifacts.resolve_artifacts(self.root, self.out, pathlib.Path("gn"))
        self.assertEqual(found.zbi, self.zbi)
        self.assertEqual(found.qemu_kernel, self.kernel)
        self.assertEqual(
            run.call_args_list[0].args[0][3],
            "//release/images/fuchsia:fuchsia.copy_zbi",
        )

    @mock.patch("artifacts.subprocess.run")
    def test_rejects_gn_output_outside_selected_output_tree(self, run: mock.Mock) -> None:
        foreign = self.root / "out" / "other" / "bad.zbi"
        foreign.parent.mkdir(parents=True)
        foreign.touch()
        run.side_effect = [
            mock.Mock(stdout="//out/other/bad.zbi\n"),
            mock.Mock(stdout=""),
        ]
        with self.assertRaisesRegex(ValueError, "outside output directory"):
            artifacts.resolve_artifacts(self.root, self.out, pathlib.Path("gn"))

    @mock.patch("artifacts.subprocess.run")
    def test_rejects_ambiguous_zbi_outputs(self, run: mock.Mock) -> None:
        second = self.out / "second.zbi"
        second.touch()
        run.side_effect = [
            mock.Mock(
                stdout="//out/smos-boot-arm64/smos.zbi\n"
                "//out/smos-boot-arm64/second.zbi\n"
            ),
            mock.Mock(stdout=""),
        ]
        with self.assertRaisesRegex(ValueError, "exactly one ZBI"):
            artifacts.resolve_artifacts(self.root, self.out, pathlib.Path("gn"))


if __name__ == "__main__":
    unittest.main()
