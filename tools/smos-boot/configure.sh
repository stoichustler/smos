#!/bin/bash
set -eu

script_dir="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
source "$script_dir/lib/common.sh"
root="$(cd "$script_dir/../.." && pwd)"

[[ "$#" -eq 1 ]] || die "usage: configure.sh ARCH"
arch="$1"
require_arch "$arch" || exit $?
out_name="smos-boot-$arch"
smos_stage "CFG: validate SDK (ARCH:$arch)"

milestone_sdk="${MILESTONE_SDK:-27}"
[[ "$milestone_sdk" =~ ^[0-9]+$ ]] ||
  die "MILESTONE_SDK must be a non-negative integer: $milestone_sdk"

[[ -n "${SMOS_SDK_ROOT:-}" ]] || die "SMOS_SDK_ROOT is required"
[[ -d "$SMOS_SDK_ROOT" ]] ||
  die "SDK root is not a directory: $SMOS_SDK_ROOT"
SMOS_SDK_ROOT="$(realpath "$SMOS_SDK_ROOT")"
export SMOS_SDK_ROOT
[[ "$SMOS_SDK_ROOT" != "$root" ]] || die "source and SDK roots must differ"
[[ ! -e "$root/prebuilt" && ! -L "$root/prebuilt" ]] ||
  die "source root must not contain prebuilt: $root/prebuilt"

python3 "$script_dir/independent_sdk.py" validate \
  --sdk "$SMOS_SDK_ROOT" \
  --architecture arm64 --architecture riscv64 >/dev/null
[[ -d "$SMOS_SDK_ROOT/prebuilt" ]] ||
  die "SDK lacks prebuilt payload: $SMOS_SDK_ROOT/prebuilt"

gn_escape_string() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//\$/\\\$}"
  printf '%s' "$value"
}
escaped_sdk_root="$(gn_escape_string "$SMOS_SDK_ROOT")"

case "$arch" in
  arm64) board="smos-qemu-arm64" ;;
  riscv64) board="smos-qemu-riscv64" ;;
esac

out_dir="$root/out/$out_name"
smos_stage "CFG: generate GN graph (ARCH:$arch, OUT:$out_dir)"
mkdir -p "$out_dir"
args_tmp="$(mktemp "$out_dir/.args.gn.XXXXXX")"
trap 'rm -f "$args_tmp"' EXIT
cat >"$args_tmp" <<EOF
import("//platform/boards/$board.gni")
import("//platform/products/smos_boot.gni")

smos_sdk_root = "$escaped_sdk_root"
smos_sdk_milestone = "$milestone_sdk"
smos_boot_build = true
smos_minimal_assembly = true
compilation_mode = "debug"
rbe_mode = "off"
include_clippy = false
build_only_labels = [
  "//userspace/smos_boot/mkcheck:mkcheck_test",
  "//userspace/smos_boot/virtcheck:virtcheck_test",
]
EOF
mv "$args_tmp" "$out_dir/args.gn"
trap - EXIT

gn_bin="$(resolve_tool "$root" "$arch" gn)" || die "missing: gn"
cd "$root"
"$gn_bin" gen "out/$out_name" --fail-on-unused-args
smos_stage "CFG: complete (ARCH:$arch)"
