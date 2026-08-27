#!/bin/bash
set -eu

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$source_root/tools/smos-boot/tests/testlib.sh"

test_tmp="$(mktemp -d)"
trap '/usr/bin/rm -rf "$test_tmp"' EXIT
fake_root="$test_tmp/root"
fake_source="$test_tmp/source"
fake_sdk="$test_tmp/sdk"
fake_bin="$test_tmp/bin"
stdout_file="$test_tmp/stdout"
stderr_file="$test_tmp/stderr"
mkdir -p "$fake_root/tools/smos-boot" "$fake_source/prebuilt/tool" \
  "$fake_sdk" "$fake_bin"
printf old >"$fake_sdk/marker"
printf tool >"$fake_source/prebuilt/tool/compiler"
ln -s "$test_tmp/original-prebuilt" "$fake_root/prebuilt"

for command in configure.sh build.sh verify.sh; do
  cat >"$fake_root/tools/smos-boot/$command" <<'EOF'
#!/bin/bash
exit 7
EOF
  chmod +x "$fake_root/tools/smos-boot/$command"
done

cat >"$fake_bin/strace" <<'EOF'
#!/bin/bash
while [[ "$#" -gt 0 && "$1" != "--" ]]; do shift; done
[[ "$#" -gt 0 ]] && shift
exec "$@"
EOF
chmod +x "$fake_bin/strace"

status=0
PATH="$fake_bin:/usr/bin:/bin" \
  "$source_root/tools/smos-boot/build-independent-sdk.sh" \
  --root "$fake_root" --source-checkout "$fake_source" \
  --destination "$fake_sdk" --replace \
  >"$stdout_file" 2>"$stderr_file" || status=$?

assert_status 7
assert_equals "$test_tmp/original-prebuilt" "$(readlink "$fake_root/prebuilt")"
assert_equals old "$(cat "$fake_sdk/marker")"
printf 'PASS: build_independent_sdk_test\n'
