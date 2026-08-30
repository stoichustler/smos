#!/usr/bin/env python3

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
LINUX_MANAGER = ROOT / "platform/products/smos_boot/virtualization/meta/linux_guest_manager.cml"
VIRTUALIZATION_BUILD = ROOT / "platform/products/smos_boot/virtualization/BUILD.gn"
BOOTSTRAP_SHARD = ROOT / "platform/products/smos_boot/meta/virtualization.bootstrap_shard.cml"
CONSOLE_LAUNCHER = ROOT / "userspace/bringup/bin/console-launcher/meta/console-launcher.cml"


class LinuxGuestManagerGraphTest(unittest.TestCase):
    def test_linux_manager_mounts_the_custom_guest_and_exposes_its_alias(self) -> None:
        self.assertTrue(LINUX_MANAGER.is_file())
        text = LINUX_MANAGER.read_text()
        self.assertIn('url: "linux_guest#meta/linux_guest.cm"', text)
        self.assertIn('as: "fuchsia.virtualization.LinuxGuestManager"', text)

    def test_host_package_contains_the_linux_manager_component(self) -> None:
        text = VIRTUALIZATION_BUILD.read_text()
        self.assertIn('fuchsia_component("linux_guest_manager_component")', text)
        self.assertIn(":linux_guest_manager_component", text)

    def test_bootstrap_routes_linux_manager_to_the_console(self) -> None:
        text = BOOTSTRAP_SHARD.read_text()
        self.assertIn('name: "linux-guest-manager"', text)
        self.assertIn('fuchsia.virtualization.LinuxGuestManager', text)
        self.assertIn('from: "#linux-guest-manager"', text)

    def test_console_optionally_uses_linux_manager(self) -> None:
        self.assertIn('fuchsia.virtualization.LinuxGuestManager', CONSOLE_LAUNCHER.read_text())


if __name__ == "__main__":
    unittest.main()
