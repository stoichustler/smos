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
mkdir -p "$fake_root/tools" "$fake_root/zircon/scripts" "$fake_bin"
cp -a "$source_root/tools/smos-boot" "$fake_root/tools/"

for tool in gn ninja clang clang++ ld.lld llvm-ar rustc buildidtool \
  qemu-system-aarch64 qemu-system-riscv64; do
  printf '#!/bin/sh\nexit 0\n' >"$fake_bin/$tool"
  chmod +x "$fake_bin/$tool"
done

cat >"$fake_root/zircon/scripts/run-zircon" <<'EOF'
#!/bin/bash
printf '%s\0' "$@" >"$RUN_ZIRCON_LOG"
EOF
chmod +x "$fake_root/zircon/scripts/run-zircon"

PATH="$fake_bin:/usr/bin:/bin"
export PATH RUN_ZIRCON_LOG="$test_tmp/args"

for arch in arm64 riscv64; do
  out="$fake_root/out/smos-boot-$arch"
  mkdir -p "$out"
  : >"$out/kernel.bin"
  : >"$out/image.zbi"
  cat >"$out/artifacts.env" <<EOF
QEMU_KERNEL=$out/kernel.bin
ZBI=$out/image.zbi
EOF

  run_output="$(cd "$fake_root" && tools/smos-boot/run-qemu.sh "$arch" -- -d guest_errors)"
  [[ "$run_output" == *"[smos] RUN: validate invocation (ARCH:$arch)"* ]] ||
    fail "$arch run script did not print invocation stage"
  [[ "$run_output" == *"[smos] RUN: validate host tools (ARCH:$arch)"* ]] ||
    fail "$arch run script did not print host-tools stage"
  [[ "$run_output" == *"[smos] RUN: load artifacts (ARCH:$arch"* ]] ||
    fail "$arch run script did not print artifacts stage"
  [[ "$run_output" == *"[smos] RUN: launch QEMU (ARCH:$arch)"* ]] ||
    fail "$arch run script did not print launch stage"
  mapfile -d '' -t args <"$RUN_ZIRCON_LOG"
  expected=(
    -a "$arch" -t "$out/kernel.bin" -z "$out/image.zbi"
    -m 2048 -s 8 --no-kvm --no-virtio
  )
  if [[ "$arch" == arm64 ]]; then
    expected+=( --gic=3 )
  fi
  expected+=( -q "$fake_bin" -- )
  expected+=( -d guest_errors )
  [[ "${args[*]}" == "${expected[*]}" ]] ||
    fail "$arch runner args differ: ${args[*]}"
done

runner_dry_run="$($source_root/zircon/scripts/run-zircon \
  -a arm64 \
  -t "$fake_root/out/smos-boot-arm64/kernel.bin" \
  -z "$fake_root/out/smos-boot-arm64/image.zbi" \
  --no-kvm \
  --no-virtio \
  --gic=3 \
  --dry-run \
  -q "$fake_bin")"
[[ "$runner_dry_run" == *'-machine virt,highmem-ecam=off,gic-version=3'* ]] ||
  fail "ARM64 runner does not use low-ECAM virt with GICv3: $runner_dry_run"
[[ "$runner_dry_run" != *'virt-2.12'* ]] ||
  fail "ARM64 runner still uses deprecated virt-2.12: $runner_dry_run"
[[ "$runner_dry_run" != *'virtio-rng-pci'* ]] ||
  fail "--no-virtio still creates a host virtio RNG device: $runner_dry_run"

printf 'PASS: run_qemu_test\n'
