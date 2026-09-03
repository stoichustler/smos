#!/usr/bin/env python3

import argparse
import json
import pathlib
import re
import subprocess
import unittest


SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[3]
PRODUCT = SOURCE_ROOT / "release" / "platform" / "products" / "smos_boot" / "BUILD.gn"
PRODUCT_GNI = SOURCE_ROOT / "release" / "platform" / "products" / "smos_boot.gni"
GN = SOURCE_ROOT / "prebuilt" / "third_party" / "gn" / "linux-x64" / "gn"
ASSEMBLY_TARGET = "//release/images/fuchsia:fuchsia_assembly"
IMAGE_ASSEMBLER_TARGET = "//release/images/fuchsia:fuchsia.image_assembler"
PLATFORM_AIB_CATALOG_TARGET = "//release/images/fuchsia:fuchsia.product_assembler"
PRODUCT_TARGET = "//release/platform/products/smos_boot:smos_boot"

REQUIRED_PRODUCT_SNIPPETS = (
    'feature_set_level = "bootstrap"',
    'build_type = "userdebug"',
    'image_mode = "ramdisk"',
    "enabled = true",
    'include_netsvc = false',
    'include_paver = false',
    'bootfs_files_labels = [ ":verification_tools" ]',
)

REQUIRED_PLATFORM_PROVIDERS = (
    ("//release/platform/bundles/assembly:console", "//userspace/bringup/bin/console:package"),
    (
        "//release/platform/bundles/assembly:console",
        "//userspace/bringup/bin/console-launcher:package",
    ),
    ("//release/platform/bundles/assembly:component_manager", "//userspace/sys/component_manager:bootfs"),
    ("//release/platform/bundles/assembly:embeddable_userdebug", "//zircon/third_party/uapp/dash:bootfs"),
    ("//release/platform/bundles/assembly:driver_framework", "//userspace/devices/bin/driver_manager:package"),
)

FORBIDDEN_PRODUCT_LABEL_PARTS = (
    "/graphics/",
    "/ui/",
    "/media/",
    "/audio/",
    "/camera/",
    "/connectivity/",
    "/wlan/",
    "/bluetooth/",
    "/recovery/",
    "/update/",
    "/package-repository",
)

def gn_labels(text: str) -> list[str]:
    return re.findall(r'"(//[^"\s]+)"', text)


class ProductPolicyTest(unittest.TestCase):
    def test_smos_boot_product_contract(self) -> None:
        product = PRODUCT.read_text()
        product_gni = PRODUCT_GNI.read_text()

        self.assertIn("use_bringup_assembly = false", product_gni)
        self.assertIn("bootfs_only = false", product_gni)
        self.assertIn("fxfs_blob = false", product_gni)
        self.assertIn('smos_zbi_name = "smos"', product_gni)
        for snippet in REQUIRED_PRODUCT_SNIPPETS:
            self.assertIn(snippet, product)

    def test_product_has_no_optional_domain_labels(self) -> None:
        labels = gn_labels(PRODUCT.read_text())
        for label in labels:
            for forbidden in FORBIDDEN_PRODUCT_LABEL_PARTS:
                self.assertNotIn(forbidden, label, label)

    def test_shell_is_owned_by_platform_bundles(self) -> None:
        bundles = (
            SOURCE_ROOT / "release" / "platform" / "bundles" / "assembly" / "BUILD.gn"
        ).read_text()
        development = (
            SOURCE_ROOT
            / "userspace/lib/assembly/platform_configuration/src/subsystems/development.rs"
        ).read_text()
        self.assertRegex(
            bundles,
            r'(?s)assembly_input_bundle\("component_manager"\).*?'
            r'//userspace/sys/component_manager:bootfs',
        )
        self.assertRegex(
            bundles,
            r'(?s)assembly_input_bundle\("embeddable_userdebug"\).*?'
            r'//zircon/third_party/uapp/dash:bootfs',
        )
        self.assertRegex(
            bundles,
            r'(?s)assembly_input_bundle\("console"\).*?'
            r'//userspace/bringup/bin/console:package.*?'
            r'//userspace/bringup/bin/console-launcher:package',
        )
        self.assertIn('(_, Some(true)) => "kernel_args_eng"', development)
        self.assertRegex(
            bundles,
            r'(?s)assembly_input_bundle\("kernel_args_eng"\).*?'
            r'"console.shell=true"',
        )


def describe_deps(out_dir: pathlib.Path, target: str, all_deps: bool = False) -> list[str]:
    command = [str(GN), "desc", str(out_dir), target, "deps"]
    if all_deps:
        command.append("--all")
    result = subprocess.run(
        command,
        cwd=SOURCE_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.splitlines()


def inspect_graph(out_dir: pathlib.Path) -> list[str]:
    # SMOS supplies a compact platform AIB allowlist. Validate the selected
    # assembly providers below rather than rejecting unrelated candidates that
    # are available to Product Assembly.
    direct_product_deps = describe_deps(out_dir, PRODUCT_TARGET)
    assembly_deps = describe_deps(out_dir, ASSEMBLY_TARGET)
    if not any(dep.startswith(IMAGE_ASSEMBLER_TARGET) for dep in assembly_deps):
        raise AssertionError(f"{out_dir}: assembly is missing the image assembler")
    image_assembler_deps = describe_deps(out_dir, IMAGE_ASSEMBLER_TARGET)
    if not any(dep.startswith(PLATFORM_AIB_CATALOG_TARGET) for dep in image_assembler_deps):
        raise AssertionError(f"{out_dir}: image assembler is missing the product assembler")
    platform_aibs = describe_deps(out_dir, PLATFORM_AIB_CATALOG_TARGET)
    for provider, required in REQUIRED_PLATFORM_PROVIDERS:
        if not any(dep.startswith(provider) for dep in platform_aibs):
            raise AssertionError(f"{out_dir}: assembly is missing provider {provider}")
        provider_deps = describe_deps(out_dir, provider, all_deps=True)
        if not any(dep.startswith(required) for dep in provider_deps):
            raise AssertionError(f"{out_dir}: {provider} does not provide {required}")

    for dep in direct_product_deps:
        label = dep.split("(", 1)[0]
        for forbidden in FORBIDDEN_PRODUCT_LABEL_PARTS:
            if forbidden in label:
                raise AssertionError(f"{out_dir}: forbidden dependency {label}")
    inspect_assembled_image(out_dir)
    return direct_product_deps


def inspect_assembled_image(out_dir: pathlib.Path) -> None:
    image = (
        out_dir
        / "obj/release/images/fuchsia/fuchsia/image_assembly.json"
    )
    if not image.is_file():
        return

    config = json.loads(image.read_text())
    kernel_args = config["kernel"]["args"]
    if "console.shell=true" not in kernel_args:
        raise AssertionError(f"{out_dir}: dash console is not enabled")
    if "netsvc.disable=true" not in kernel_args:
        raise AssertionError(f"{out_dir}: netsvc is not disabled")

    payload = "\n".join(
        [entry["destination"] for entry in config["bootfs_files"]]
        + config["bootfs_packages"]
    ).lower()
    destinations = {entry["destination"] for entry in config["bootfs_files"]}
    for required in ("bin/component_manager", "bin/mkcheck", "bin/sh", "bin/virtcheck"):
        if required not in destinations:
            raise AssertionError(f"{out_dir}: missing BootFS file {required}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gn-desc", action="append", type=pathlib.Path, default=[])
    args = parser.parse_args()
    if not args.gn_desc:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProductPolicyTest)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    for out_dir in args.gn_desc:
        inspect_graph(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
