#!/usr/bin/env python3

import argparse
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
PRODUCT = ROOT / "release/platform/products/smos_boot/BUILD.gn"
VIRTUALIZATION = ROOT / "release/platform/products/smos_boot/virtualization/BUILD.gn"
SHARD = ROOT / "release/platform/products/smos_boot/meta/virtualization.bootstrap_shard.cml"
CONSOLE_LAUNCHER = ROOT / "userspace/bringup/bin/console-launcher/meta/console-launcher.cml"
CONSOLE_SHARD = ROOT / "release/platform/products/smos_boot/meta/console.bootstrap_shard.cml"
ARCHIVIST = ROOT / "userspace/diagnostics/archivist/meta/archivist.cml"
ARCHIVIST_SHARD = ROOT / "userspace/diagnostics/archivist/meta/archivist.bootstrap_shard.cml"
GN = ROOT / "prebuilt/third_party/gn/linux-x64/gn"

FORBIDDEN_HOST_PACKAGE_LABEL_PARTS = (
    "virtio_gpu",
    "virtio_input",
    "virtio_sound",
    "virtio_wl",
    "virtio_magma",
    "wayland",
    "//third_party/mesa",
    "//third_party/vulkan-",
)


class VirtualizationScopeTest(unittest.TestCase):
    def test_arm64_host_runtime_is_packaged(self) -> None:
        text = VIRTUALIZATION.read_text()
        for required in (
            "//userspace/virtualization/bin/guest:bin",
            "//userspace/virtualization/bin/guest_manager:bin",
            "//userspace/virtualization/bin/vmm:bin",
            "//userspace/virtualization/bin/vmm_launcher:vmm_launcher_bin",
            "virtio_block_component",
            "virtio_console_component",
            "virtio_rng_component",
            "virtio_vsock_cmp",
        ):
            self.assertIn(required, text)

    def test_arm64_host_package_excludes_graphics_labels(self) -> None:
        text = VIRTUALIZATION.read_text().lower()
        for forbidden in FORBIDDEN_HOST_PACKAGE_LABEL_PARTS:
            with self.subTest(label=forbidden):
                self.assertNotIn(forbidden, text, forbidden)

    def test_bootstrap_realm_has_only_server_routes(self) -> None:
        text = SHARD.read_text().lower()
        for required in (
            "hypervisorresource",
            "vmexresource",
            "zircon-guest-manager",
            "vmm-launcher",
        ):
            self.assertIn(required, text)
        for forbidden in (
            "audio",
            "debian",
            "gpu",
            "net.",
            "scenic",
            "termina",
            "vulkan",
            "wayland",
        ):
            self.assertNotIn(forbidden, text)

    def test_console_launcher_excludes_debian_and_termina(self) -> None:
        text = CONSOLE_LAUNCHER.read_text()
        self.assertNotIn("fuchsia.virtualization.DebianGuestManager", text)
        self.assertNotIn("fuchsia.virtualization.TerminaGuestManager", text)
        self.assertIn("fuchsia.virtualization.ZirconGuestManager", text)

    def test_console_manifest_excludes_unavailable_smos_protocols(self) -> None:
        text = "\n".join((CONSOLE_LAUNCHER.read_text(), CONSOLE_SHARD.read_text()))
        for protocol in (
            "fuchsia.feedback.DataProvider",
            "fuchsia.metrics.MetricEventLoggerFactory",
            "fuchsia.net.name.Lookup",
            "fuchsia.paver.Paver",
            "fuchsia.pkg.PackageResolver",
            "fuchsia.pkg.RepositoryManager",
            "fuchsia.pkg.rewrite.Engine",
            "fuchsia.posix.socket.Provider",
            "fuchsia.power.broker.Topology",
            "fuchsia.power.suspend.Stats",
            "fuchsia.power.system.ActivityGovernor",
            "fuchsia.power.system.BootControl",
            "fuchsia.sys2.RealmExplorer.root",
            "fuchsia.sysmem.Allocator",
            "fuchsia.sysmem2.Allocator",
            "fuchsia.test.manager.Query",
            "fuchsia.virtualconsole.SessionManager",
            "fuchsia.virtualization.LinuxManager",
        ):
            with self.subTest(protocol=protocol):
                self.assertNotIn(protocol, text)

    def test_console_launcher_receives_component_introspection_protocols(self) -> None:
        launcher = CONSOLE_LAUNCHER.read_text()
        shard = CONSOLE_SHARD.read_text()
        for protocol in (
            "fuchsia.sys2.ConfigOverride.root",
            "fuchsia.sys2.LifecycleController.root",
            "fuchsia.sys2.RealmQuery.root",
            "fuchsia.sys2.RouteValidator.root",
        ):
            with self.subTest(protocol=protocol):
                self.assertIn(protocol, launcher)
                self.assertIn(protocol, shard)

    def test_smos_manifests_exclude_unavailable_directories(self) -> None:
        text = "\n".join(
            (
                CONSOLE_LAUNCHER.read_text(),
                CONSOLE_SHARD.read_text(),
                ARCHIVIST.read_text(),
                ARCHIVIST_SHARD.read_text(),
            )
        )
        self.assertNotIn("boot-bin", text)
        self.assertNotIn("netstack-diagnostics", text)

    def test_product_requests_bootstrap_virtualization(self) -> None:
        text = PRODUCT.read_text()
        self.assertRegex(
            text,
            r"(?s)virtualization\s*=\s*\{.*?bootstrap_enabled\s*=\s*true",
        )
        self.assertIn("smos_minimal_assembly = true", (ROOT / "release/platform/products/smos_boot.gni").read_text())


