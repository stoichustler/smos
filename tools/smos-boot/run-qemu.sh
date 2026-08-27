#!/bin/bash
set -eu

script_dir="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
source "$script_dir/lib/common.sh"
root="$(cd "$script_dir/../.." && pwd)"

[[ "$#" -ge 1 ]] || die "usage: run-qemu.sh ARCH [-- QEMU_ARGS...]"
arch="$1"
shift
require_arch "$arch" || exit $?
out_name="smos-boot-$arch"
smos_stage "RUN: validate invocation (ARCH:$arch)"

if [[ "$#" -gt 0 ]]; then
  [[ "$1" == "--" ]] || die "QEMU arguments must follow --"
  shift
fi

smos_stage "RUN: validate host tools (ARCH:$arch)"
"$script_dir/preflight.sh" --root "$root" "$arch"
artifacts="$root/out/$out_name/artifacts.env"
[[ -f "$artifacts" ]] || die "missing artifacts: $artifacts (run build.sh $arch)"
smos_stage "RUN: load artifacts (ARCH:$arch, FILE:$artifacts)"
unset QEMU_KERNEL ZBI
source "$artifacts"
: "${QEMU_KERNEL:?missing QEMU_KERNEL in $artifacts}"
: "${ZBI:?missing ZBI in $artifacts}"

canonical_in_tree() {
  local path
  path="$(realpath "$1")" || die "invalid artifact path: $1"
  case "$path" in
    "$root"/*) printf '%s\n' "$path" ;;
    *) die "artifact is outside source tree: $path" ;;
  esac
}

QEMU_KERNEL="$(canonical_in_tree "$QEMU_KERNEL")"
ZBI="$(canonical_in_tree "$ZBI")"
[[ -f "$QEMU_KERNEL" ]] || die "missing QEMU kernel: $QEMU_KERNEL"
[[ -f "$ZBI" ]] || die "missing ZBI: $ZBI"

case "$arch" in
  arm64) qemu_name="qemu-system-aarch64" ;;
  riscv64) qemu_name="qemu-system-riscv64" ;;
esac
qemu_bin="$(resolve_tool "$root" "$arch" "$qemu_name")" ||
  die "missing: $qemu_name"
qemu_dir="$(dirname "$qemu_bin")"
runner="${SMOS_RUN_ZIRCON:-$root/zircon/scripts/run-zircon}"
[[ -x "$runner" ]] || die "missing executable runner: $runner"
runner_arch_args=()
if [[ "$arch" == "arm64" ]]; then
  runner_arch_args=( --gic=3 )
fi

smos_stage "RUN: launch QEMU (ARCH:$arch)"
exec "$runner" \
  -a "$arch" \
  -t "$QEMU_KERNEL" \
  -z "$ZBI" \
  -m 2048 \
  -s 8 \
  --no-kvm \
  --no-virtio \
  "${runner_arch_args[@]}" \
  -q "$qemu_dir" \
  -- "$@"
