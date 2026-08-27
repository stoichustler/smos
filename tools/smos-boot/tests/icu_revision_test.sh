#!/bin/bash
set -eu

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$source_root/tools/smos-boot/tests/testlib.sh"

test_tmp="$(mktemp -d)"
trap '/usr/bin/rm -rf "$test_tmp"' EXIT
default="$test_tmp/default"
latest="$test_tmp/latest"
stdout_file="$test_tmp/stdout"
stderr_file="$test_tmp/stderr"
mkdir -p "$default" "$latest"
printf '%s\n' d30b7b0bb3829f2e220df403ed461a1ede78b774 >"$default/git-revision"
printf '%s\n' 4239b1559d11d4fa66c100543eda4161e060311e >"$latest/git-revision"

status=0
bash "$source_root/release/icu/update-config-json.sh" \
  --icu-default-dir="$default" --icu-latest-dir="$latest" --mode=print \
  >"$stdout_file" 2>"$stderr_file" || status=$?
assert_status 0
grep -Fq '"default": "d30b7b0bb3829f2e220df403ed461a1ede78b774"' \
  "$stdout_file" || fail 'default pinned revision is absent'
grep -Fq '"latest": "4239b1559d11d4fa66c100543eda4161e060311e"' \
  "$stdout_file" || fail 'latest pinned revision is absent'

printf invalid >"$latest/git-revision"
status=0
bash "$source_root/release/icu/update-config-json.sh" \
  --icu-default-dir="$default" --icu-latest-dir="$latest" --mode=print \
  >"$stdout_file" 2>"$stderr_file" || status=$?
assert_status 1
assert_stderr_contains 'invalid ICU revision'
printf 'PASS: icu_revision_test\n'
