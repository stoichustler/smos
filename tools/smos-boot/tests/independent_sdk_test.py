#!/usr/bin/env python3

import hashlib
import json
import pathlib
import tempfile
import unittest

import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import independent_sdk


class IndependentSdkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sdk = pathlib.Path(self.temp.name) / "sdk"
        self.prebuilt = self.sdk / "prebuilt"
        self.prebuilt.mkdir(parents=True)

        self.payload = self.prebuilt / "toolchains/clang/bin/clang"
        self.payload.parent.mkdir(parents=True)
        self.payload.write_bytes(b"clang payload\n")
        self.payload.chmod(0o755)

    def write_manifest(self) -> pathlib.Path:
        return independent_sdk.write_manifest(
            self.sdk, architectures=("arm64", "riscv64")
        )

    def test_create_manifest_records_sorted_regular_files(self) -> None:
        first = self.prebuilt / "00-sysroot/include/header.h"
        first.parent.mkdir(parents=True)
        first.write_bytes(b"header\n")

        manifest = independent_sdk.create_manifest(
            self.sdk, architectures=("arm64", "riscv64")
        )

        self.assertEqual(1, manifest["version"])
        self.assertEqual(["arm64", "riscv64"], manifest["architectures"])
        self.assertEqual(
            [
                "prebuilt/00-sysroot/include/header.h",
                "prebuilt/toolchains/clang/bin/clang",
            ],
            [entry["path"] for entry in manifest["files"]],
        )
        clang = manifest["files"][1]
        self.assertEqual(len(self.payload.read_bytes()), clang["size"])
        self.assertEqual(
            hashlib.sha256(self.payload.read_bytes()).hexdigest(), clang["sha256"]
        )
        self.assertTrue(clang["executable"])
        self.assertFalse(manifest["files"][0]["executable"])
        self.assertEqual(
            len(first.read_bytes()) + len(self.payload.read_bytes()),
            manifest["total_bytes"],
        )

    def test_validate_accepts_unchanged_sdk(self) -> None:
        self.write_manifest()

        manifest = independent_sdk.validate_sdk(
            self.sdk, required_architectures=("arm64", "riscv64")
        )

        self.assertEqual(["arm64", "riscv64"], manifest["architectures"])

    def test_validate_rejects_changed_file(self) -> None:
        self.write_manifest()
        self.payload.write_bytes(b"tampered\n")

        with self.assertRaisesRegex(ValueError, "hash|size"):
            independent_sdk.validate_sdk(self.sdk)

    def test_manifest_accepts_contained_relative_symlink(self) -> None:
        alias = self.payload.parent / "clang++"
        alias.symlink_to("clang")

        manifest_path = self.write_manifest()
        manifest = independent_sdk.validate_sdk(self.sdk)

        entry = next(item for item in manifest["files"] if item["path"].endswith("clang++"))
        self.assertEqual("symlink", entry["kind"])
        self.assertEqual("clang", entry["target"])
        self.assertTrue(alias.is_symlink())

    def test_validate_rejects_absolute_symlink(self) -> None:
        self.write_manifest()
        (self.prebuilt / "absolute-link").symlink_to("/etc/passwd")

        with self.assertRaisesRegex(ValueError, "symlink"):
            independent_sdk.validate_sdk(self.sdk)

    def test_validate_rejects_relative_symlink_escaping_sdk(self) -> None:
        self.write_manifest()
        (self.prebuilt / "escaping-link").symlink_to("../../outside")

        with self.assertRaisesRegex(ValueError, "symlink"):
            independent_sdk.validate_sdk(self.sdk)

    def test_validate_rejects_missing_required_architecture(self) -> None:
        independent_sdk.write_manifest(self.sdk, architectures=("arm64",))

        with self.assertRaisesRegex(ValueError, "riscv64"):
            independent_sdk.validate_sdk(
                self.sdk, required_architectures=("arm64", "riscv64")
            )

    def test_validate_rejects_unsafe_manifest_path(self) -> None:
        manifest_path = self.write_manifest()
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][0]["path"] = "../outside"
        manifest_path.write_text(json.dumps(manifest))

        with self.assertRaisesRegex(ValueError, "unsafe|contained"):
            independent_sdk.validate_sdk(self.sdk)

    def test_trace_paths_keeps_only_prebuilt_files(self) -> None:
        source_root = pathlib.Path(self.temp.name) / "work/smos"
        source_prebuilt = pathlib.Path(self.temp.name) / "source/prebuilt"
        output = source_root / "out/smos-boot-arm64"
        output.mkdir(parents=True)
        source_prebuilt.mkdir(parents=True)
        (source_root / "prebuilt").symlink_to(source_prebuilt)
        clang = source_prebuilt / "third_party/clang/linux-x64/bin/clang"
        python = source_prebuilt / "third_party/python3/linux-x64/bin/python3"
        for path in (clang, python):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(path.name)
        (source_root / "userspace").mkdir()
        (source_root / "userspace/main.cc").write_text("source")

        lines = [
            f'123 openat(AT_FDCWD<{output}>, "../../prebuilt/third_party/clang/linux-x64/bin/clang", O_RDONLY) = 3',
            f'124 openat(5<{python.parent}>, "python3", O_RDONLY) = 6',
            f'125 openat(AT_FDCWD<{output}>, "../../userspace/main.cc", O_RDONLY) = 3',
        ]

        self.assertEqual(
            {
                pathlib.Path("third_party/clang/linux-x64/bin/clang"),
                pathlib.Path("third_party/python3/linux-x64/bin/python3"),
            },
            independent_sdk.trace_paths(lines, source_root, source_prebuilt),
        )

    def test_extract_sdk_materializes_links_and_preserves_mode(self) -> None:
        source = pathlib.Path(self.temp.name) / "source-prebuilt"
        tool = source / "third_party/clang/bin/clang-real"
        tool.parent.mkdir(parents=True)
        tool.write_bytes(b"compiler")
        tool.chmod(0o755)
        (tool.parent / "clang").symlink_to("clang-real")
        destination = pathlib.Path(self.temp.name) / "published-sdk"

        manifest = independent_sdk.extract_sdk(
            source,
            destination,
            [pathlib.Path("third_party/clang/bin/clang")],
            ("arm64", "riscv64"),
        )

        published = destination / "prebuilt/third_party/clang/bin/clang"
        self.assertTrue(published.is_file())
        self.assertFalse(published.is_symlink())
        self.assertEqual(b"compiler", published.read_bytes())
        self.assertTrue(published.stat().st_mode & 0o111)
        self.assertEqual(1, manifest["version"])
        independent_sdk.validate_sdk(
            destination, required_architectures=("arm64", "riscv64")
        )

    def test_extract_sdk_rejects_escape_and_keeps_existing_sdk(self) -> None:
        source = pathlib.Path(self.temp.name) / "source-prebuilt"
        source.mkdir()
        destination = pathlib.Path(self.temp.name) / "published-sdk"
        destination.mkdir()
        marker = destination / "old"
        marker.write_text("keep")

        with self.assertRaisesRegex(ValueError, "unsafe|escape"):
            independent_sdk.extract_sdk(
                source,
                destination,
                [pathlib.Path("../outside")],
                ("arm64", "riscv64"),
                replace=True,
            )

        self.assertEqual("keep", marker.read_text())


if __name__ == "__main__":
    unittest.main()
