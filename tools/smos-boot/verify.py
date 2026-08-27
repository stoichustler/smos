#!/usr/bin/env python3
"""Boot SMOS on a PTY and verify its interactive dash contract."""

import argparse
import dataclasses
import errno
import os
import pathlib
import pty
import re
import selectors
import signal
import subprocess
import sys
import time


COMMON_MARKERS = (
    "SHELL_OK",
    "MKCHECK:THREAD:PASS",
    "MKCHECK:VMO:PASS",
    "MKCHECK:CHANNEL:PASS",
    "MKCHECK:EVENT:PASS",
    "MKCHECK:TIMER:PASS",
    "MKCHECK:ALL:PASS",
)
BOOT_MARKERS = (
    "welcome to ",
    "[component_manager]",
    "[driver_manager.cm]",
    "Bootup completed.",
)
FATAL_MARKERS = (
    "<== CRASH:",
    "ZIRCON KERNEL OOPS",
    "KERNEL PANIC",
)
COMMANDS = (
    "echo SHELL_OK",
    "ls /boot",
    "/boot/bin/mkcheck",
    "/boot/bin/virtcheck",
)
# The shell redraws the prompt after an ANSI cursor-positioning sequence, and
# concurrent kernel logs can arrive on the same terminal line.
PROMPT = re.compile(
    rb"(?:^|[\r\n]|\x1b\[[0-9;?]*[A-Za-z])(?:smos:\\>|\$|#|>) "
)


@dataclasses.dataclass(frozen=True)
class Result:
    ok: bool
    reason: str


def _virtualization_ok(arch: str, text: str) -> bool:
    if arch == "arm64":
        return any(
            marker in text
            for marker in (
                "VIRTUALIZATION:ARM64:PASS",
                "VIRTUALIZATION:ARM64:NO_NESTED_EL2",
            )
        )
    return "VIRTUALIZATION:RISCV64:UNSUPPORTED" in text


def _missing_reason(arch: str, text: str) -> str | None:
    for marker in FATAL_MARKERS:
        if marker in text:
            return f"{arch}: fatal boot marker {marker}"
    for marker in COMMON_MARKERS:
        if marker not in text:
            return f"{arch}: missing marker {marker}"
    for marker in BOOT_MARKERS:
        if marker not in text:
            return f"{arch}: missing boot marker {marker}"
    if not _virtualization_ok(arch, text):
        expected = (
            "VIRTUALIZATION:ARM64:PASS|NO_NESTED_EL2"
            if arch == "arm64"
            else "VIRTUALIZATION:RISCV64:UNSUPPORTED"
        )
        return f"{arch}: missing marker {expected}"
    return None


def _terminate_group(child: subprocess.Popen[bytes]) -> None:
    if child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=0.5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()


def run_session(
    arch: str, command: list[str], serial_log: pathlib.Path, timeout: float
) -> Result:
    if arch not in ("arm64", "riscv64"):
        return Result(False, f"{arch}: unsupported architecture")
    serial_log.parent.mkdir(parents=True, exist_ok=True)
    master, slave = pty.openpty()
    child: subprocess.Popen[bytes] | None = None
    transcript = bytearray()
    commands_sent = 0
    handled_prompt_end = 0
    answered_cursor_queries = 0
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    try:
        child = subprocess.Popen(
            command,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave)
        slave = -1
        os.set_blocking(master, False)
        selector.register(master, selectors.EVENT_READ)
        with serial_log.open("wb") as log:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    text = transcript.decode(errors="replace")
                    if commands_sent:
                        reason = _missing_reason(arch, text)
                        if reason is not None:
                            return Result(False, reason)
                    return Result(False, f"{arch}: timeout waiting for dash prompt")

                for _key, _events in selector.select(min(remaining, 0.1)):
                    try:
                        data = os.read(master, 65536)
                    except OSError as error:
                        if error.errno == errno.EIO:
                            data = b""
                        else:
                            raise
                    if data:
                        transcript.extend(data)
                        log.write(data)
                        log.flush()

                # dash asks an interactive terminal for the cursor position
                # before drawing its prompt.  A raw PTY has no terminal
                # emulator to answer the ANSI DSR query, so provide the
                # minimal response expected by the shell.
                cursor_queries = transcript.count(b"\x1b[6n")
                while answered_cursor_queries < cursor_queries:
                    os.write(master, b"\x1b[1;1R")
                    answered_cursor_queries += 1

                prompts = list(PROMPT.finditer(transcript))
                latest_prompt = prompts[-1] if prompts else None
                if (
                    latest_prompt is not None
                    and latest_prompt.end() > handled_prompt_end
                    and commands_sent < len(COMMANDS)
                    and all(marker.encode() in transcript for marker in BOOT_MARKERS)
                ):
                    os.write(master, f"{COMMANDS[commands_sent]}\n".encode())
                    commands_sent += 1
                    handled_prompt_end = latest_prompt.end()

                text = transcript.decode(errors="replace")
                if commands_sent == len(COMMANDS) and _missing_reason(arch, text) is None:
                    return Result(True, "pass")

                if child.poll() is not None:
                    if not commands_sent:
                        return Result(False, f"{arch}: QEMU exited before dash prompt")
                    reason = _missing_reason(arch, text)
                    return Result(False, reason or f"{arch}: QEMU exited unexpectedly")
    finally:
        selector.close()
        if child is not None:
            _terminate_group(child)
        os.close(master)
        if slave >= 0:
            os.close(slave)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("arch", choices=("arm64", "riscv64"))
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[2]
    log = root / "out" / f"smos-boot-{args.arch}" / "logs" / "serial.log"
    runner = root / "tools" / "smos-boot" / "run-qemu.sh"
    result = run_session(args.arch, [str(runner), args.arch], log, args.timeout)
    if result.ok:
        print(f"VERIFY:{args.arch.upper()}:PASS")
        return 0
    print(f"VERIFY:{args.arch.upper()}:FAIL:{result.reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
