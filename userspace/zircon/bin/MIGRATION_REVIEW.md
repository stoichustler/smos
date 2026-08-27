# Zircon Bin Migration Code Review

## Scope

This review covers the migration of the remaining supported `zircon/bin` tools
into `userspace/zircon/bin`, the `role_manager` test support tree, and removal
of the Rust `time` and `uname` dash commands. The hardware stress tool was
omitted after validation showed that its dependency closure is outside the
compact source tree.

## Findings

No blocking C or C++ correctness findings. The migrated C/C++ sources preserve
the upstream implementation; changes are limited to source placement,
include paths, and GN dependency labels.

## Residual risks

- Some upstream test-only dependencies remain outside the compact source tree,
  including `//userspace/devices/lib/block`, `//userspace/lib/testing/predicates`, and the
  role-manager realm-proxy/test-runner infrastructure.
- The VM stress tool was removed from the compact tree after its arm64 compile exposed
  Zircon API symbols that are absent from the compact tree's headers.
- Stress tools remain outside the SMOS minimal runtime graph.
- C `time` and C `uname` now provide the package targets previously supplied by
  the Rust dash commands, preserving package names and shell command entries.

## Review disposition

Approved for build and graph verification, subject to recording any missing
test-only dependency failures with exact target labels.
