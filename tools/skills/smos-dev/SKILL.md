---
name: smos-dev
description: "Default mandatory SMOS development workflow based on a gated V-model lifecycle: requirement analysis, architecture design, environment setup, implementation, test and verification, optimization and iteration, and release and maintenance."
---

# SMOS Development

Use this skill for any change under the SMOS checkout, especially changes to
`zircon/`, `userspace/`, `sdk/`, `platform/products/`, `platform/bundles/`, build scripts, boot images,
components, or user-space drivers. Read [SMOS.md](../../../sdk/smos/SMOS.md) when the task
touches product scope, runtime architecture, SDK packaging, or supported
architectures.

## Documentation language

English is the first and default language for SMOS documentation, design
notes, code-path explanations, and validation reports. Preserve code symbols,
file paths, command names, and protocol identifiers exactly as written. Use
another language only when the requester explicitly asks for it or when a
quoted source requires it.

## Markdown diagram convention

Use [Workflow.md](../../../sdk/smos/Workflow.md) as the canonical source for
SMOS workflow and framework diagrams. Prefer its Unicode box-drawing style and
copy one of its templates before inventing a new layout. For execution-order
diagrams, use the [Code flow](../../../sdk/smos/Workflow.md#code-flow) section
to trace the detailed call chain in its linear, branch, loop, parallel, or
asynchronous template.

| Pattern | Meaning |
| --- | --- |
| `┌─┐` / `└─┘` | Step, component, service, or logical boundary |
| `╭─╮` / `╰─╯` | Rounded container or externally visible stage |
| `▼` `▲` `►` `◄` | Control, data, or lifecycle direction |
| `─┬─` / `─┴─` | Parallel split or merge |
| `──┤` / `├──` | Branch point or crossed boundary |
| `╰─▶` / `◀─╮` | Return, feedback, or cross-level relationship |

Choose `Code flow` for execution order and `Framework` for ownership,
layering, capability boundaries, or peer components. Use `Sequence Diagram` for
message order between peers. Put diagrams in fenced `text` blocks and preserve
whitespace. Code flows are detailed call-chain traces: use plain-text nodes,
indentation, `│`, `├──►`, `╰──►`, and `◄──`; do not use graph boxes in Code flow.
Label conditions, returns, retry bounds, events, and terminal outcomes. Keep
all diagrams within 88 columns. If a renderer cannot preserve Unicode
connectors, provide an ASCII equivalent with the same topology and labels.
Explain any deliberate deviation from `Workflow.md` next to the diagram.

## Required V-model lifecycle

Every development task follows the lifecycle below. Do not silently skip a
phase. Record the phase status, evidence, decisions, and unverified paths in
the work update or completion report.

Each phase is a gate: present its outputs for human review and wait for
explicit approval before starting the next phase. Approval for one phase does
not authorize later phases. If new evidence changes the scope, stop and return
to the affected phase for review.

## Commit authorization

Code must not be submitted without explicit human authorization. This is a
separate gate from requirement, design, implementation, code-review, and
verification approval.

- Do not run `git commit`, `git commit --amend`, `git push`, or create/update a
  change for review unless the requester explicitly authorizes that submission
  in the current task.
- Before requesting submission authorization, report the final file list,
  intended commit message, review status, verification results, and known
  limitations. Wait for an unambiguous approval such as `批准提交`.
- Approval to implement, review, build, or verify is not approval to commit.
  If the requester says only `批准`, ask which gate or action is approved when
  the context does not make submission authorization explicit.
- Inspect both `git diff` and `git diff --cached` immediately before a commit.
  Never include pre-existing or unrelated staged changes; unstage them or stop
  and report the conflict for human direction.
- If submission is not authorized, leave the working tree uncommitted and
  provide reproducible validation results instead.

### 1. Requirement analysis

- Identify requested behavior, affected architectures, acceptance criteria,
  constraints, risks, and likely files.
- Resolve ambiguity from repository evidence before proposing an edit.
- Define the system-level acceptance tests that will be used on the right side
  of the V-model.
- Output: a scoped requirement record and acceptance criteria.
- Gate: obtain human approval of the requirement record.

### 2. Architecture design

- Inspect product graphs, component manifests, driver bind rules, build
  targets, interfaces, and nearby tests.
- Select the smallest implementation approach and document data flow,
  ownership boundaries, compatibility impact, and failure handling.
- Map design decisions to integration and system tests. For boot or driver
  work, describe the path from boot-shim through component manager and driver
  framework.
- Output: an implementation design, test strategy, and risk list.
- Gate: obtain human approval of the design.

### 3. Environment setup

- Verify repository state, required SDK/toolchain paths, host tools, target
  architectures, generated-file policy, and any required caches or services.
- Prefer reproducible commands and record versions, environment variables, and
  output directories.
- Do not modify source files as part of setup unless that change is separately
  proposed and approved.
- Output: a reproducible environment checklist and setup evidence.
- Gate: obtain human approval that the environment is ready.

### 4. Implementation

- Make the scoped change using repository conventions and preserve unrelated
  working-tree changes.
- Prefer Rust for new functionality unless module conventions, ABI, or
  platform constraints require another language.
- Update tests, documentation, manifests, and build contracts when behavior
  or interfaces change.
- Output: source changes and focused automated checks.
- Gate: obtain human approval to enter code review.

### Code review gate

- Review the implementation against the approved requirements, architecture,
  repository conventions, security boundaries, and test strategy.
- For C++ changes, use
  [`tools/skills/cpp-code-review/SKILL.md`](../cpp-code-review/SKILL.md) and
  report findings before proceeding.
- For Rust changes, use
  [`tools/skills/rust-code-review/SKILL.md`](../rust-code-review/SKILL.md) and
  report findings before proceeding.
- Resolve blocking findings and record accepted residual risks.
- Output: review findings, resolutions, and approval to validate.
- Gate: obtain human approval before starting Test and verification.

### 5. Test and verification

- Run the narrowest checks that prove the change, then expand for cross-layer
  risk. Include static, unit, build, integration, and runtime checks as
  applicable.
- For runtime checks, explicitly confirm whether manual QEMU, console, boot,
  or device validation is authorized.
- Report exact commands, target architecture, results, and unverified paths.
- Output: reproducible verification evidence and a pass/fail disposition.
- Gate: obtain human approval of the verification results.

### 6. Optimization and iteration

- Use measured failures, performance data, size data, or review findings to
  identify the smallest corrective iteration.
- Return to the relevant earlier phase when requirements, architecture,
  environment, or implementation assumptions change; repeat its approval gate.
- Do not apply speculative refactors without evidence and an approved scope.
- Output: iteration record, comparison evidence, and updated risks.
- Gate: obtain human approval to finalize or start another iteration.

### 7. Release and maintenance

- Validate release artifacts, manifests, symbols, licenses, generated files,
  changelog entries, and supported-architecture coverage.
- Record known limitations, rollback or recovery steps, ownership, and follow-up
  maintenance work.
- Preserve the evidence needed to reproduce the release and its verification.
- Output: release checklist, maintenance notes, and final report.
- Gate: obtain explicit approval before release or handoff.

## V-model verification mapping

The left side defines the right-side evidence before implementation begins:

| Definition phase | Verification counterpart |
| --- | --- |
| Requirement analysis | System acceptance and user-workflow tests |
| Architecture design | Integration, interface, and component-boundary tests |
| Environment setup | Toolchain, reproducibility, and build preflight checks |
| Implementation | Unit tests, static analysis, and compile checks |
| Test and verification | Target-architecture, runtime, and regression validation |

Optimization and iteration must cite the failed or improved counterpart test;
release and maintenance must preserve the full traceability record.

## Mandatory SMOS constraints

- Any new code under `zircon/` must be controlled by the `SMOS_HYPER`
  compile-time switch. The default/non-Hyper build must retain the original
  Zircon logic and behavior; do not rewrite, reorder, or otherwise alter the
  unguarded upstream path.
- Any new Rust or C++ code comment must use this header format, including the
  topic and date:

  ```text
  [smos] (20260822) <Topic>

  Note: The description must be written in English. It may include ASCII
  flowcharts, sequence diagrams, or framework diagrams with explanatory text.
  ```

  Keep the description focused on the SMOS-specific behavior or constraint.
  Add an ASCII framework, flow, or sequence diagram when it makes a complex
  control path, ownership boundary, or state transition easier to review.
  Keep one reading direction, use aligned nodes and explicit arrows, and label
  branches or protocol crossings when their meaning is not obvious. Keep the
  diagram at 88 columns or less and follow it with concise English prose. Do
  not rely on color, font, or renderer-specific features, and do not use a
  diagram to replace required invariants or error-handling details.
  Existing upstream comments do not need to be rewritten unless the change
  modifies their surrounding logic.

## SMOS-specific checks

- Preserve the compact product boundary. Do not add graphics/UI, conventional
  networking, WLAN, Bluetooth, audio, camera, update, or recovery services
  without an explicit scope change.
- For boot changes, check both `arm64` and `riscv64` unless the requirement is
  architecture-specific. Confirm boot-shim inputs, ZBI items, cmdline, UART,
  and hand-off behavior.
- For driver changes, trace the complete path: board/device discovery,
  `driver_index` bind match, `driver_manager` launch, isolated `driver-host`,
  protocol or devfs publication, and client access.
- For component changes, inspect the relevant `.cml` offers/exposes, package
  contents, startup mode, capability policy, and product assembly graph.
- For dash or shell-command changes, distinguish dash builtins from `/boot/bin`
  or package-provided commands and verify the command in the target image.
- For Zircon changes, inspect the preprocessed Hyper and non-Hyper paths and
  confirm that every newly added branch, declaration, source file, and comment
  follows the constraints above.

## Validation guidance

Use the narrowest checks that prove the change, then expand for cross-layer
risk. Typical checks include:

```sh
python3 -m unittest tools.smos-boot.tests.docs_test
git diff --check
tools/smos-boot/configure.sh arm64
tools/smos-boot/build.sh arm64
tools/smos-boot/verify.sh arm64
tools/smos-boot/configure.sh riscv64
tools/smos-boot/build.sh riscv64
```

For runtime changes, use `tools/smos-boot/run-qemu.sh arm64` or the
appropriate target and manually confirm the serial prompt, component startup,
driver availability, and the changed workflow. If QEMU or a full build is not
available, run static/unit/documentation checks and explicitly identify the
remaining gap.

## Completion report

The final report must include:

- requirement and scope confirmed;
- design/implementation summary;
- files changed;
- validation mode: manual, AI automated, or both;
- exact checks and results;
- known limitations or unverified architecture/runtime paths.
