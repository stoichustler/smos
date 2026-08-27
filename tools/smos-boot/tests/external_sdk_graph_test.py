#!/usr/bin/env python3

import os
import pathlib
import sys
import tempfile
import unittest


TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import check_external_sdk_graph


class ExternalSdkGraphTest(unittest.TestCase):
    def test_rejects_absolute_source_prebuilt_path(self) -> None:
        root = pathlib.Path("/work/smos")
        text = "command = /work/smos/prebuilt/third_party/clang/bin/clang\n"
        self.assertEqual(
            ["/work/smos/prebuilt/"],
            check_external_sdk_graph.forbidden_references(text, root),
        )

    def test_rejects_source_relative_prebuilt_path(self) -> None:
        root = pathlib.Path("/work/smos")
        text = "command = ../../prebuilt/third_party/python3/bin/python3\n"
        self.assertEqual(
            ["../../prebuilt/"],
            check_external_sdk_graph.forbidden_references(text, root),
        )

    def test_accepts_external_sdk_path(self) -> None:
        root = pathlib.Path("/work/smos")
        text = "command = ../../../smos-sdk/prebuilt/third_party/gn/gn\n"
        self.assertEqual([], check_external_sdk_graph.forbidden_references(text, root))

    def test_checks_generated_ninja_tree_for_external_sdk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            root = base / "smos"
            sdk = base / "smos-sdk"
            out = root / "out/smos-boot-arm64"
            out.mkdir(parents=True)
            (sdk / "prebuilt").mkdir(parents=True)
            external = pathlib.Path(os.path.relpath(sdk / "prebuilt", out)).as_posix()
            (out / "build.ninja").write_text(
                f"command = {external}/third_party/gn/linux-x64/gn\n"
            )

            check_external_sdk_graph.check_graph(root, sdk, (out,))


if __name__ == "__main__":
    unittest.main()
