# SMOS Scheduler

This document adapts Fuchsia's `kernel_scheduling.md`, `fair_scheduler.md`,
and `kernel_thread_signaling.md` to the scheduler in the SMOS Zircon checkout.
It describes kernel scheduling and thread-signal behavior, not the separate
Driver Framework dispatcher or userspace executor policies.

## Scheduling model

Zircon keeps scheduler state for each logical CPU. Each CPU owns run queues for
runnable threads and uses inter-processor interrupts (IPIs) to coordinate
changes made by another CPU. A thread is either running on one CPU, ready in a
CPU run queue, or blocked on a wait queue. If no ordinary thread is runnable,
the CPU runs its idle thread.

The scheduler state and queue operations are implemented in
`zircon/kernel/include/kernel/scheduler.h`, `zircon/kernel/kernel/scheduler.cc`,
and `zircon/kernel/kernel/scheduler_state.cc`. Thread dispatchers, wait queues,
timers, interrupts, and owned locks call into this state; the scheduler does
not own component-manager or userspace lifecycle policy.

## Priority and run queues

The priority scheduler has 32 base priority levels, with 0 lowest and 31
highest. A thread's effective priority combines its base priority, temporary
priority adjustment, and inherited priority from an owned wait queue. When the
effective priority changes, the scheduler can move the thread to another queue
and request a reschedule.

Each priority queue is FIFO. A thread that still has time remaining after a
preemption or wakeup can be placed at the front; a thread that consumed its
time slice is placed at the back. Unblocking also provides a temporary boost so
that interactive work can receive prompt service. Priority inheritance lets a
thread holding a contended resource run long enough to release it for a higher
priority waiter.

Priority is a scheduling input, not an execution-time guarantee. CPU affinity,
interrupts, wait-queue ownership, preemption state, and higher-priority work
can all affect when a thread actually runs.

## Time slices, yield, and preemption

When a thread is selected, the CPU programs a preemption deadline for its full
or remaining time slice. `zx_thread_yield` voluntarily gives up the current
turn. Timer expiry, a remote queue update, or an interrupt that wakes a more
eligible thread can request preemption. The scheduler accounts for the old
thread, selects a replacement, and performs the context switch.

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

### Reschedule and context-switch Code Flow

The common path is entered by a timer, an explicit reschedule, a yield, or a
blocking transition. `RescheduleCommon` owns the current thread lock and the
destination scheduler queue lock while it accounts runtime and selects the
next thread.

```text
sched_reschedule() / sched_preempt() / sched_yield()
 |
 └──► Scheduler::RescheduleCommon(current, now)
       ├──► ProcessSaveStateList(now)
       ├──► UpdateTimeline(now)
       ├──► mark current READY + transient Rescheduling
       ├──► account runtime and energy
       ├──► adjust fair rate when weight_total_ changed
       ├──► EvaluateNextThread(now, current, ...)
       │     ├──► QueueThread(current) when its slice expired
       │     ├──► DequeueThread(now)
       │     │     ├──► idle power work
       │     │     ├──► DequeueDeadlineThread(now)
       │     │     ├──► DequeueFairThread()
       │     │     ├──► StealWork() when local queues are empty
       │     │     └──► idle_power_thread when no work exists
       │     └──► return next_thread
       ├──► next thread idle?
       │     └──► set idle deadline ──► PreemptReset()
       ├──► timeslice expired or thread changed?
       │     ├──► NextThreadTimeslice(next_thread, now)
       │     └──► clamp deadline ──► PreemptReset()
       ├──► otherwise continue current thread
       │     └──► adjust deadline if needed ──► PreemptReset()
       ├──► set next thread RUNNING
       └──► thread changed? ──► context switch ──► restore lock state
```

`sched_reschedule` can defer the operation when preemption is disabled, more
than one spinlock is held, or blocking is disallowed. The request is recorded
in the current thread's pending-preemption mask and is retried at a safe
point. `StealWork` temporarily releases the local queue lock while inspecting
another CPU, then marks the stolen thread's transient state before returning.

The implementation uses preemption state and time-slice extensions to protect
short critical sections. Disabling preemption is not a substitute for the
locks that protect a queue or dispatcher; it only constrains local scheduling
while the protected operation is in progress.

## CPU affinity and migration

Each thread has a CPU affinity mask. When a runnable thread needs a CPU, the
scheduler prefers an idle eligible CPU, then the thread's last CPU when it is
eligible, and finally another active CPU in the mask. If all requested CPUs
are inactive, the scheduler may temporarily run the thread elsewhere. A
single-CPU mask can therefore leave a thread waiting until its pinned CPU is
reactivated.

