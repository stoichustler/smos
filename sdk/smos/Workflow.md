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

Use `Code flow` to trace a detailed call chain through functions, commands, or
boot stages. It answers “which function calls which, in what order, and what
returns?”. Use plain-text nodes with indentation and connectors; do not use
boxes. Use `Sequence Diagram` for message order between peers and `Framework`
for ownership, layering, or capability boundaries.

### Purpose and selection

Choose Code flow when the important question is “what calls what next?”. Use
one line for each meaningful function, method, command, callback, or return.
Use `Sequence Diagram` when the important question is “which peer sends which
message, and when?”. Use `Framework` when the important question is ownership,
layering, or a capability boundary.

### Notation

- Write one function, method, command, event, or return value per line. Use
  implementation identifiers in `backticks` when prose introduces the flow.
- Use `│` to continue the current call stack, `├──►` for a sibling call, and
  `╰──►` for the final call at that level.
- Indent a callee beneath its caller. Keep the caller visible until its return
  or terminal outcome is shown.
- Use `◄──` for a return only when its value, error, or ownership matters.
  Label the return with `ok`, an error, or the concrete result type.
- Put conditions beside the connector, for example `valid`, `retry < 3`, or
  `PEER_CLOSED`. Keep exceptional paths explicit and end them with a result.
- Use `╰─▶` for a callback, retry, or feedback edge that leaves the current
  stack. State the event or exit condition beside the edge.
- Do not use `┌─┐`, `└─┘`, `╭─╮`, or other boxes in Code flow. Those shapes belong
  to Framework and Sequence Diagram diagrams.

### Linear flow

```text
main()
 │
 ├──► parse_args()
 │     │
 │     ╰──► validate_args()
 │           │
 │           ◄── Config
 │
 ╰──► run(Config)
       │
       ╰──► return Result
```

The vertical alignment shows the active call stack. Keep every call that is
needed to understand the result; collapse only implementation details that do
not change control flow or error handling.

### Branch and feedback

```text
handle_request()
 │
 ├──► validate(request)
 │     ├──► invalid ──► return InvalidArgument
 │     ╰──► valid
 │
 ╰──► execute(request)
       ├──► success ──► return Reply
       ╰──► failure ──► return InternalError
```

Keep success and failure at the call site that observes them. Do not represent
an error only in prose when it changes which caller runs next.

### Nested calls and returns

Use indentation to show a call stack. A return edge must identify the result
that the caller receives; this keeps nested calls distinct from peer messages.

```text
handle_request()
 │
 ╰──► validate_request()
       │
       ╰──► execute_request()
             │
             ◄── Result
       │
       ◄── Result
```

### Loop and bounded retry

Show the loop condition and the bound that prevents an accidental infinite
path. Point the retry edge to the operation that actually repeats.

```text
retry_request()
 │
 ├──► attempt()
 │     ├──► success ──► return Reply
 │     ╰──► failure
 │
 ├──► retry < 3 ╰─▶ attempt()
 ╰──► retry = 3 ──► return Unavailable
```

Show the retry bound and point the feedback edge to the operation that repeats.
If the loop is unbounded by design, state its cancellation or shutdown event.

### Parallel calls and join

Use sibling calls only for work that is concurrent or independently scheduled.
Name the join condition and show how a failed branch reaches the caller.

```text
start()
 │
 ├──► load_config()
 ├──► start_workers()
 │
 ╰──► join when both complete
       │
       ╰──► serve()
```

### Asynchronous hand-off

Use an explicit callback or event line when control leaves the current stack.
Do not draw an asynchronous hand-off as a synchronous nested call.

```text
submit()
 │
 ╰──► queue_work()
       │
       ╰──► event: work_done
             │
             ╰──► on_work_done(result)
                   │
                   ◄── return status
```

An event or callback starts a new path; it is not a synchronous nested call.
Use `Sequence Diagram` instead when the callback crosses multiple peer
participants and message timing is the subject.

### Code flow checklist

Before publishing a Code flow, check that it has one clear entry point, a
single primary reading direction, visible call depth, explicit returns or
terminal outcomes, and no graph boxes. Keep it narrow enough for 88 columns.
If the diagram needs peer lifelines, ownership boundaries, or many crossing
messages, split it into Code flow plus a Sequence Diagram or Framework.

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

### Sequence Diagram

Use a sequence diagram when the order of messages between two or more peers is
the subject of the explanation. Place participants from left to right and read
time from top to bottom.

```text
╭──────────────────╮  ╭──────────────────╮  ╭────────────────────╮
│ Client           │  │ Service          │  │ Peer / kernel obj  │
╰────────┬─────────╯  ╰────────┬─────────╯  ╰─────────┬──────────╯
         │                     │                      │
         │ request             │                      │
         ├────────────────────►│ validate / dispatch  │
         │                     │ operation            │
         │                     ├─────────────────────►│
         │                     │◄─────────────────────┤ result
         │◄────────────────────┤ reply                │
         │                     │                      │
         │                     │◄─────────────────────┤ event / peer close
         │◄────────────────────┤ forward event        │
```

The vertical line below each participant is its lifeline. A horizontal arrow
starts at the sender and ends at the receiver; label it with the protocol,
operation, result, or event. Write state such as `in transit`, `PEER_CLOSED`,
or an error beside the message that causes or observes it. Use a separate
sequence diagram when interactions would otherwise cross or exceed 88 columns.

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
