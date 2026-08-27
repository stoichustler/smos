#!/bin/bash

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

smos_stage() {
  printf '[smos] %s\n' "$*"
}

repo_root() {
  git rev-parse --show-toplevel
}

require_arch() {
  case "$1" in
    arm64 | riscv64) ;;
    *)
      printf 'unsupported architecture: %s\n' "$1" >&2
      return 2
      ;;
  esac
}

resolve_tool() {
  local root="$1"
  local name="$3"
  local candidate base external="" sdk=""
  local -a candidates=()
  local -a roots=("$root")

  if [[ -n "${SMOS_SDK_ROOT:-}" ]]; then
    sdk="$(/usr/bin/realpath -m "$SMOS_SDK_ROOT")"
  elif [[ -n "${HOME:-}" ]]; then
    sdk="$(/usr/bin/realpath -m "$HOME/clot/smos-sdk")"
  fi
  if [[ -n "$sdk" ]]; then
    roots+=("$sdk")
  fi

  if [[ -n "${SMOS_TOOLCHAIN_ROOT:-}" ]]; then
    external="$(/usr/bin/realpath -m "$SMOS_TOOLCHAIN_ROOT")"
    if [[ "$external" != "$sdk" ]]; then
      roots+=("$external")
    fi
  fi

  for base in "${roots[@]}"; do
    case "$name" in
      gn)
        candidates+=(
          "$base/prebuilt/third_party/gn/linux-x64/gn"
          "$base/buildtools/linux-x64/gn"
        )
        ;;
      ninja)
        candidates+=(
          "$base/prebuilt/third_party/ninja/linux-x64/ninja"
          "$base/prebuilt/third_party/ninja/linux-x64/bin/ninja"
          "$base/buildtools/linux-x64/ninja"
        )
        ;;
      clang | clang++ | ld.lld | llvm-ar)
        candidates+=("$base/prebuilt/third_party/clang/linux-x64/bin/$name")
        ;;
      rustc)
        candidates+=("$base/prebuilt/third_party/rust/linux-x64/bin/rustc")
        ;;
      python3)
        candidates+=(
          "$base/prebuilt/third_party/python3/linux-x64/bin/python3"
          "$base/prebuilt/third_party/python3/linux-x64/bin/python3.11"
        )
        ;;
      buildidtool)
        candidates+=("$base/prebuilt/tools/buildidtool/linux-x64/buildidtool")
        ;;
      qemu-system-aarch64)
        candidates+=(
          "$base/prebuilt/third_party/qemu/linux-x64/bin/$name"
          "$base/prebuilt/third_party/android/aemu/release/linux-x64/qemu/linux-x86_64/$name"
        )
        ;;
      qemu-system-riscv64)
        candidates+=("$base/prebuilt/third_party/qemu/linux-x64/bin/$name")
        ;;
    esac
  done

  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate" && -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  command -v "$name" 2>/dev/null
}