The scheduler reevaluates CPU placement when a thread wakes, changes affinity,
is preempted, yields, or voluntarily reschedules. A CPU being deactivated
causes runnable work to move to eligible CPUs; pinned work remains queued until
the CPU is active again. Reactivating a CPU does not perform global eager
rebalancing, but normal wakeup and migration decisions can use it.

### Unblock and migration Code Flow

An unblock operation chooses a destination CPU under the target queue lock. If
the thread has a migration callback, the last CPU may be retained temporarily
so that the callback can complete on the expected queue.

```text
Scheduler::Unblock(thread)
 |
 ├──► FindTargetCpu(thread)
 ├──► needs_migration? ──► retain last_cpu
 ├──► lock target->queue_lock_
 ├──► target active?
 │     ├──► no ──► retry FindTargetCpu()
 │     └──► yes
 ├──► thread->set_ready()
 ├──► migration pending? ──► save_state_list_.push_front(thread)
 ├──► otherwise ──► target->Insert(now, thread)
 │     └──► QueueThread() and fair/deadline run-queue insertion
 ├──► release thread lock
 └──► RescheduleMask(target_cpu)
```

The retry is bounded by the target CPU becoming an active scheduler; a target
that is concurrently deactivated cannot receive a new queue insertion. A
remote wakeup therefore requests rescheduling after releasing the queue lock,
rather than running a driver callback in the scheduler path.

## Idle and realtime threads

There is one idle thread per CPU. It lives outside the ordinary run queues and
executes when no other eligible work is runnable, allowing the platform to
enter an idle or low-power state. Realtime threads are handled specially by
the kernel scheduler and may run without ordinary preemption until they block,
yield, or explicitly reschedule. These classes still must obey their kernel
state and shutdown rules.

## Fair scheduling

The scheduler also contains fair scheduling state. A fair thread has a weight,
an effective virtual start and finish time, and a calculated time slice. The
run queue orders fair threads by virtual finish time so CPU bandwidth is
distributed approximately in proportion to weight while avoiding unbounded
wait for a runnable thread.

For a CPU with runnable thread count `n`, total weight `W`, target latency `L`,
and minimum granularity `M`, the conceptual scheduling period is `L` while
there are few competitors and stretches toward `n * M` when needed. A thread's
normalized virtual finish is derived from its start time, the period, and its
weight. The exact fixed-point representation and deadline interaction are
implemented in `scheduler_state.cc` and `scheduler_pi.cc`; documentation must
not assume that a particular tuning value is present in every product build.

Fair and deadline scheduling state can interact through priority inheritance
and owned wait queues. When a thread blocks, wakes, changes profile, or joins
an owned queue, the scheduler updates per-CPU runnable weight and may adjust
the next preemption time.

### Fair queue insertion Code Flow

Fair scheduling updates virtual time and period state before inserting a thread
into the ordered fair queue. A preemption preserves a positive normalized
remainder; a fresh insertion receives a new virtual interval.

```text
Scheduler::Insert(now, thread, placement)
 |
 ├──► queue_state.OnInsert()
 ├──► UpdateTotalExpectedRuntime()
 ├──► fair thread? ──► UpdatePeriod() + weight_total_ += weight
 ├──► QueueThread(thread, placement, now)
 │     ├──► subtract consumed runtime from time_slice_ns_
 │     ├──► compute normalized remainder
 │     ├──► exhausted or insertion? ──► start=max(finish, virtual_time)
 │     ├──► calculate period and fixed-point rate
 │     ├──► finish_time = start_time + delta_norm
 │     ├──► assign generation and sched_latency flow id
 │     └──► fair_run_queue_.insert(thread)
 ├──► deadline thread? ──► deadline_run_queue_.insert(thread)
 └──► TraceThreadQueueEvent("tqe_enque", thread)
```

`UpdatePeriod` uses the larger of the runnable fair-thread count and target
latency in granularity units. `CalculateTimeslice` derives the proportional
slice from `weight_total_`, rounds to an integer number of granules, and clamps
the result to at least one granule. The virtual finish time is fixed-point in
the implementation even though the design formulas are written as real-valued
ratios.

### Algorithm notation

The formulas below use the notation from Fuchsia's fair-scheduler design. The
subscripts identify a thread or CPU; they do not change the meaning of the
letter itself.

