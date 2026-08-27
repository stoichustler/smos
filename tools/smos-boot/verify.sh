#!/bin/bash
set -eu

script_dir="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
source "$script_dir/lib/common.sh"
root="$(cd "$script_dir/../.." && pwd)"
[[ "$#" -eq 1 ]] || die "usage: verify.sh ARCH|all"

run_arch() {
  local arch="$1" python_bin
  python_bin="$(resolve_tool "$root" "$arch" python3)" || die "missing: python3"
  "$python_bin" "$script_dir/verify.py" "$arch"
}

case "$1" in
  arm64 | riscv64) run_arch "$1" ;;
  all)
    run_arch arm64
    printf '[smos] riscv64 QEMU verification is manual: run-qemu.sh riscv64\n'
    ;;
  *) require_arch "$1" ;;
esac
