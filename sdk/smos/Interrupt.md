# SMOS Interrupt Delivery

This document traces an interrupt from an arm64 device or virtual source to a
Zircon interrupt object and, finally, to a driver thread or port. It separates
architecture entry, interrupt-controller acknowledgement, dispatcher state,
and userspace notification. The exact controller path is architecture and
product dependent; the arm64 GICv3 path below is source-confirmed for the SMOS
QEMU `virt` configuration.

## Interrupt layers

An interrupt is asynchronous relative to the instruction currently executing.
The CPU first takes an IRQ exception; the interrupt controller then identifies
the source; Zircon dispatches the source to a registered handler; and the
handler signals an object or queues a port packet. A driver does not access a
GIC register merely by owning an interrupt handle.

| Layer | Responsibility | SMOS source |
| --- | --- | --- |
| Arm exception vector | Save the interrupted frame and select `arm64_irq`. | `arch/arm64/exceptions.S` |
| Generic IRQ entry | Account, call platform delivery, and decide preemption. | `arch/arm64/exceptions_c.cc` |
| GIC | Select an INTID and complete EOI/deactivation. | `dev/interrupt/gic/v3/arm_gicv3.cc` |
| Platform registry | Invoke the handler registered for the INTID. | `pdev_invoke_int_if_present` |
| Interrupt dispatcher | Track triggered/acknowledged state and wake waiters. | `object/interrupt_dispatcher.cc` |
| Driver thread or port | Consume `zx_interrupt_wait` or a `zx_port_packet_t`. | userspace driver |

## Arm64 exception entry

`VBAR_EL1` points to the EL1 exception table. Each vector slot is selected by
the origin (current EL or lower EL), execution state, and exception class
(synchronous, IRQ, FIQ, or SError). The assembly saves an `iframe_t` before it
calls C code; the interrupted PC and PSTATE are restored only after the C path
returns.

```text
device asserts IRQ
 |
 `──► VBAR_EL1 IRQ slot
       ├──► save registers and ELR_EL1/SPSR_EL1 into iframe_t
       ├──► select arm64_el1_exception_*_irq_* entry
       └──► arm64_irq(iframe, exception_flags)
```

The vector entry does not identify the device. It only preserves the CPU
context and routes control to the common interrupt entry function.

## GICv3 delivery Code Flow

The GICv3 handler reads the interrupt-acknowledge register, rejects spurious
INTIDs, invokes the platform registry, and writes EOI. The handler runs with
the interrupt-context restrictions required by the platform path.

```text
arm64_irq(iframe, exception_flags)
 |
 ├──► int_handler_start(&state)
 ├──► kcounter_add(exceptions_irq, 1)
 ├──► platform_irq(iframe)
 │     └──► gic_handle_irq(frame)
 │           ├──► gic_read_iar() ──► vector/INTID
 │           ├──► spurious INTID ──► return
 │           ├──► pdev_invoke_int_if_present(vector)
 │           │     └──► registered interrupt handler
 │           └──► gic_write_eoir(vector)
 ├──► int_handler_finish(&state)
 ├──► user origin? ──► arch_iframe_process_pending_signals(iframe)
 ├──► do_preempt? ──► preempt current thread
 └──► return ──► exception assembly restores iframe and executes eret
```

GIC delivery and Zircon object notification are separate operations. EOI
completes the controller-side state, while the registered handler calls
`InterruptDispatcher::InterruptHandler` to publish the event to its consumer.

## Interrupt object creation and wait

The syscall layer validates a resource or device source, creates an
`InterruptDispatcher` subtype, and registers the platform handler. A driver
thread then waits on the object. The wait path consumes the `TRIGGERED` state,
returns the first saved timestamp, and moves the object to `NEEDACK`.

```text
zx_interrupt_create() / zx_pci_map_interrupt()
 |
 `──► sys_interrupt_create() or PciDeviceDispatcher::MapInterrupt()
       ├──► validate resource, vector, rights, and options
       ├──► create InterruptEventDispatcher/MSI/PCI dispatcher
       ├──► RegisterInterruptHandler()
       └──► return interrupt handle

zx_interrupt_wait(handle, &timestamp)
 |
 `──► sys_interrupt_wait()
       └──► InterruptDispatcher::WaitForInterrupt()
             ├──► DESTROYED ──► return ZX_ERR_CANCELED
             ├──► TRIGGERED ──► state=NEEDACK, return timestamp
             ├──► NEEDACK ──► unmask if configured
             ├──► state=WAITING
             ├──► Event::Wait(infinite)
             ├──► interrupted wait ──► state=IDLE, return status
             └──► signaled ──► retry state machine