| Symbol | Semantic meaning | Unit or domain |
| --- | --- | --- |
| `P[i]` | The `i`-th thread competing for CPU time | thread |
| `C[j]` | The `j`-th logical CPU and its run queue | CPU |
| `w[i]` | Scheduling weight assigned to `P[i]` | positive weight |
| `W[j]` | Sum of weights competing on `C[j]` | weight |
| `R[i]` | `P[i]`'s normalized share of CPU service on `C[j]` | `0 < R[i] <= 1` |
| `M` | Minimum time-slice granularity | duration |
| `L` | Target scheduling latency for one CPU round | duration |
| `n[j]` | Number of runnable threads competing on `C[j]` | count |
| `p[j]` | Scheduling period for `C[j]` | duration |
| `g[j]` | Number of `M` units in `p[j]` | integer count |
| `s[i]` | Virtual start time of `P[i]`'s current turn | virtual time |
| `f[i]` | Virtual finish time used to order `P[i]` | virtual time |
| `t[i]` | Time slice allocated to `P[i]` in this period | duration |

`R[i]` is a relative service proportion, not a CPU frequency, wall-clock
rate, or promise that `P[i]` runs continuously. For a thread with positive
weight, `R[i] = w[i] / W[j]`; all competing relative rates on `C[j]` sum to
approximately one. The scheduler uses this proportion to allocate bandwidth
over time.

### Scheduling formulas

Let `N` be the largest number of competing threads that can each receive one
minimum-granularity slice while the CPU still meets target latency `L`:

```none
N = floor(L / M)

p[j] = max(L, M * n[j])
```

When `n[j] <= N`, the period remains `L`. When more threads compete, `p[j]`
stretches so that every thread can receive at least `M` in the period.

When `P[i]` enters the run queue at CPU system time `T`, its virtual interval is
defined as:

```none
s[i] = T
f[i] = s[i] + p[j] / w[i]
```

The run queue orders fair threads by ascending `f[i]`. A smaller `f[i]` means
that the thread is earlier in the virtual service schedule; it is not a
measurement of elapsed wall-clock execution. The period `p[j]` is used as an
idealized normalized service interval so that threads joining at different
times are compared consistently.

For the time slice, first express the period in `M`-sized units and then derive
the thread's relative service share:

```none
g[j] = floor(p[j] / M)
R[i] = w[i] / W[j]
t[i] = ceil(g[j] * R[i]) * M
```

Thus `t[i]` is an integer number of minimum-granularity units and is
approximately proportional to `w[i]`. Increasing `w[i]` increases the share
relative to other threads on the same CPU; it does not create additional CPU
capacity.

### SMOS implementation mapping

The current implementation stores these quantities in fixed-point or integer
fields rather than the real-number notation above:

| Formula concept | SMOS field or operation |
| --- | --- |
| `M` | `minimum_granularity_ns_` (default 1 ms) |
| `L` | `target_latency_grans_` (default 8 ms, in granularity units) |
| `p[j]` | `scheduling_period_grans_`, updated by `UpdatePeriod()` |
| `W[j]` | `weight_total_` |
| `s[i]`, `f[i]` | `start_time_`, `finish_time_` |
| `t[i]` | `CalculateTimeslice()` and `time_slice_ns_` |

`Scheduler::UpdatePeriod()` stretches the period in granularity units using
the runnable fair-thread count. `Scheduler::CalculateTimeslice()` computes
the proportional slice from `ep.fair.weight / weight_total_`, rounds it to an
integer number of granularity units, and clamps it to at least one unit. The
virtual finish interval is computed from the period and a fixed-point rate in
`scheduler.cc`, so the abstract `ceil` expression above is a semantic model,
not a claim about the exact machine instruction or rounding primitive.

## Blocking and wakeup

When a thread waits on a kernel object, futex, semaphore, pager operation, or
internal lock, it leaves the run queue and enters a wait queue. A signal or
resource release wakes it with a status. The wakeup path chooses an eligible
CPU, restores the thread's scheduling state, enqueues it by effective priority
or fair finish time, and requests an IPI or local reschedule when necessary.

```text
running(thread)
 │
 ╰──► block_on(object)
       │
       ╰──► wait_queue(object)
             │
             ╰──► wake(thread, status)
                   ├──► choose_eligible_cpu()
                   ├──► restore_scheduling_state()
                   ├──► enqueue_run_queue()
                   ╰──► request_reschedule_or_ipi()
```

The special statuses `ZX_ERR_INTERNAL_INTR_RETRY` and
`ZX_ERR_INTERNAL_INTR_KILLED` can interrupt an otherwise blocking operation.
Callers must propagate them according to the operation's suspend and kill
contract instead of treating them as an ordinary timeout.

## Thread signaling and safe points

Suspend and kill are requests, not arbitrary asynchronous destruction of a
running kernel stack. A thread records `THREAD_SIGNAL_SUSPEND` or
`THREAD_SIGNAL_KILL`, then processes the request at a safe point after its
kernel stack has unwound. The safe points are the transitions from a user-mode
syscall or user-mode exception back to user mode; returning to an outer
kernel-mode context is not safe because that context may still hold resources.

