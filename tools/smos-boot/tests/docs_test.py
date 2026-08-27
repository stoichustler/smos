#!/usr/bin/env python3

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]


class DocumentationTest(unittest.TestCase):
    def test_compact_workflow_is_documented(self) -> None:
        text = (ROOT / "sdk/smos/SVE-os.md").read_text()
        for required in (
            "/home/beau/clot/smos-sdk",
            "build-independent-sdk.sh",
            "--source-checkout",
            "--sdk",
            "SMOS_SDK_ROOT",
            "sdk-manifest.json",
            "does not create a source-root `prebuilt`",
            "validates the SDK before running GN",
            "configure.sh arm64",
            "configure.sh riscv64",
            "build.sh arm64",
            "build.sh riscv64",
            "verify.sh all",
            "--max-bytes 524288000",
            "VIRTUALIZATION:ARM64:NO_NESTED_EL2",
            "VIRTUALIZATION:RISCV64:UNSUPPORTED",
            "Virtio socket remains",
            "GPU virtualization devices are removed",
            "block, console, RNG, vsock, balloon, and memory",
        ):
            self.assertIn(required, text)
        for forbidden in (
            "../orig",
            "/zircon/orig",
            "requires `.cipd`",
            "virtio-gpu is retained",
            "Activation creates",
            "automatically validates and activates",
        ):
            self.assertNotIn(forbidden, text)

    def test_readme_links_compact_guide(self) -> None:
        self.assertIn("[SVE-os.md](sdk/smos/SVE-os.md)", (ROOT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
