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
/usr/bin/mkdir -p "$fake_root/tools" "$fake_bin"
/usr/bin/cp -a "$source_root/tools/smos-boot" "$fake_root/tools/"

for tool in gn clang clang++ ld.lld llvm-ar rustc buildidtool \
  qemu-system-aarch64 qemu-system-riscv64; do
  cat >"$fake_bin/$tool" <<'EOF'
#!/bin/sh
exit 0
EOF
  /usr/bin/chmod +x "$fake_bin/$tool"
done

/usr/bin/rm -f "$fake_bin/gn"
cat >"$fake_bin/gn" <<'EOF'
#!/bin/bash
if [[ "$1" == "desc" && "$4" == "outputs" ]]; then
  out="$2"
  out_rel="$(realpath --relative-to="$PWD" "$out")"
  case "$3" in
    *copy_zbi)
      mkdir -p "$out"
      : >"$out/smos.zbi"
      printf '//%s/smos.zbi\n' "$out_rel"
      ;;
    *product_assembler)
      printf '//%s/obj/release/images/fuchsia/fuchsia/image_assembly.json\n' "$out_rel"
      ;;
  esac
fi
EOF
/usr/bin/chmod +x "$fake_bin/gn"

cat >"$fake_bin/ninja" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >>"$FAKE_NINJA_LOG"
arch=arm64
out=out/smos-boot-arm64
for ((i = 1; i <= $#; ++i)); do
  if [[ "${!i}" == "-C" ]]; then
    next=$((i + 1))
    out="${!next}"
  fi
done
if [[ "$out" == *riscv64 ]]; then
  arch=riscv64
fi
if [[ "$*" == *" -t commands "* ]]; then
  printf 'compile core.cc\nlink compact-image\n'
  exit 0
fi
  mkdir -p "$out/kernel.phys_$arch" \
  "$out/obj/release/images/fuchsia/fuchsia"
: >"$out/kernel.phys_$arch/linux-$arch-boot-shim.bin"
cat >"$out/obj/release/images/fuchsia/fuchsia/image_assembly.json" <<JSON
{"qemu_kernel":"kernel.phys_$arch/linux-$arch-boot-shim.bin"}
JSON
printf '[1/2] compile core\n[2/2] assemble image\n'
EOF
/usr/bin/chmod +x "$fake_bin/ninja"

PATH="$fake_bin:/usr/bin:/bin"
export PATH
export FAKE_NINJA_LOG="$test_tmp/ninja.log"

for arch in arm64 riscv64; do
  /usr/bin/mkdir -p "$fake_root/out/smos-boot-$arch"
  : >"$fake_root/out/smos-boot-$arch/build.ninja"
done

run_build() {
  local arch="$1"
  stdout_file="$test_tmp/stdout"
  stderr_file="$test_tmp/stderr"
  status=0
  (
    cd "$fake_root"
    /bin/bash tools/smos-boot/build.sh "$arch"
  ) >"$stdout_file" 2>"$stderr_file" || status=$?
}

assert_log_line() {
  local expected="$1"
  /usr/bin/grep -Fxq -- "$expected" "$FAKE_NINJA_LOG" ||
    fail "Ninja log does not contain '$expected': $(cat "$FAKE_NINJA_LOG")"
}

run_build arm64
assert_status 0
assert_log_line '-C out/smos-boot-arm64 -k 0 release/images/fuchsia:fuchsia_assembly kernel.phys_arm64/linux-arm64-boot-shim.bin userspace/smos_boot/virtcheck:virtcheck_test'
/usr/bin/grep -Fq 'QEMU_KERNEL=' "$fake_root/out/smos-boot-arm64/artifacts.env" ||
  fail 'arm64 artifacts.env lacks QEMU_KERNEL'
/usr/bin/grep -Fq "$fake_root/out/smos-boot-arm64/smos.zbi" \
  "$fake_root/out/smos-boot-arm64/artifacts.env" ||
  fail 'arm64 artifacts.env did not use the GN-described ZBI'
/usr/bin/grep -Fxq 'NINJA_ACTIONS=2' \
  "$fake_root/out/smos-boot-arm64/build-metrics.env" ||
  fail 'arm64 action count was not recorded'
/usr/bin/grep -Fq '[smos] BLD: arm64 declared Ninja actions: 2' "$stdout_file" ||
  fail 'arm64 action count stage was not formatted'

: >"$FAKE_NINJA_LOG"
run_build riscv64
assert_status 0
assert_log_line '-C out/smos-boot-riscv64 -k 0 release/images/fuchsia:fuchsia_assembly kernel.phys_riscv64/linux-riscv64-boot-shim.bin userspace/smos_boot/virtcheck:virtcheck_test'

printf 'PASS: build_test\n'
