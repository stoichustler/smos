#!/usr/bin/env python3

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
BOARD_FILES = (
    ROOT / "platform/boards/smos-qemu-arm64.gni",
    ROOT / "platform/boards/smos-qemu-arm64/BUILD.gn",
    ROOT / "platform/boards/smos-qemu-riscv64/BUILD.gn",
    ROOT / "platform/boards/smos-server-drivers/BUILD.gn",
)
GENERIC_GRAPHICS_OWNERS = (
    ROOT / "platform/boards/smos-qemu-arm64/BUILD.gn",
)
BOARDS_AGGREGATE = ROOT / "platform/boards/BUILD.gn"
VIRTIO_BUILD = ROOT / "userspace/devices/bus/lib/virtio/BUILD.gn"
PCI_BUS = ROOT / "userspace/devices/bus/drivers/pci/bus.cc"
PCI_MANIFEST = ROOT / "userspace/devices/bus/drivers/pci/meta/pci.cml"
REQUIRED = {
    "//userspace/devices/board/drivers/qemu-arm64:package",
    "//userspace/devices/board/drivers/qemu-riscv64:package",
    "//userspace/devices/bus/drivers/pci:bus-pci-package",
    "//userspace/devices/block/drivers/virtio:virtio_block_package",
    "//userspace/devices/misc/drivers/virtio-socket:package",
    "//userspace/devices/serial/drivers/virtio-console:package",
}
FORBIDDEN = (
    "/graphics/",
    "/ui/",
    "virtio_netdevice",
    "wlan",
    "bluetooth",
    "audio",
    "camera",
    "goldfish",
    "virtio-gpu",
)


class BoardGraphPolicyTest(unittest.TestCase):
    def board_text(self) -> str:
        return "\n".join(path.read_text() for path in BOARD_FILES)

    def test_all_board_files_exist(self) -> None:
        missing = [str(path.relative_to(ROOT)) for path in BOARD_FILES if not path.is_file()]
        self.assertEqual([], missing)

    def test_required_server_drivers_are_retained(self) -> None:
        text = self.board_text()
        missing = sorted(label for label in REQUIRED if label not in text)
        self.assertEqual([], missing)

    def test_arm64_uses_userspace_pci_root(self) -> None:
        arm64 = (ROOT / "platform/boards/smos-qemu-arm64.gni").read_text()
        self.assertIn("qemu_arm64_enable_user_pci = true", arm64)

    def test_graphical_and_network_drivers_are_absent(self) -> None:
        text = self.board_text().lower()
        present = sorted(token for token in FORBIDDEN if token in text)
        self.assertEqual([], present)

    def test_unused_host_rng_driver_is_absent(self) -> None:
        text = (ROOT / "platform/boards/smos-server-drivers/BUILD.gn").read_text()
        self.assertNotIn("virtio-rng", text)
        self.assertNotIn("virtio_rng", text)

    def test_loaded_generic_boards_do_not_name_deleted_graphics(self) -> None:
        text = "\n".join(path.read_text() for path in GENERIC_GRAPHICS_OWNERS).lower()
        for token in ("/graphics/", "/ui/", "vulkan", "goldfish", "virtio-gpu"):
            with self.subTest(token=token):
                self.assertNotIn(token, text)

    def test_minimal_board_aggregate_loads_only_smos_boards(self) -> None:
        text = BOARDS_AGGREGATE.read_text()
        self.assertIn("if (smos_minimal_assembly)", text)
        self.assertIn("//platform/boards/smos-qemu-arm64", text)
        self.assertIn("//platform/boards/smos-qemu-riscv64", text)

    def test_retained_virtio_library_has_no_graphics_dependency(self) -> None:
        text = VIRTIO_BUILD.read_text()
        self.assertNotIn("//userspace/graphics/", text)
        self.assertIn(":logging-dfv1", text)
        self.assertIn(":logging-dfv2", text)

    def test_optional_pci_board_metadata_is_quiet_when_not_offered(self) -> None:
        manifest = PCI_MANIFEST.read_text()
        bus = PCI_BUS.read_text()
        self.assertRegex(
            manifest,
            r"(?s)fuchsia\.hardware\.pci\.BoardConfiguration.*?availability:\s*'optional'",
        )
        self.assertIn("GetMetadataIfExists<PciFidl::BoardConfiguration>", bus)


if __name__ == "__main__":
    unittest.main()
