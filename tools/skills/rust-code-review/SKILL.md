---
name: rust-code-review
description: Review Rust changes in SMOS/Fuchsia-style source trees. Use for every Rust code-review task, especially changes to Rust sources, Rust GN targets, unit tests, FIDL components, unsafe code, async code, logging, or external crates.
---

# Rust code review

Review the changed code and its full local context. Focus on correctness,
resource ownership, Fuchsia target behavior, and the approved change scope.
Produce review artifacts in English.

## Required reading

Before reviewing any Rust change, read these in-tree references:

- [`platform/coding/rust/README.md`](../../../platform/coding/rust/README.md)
- [`platform/coding/rust/testing.md`](../../../platform/coding/rust/testing.md)
- [`platform/coding/rust/unsafe.md`](../../../platform/coding/rust/unsafe.md)
- [`platform/coding/rust/logging.md`](../../../platform/coding/rust/logging.md)

When a change adds, updates, vendors, or directly promotes an external crate,
also read and apply:

- [`platform/coding/rust/external_crates.md`](../../../platform/coding/rust/external_crates.md)
- [`platform/coding/rust/external_crates/review.md`](../../../platform/coding/rust/external_crates/review.md)

## Review workflow

1. Read the approved requirement and design, then inspect the complete diff and
   the full changed files. Trace affected call sites, capability boundaries, and
   error paths far enough to establish the changed invariant.
2. Inspect the relevant GN targets. Rust targets are built through GN, not
   Cargo. Check the selected `rustc_library`, `rustc_binary`, `rustc_test`, or
   `rustc_macro` template, dependencies, target placement, and packaging.
   Confirm `with_unit_tests = true` when unit tests are expected for a binary
   or library.
3. Review ownership and failure behavior. Confirm values, handles, files, and
   tasks have an unambiguous owner and cleanup path. Require a justified,
   locally provable invariant for production `unwrap`, `expect`, `panic!`, or
   unchecked conversion; otherwise require error propagation or handling.
4. Review concurrency and target I/O. Check that locks, borrows, or resources
   are not held across `.await`; identify blocking operations in async or
   component paths; and confirm cancellation and peer-closure behavior. For
   component logs, prefer the `log` crate. Treat `stdout` and `stderr` as
   explicit runtime interfaces whose availability and blocking behavior must be
   appropriate for the target.
5. Review every added or changed `unsafe` block, unsafe function, unsafe trait
   implementation, raw-pointer field, or `UnsafeCell`. Require a concise
   English safety comment that names the invariants, proves they hold, and
   keeps unsafety behind the smallest safe abstraction. Escalate atomics,
   concurrency, cryptography, protocol parsing, and security-critical code
   when the needed domain expertise is unavailable.
6. Review tests for meaningful semantic coverage of the changed behavior and
   failure paths. Use `#[fuchsia::test]` for Fuchsia-specific async or logging
   needs; `#[test]` remains appropriate for portable code. Confirm the planned
   validation includes rustfmt and a warnings-as-errors GN build where those
   checks are available.

## Report

Write an English Markdown review artifact; do not place the full review only in
the conversation. Include:

- scope and references reviewed;
- findings ordered by severity, each with a file and line reference;
- resolutions or accepted residual risks;
- exact static checks performed and checks deferred to verification.

State explicitly when no blocking findings exist. Do not treat passing tests or
the borrow checker as evidence that semantic, async, capability, or unsafe
invariants have been fully reviewed.
