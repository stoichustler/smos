# SVE-os AI workflow

## Language

Project documentation, design descriptions, code comments, review reports,
and validation reports must be written in English. Codex terminal interaction,
progress updates, and final responses remain in Chinese unless the requester
asks for another language.

## Global skills

Use [`tools/skills/smos-dev/SKILL.md`](tools/skills/smos-dev/SKILL.md) as the
global skill for every SMOS task.

For SMOS C++ code-review tasks, also use:
[`tools/skills/cpp-code-review/SKILL.md`](tools/skills/cpp-code-review/SKILL.md).

## Gated workflow

Follow this lifecycle for every development task:

    Requirement confirmation -> Solution design -> Implementation
    -> Code review -> Build verification

Each phase requires explicit human review and approval before the next phase
begins. Do not edit files, run code review, or start build validation before
the requester approves the corresponding preceding phase. C++ changes must use
the C++ review skill during the Code review phase.
