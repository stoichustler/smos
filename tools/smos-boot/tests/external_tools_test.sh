#!/bin/bash
set -u

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$source_root/tools/smos-boot/tests/testlib.sh"

test_tmp="$(mktemp -d)"
trap '/usr/bin/rm -rf "$test_tmp"' EXIT
HOME="$test_tmp/home-isolated"
export HOME
fake_root="$test_tmp/root"
fake_external="$test_tmp/standalone sdk"
fake_bin="$test_tmp/bin"
stdout_file="$test_tmp/stdout"
stderr_file="$test_tmp/stderr"
/usr/bin/mkdir -p "$fake_root" "$fake_external" "$fake_bin"

make_external_tool() {
  local relative="$1"
  local path="$fake_external/$relative"
  /usr/bin/mkdir -p "${path%/*}"
  printf '#!/bin/sh\nexit 0\n' >"$path"
  /usr/bin/chmod +x "$path"
}

make_external_tool prebuilt/third_party/gn/linux-x64/gn
make_external_tool prebuilt/third_party/ninja/linux-x64/ninja
for tool in clang clang++ ld.lld llvm-ar; do
  make_external_tool "prebuilt/third_party/clang/linux-x64/bin/$tool"
done
make_external_tool prebuilt/third_party/rust/linux-x64/bin/rustc
make_external_tool prebuilt/third_party/python3/linux-x64/bin/python3
make_external_tool prebuilt/tools/buildidtool/linux-x64/buildidtool
make_external_tool prebuilt/third_party/qemu/linux-x64/bin/qemu-system-riscv64
make_external_tool \
  prebuilt/third_party/android/aemu/release/linux-x64/qemu/linux-x86_64/qemu-system-aarch64

PYTHONPATH="$source_root/tools/smos-boot" python3 - "$fake_external" <<'PY'
import pathlib
import sys
import independent_sdk
independent_sdk.write_manifest(pathlib.Path(sys.argv[1]), ("arm64", "riscv64"))
PY

status=0
/bin/bash "$source_root/tools/smos-boot/prepare-external-tools.sh" \
  --root "$fake_root" --sdk "$fake_external" \
  >"$stdout_file" 2>"$stderr_file" || status=$?
assert_status 0
[[ ! -e "$fake_root/prebuilt" && ! -L "$fake_root/prebuilt" ]] ||
  fail 'validation created a source prebuilt entry'
[[ ! -e "$fake_root/.cipd" && ! -L "$fake_root/.cipd" ]] ||
  fail '.cipd must not be linked'

PATH="$fake_bin:/usr/bin:/bin"
export PATH
SMOS_SDK_ROOT="$fake_external"
export SMOS_SDK_ROOT
run_preflight "$fake_root" arm64
assert_status 0
run_preflight "$fake_root" riscv64
assert_status 0

/usr/bin/rm "$fake_external/prebuilt/third_party/rust/linux-x64/bin/rustc"
/usr/bin/rm "$fake_external/prebuilt/tools/buildidtool/linux-x64/buildidtool"
run_preflight "$fake_root" arm64
assert_status 1
assert_stderr_contains 'missing: rustc'
assert_stderr_contains 'missing: buildidtool'

bad_external="$test_tmp/bad-external"
/usr/bin/mkdir -p "$bad_external/prebuilt"
status=0
/bin/bash "$source_root/tools/smos-boot/prepare-external-tools.sh" \
  --root "$test_tmp/bad-root" --sdk "$bad_external" \
  >"$stdout_file" 2>"$stderr_file" || status=$?
assert_status 1

# A failed validation does not inspect or change an existing source entry.
/usr/bin/mkdir "$fake_root/prebuilt"
printf 'sentinel\n' >"$fake_root/prebuilt/owned-by-source"
printf tampered >>"$fake_external/prebuilt/third_party/gn/linux-x64/gn"
status=0
/bin/bash "$source_root/tools/smos-boot/prepare-external-tools.sh" \
  --root "$fake_root" --sdk "$fake_external" \
  >"$stdout_file" 2>"$stderr_file" || status=$?
assert_status 1
assert_file_contains() {
  local file="$1"
  local expected="$2"
  /usr/bin/grep -Fq -- "$expected" "$file" ||
    fail "$file does not contain '$expected'"
}
assert_file_contains "$fake_root/prebuilt/owned-by-source" 'sentinel'

# Successful validation also ignores an existing source-owned prebuilt entry.
PYTHONPATH="$source_root/tools/smos-boot" python3 - \
  "$fake_external" <<'PY'
import pathlib
import sys
import independent_sdk
independent_sdk.write_manifest(pathlib.Path(sys.argv[1]), ("arm64", "riscv64"))
PY
status=0
/bin/bash "$source_root/tools/smos-boot/prepare-external-tools.sh" \
  --root "$fake_root" --sdk "$fake_external" \
  >"$stdout_file" 2>"$stderr_file" || status=$?
assert_status 0
assert_file_contains "$fake_root/prebuilt/owned-by-source" 'sentinel'

# With no --sdk argument, validation defaults to $HOME/clot/smos-sdk.
default_home="$test_tmp/home"
default_root="$test_tmp/default-root"
/usr/bin/mkdir -p "$default_home/clot" "$default_root"
/usr/bin/cp -a "$fake_external" "$default_home/clot/smos-sdk"
# Restore the copied SDK's manifest after copying the deliberately stale tree.
PYTHONPATH="$source_root/tools/smos-boot" python3 - \
  "$default_home/clot/smos-sdk" <<'PY'
import pathlib
import sys
import independent_sdk
independent_sdk.write_manifest(pathlib.Path(sys.argv[1]), ("arm64", "riscv64"))
PY
status=0
HOME="$default_home" /bin/bash \
  "$source_root/tools/smos-boot/prepare-external-tools.sh" \
  --root "$default_root" >"$stdout_file" 2>"$stderr_file" || status=$?
assert_status 0
[[ ! -e "$default_root/prebuilt" && ! -L "$default_root/prebuilt" ]] ||
  fail 'default SDK validation created a source prebuilt entry'

printf 'PASS: external_tools_test\n'
