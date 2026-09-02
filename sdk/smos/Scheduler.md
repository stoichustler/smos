# SMOS Scheduler

This document adapts Fuchsia's kernel scheduling guides to the scheduler in
the SMOS Zircon checkout. It focuses on the mechanisms that determine which
thread runs on which CPU and how a blocked thread becomes runnable again.

## Scheduling model

Zircon maintains scheduler state per logical CPU. Each CPU owns priority queues
of runnable threads and coordinates with other CPUs using inter-processor
interrupts (IPIs). A runnable thread is placed on an eligible CPU; the local
scheduler selects the highest effective priority and removes the queue head.
If no runnable thread exists, the CPU runs its idle thread.

The scheduler implementation and state are centered in
`zircon/kernel/include/kernel/scheduler.h` and the nearby scheduler sources.
Thread state, wait queues, CPU masks, and dispatcher wakeups feed this state;
the scheduler does not own userspace policy or component lifecycle.

## Priority and queue order

A thread's effective priority is derived from its base priority and any kernel
priority adjustments. Higher effective priority wins. Threads at the same
priority are ordered FIFO, subject to a thread's remaining time slice. A thread
that still has time remaining is placed at the front when it becomes runnable;
one that consumed its slice returns to the back.

Priority is a scheduling input, not a guarantee of immediate execution. An
interrupt, a higher-priority wakeup, CPU affinity, or a preemption decision can
change when a queued thread runs.

## Time slices, yield, and preemption

When a thread is selected, the CPU programs a preemption deadline for its full
or remaining time slice. `zx_thread_yield` voluntarily gives up the current
turn. Timer expiry, a remote reschedule request, or an interrupt that wakes a
more eligible thread can request preemption. The scheduler then accounts for
the running thread, chooses a replacement, and performs the context switch.

```text
select_next_thread(cpu)
 │
 ╰──► program_preemption_timer(slice)
       │
       ╰──► run(thread)
             ├──► yield ──► requeue(thread)
             ├──► timer expiry ──► requeue(thread)
             ├──► block ──► wait_queue
             ╰──► interrupt ──► reschedule(cpu)
```

## Blocking and wakeup

When a thread waits on a kernel object, futex, or internal lock, it leaves the
runnable queue and enters that object's wait queue. A signal or wake operation
makes it runnable again. The scheduler selects an eligible CPU using affinity,
load, and current CPU state, then sends an IPI when another CPU must reevaluate
its run queue.

```text
running(thread)
 │
 ╰──► block_on(object)
       │
       ╰──► wait_queue(object)
             │
             ╰──► wake(thread)
                   ├──► choose_eligible_cpu()
                   ├──► enqueue_by_priority()
                   ╰──► request_reschedule_if_needed()
```

The wakeup path does not promise that the thread runs on the CPU that woke it.
CPU migration is an implementation decision constrained by affinity and
per-CPU scheduler state.

## CPU assignment and migration

Each thread has an affinity mask. A thread may migrate when it becomes runnable,
when its current CPU is deactivated, or when balancing policy selects another
eligible CPU. Remote queue changes are synchronized with the destination CPU
through scheduler locks and IPI-driven rescheduling. The idle thread is used
when a CPU has no runnable work, while realtime and other special scheduling
classes follow their kernel-specific rules.

## Fair-scheduling terminology

The upstream fair-scheduler documentation describes virtual timelines,
scheduling periods, runnable demand, and per-thread weights. SMOS should treat
those as conceptual terminology unless the selected kernel configuration
exposes the corresponding implementation. This checkout does not define an
`enable_fair_scheduler` GN argument, so this document does not prescribe a
build command that enables it.

## Tracing and diagnosis

Scheduler tracing, when enabled by the selected kernel build, can correlate
blocking, wakeups, yields, preemption, and reschedule decisions on per-CPU
timelines. Typical event names in the upstream instrumentation include
`sched_block`, `sched_unblock`, `sched_yield`, `sched_preempt`, and
`sched_reschedule`; verify that an event is present in the target image before
using it in an analysis.

For a scheduling investigation, record the thread koid, effective priority,
CPU affinity, wait object, wake source, and whether a preemption timer or IPI
caused the next decision. A trace without these correlations can show timing
but not the reason for a scheduling transition.

## Source map

| Topic | SMOS source |
| --- | --- |
| Scheduler state and queues | `zircon/kernel/include/kernel/scheduler.h` |
| Thread lifecycle and dispatch | `zircon/kernel/object/thread_dispatcher.cc` |
| Wait queues and wakeups | `zircon/kernel/` scheduler and object wait-queue sources |
| CPU activation and affinity | `zircon/kernel/arch/` and scheduler sources |

The conceptual material is adapted from Fuchsia's `kernel_scheduling.md` and
`fair_scheduler.md` under the Fuchsia BSD license. Configuration and event
names above are descriptive unless confirmed in the selected SMOS build.