def describe(out_dir: pathlib.Path, target: str) -> str:
    return subprocess.run(
        [str(GN), "desc", str(out_dir), target, "deps", "--all"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout


def inspect_graph(out_dir: pathlib.Path) -> None:
    graph = describe(out_dir, "//release/platform/bundles/assembly:virtualization_support")
    if out_dir.name.endswith("arm64"):
        for required in (
            "//release/platform/products/smos_boot/virtualization:host",
            "//userspace/virtualization/bin/guest:bin",
            "//userspace/virtualization/bin/guest_manager:bin",
            "//userspace/virtualization/bin/vmm:bin",
            "//userspace/virtualization/bin/vmm_launcher:vmm_launcher_bin",
        ):
            if required not in graph:
                raise AssertionError(f"{out_dir}: missing {required}")
        system_graph = describe(out_dir, "//release/images/fuchsia:fuchsia_assembly")
        if "//zircon/kernel/arch/arm64/hypervisor:hypervisor" not in system_graph:
            raise AssertionError(f"{out_dir}: arm64 kernel hypervisor support is missing")
        for forbidden in (
            "debian_guest_manager",
            "termina_guest_manager",
            "virtio_gpu_component",
            "virtio_net_component",
            "virtio_sound_component",
            "virtio_wl_component",
        ):
            if forbidden in graph:
                raise AssertionError(f"{out_dir}: forbidden runtime {forbidden}")

        image = out_dir / "obj/release/images/fuchsia/fuchsia/image_assembly.json"
        if image.is_file():
            payload = image.read_text().lower()
            for required in ("bin/guest", "smos-virtualization-host"):
                if required not in payload:
                    raise AssertionError(f"{out_dir}: missing assembled {required}")
            for forbidden in ("debian", "termina", "virtio_gpu", "virtio_net", "virtio_sound"):
                if forbidden in payload:
                    raise AssertionError(f"{out_dir}: forbidden assembled {forbidden}")
    elif "//release/platform/products/smos_boot/virtualization:host" in graph:
        raise AssertionError(f"{out_dir}: riscv64 unexpectedly packages the host runtime")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gn-desc", action="append", type=pathlib.Path, default=[])
    args = parser.parse_args()
    if not args.gn_desc:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(VirtualizationScopeTest)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    for out_dir in args.gn_desc:
        inspect_graph(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
