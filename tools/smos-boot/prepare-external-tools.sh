#!/bin/bash
set -eu

script_dir="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
source "$script_dir/lib/common.sh"

root=""
sdk=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --root)
      [[ "$#" -ge 2 ]] || die "--root requires a directory"
      root="$2"
      shift 2
      ;;
    --sdk | --external)
      [[ "$#" -ge 2 ]] || die "$1 requires a directory"
      sdk="$2"
      shift 2
      ;;
    *) die "unknown argument: $1" ;;
  esac
done

if [[ -z "$sdk" && -n "${HOME:-}" ]]; then
  sdk="$HOME/clot/smos-sdk"
fi
[[ -n "$root" && -n "$sdk" ]] ||
  die "usage: prepare-external-tools.sh --root ROOT [--sdk SDK]"
[[ -d "$root" ]] || die "source root is not a directory: $root"
[[ -d "$sdk" ]] || die "SDK root is not a directory: $sdk"

root="$(realpath "$root")"
sdk="$(realpath "$sdk")"
[[ "$root" != "$sdk" ]] || die "source and SDK roots must differ"

python3 "$script_dir/independent_sdk.py" validate --sdk "$sdk" \
  --architecture arm64 --architecture riscv64 >/dev/null
[[ -d "$sdk/prebuilt" ]] || die "SDK lacks prebuilt payload: $sdk/prebuilt"
