# Workflow

This document defines the preferred visual language for workflow and
architecture diagrams in SMOS Markdown documentation. The examples are
deliberately plain text so that they remain reviewable in a terminal, a code
review, or a rendered Markdown page without an image asset.

Use a diagram when the relationships or order of operations are easier to
understand visually than as a list. Always introduce the purpose of the
diagram in one sentence and follow it with a short explanation of the main
path and any important exception path.

## Diagram language

Put every diagram in a fenced `text` block. Keep the drawing left-aligned and
preserve its whitespace. The preferred width is 88 columns or less; shorten a
label or add a line inside a box instead of allowing a line to wrap.

Use the following shapes and connectors consistently:

| Pattern | Meaning |
| --- | --- |
| `┌─────┐` and `└─────┘` | A step, component, service, or logical boundary. |
| `╭─────╮` and `╰─────╯` | A rounded container or an externally visible stage. |
| `▼`, `▲`, `►`, `◄` | Direction of control, data, or lifecycle progression. |
| `──┤` and `├──` | A branch point or a boundary crossed by a relationship. |
| `─┬─` and `─┴─` | A split into parallel paths or a merge from parallel paths. |
| `╰─▶` and `◀─╮` | A return, feedback, or cross-level relationship. |
| `text` beside an edge | Protocol, event, capability, or condition. |

An arrow describes a relationship, not necessarily ownership. Label edges when
the distinction matters, for example `launches`, `offers`, `calls`, `owns`,
or `fails`. Use one primary direction in a diagram. A reverse arrow is for a
reply or feedback path, not for decoration.

## Code flow

Use `Code flow` for an ordered path through functions, commands, boot stages,
or request handling. The vertical path is the default because it remains easy
to scan in narrow terminals.

### Linear flow

```text
┌───────────────────────────────┐
│ Input or triggering event     │
└───────────────┬───────────────┘
                │ validates
                ▼
┌───────────────────────────────┐
│ Main operation                │
└───────────────┬───────────────┘
                │ produces result
                ▼
╭───────────────────────────────╮
│ Output or next workflow stage │
╰───────────────────────────────╯
```

Read the central vertical line as the normal execution path. Keep each box to
one responsibility and put implementation identifiers in backticks in the
surrounding prose when the diagram would become too dense.

### Branch and feedback

```text
┌───────────────────────────────┐
│ Operation                     │
└───────────────┬───────────────┘
                │ result
                ▼
        ┌───────┴───────┐
        │ condition?    │
        └───┬───────┬───┘
           yes      no
            ▼       ▼
┌────────────────┐  ┌────────────────┐
│ Continue       │  │ Recover or log │
└────────┬───────┘  └────────┬───────┘
         │                   │ retry
         │                   ╰─▶ Operation
         ▼
╭───────────────────────────────╮
│ Completed                     │
╰───────────────────────────────╯
```

Place branch labels next to the outgoing connector. Show a retry or recovery
edge only when it changes the reader's understanding of termination or state;
otherwise describe it in prose.

## Framework

Use `Framework` for ownership, layering, capability boundaries, or component
relationships. Arrange layers from the consumer or policy layer at the top to
the mechanism or hardware layer at the bottom. A horizontal relationship is
appropriate when two components are peers.

### Layered framework

```text
┌────────────────────────────────────────────┐
│ Policy or client components                │
│ commands, clients, and user-facing policy  │
└──────────────────────┬─────────────────────┘
                       │ FIDL / protocol
┌──────────────────────▼─────────────────────┐
│ Framework services                         │
│ component manager, driver manager, storage │
└──────────────────────┬─────────────────────┘
                       │ handles / syscalls
┌──────────────────────▼─────────────────────┐
│ Kernel or platform mechanisms              │
│ processes, memory, IPC, interrupts         │
└────────────────────────────────────────────┘
```

Explain the authority boundary in the text below the diagram. If a component
does not own the resource shown, label the edge with `uses`, `offers`, or
`borrows` rather than implying ownership by vertical placement.

### Peer components

```text
╭─────────────────────╮       ╭─────────────────────╮
│ Component A         │──────►│ Component B         │
│ publishes protocol  │ calls │ consumes protocol   │
╰─────────────────────╯       ╰─────────────────────╯
            ▲                         │
            ╰─────── reply / event ───╯
```

Use peer diagrams for IPC, driver discovery, or a capability hand-off. Keep
the protocol or capability name on the connector when more than one relation
exists between the same pair of boxes.

## Authoring rules

1. Choose one diagram purpose: execution order, ownership, layering, or peer
   interaction. Split unrelated relationships into separate diagrams.
2. Use the existing box-drawing characters and connector shapes before
   inventing new symbols. Keep matching borders and junctions aligned.
3. Keep labels short, stable, and noun-based. Put detailed rationale,
   conditions, and source references in prose below the diagram.
4. Use a consistent reading direction and make exceptional paths explicit.
   Do not rely on color, font, or visual position alone to convey meaning.
5. Prefer Unicode box-drawing characters for SMOS Markdown. If a target
   renderer cannot preserve them, provide an ASCII-compatible equivalent with
   the same topology and labels.
6. Review the rendered diagram at terminal width and in a normal Markdown
   viewer. A diagram is invalid when borders wrap, arrows become ambiguous, or
   labels overlap.

## Adoption

Future SMOS Markdown documents should use this file's symbols, layout rules,
and templates as the first choice for workflow and framework diagrams. A
document may introduce a different shape only when its relationship cannot be
expressed clearly with these patterns; explain that exception next to the
diagram and keep the same connector semantics.
