#!/usr/bin/env python3

import pathlib
import stat
import sys
import tempfile
import textwrap
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import verify


class VerifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = pathlib.Path(self.temp.name)
        self.log = root / "serial.log"
        self.child = root / "child.py"

    def write_child(self, body: str) -> None:
        self.child.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body))
        self.child.chmod(self.child.stat().st_mode | stat.S_IXUSR)

    def test_prompt_commands_and_markers_pass(self) -> None:
        self.write_child(
            """
            import sys
            print('welcome to test Zircon', flush=True)
            print('[driver_manager.cm] started', flush=True)
            print('[component_manager] started', flush=True)
            print('Bootup completed.', flush=True)
            print('smos:\\> ', end='', flush=True)
            for line in sys.stdin:
                command = line.strip()
                print(command, flush=True)
                if command == 'echo SHELL_OK': print('SHELL_OK', flush=True)
                if command == '/boot/bin/mkcheck':
                    for name in ('THREAD', 'VMO', 'CHANNEL', 'EVENT', 'TIMER', 'ALL'):
                        print(f'MKCHECK:{name}:PASS', flush=True)
                if command == '/boot/bin/virtcheck':
                    print('VIRTUALIZATION:ARM64:PASS', flush=True)
                print('smos:\\> ', end='', flush=True)
            """
        )
        result = verify.run_session("arm64", [str(self.child)], self.log, 2.0)
        self.assertTrue(result.ok, result.reason)
        transcript = self.log.read_text()
        expected = [
            "echo SHELL_OK",
            "ls /boot",
            "/boot/bin/mkcheck",
            "/boot/bin/virtcheck",
        ]
        positions = [transcript.index(command) for command in expected]
        self.assertEqual(positions, sorted(positions))

    def test_missing_marker_names_architecture(self) -> None:
        self.write_child(
            """
            import sys
            print('welcome to test Zircon', flush=True)
            print('[driver_manager.cm] Bootup completed.', flush=True)
            print('[component_manager] started', flush=True)
            print('$ ', end='', flush=True)
            for line in sys.stdin:
                if line.strip() == 'echo SHELL_OK': print('SHELL_OK', flush=True)
                if line.strip() == '/boot/bin/virtcheck':
                    print('VIRTUALIZATION:RISCV64:UNSUPPORTED', flush=True)
                print('$ ', end='', flush=True)
            """
        )
        result = verify.run_session("riscv64", [str(self.child)], self.log, 0.5)
        self.assertFalse(result.ok)
        self.assertIn("riscv64", result.reason)
        self.assertIn("MKCHECK:THREAD:PASS", result.reason)
        self.assertTrue(self.log.is_file())

    def test_child_exit_before_prompt(self) -> None:
        self.write_child("print('boot failed', flush=True)\n")
        result = verify.run_session("arm64", [str(self.child)], self.log, 1.0)
        self.assertFalse(result.ok)
        self.assertIn("arm64", result.reason)
        self.assertIn("before dash prompt", result.reason)

    def test_timeout_retains_log(self) -> None:
        self.write_child(
            """
            import time
            print('still booting', flush=True)
            time.sleep(30)
            """
        )
        result = verify.run_session("riscv64", [str(self.child)], self.log, 0.1)
        self.assertFalse(result.ok)
        self.assertIn("riscv64", result.reason)
        self.assertIn("timeout", result.reason)
        self.assertIn("still booting", self.log.read_text())

    def test_arm64_nested_el2_unavailable_is_supported_result(self) -> None:
        common = "\n".join(verify.COMMON_MARKERS)
        boot = "\n".join(verify.BOOT_MARKERS)
        self.write_child(
            f"""
            import sys
            print({boot!r}, flush=True)
            print('$ ', end='', flush=True)
            for line in sys.stdin:
                if line.strip() == '/boot/bin/virtcheck':
                    print({common!r}, flush=True)
                    print('VIRTUALIZATION:ARM64:NO_NESTED_EL2', flush=True)
                print('$ ', end='', flush=True)
            """
        )
        result = verify.run_session("arm64", [str(self.child)], self.log, 1.0)
        self.assertTrue(result.ok, result.reason)

    def test_background_driver_crash_fails_a_complete_boot(self) -> None:
        common = "\n".join(verify.COMMON_MARKERS)
        boot = "\n".join(verify.BOOT_MARKERS)
        self.write_child(
            f"""
            import sys
            print({boot!r}, flush=True)
            print('<== CRASH: process driver_host.cm[1]', flush=True)
            print('$ ', end='', flush=True)
            for line in sys.stdin:
                if line.strip() == '/boot/bin/virtcheck':
                    print({common!r}, flush=True)
                    print('VIRTUALIZATION:ARM64:NO_NESTED_EL2', flush=True)
                print('$ ', end='', flush=True)
            """
        )
        result = verify.run_session("arm64", [str(self.child)], self.log, 1.0)
        self.assertFalse(result.ok)
        self.assertIn("CRASH", result.reason)


if __name__ == "__main__":
    unittest.main()
