#!/bin/bash
set -uo pipefail

script_dir="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
source "$script_dir/lib/common.sh"
root="$(cd "$script_dir/../.." && pwd)"

[[ "$#" -eq 1 ]] || die "usage: build.sh ARCH"
assembly_target="release/images/fuchsia:fuchsia_assembly"
assembly_name="fuchsia"

build_arch() {
  local arch="$1"
  local out_rel="out/smos-boot-$arch"
  local out_dir="$root/$out_rel"
  local boot_target="kernel.phys_$arch/linux-$arch-boot-shim.bin"
  local -a targets=(
    "$assembly_target"
    "$boot_target"
  )
  targets+=(userspace/smos_boot/virtcheck:virtcheck_test)

  smos_stage "BLD: preflight (ARCH:$arch)"
  "$script_dir/preflight.sh" --root "$root" "$arch" || return $?
  if [[ ! -f "$out_dir/build.ninja" ]]; then
    "$script_dir/configure.sh" "$arch" || return $?
  fi

  mkdir -p "$out_dir/logs"
  local ninja_bin
  ninja_bin="$(resolve_tool "$root" "$arch" ninja)" || {
    printf 'error: missing: ninja\n' >&2
    return 1
  }

  cd "$root"
  smos_stage "BLD: compile image (ARCH:$arch, TARGETS:${#targets[@]})"
  "$ninja_bin" -C "$out_rel" -k 0 \
    "${targets[@]}" 2>&1 |
    tee "$out_rel/logs/build.log"
  local ninja_status=${PIPESTATUS[0]}
  if [[ "$ninja_status" -ne 0 ]]; then
    return "$ninja_status"
  fi

  smos_stage "BLD: validate image graph (ARCH:$arch)"
  "$ninja_bin" -C "$out_rel" -t commands "${targets[@]}" \
    >"$out_dir/logs/action-commands.log" || return $?
  local action_count
  action_count="$(wc -l <"$out_dir/logs/action-commands.log")"
  printf 'NINJA_ACTIONS=%s\n' "$action_count" >"$out_dir/build-metrics.env"
  smos_stage "BLD: $arch declared Ninja actions: $action_count"

  local gn_bin python_bin
  gn_bin="$(resolve_tool "$root" "$arch" gn)" || {
    printf 'error: missing: gn\n' >&2
    return 1
  }
  python_bin="$(resolve_tool "$root" "$arch" python3)" || {
    printf 'error: missing: python3\n' >&2
    return 1
  }
  local attempt
  for attempt in 1 2 3; do
    if "$python_bin" "$script_dir/artifacts.py" \
      --source-root "$root" \
      --out-dir "$out_dir" \
      --gn "$gn_bin" \
      --assembly "$assembly_name" \
      --write "$out_dir/artifacts.env"; then
      smos_stage "BLD: complete (ARCH:$arch, ARTIFACTS:$out_dir/artifacts.env)"
      return 0
    fi
    if [[ "$attempt" -lt 3 ]]; then
      printf 'warning: GN artifact query failed; retrying (%s/3)\n' "$attempt" >&2
      sleep 1
    fi
  done
  return 1
}

case "$1" in
  arm64 | riscv64) build_arch "$1" ;;
  *)
    require_arch "$1"
    exit $?
    ;;
esac