```

The wait operation is not an acknowledgement. Until `zx_interrupt_ack` moves
the object back toward `IDLE` and unmasks it as configured, another hardware
edge may remain pending or be intentionally coalesced.

## Interrupt handler notification

`InterruptDispatcher::InterruptHandler` executes in interrupt context. It
records the first timestamp, handles mask-after-wait policy, and either signals
the event used by a waiting thread or queues a packet for a bound port.

```text
platform handler
 |
 `──► InterruptDispatcher::InterruptHandler()
       ├──► AutoPreemptDisabler + spinlock_ with IRQs saved
       ├──► record timestamp if empty
       ├──► state=NEEDACK? ──► coalesce and return
       ├──► port bound? ──► SendPacketLocked()
       │     └──► PortDispatcher::QueueInterruptPacket()
       ├──► no port ──► Signal() and state=TRIGGERED
       ├──► wake-vector enabled? ──► wake_event_.Trigger()
       └──► return to gic_handle_irq()
```

The dispatcher holds its spinlock only while changing state or queueing the
packet. Driver work belongs in the awakened thread, not in the hardware IRQ
handler.

## Port binding and acknowledgement

Binding changes the notification destination but does not create a second
interrupt source. If an interrupt was already triggered, `Bind` immediately
queues the saved timestamp and changes the state to `NEEDACK`. A port consumer
must acknowledge after processing the packet.

```text
zx_interrupt_bind(interrupt, port, key)
 |
 `──► sys_interrupt_bind()
       └──► InterruptDispatcher::Bind(port_dispatcher, key)
             ├──► DESTROYED ──► return ZX_ERR_CANCELED
             ├──► WAITING ──► return ZX_ERR_BAD_STATE
             ├──► already bound ──► return ZX_ERR_ALREADY_BOUND
             ├──► validate mask/unmask option combination
             ├──► attach port_dispatcher_ and port_packet_.key
             ├──► TRIGGERED? ──► SendPacketLocked(timestamp_)
             └──► return ZX_OK

zx_port_wait(port, &packet)
 |
 `──► PortDispatcher::Wait()
       └──► consume ZX_PKT_TYPE_INTERRUPT and its key/timestamp
             └──► zx_interrupt_ack(interrupt)
                   └──► InterruptDispatcher::Ack()
                         ├──► NEEDACK? ──► unmask or requeue pending timestamp
                         └──► no pending timestamp ──► state=IDLE
```

`Bind` rejects a waiter that is already blocked in `WaitForInterrupt`; a
consumer must choose either direct waiting or port delivery for one interrupt
object at a time.

## MSI, virtual interrupts, and destruction

MSI and MSI-X dispatchers register a vector-backed handler and may mask or
unmask the device-specific interrupt. Virtual interrupts use
`InterruptDispatcher::Trigger` instead of a physical GIC source and still
share the same triggered/acknowledged state machine. These paths converge at
`InterruptHandler` or `Trigger` after their source-specific validation.

Destroying an interrupt masks and deactivates the source, unregisters the
platform handler, removes a queued port packet, and then marks the dispatcher
`DESTROYED`. The unregister operation is deliberately performed before taking
the dispatcher spinlock again, avoiding a lock inversion with an IRQ arriving
concurrently.

```text
zx_handle_close(interrupt)
 |
 `──► InterruptDispatcher::on_zero_handles()
       └──► Destroy()
             ├──► MaskInterrupt()
             ├──► DeactivateInterrupt()
             ├──► UnregisterInterruptHandler()
             ├──► remove pending port packet when bound
             ├──► mark DESTROYED
             └──► signal direct waiter or return ZX_ERR_NOT_FOUND if required
```

## Source map and limits

| Topic | Source |
| --- | --- |
| arm64 vectors and frame save | `zircon/kernel/arch/arm64/exceptions.S` |
| Generic IRQ entry | `zircon/kernel/arch/arm64/exceptions_c.cc` |
| GICv3 acknowledge/EOI | `zircon/kernel/dev/interrupt/gic/v3/arm_gicv3.cc` |
| Interrupt object state | `zircon/kernel/object/interrupt_dispatcher.cc` |
| Interrupt syscalls | `zircon/kernel/lib/syscalls/driver.cc` |
| Port packet delivery | `zircon/kernel/object/port_dispatcher.cc` |
| MSI and virtual variants | `zircon/kernel/object/*interrupt_dispatcher.cc` |

The arm64 GICv3 flow is source-confirmed. GICv2, PCI MSI, virtual interrupt,
and non-arm64 paths share the dispatcher contract but use different controller
registration and acknowledgement functions. Product capability routing still
determines which interrupt handles a driver can obtain.
