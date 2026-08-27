#!/bin/bash
set -u

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$source_root/tools/smos-boot/tests/testlib.sh"

test_tmp="$(mktemp -d)"
trap '/usr/bin/rm -rf "$test_tmp"' EXIT
HOME="$test_tmp/home"
export HOME
unset SMOS_SDK_ROOT SMOS_TOOLCHAIN_ROOT
fake_root="$test_tmp/root"
fake_bin="$test_tmp/bin"
/usr/bin/mkdir -p "$fake_root/tools" "$fake_bin"
/usr/bin/cp -a "$source_root/tools/smos-boot" "$fake_root/tools/"

cat >"$fake_root/tools/smos-boot/prepare-external-tools.sh" <<'EOF'
#!/bin/bash
printf 'prepare-external-tools.sh must not be invoked\n' >"$FAKE_PREPARE_ARGS"
exit 99
EOF
/usr/bin/chmod +x "$fake_root/tools/smos-boot/prepare-external-tools.sh"

cat >"$fake_bin/gn" <<'EOF'
#!/bin/bash
printf '%s\n' "$@" >"$FAKE_GN_ARGS"
exit 0
EOF
/usr/bin/chmod +x "$fake_bin/gn"
PATH="$fake_bin:/usr/bin:/bin"
export PATH
export FAKE_GN_ARGS="$test_tmp/gn.args"
export FAKE_PREPARE_ARGS="$test_tmp/prepare.args"

assert_file_contains() {
  local file="$1"
  local expected="$2"
  /usr/bin/grep -Fq -- "$expected" "$file" ||
    fail "$file does not contain '$expected'"
}

assert_not_file_contains() {
  local file="$1"
  local unexpected="$2"
  if /usr/bin/grep -Fq -- "$unexpected" "$file"; then
    fail "$file unexpectedly contains '$unexpected'"
  fi
}

configure() {
  local arch="$1"
  stdout_file="$test_tmp/stdout"
  stderr_file="$test_tmp/stderr"
  status=0
  (
    cd "$fake_root"
    /bin/bash tools/smos-boot/configure.sh "$arch"
  ) >"$stdout_file" 2>"$stderr_file" || status=$?
}

configure arm64
assert_status 1
assert_stderr_contains 'SMOS_SDK_ROOT'

SMOS_SDK_ROOT="$test_tmp/missing-sdk"
export SMOS_SDK_ROOT
configure arm64
assert_status 1
assert_stderr_contains 'SDK root is not a directory'

invalid_sdk="$test_tmp/invalid-sdk"
/usr/bin/mkdir -p "$invalid_sdk/prebuilt"
SMOS_SDK_ROOT="$invalid_sdk"
export SMOS_SDK_ROOT
configure arm64
assert_status 1
assert_stderr_contains 'SDK manifest is missing'

fake_sdk="$test_tmp/standalone sdk \"quoted\"\\root \$literal"
/usr/bin/mkdir -p "$fake_sdk/prebuilt"
PYTHONPATH="$fake_root/tools/smos-boot" python3 - "$fake_sdk" <<'PY'
import pathlib
import sys
import independent_sdk
independent_sdk.write_manifest(pathlib.Path(sys.argv[1]), ("arm64", "riscv64"))
PY
SMOS_SDK_ROOT="$fake_sdk"
export SMOS_SDK_ROOT

configure arm64
assert_status 0
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" \
  'smos_sdk_milestone = "27"'
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" \
  'import("//platform/boards/smos-qemu-arm64.gni")'
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" \
  'import("//platform/products/smos_boot.gni")'
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" \
  'smos_boot_build = true'
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" \
  'compilation_mode = "debug"'
assert_not_file_contains "$fake_root/out/smos-boot-arm64/args.gn" \
  'is_debug = true'
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" \
  'rbe_mode = "off"'
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" \
  '//userspace/smos_boot/virtcheck:virtcheck_test'
escaped_sdk="${fake_sdk//\\/\\\\}"
escaped_sdk="${escaped_sdk//\"/\\\"}"
escaped_sdk="${escaped_sdk//\$/\\\$}"
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" \
  "smos_sdk_root = \"$escaped_sdk\""
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" '\"quoted\"'
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" '\$literal'
assert_file_contains "$FAKE_GN_ARGS" 'gen'
assert_file_contains "$FAKE_GN_ARGS" '--fail-on-unused-args'
[[ ! -e "$fake_root/prebuilt" && ! -L "$fake_root/prebuilt" ]] ||
  fail 'configure created a source prebuilt entry'
[[ ! -e "$FAKE_PREPARE_ARGS" ]] ||
  fail 'configure invoked prepare-external-tools.sh'

MILESTONE_SDK=28
export MILESTONE_SDK
configure arm64
assert_status 0
assert_file_contains "$fake_root/out/smos-boot-arm64/args.gn" \
  'smos_sdk_milestone = "28"'

MILESTONE_SDK=invalid
export MILESTONE_SDK
configure arm64
assert_status 1
assert_stderr_contains 'MILESTONE_SDK must be a non-negative integer'
unset MILESTONE_SDK

configure riscv64
assert_status 0
assert_file_contains "$fake_root/out/smos-boot-riscv64/args.gn" \
  'import("//platform/boards/smos-qemu-riscv64.gni")'
assert_not_file_contains "$fake_root/out/smos-boot-riscv64/args.gn" \
  'smos-qemu-arm64.gni'

configure x64
assert_status 2

/usr/bin/mkdir "$fake_root/prebuilt"
configure arm64
assert_status 1
assert_stderr_contains 'source root must not contain prebuilt'

printf 'PASS: configure_test\n'
