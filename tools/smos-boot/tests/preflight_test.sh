#!/bin/bash
set -u

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$source_root/tools/smos-boot/tests/testlib.sh"

test_tmp="$(mktemp -d)"
trap '/usr/bin/rm -rf "$test_tmp"' EXIT
HOME="$test_tmp/home"
export HOME
fake_root="$test_tmp/root"
fake_bin="$test_tmp/bin"
/usr/bin/mkdir -p "$fake_root" "$fake_bin"
PATH="$fake_bin"
export PATH

# Python is a baseline prerequisite so the first case can focus on reporting
# every missing build and architecture tool in one pass.
install_fake_tool python3

run_preflight "$fake_root" arm64
assert_status 1
assert_stderr_contains "missing: clang"
assert_stderr_contains "missing: clang++"
assert_stderr_contains "missing: ld.lld"
assert_stderr_contains "missing: llvm-ar"
assert_stderr_contains "missing: rustc"
assert_stderr_contains "missing: buildidtool"
assert_stderr_contains "missing: gn"
assert_stderr_contains "missing: ninja"
assert_stderr_contains "missing: qemu-system-aarch64"

install_fake_tool clang
install_fake_tool clang++
install_fake_tool ld.lld
install_fake_tool llvm-ar
install_fake_tool rustc
install_fake_tool buildidtool
install_fake_tool gn
install_fake_tool ninja
install_fake_tool qemu-system-aarch64
run_preflight "$fake_root" arm64
assert_status 0

run_preflight "$fake_root" x64
assert_status 2
assert_stderr_contains "unsupported architecture: x64"

# Image assembly tools are produced by this checkout's Ninja graph and are not
# external preconditions.
/usr/bin/mkdir -p "$fake_root/out/smos-boot-arm64"
printf 'build host-tools/ffx-assembly: host_tool\n' \
  >"$fake_root/out/smos-boot-arm64/build.ninja"
run_preflight "$fake_root" arm64
assert_status 0

# Repository prebuilts are selected before identically named PATH tools.
/usr/bin/mkdir -p "$fake_root/prebuilt/third_party/clang/linux-x64/bin"
/usr/bin/cp "$fake_bin/clang" \
  "$fake_root/prebuilt/third_party/clang/linux-x64/bin/clang"
source "$source_root/tools/smos-boot/lib/common.sh"
resolved="$(resolve_tool "$fake_root" arm64 clang)"
assert_equals \
  "$fake_root/prebuilt/third_party/clang/linux-x64/bin/clang" "$resolved"

# An explicitly configured standalone SDK is preferred over the compatibility
# toolchain root and PATH.
fake_sdk="$test_tmp/sdk"
/usr/bin/mkdir -p "$fake_sdk/prebuilt/third_party/clang/linux-x64/bin"
/usr/bin/cp "$fake_bin/clang" \
  "$fake_sdk/prebuilt/third_party/clang/linux-x64/bin/clang"
SMOS_SDK_ROOT="$fake_sdk"
export SMOS_SDK_ROOT
resolved="$(resolve_tool "$test_tmp/empty-root" arm64 clang)"
assert_equals \
  "$fake_sdk/prebuilt/third_party/clang/linux-x64/bin/clang" "$resolved"

printf 'PASS: preflight_test\n'
