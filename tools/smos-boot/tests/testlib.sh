#!/bin/bash

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

run_preflight() {
  local root="$1"
  local arch="$2"

  stdout_file="$test_tmp/stdout"
  stderr_file="$test_tmp/stderr"
  status=0
  /bin/bash "$source_root/tools/smos-boot/preflight.sh" \
    --root "$root" "$arch" >"$stdout_file" 2>"$stderr_file" || status=$?
}

install_fake_tool() {
  local name="$1"
  /usr/bin/mkdir -p "$fake_bin"
  printf '#!/bin/sh\nexit 0\n' >"$fake_bin/$name"
  /usr/bin/chmod +x "$fake_bin/$name"
}

assert_status() {
  local expected="$1"
  [[ "$status" -eq "$expected" ]] ||
    fail "expected status $expected, got $status; stderr: $(/usr/bin/cat "$stderr_file")"
}

assert_stderr_contains() {
  local expected="$1"
  /usr/bin/grep -Fq -- "$expected" "$stderr_file" ||
    fail "stderr does not contain '$expected': $(/usr/bin/cat "$stderr_file")"
}

assert_equals() {
  local expected="$1"
  local actual="$2"
  [[ "$actual" == "$expected" ]] ||
    fail "expected '$expected', got '$actual'"
}
