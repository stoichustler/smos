#!/bin/bash
set -u

script_dir="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
source "$script_dir/lib/common.sh"

root=""
if [[ "${1:-}" == "--root" ]]; then
  [[ -n "${2:-}" ]] || die "--root requires a directory"
  root="$2"
  shift 2
fi

[[ "$#" -eq 1 ]] || die "usage: preflight.sh --root DIR ARCH"
arch="$1"
require_arch "$arch" || exit $?
[[ -d "$root" ]] || die "repository root is not a directory: $root"

qemu="qemu-system-aarch64"
if [[ "$arch" == "riscv64" ]]; then
  qemu="qemu-system-riscv64"
fi

# zbi, fvm, and ffx-assembly are generated host tools in this checkout.  Their
# availability is validated by Ninja's build graph rather than as an external
# precondition.
tools=(gn ninja clang clang++ ld.lld llvm-ar rustc python3 buildidtool "$qemu")

missing=0
for tool in "${tools[@]}"; do
  if ! resolve_tool "$root" "$arch" "$tool" >/dev/null; then
    printf 'missing: %s\n' "$tool" >&2
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  printf 'hint: activate the SDK with prepare-external-tools.sh --root %s --sdk %s\n' \
    "$root" "${SMOS_SDK_ROOT:-${HOME:-~}/clot/smos-sdk}" >&2
fi

exit "$missing"