For a blocked interruptible thread, the signal path wakes it with
`ZX_ERR_INTERNAL_INTR_RETRY` for suspend or
`ZX_ERR_INTERNAL_INTR_KILLED` for kill. The status propagates through the
blocking call until the thread reaches the user boundary. A suspended thread
must resume briefly to observe a kill request and act on it.

For a running thread, the sender issues an IPI to its current CPU. If the IPI
arrives while the target is returning from user mode, the architecture signal
handler can process the request immediately. If it arrives in kernel mode, the
handler returns to the interrupted kernel context, which must later reach a
safe point. This distinction prevents termination while a kernel lock or
resource is held.

```text
request_suspend_or_kill(target)
 │
 ├──► set THREAD_SIGNAL_SUSPEND or THREAD_SIGNAL_KILL
 ├──► blocked? ──► wake with RETRY or KILLED status
 ├──► running? ──► send IPI to target CPU
 │     ├──► user context ──► process_pending_signals()
 │     ╰──► kernel context ──► return to interrupted kernel path
 ╰──► safe point ──► unwind stack and suspend or terminate
```

The implementation is distributed across `thread_dispatcher.cc`,
`suspend_token_dispatcher.cc`, architecture interrupt code, and wait-queue
users. The same IPI mechanism is important for a thread executing a long
`zx_vcpu_enter` operation: a VM exit gives the host kernel a chance to observe
pending signals and unwind safely.

### Pending-signal Code Flow

Signals are consumed at a user-return boundary after the interrupted kernel
stack is safe to unwind. The architecture wrapper supplies the saved iframe;
the thread code decides whether to suspend, terminate, or continue.

```text
arm64_irq() / arm64_sync_exception()
 |
 └──► arch_iframe_process_pending_signals(iframe)
       └──► Thread::Current::ProcessPendingSignals(Iframe, iframe)
             ├──► read THREAD_SIGNAL_KILL/SUSPEND
             ├──► KILL set ──► Thread::Current::Exit(0) ──► terminal state
             ├──► SUSPEND set ──► SaveUserStateLocked() ──► DoSuspend()
             ├──► restore saved user state and clear suspend bookkeeping
             ├──► pending exception? ──► ExceptionDispatcher response wait
             └──► no terminal signal ──► return to user via eret
```

An interrupt delivered while EL1 code holds a resource returns to that kernel
context first; the signal is handled only when the path reaches this boundary.
This ordering prevents a kill or suspend request from abandoning a lock or a
partially updated scheduler/VM data structure.

## Scheduler tracing

Scheduler tracing is controlled by kernel build settings such as
`SCHEDULER_TRACING_LEVEL` and `SCHEDULER_QUEUE_TRACING_ENABLED`, defined in
`zircon/kernel/BUILD.gn` and `scheduler.h`. The target build determines which
events are emitted. Upstream instrumentation commonly includes:

- `sched_block` and `sched_unblock` for wait-queue transitions;
- `sched_yield` for voluntary yield;
- `sched_preempt` for timer, interrupt, or remote-reschedule preemption;
- `sched_reschedule` when a run-queue change may select another thread;
- `sched_latency` when runnable-to-running latency is instrumented.

Events appear on per-CPU timelines. Correlate them with thread koid, effective
priority or fair weight, affinity, wait object, wake status, preemption timer,
IPI, and VM-exit records. Event names and trace categories must be verified in
the target image before being used as a product guarantee.

## Driver dispatcher boundary

`fdf::Dispatcher` is a Driver Framework runtime facility backed by shared
driver-host threads. Synchronized and unsynchronized dispatchers define
driver callback concurrency and reentrancy; they are not the kernel's per-CPU
run queues. Driver callback scheduling can ultimately consume kernel threads,
but dispatcher lifetime, callback cancellation, and driver hooks belong in the
Driver Framework documentation.

## Source and adaptation map

| Topic | SMOS source or reference |
| --- | --- |
| Run queues and scheduling state | `zircon/kernel/include/kernel/scheduler.h` |
| Scheduler implementation | `zircon/kernel/kernel/scheduler.cc` |
| Fair/deadline state | `scheduler_state.cc`, `scheduler_pi.cc` |
| Thread state and signals | `zircon/kernel/object/thread_dispatcher.cc` |
| Suspend requests | `zircon/kernel/object/suspend_token_dispatcher.cc` |
| Wait and wake propagation | `zircon/kernel/kernel/`, object wait-queue users |
| Scheduler build controls | `zircon/kernel/BUILD.gn` |

The explanatory material is adapted from Fuchsia's
`docs/concepts/kernel/kernel_scheduling.md`, `fair_scheduler.md`, and
`kernel_thread_signaling.md` under the Fuchsia BSD license. Product-specific
claims in this document are limited to mechanisms and symbols confirmed in the
SMOS source tree.
