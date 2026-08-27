#!/bin/bash
set -eu

script_dir="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
source "$script_dir/lib/common.sh"

root=""
source_checkout=""
destination=""
replace=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --root)
      [[ "$#" -ge 2 ]] || die "--root requires a directory"
      root="$2"
      shift 2
      ;;
    --source-checkout)
      [[ "$#" -ge 2 ]] || die "--source-checkout requires a directory"
      source_checkout="$2"
      shift 2
      ;;
    --destination)
      [[ "$#" -ge 2 ]] || die "--destination requires a directory"
      destination="$2"
      shift 2
      ;;
    --replace)
      replace=1
      shift
      ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$root" && -n "$source_checkout" && -n "$destination" ]] ||
  die "usage: build-independent-sdk.sh --root ROOT --source-checkout CHECKOUT --destination SDK [--replace]"
[[ -d "$root" ]] || die "source root is not a directory: $root"
[[ -d "$source_checkout/prebuilt" ]] ||
  die "compatible checkout lacks prebuilt: $source_checkout/prebuilt"
command -v strace >/dev/null || die "missing: strace"

root="$(realpath "$root")"
source_checkout="$(realpath "$source_checkout")"
destination="$(realpath -m "$destination")"
[[ "$root" != "$source_checkout" ]] || die "source and compatible checkout must differ"
[[ "$destination" != "$source_checkout" ]] || die "SDK and compatible checkout must differ"

prebuilt_link="$root/prebuilt"
old_link=""
had_old_link=0
if [[ -L "$prebuilt_link" ]]; then
  had_old_link=1
  old_link="$(readlink "$prebuilt_link")"
elif [[ -e "$prebuilt_link" ]]; then
  die "refusing to replace real path: $prebuilt_link"
fi

trace_file="$(mktemp "${TMPDIR:-/tmp}/smos-sdk-trace.XXXXXX")"
cleanup() {
  rm -f "$prebuilt_link" "$trace_file"
  if [[ "$had_old_link" -eq 1 ]]; then
    ln -s "$old_link" "$prebuilt_link"
  fi
}
trap cleanup EXIT

if [[ "$had_old_link" -eq 1 ]]; then
  rm "$prebuilt_link"
fi
ln -s "$source_checkout/prebuilt" "$prebuilt_link"
export SMOS_TOOLCHAIN_ROOT="$source_checkout"

strace -f -yy -s 4096 -e trace=%file -o "$trace_file" -- \
  /bin/bash -c '
    set -e
    root="$1"
    rm -rf "$root/out/smos-boot-arm64" "$root/out/smos-boot-riscv64"
    "$root/tools/smos-boot/configure.sh" arm64
    "$root/tools/smos-boot/configure.sh" riscv64
    "$root/tools/smos-boot/build.sh" all
    "$root/tools/smos-boot/verify.sh" all
  ' smos-sdk-build "$root"

extract_args=(
  extract
  --source-root "$root"
  --source-prebuilt "$source_checkout/prebuilt"
  --destination "$destination"
  --trace "$trace_file"
  --architecture arm64
  --architecture riscv64
)
if [[ "$replace" -eq 1 ]]; then
  extract_args+=(--replace)
fi
python3 "$script_dir/independent_sdk.py" "${extract_args[@]}"
python3 "$script_dir/independent_sdk.py" validate \
  --sdk "$destination" --architecture arm64 --architecture riscv64
