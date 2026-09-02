# SMOS ARM64 Architecture

This document combines the AArch64 architecture notes used by SMOS with the
platform mechanisms that matter to the Zircon microkernel, the QEMU arm64
board, and the optional virtualization stack.  It covers ARMv8-A and the
ARMv9-compatible instructions that are relevant to system software.

## SMOS execution model

SMOS runs Zircon at EL1 and places the component framework, drivers, shells,
and virtualization services in user space.  Firmware or QEMU enters the
arm64 boot shim, which loads the ZBI and transfers control to Zircon.  The
microkernel owns scheduling, virtual memory, interrupt delivery, objects, and
syscalls; user space owns policy and device protocols.

```text
                    QEMU virt machine / ARM firmware
                                  |
                    boot shim -> kernel.phys -> ZBI
                                  v
        +----------------------------------------------------+
        | Zircon EL1: scheduler, VM, objects, IRQs, syscalls |
        +-------------------------+--------------------------+
                                  |
              handles, VMOs, channels, sockets, FIDL protocols
                                  v
        +----------------------------------------------------+
        | SMOS user space: userboot, component_manager,      |
        | driver_manager, virtio drivers, console, dash, VMM |
        +-------------------------+--------------------------+
                                  |
                    GICv3 / UART / PCI / virtio / SMMU
```

The SMOS arm64 board uses QEMU's `virt` machine with GICv3 and a low PCI ECAM
window.  The default product is console-only; graphics and conventional IP
networking are outside its scope.  The optional virtio-vsock path uses the
same EL1 object and capability model as the rest of the product.

## Architecture foundations

ARMv8-A defines two execution states.  AArch64 uses 64-bit general-purpose
registers and the A64 instruction set; AArch32 uses 32-bit registers and the
A32 or T32 instruction set.  A processor can implement both states, but a
given exception level executes in only one state at a time.  SMOS user and
kernel paths are AArch64; AArch32 compatibility is not implied by the product
configuration.

The architecture also defines four exception levels (ELs).  A larger number
means more privilege within the current security state:

| Level | Typical role | SMOS mapping |
| --- | --- | --- |
| EL0 | Applications and unprivileged services | Components, drivers, and dash |
| EL1 | Operating-system kernel | Zircon |
| EL2 | Hypervisor and guest virtualization | Optional SMOS hypervisor |
| EL3 | Secure monitor and firmware transition | Platform firmware, outside SMOS |

Normal and Secure worlds are a separate security dimension.  EL2 commonly
belongs to the Normal world, while EL3 arbitrates transitions between worlds.
An exception can be routed to the current or a higher implemented EL, never
directly to a lower EL.  `eret` returns to the EL recorded in `SPSR_ELn` and
the address in `ELR_ELn`; return can stay at the same EL or move lower.

An exception entry is therefore a state transfer, not just a function call:

```text
lower-EL instruction or interrupt
  |
  +--> save return PC and PSTATE in ELR_ELn/SPSR_ELn
  +--> select the target EL stack and vector slot
  +--> handler saves general registers and dispatches the cause
  `--> eret restores the recorded context
```

The vector slot depends on whether the exception came from the current EL or a
lower EL and whether the lower context was AArch64 or AArch32.  This is why a
kernel exception table must be aligned and laid out for all contexts it
accepts.

### Registers and processor state

AArch64 exposes `x0` through `x30`, each 64 bits wide.  `w0` through `w30` are
the low 32-bit views; writing a `w` register clears the upper 32 bits of its
`x` register.  `x30` is the link register, while `sp` is a dedicated stack
pointer and is not part of the numbered register file.  The program counter is
not directly addressable as a general-purpose register.

`PSTATE` contains the execution state, current EL, interrupt masks (`DAIF`),
condition flags (`N`, `Z`, `C`, `V`), and the selected stack-pointer mode.
Exception entry snapshots it in `SPSR_ELn`; system instructions update the
architectural controls through named registers such as `SCTLR_EL1`, `TCR_EL1`,
`TTBR0_EL1`, and `VBAR_EL1`.  Access to these registers is restricted by EL
and by the register's access policy.

The stack pointer must remain 16-byte aligned at public call boundaries.  A
prologue commonly saves the frame pointer and link register with `stp`, and an
epilogue restores them with `ldp` before `ret`.  Interrupt and exception entry
code must preserve the interrupted context explicitly because the hardware
only saves the ELR and PSTATE pair.

## AArch64 ISA

The AArch64 ISA provides 31 general-purpose registers, `x0` through `x30`.
`x30` is the link register, and `sp` is the stack pointer.  AArch64 stacks
must remain 128-bit aligned at every public call boundary.

<img src="assets/arm64/Arm64_program_registers.png" alt="AArch64 program registers" width="750">

The complete instruction reference is available in
[`ARM_instruction_set.pdf`](assets/arm64/ARM_instruction_set.pdf).  The
following instructions occur frequently in boot and kernel code:

### Bit manipulation

`BFI` inserts a bit field, while `UBFX` extracts an unsigned bit field.

<img src="assets/arm64/Bit_manipulation.png" alt="Bit manipulation" width="750">

### Load/store pairs

`stp` and `ldp` transfer two registers in one instruction and are commonly
used to save and restore stack frames:

```asm
stp     x0, x1, [sp, #-16]!
ldp     x0, x1, [sp], #16
```

### PC-relative addresses

`adr` computes a label address within approximately +/-1 MiB.  `adrp` computes
the 4 KiB page address of a label within approximately +/-4 GiB; an `add` then
supplies the page offset.  This is the usual position-independent sequence:

```asm
adrp    x0, symbol
add     x0, x0, :lo12:symbol
```

### Exception return

`eret` restores `PSTATE` from the current exception level's `SPSR` and branches
to `ELR`.  Zircon exception vectors use this instruction after dispatching a
syscall, fault, IRQ, or other exception.

### Instruction classes and addressing

A64 instructions have a fixed 32-bit encoding, but their operands can be
32-bit (`Wn`) or 64-bit (`Xn`).  The main classes are data processing, loads and
stores, branches, and system/control instructions.  Load/store instructions
support base-plus-immediate, register-offset, pre-indexed, and post-indexed
forms.  Pre-indexing updates the base before the access; post-indexing updates
it after the access, which is useful for stack and ring-buffer walkers.

Conditional execution is expressed mostly through conditional branches and
conditional select instructions rather than a condition suffix on every
instruction.  Immediate fields have instruction-specific widths and scaling,
so an assembler may need a sequence such as `movz`/`movk` or `adrp`/`add` for a
constant or address that does not fit one encoding.  `w`-register writes,
sign/zero extension, and implicit shift amounts are frequent sources of bugs
when porting 32-bit code.

## Memory system

The cache hierarchy is implementation-defined, but a typical arm64 system has
private L1/L2 caches and a larger shared L3 cache.  Cache lines are commonly 64
bytes.  Temporal locality keeps recently used lines close to a core; spatial
locality makes adjacent lines useful for sequential accesses.

<img src="assets/arm64/Cache_basics.png" alt="Cache basics" width="750">

<img src="assets/arm64/Cache_hierarchy.png" alt="Cache hierarchy" width="750">

SMOS also models the multi-core system explicitly:

- **SMP** gives every core the same view of memory and shared hardware.
- **AMP** assigns statically different software roles to different cores.
- **HMP** combines performance and efficiency cores, as in big.LITTLE systems.

<img src="assets/arm64/Cache_and_memory_hierarchy.png" alt="Cache and memory hierarchy" width="750">

### Address translation

The MMU translates a virtual address to a physical address by reading the
translation-table base register and walking the descriptors at each level.
Zircon creates VMOs and VMARs and programs the arm64 page tables; user
processes receive mappings through handles rather than by writing page-table
descriptors directly.

<img src="assets/arm64/Address_translation_process.png" alt="Address translation process" width="750">

### TLBs and translation context

The Translation Lookaside Buffer (TLB) caches recent virtual-to-physical
translations so that every access does not walk the page tables.  A TLB miss
causes a hardware table walk; a permission, address-size, or execute-never
failure then raises a translation fault rather than returning a partial
mapping.

`TTBR0_EL1` and `TTBR1_EL1` commonly select separate user and kernel address
spaces.  An ASID tags translations belonging to a process so that a context
switch can change address spaces without flushing unrelated entries.  A VMID
serves the analogous purpose for stage-2 translations at EL2.  When a page
table entry changes, software must invalidate the affected TLB entries with
the architecture-defined invalidate operation and follow it with the required
barrier sequence before executing or accessing the new mapping.

ARMv8-A supports 4 KiB, 16 KiB, and 64 KiB translation granules.  A table
descriptor points to another level, a block descriptor maps a larger aligned
range, and a page descriptor maps the final granule.  The selected granule,
virtual-address size, and level count are configured by `TCR_EL1`; the chosen
descriptor's `AttrIndx`, access-permission, shareability, and execute-never
bits are combined with `MAIR_EL1` to define the mapping.

### Cache maintenance and points of coherency

The point of unification (PoU) is where instruction and data views become
consistent; the point of coherency (PoC) is where observers such as other
cores see a coherent value.  Cache maintenance instructions operate on cache
lines, so callers must align and size ranges according to the reported cache
line length.  Typical operations are:

| Operation | Purpose |
| --- | --- |
| Clean | Write dirty cache lines to the next memory level. |
| Invalidate | Discard a cache line so a later load refetches it. |
| Clean and invalidate | Write back, then discard, a cache line. |

The `DC` instruction family maintains data-cache lines and `IC` invalidates
instruction-cache lines.  After writing code or changing executable mappings,
software normally cleans data to PoU, invalidates the instruction cache, and
executes `DSB` followed by `ISB` at the architecturally required points.  DMA
ownership still requires the platform's cache and barrier sequence even when
the CPU caches are coherent with one another.

### Memory ordering

Arm64 uses a weak memory-ordering model.  Instructions still retire according
to the architectural execution rules, but independent loads and stores can be
issued, completed, or observed out of program order.  The processor and the
interconnect can therefore overlap cache misses, write-buffer drains, and
device transactions.  A single-core test may appear correct while a second
core or a device observes the operations in a different order.

For a producer/consumer hand-off, the producer must make the data visible
before publishing the descriptor, and the consumer must acquire the
descriptor before reading the data:

```text
Producer: write payload -> DMB/DSB -> publish ready flag
                                      |
                                      v
Consumer: read ready flag -> DMB    -> read payload
```

The three architectural barriers have different guarantees:

| Barrier | Guarantee | Typical SMOS use |
| --- | --- | --- |
| `DMB` | Orders explicit memory accesses around the barrier. | Publish a ring-buffer entry before an IRQ or doorbell. |
| `DSB` | Waits until selected memory effects are complete. | Finish cache maintenance before handing a buffer to DMA. |
| `ISB` | Flushes the instruction stream and synchronizes execution context. | Apply a new translation, control, or exception-vector setting. |

`DMB` does not wait for a peripheral to finish, and `DSB` does not make a
non-atomic read/modify/write sequence atomic.  Use acquire/release atomics or
exclusive accesses for ownership state, then use the appropriate barrier when
that state crosses a CPU, interrupt, or device boundary.  Device register
accesses should use the accessors supplied by the driver framework rather than
ordinary C pointer dereferences.

### Memory types and attributes

Arm64 classifies every translation as **Normal memory** or **Device memory**.
The type is selected by the page-table descriptor and is not a property that a
user process can change with a normal load or store.

| Type | Intended contents | Permitted optimization |
| --- | --- | --- |
| Normal | RAM, code, stacks, VMOs, and frame buffers. | Caching, speculation, gathering, and reordering according to the mapping. |
| Device | MMIO registers and explicitly device-owned windows. | Restricted speculation and ordering suitable for side-effecting accesses. |

Normal memory has cacheability and shareability attributes.  A cacheable
mapping can retain dirty lines in a write-back cache; a non-cacheable mapping
must reach the memory system for each access.  Device memory adds three
independent properties:

- `G`/`nG` controls whether adjacent accesses may be gathered;
- `R`/`nR` controls whether accesses may be reordered; and
- `E`/`nE` controls early write acknowledgement from an intermediate buffer.

`Device-nGnRnE` is the most restrictive common device mapping.  It is a safe
default for registers with strong side effects, but it can be unnecessarily
slow for a bulk data window.  A less restrictive mapping is valid only when
the device specification permits gathering, reordering, and early completion.
Mapping an MMIO register as Normal memory is unsafe because speculative or
reordered accesses can trigger an operation that software did not request.

### MAIR and page-table selection

The Memory Attribute Indirection Register (`MAIR_ELn`) contains up to eight
8-bit attribute encodings.  Each leaf page-table descriptor carries an
`AttrIndx[2:0]` field that selects one encoding.  During a TLB miss, the MMU
combines the descriptor's index with `MAIR_EL1` to determine how that page is
accessed:

```text
virtual address
      |
      v
translation-table walk -> leaf descriptor -> AttrIndx[2:0]
                                                   |
                                                   v
                                            MAIR_EL1 entry
                                                   |
                                                   v
                                   Normal/Device + cache/shareability rules
```

The attribute granularity is a page, not a C/C++ object.  Two buffers in one
page cannot safely require incompatible memory types.  Zircon's VMOs and VMARs
must therefore keep page alignment and mapping permissions consistent with the
board's memory description.  A driver that maps a register range must also
preserve the range's Device type when it creates a user-visible mapping.

### Cache hierarchy and write buffers

An access can be delayed at several levels: a private L1 cache, a private or
cluster L2 cache, a shared last-level cache, a write buffer, the interconnect,
or the target device.  A store can retire after entering a write buffer while a
load that misses in every cache waits for the external response.  This is why
a profiler can attribute most of a loop's time to a simple arithmetic
instruction: the instruction may be waiting on an older memory dependency.

Write combining coalesces adjacent stores or repeated stores to the same
cache line.  It improves sequential output but does not make a buffer visible
to a device by itself.  The software ownership transition still needs the
barrier and cache-maintenance operation required by the platform.

### Shareability domains

Shareability states the hardware scope in which cache coherence is guaranteed:

1. **Non-shareable**: one processing element or a private cache hierarchy.
2. **Inner Shareable**: the cores in one coherency cluster.
3. **Outer Shareable**: multiple clusters joined by the system interconnect.
4. **System Shareable**: all relevant agents, including DMA, GPU, and NPU.

The label is not a promise that every device is coherent.  A DMA engine behind
a non-coherent bridge can still require explicit cache maintenance even when
the CPU mapping is marked shareable.  The platform's interconnect and IOMMU
configuration determine whether the System Shareable domain includes that
device.

### DMA ownership and cache coherency

DMA removes the CPU from the byte-copy path, but it creates a cache ownership
problem.  A CPU write can be newer than DRAM because it is dirty in a cache; a
device write can be newer than a stale CPU cache line.  Treat a DMA buffer as a
small state machine:

```text
CPU-owned, writable
        |
        +-- clean cache lines; DMB/DSB; publish descriptor
        v
Device-owned, in-flight
        |
        +-- device completion/IRQ; reclaim ownership
        v
CPU-owned, readable
        |
        +-- invalidate or synchronize cache lines before reading
        v
CPU-owned, writable again
```

For a non-coherent device, the usual directions are:

- **CPU -> device**: complete CPU stores, clean the relevant cache lines, then
  publish the descriptor and start the device;
- **device -> CPU**: wait for completion, invalidate or synchronize stale cache
  lines, then read the payload; and
- **bidirectional**: use a platform-defined clean/invalidate sequence and keep
  ownership exclusive while the device is active.

System-level hardware coherence can remove some explicit cache operations, but
it does not remove the ownership protocol, descriptor ordering, or lifetime
rules.  Never infer DMA visibility merely from a successful `memcpy()` or from
the fact that two virtual mappings refer to the same VMO.

### SMMU, BTI, and SMOS buffers

In SMOS, a VMO identifies storage, a BTI limits which physical memory a device
can access, and an SMMU/IOMMU can translate or reject the device's DMA address.
These mechanisms solve different parts of the problem:

| Mechanism | Protects or describes |
| --- | --- |
| VMO/VMAR | Which user-space component can map and access the bytes. |
| BTI | Which physical pages a device is permitted to pin or use for DMA. |
| SMMU/IOMMU | How a device address is translated and which ranges are rejected. |
| Cache/barrier operations | When CPU and device observations become ordered and coherent. |

An IOMMU mapping is not a cache flush, and a cache flush is not an access
control boundary.  Drivers must establish both before starting a transfer.
When the board lacks system-level coherence, the driver must use the
platform's cache-maintenance primitives around the DMA ownership transitions.

### Memory and DMA performance diagnosis

When a DMA path is unexpectedly slow, measure the directions independently:

1. CPU-only sequential reads from Normal cacheable memory;
2. CPU-only sequential writes to the same memory;
3. CPU reads from the device's buffer mapping;
4. CPU writes to the device's buffer mapping; and
5. end-to-end device-to-memory and memory-to-device transfers.

Record page size, cacheability, memory type, shareability, alignment, transfer
size, and whether the path is hardware-coherent.  A read-heavy workload on an
uncached Device mapping can be much slower than a write-heavy workload because
stores may be posted or combined while loads wait for the external target.
Cache-miss counters alone do not identify this case: a stalled load, an
interconnect queue, or a write-buffer drain can dominate the elapsed time.

Common mistakes are mapping registers as Normal memory, using a cacheable
buffer without a DMA ownership transition, issuing `DMB` where completion
requires `DSB`, and reusing a descriptor before the device has returned it.
Keep the descriptor, buffer, interrupt, and reclamation protocol explicit in
the driver state machine.

### Page-table and context-switch checklist

When debugging a translation failure, inspect the complete tuple rather than
only the faulting virtual address:

1. Which `TTBR` and ASID/VMID selected the address space?
2. Which descriptor level and granule size matched the address?
3. What `AP`, `UXN`, `PXN`, shareability, and `AttrIndx` bits were present?
4. Was a stale TLB entry invalidated after the table update?
5. Did the required `DSB`/`ISB` sequence complete before the access?

This checklist separates a bad page-table descriptor from a stale translation,
an incorrect memory type, and a genuine physical access fault.

## Exceptions and exception levels

Synchronous exceptions are associated with the executing instruction:

- invalid instructions and trap instructions;
- memory-access faults;
- `SVC`, `HVC`, and `SMC` calls; and
- debug exceptions.

Asynchronous exceptions arrive independently of the current instruction:

- physical and virtual interrupts;
- IRQ and FIQ; and
- SError.

IRQ and FIQ can be masked temporarily, leaving the interrupt pending until it
is unmasked.  The exception vector selects a handler based on the current
exception level and whether the lower context is AArch64 or AArch32.

<img src="assets/arm64/ARM_exception_handler.png" alt="ARM exception handler" width="750">

ARMv8-A defines EL0 through EL3.  SMOS user processes execute at EL0 and
Zircon executes at EL1.  A hypervisor, when present, executes at EL2; firmware
and secure-monitor code execute at EL3.  `SVC`, `HVC`, and `SMC` are exception
generators that provide entry points into those higher-level services.

<img src="assets/arm64/ARM_service_call_routing.png" alt="ARM service call routing" width="750">

## Synchronization and atomics

Arm exclusive accesses support lock-free synchronization:

```asm
FUNCTION(arch_spin_lock)
    mov     x1, #1
    sevl
1:
    wfe
    ldaxr   x2, [x0]
    cbnz    x2, 1b
    stxr    w2, x1, [x0]
    cbnz    w2, 1b
    ret

FUNCTION(arch_spin_unlock)
    stlr    xzr, [x0]
    ret
```

`ldaxr` is an acquire load-exclusive operation.  `stxr` conditionally stores
and returns zero on success.  `stlr` is a release store.  `sevl` primes the
local event state and `wfe` waits for an event, reducing contention in the
retry loop.

<img src="assets/arm64/ARM_exclusive_monitor.png" alt="ARM exclusive monitor" width="750">

## AArch64 ABI and porting

The AArch64 Procedure Call Standard (AAPCS64) defines the boundary between
compiled code and hand-written assembly.  The first eight integer or pointer
arguments use `x0`-`x7`; an indirect result address may use `x8`.  `x0`-`x17`
are caller-saved scratch registers (with `x16` and `x17` reserved for
linker/PLT veneers and `x18` reserved by the platform ABI).  `x19`-`x28`,
`x29` (the frame pointer), and `x30` (the link register) are callee-saved.
Floating-point and NEON arguments use `v0`-`v7`; the lower 64 bits of
`v8`-`v15` are callee-saved.  The stack remains 16-byte aligned at every
public interface.

These rules explain why a context switch saves more than the registers used by
one C function: an interrupted thread must preserve the complete architectural
state, while a leaf function only needs to preserve the callee-saved subset.
Assembly that calls C must also declare clobbers and obey the compiler's stack
and register assumptions.

Porting from a 32-bit ABI requires more than changing `int` to `long`.  Keep
these distinctions explicit:

- `size_t`, pointers, and `uintptr_t` are 64-bit in AArch64 user space;
- `int` remains 32-bit, so implicit pointer-to-integer conversions can truncate;
- structure alignment and padding can change the layout of shared interfaces;
- shifts and masks must use a type wide enough for the intended address bits;
- variadic arguments follow the AAPCS64 register-save and stack rules; and
- inline assembly must use the AArch64 register names and constraints.

For an ABI boundary shared with a driver, hypervisor, or firmware, specify
field widths and endianness in the protocol instead of relying on a compiler's
default layout.

## GICv3 interrupt controller

The Generic Interrupt Controller (GIC) routes interrupt sources to processor
elements (PEs).  SMOS arm64 uses the QEMU GICv3 model.

### Components

- **Distributor** prioritizes and distributes SPIs and SGIs.
- **Redistributor** holds per-PE state for PPIs and LPIs.
- **CPU interface** acknowledges interrupts, drops priority, masks priorities,
  and identifies the highest-priority pending interrupt.
- **ITS** is an optional translation service that maps device EventIDs to LPI
  interrupt IDs through a command queue and in-memory tables.

<img src="assets/arm64/ARM_GIC_logical_partitioning.png" alt="GIC logical partitioning" width="750">

### Physical IRQ lifecycle

1. A peripheral or software generates an interrupt.
2. The GIC prioritizes and distributes it.
3. The CPU interface delivers it to the PE.
4. Software acknowledges it, making it active (and possibly still pending).
5. Software performs a priority drop after the handler has made progress.
6. Software deactivates it, allowing a pending interrupt to be delivered again.

<img src="assets/arm64/ARM_GIC_pIRQ_lifecycle.png" alt="GIC physical IRQ lifecycle" width="750">

The state transitions are inactive -> pending -> active and pending -> active
-> inactive.  A peripheral normally clears the source between the latter two
states; software writes the End of Interrupt register to complete handling.

<img src="assets/arm64/ARM_GIC_IRQ_handling_state_machine.png" alt="GIC IRQ handling state machine" width="750">

## Multi-core and power management

SMP, AMP, and HMP describe different software assumptions:

- **SMP** runs one kernel image with equivalent cores and shared scheduling;
- **AMP** assigns fixed roles or images to different cores; and
- **HMP** schedules across performance and efficiency cores with different
  capacity and energy costs.

The exclusive monitor tracks the address used by a load-exclusive operation.
Another core, an interrupt, or an implementation-defined eviction can clear
the monitor, so `stxr` must be treated as a retryable failure.  The monitor is
not a general transaction log and does not make a sequence of unrelated
addresses atomic.  Use cache-coherent shareability and acquire/release
ordering around the lock or queue that the exclusive sequence protects.

Idle and power transitions have progressively stronger state-loss effects:

| State | Architectural effect and software action |
| --- | --- |
| Clock/standby idle | State is retained; preserve wake and interrupt routing. |
| Retention | Some domains lose clocks; restore clocks and validate wake status. |
| Power-down or hotplug | Context may be lost; restore it and reinitialize interfaces. |

DVFS changes frequency and voltage without changing the architectural ISA, but
timer conversion, scheduler accounting, and thermal policy must use the
platform's clock description.  PSCI provides the firmware interface commonly
used to start, stop, suspend, and power CPUs; SMOS must not assume a PSCI
function exists on every QEMU or board configuration.

On a big.LITTLE system, migration policy can be cluster-based, CPU-based, or
global.  A runnable thread may migrate on wakeup, fork, idle pull, or thermal
pressure, but migration must preserve affinity, priority, timer ownership, and
cache-coherency assumptions.  SMOS's QEMU `virt` board is homogeneous by
default, so HMP policy is an optional hardware concern rather than a scheduler
guarantee.


## SMMUv3 and DMA

An SMMU translates addresses in DMA requests from I/O devices.  It is separate
from the PE MMU: the PE translates virtual addresses, while the SMMU protects
device access to physical or intermediate physical addresses.

A StreamID selects a Stream Table Entry (STE).  An STE enables the stream and
selects stage 1 translation, stage 2 translation, or both:

- stage 1 translates a device virtual address to an IPA using Context
  Descriptors (CDs) and an ASID;
- stage 2 translates an IPA to a PA using a VMID and stage-2 tables; and
- multiple devices can share stage-2 tables while retaining separate STEs.

Stream tables can be linear or two-level.  The two-level form bounds the amount
of memory needed for sparse StreamID ranges.

<img src="assets/arm64/ARM_SMMU_2_level_stream_table.png" alt="SMMUv3 two-level stream table" width="750">

<img src="assets/arm64/ARM_SMMU_configuration_structure.jpg" alt="SMMUv3 configuration structure" width="750">

<img src="assets/arm64/ARM_SMMU_multi-CD_for_substreams.png" alt="SMMUv3 multiple CDs" width="750">

When SMOS hosts a virtual machine, the hypervisor must ensure that device DMA
cannot escape the guest's assigned address space.  The exact SMMU programming
is platform-dependent; the conceptual contract is the same as Zircon's VMO,
BTI, and IOMMU capability boundaries.

## TrustZone and secure calls

TrustZone divides the system into a Normal World (REE) and a Trusted World
(TEE), with hardware-enforced isolation.  SMOS normally runs in the Normal
World; a secure monitor or TEE may remain outside the SMOS product boundary.

<img src="assets/arm64/TrustZone_enabled_system.png" alt="TrustZone enabled system" width="750">

The Secure Monitor Calling Convention (SMCCC) defines register arguments and
results for `SMC` and `HVC` calls.  The caller must preserve the convention's
width, ownership, and error-return rules across an exception-level transition.

<img src="assets/arm64/SMC_calling.png" alt="SMC calling convention" width="750">

See [`Hypervisor.md`](Hypervisor.md) for SMOS virtualization boundaries.  TEE
firmware and secure-monitor interfaces remain platform-specific and outside
the default SMOS product.

## Debug and CoreSight

ARM debug has two broad operating styles.  Halting debug stops a PE so an
external debugger can inspect registers and memory; self-hosted debug lets
software observe debug events while the PE continues to run.  Breakpoints,
watchpoints, single-step state, and debug exceptions are subject to the current
EL and security state.  A debugger must not treat a halted core as equivalent
to a normally preempted Zircon thread: timers, locks, and device handshakes may
remain frozen.

The call stack is reconstructed from the frame-pointer/link-register chain or
from unwind metadata.  Optimized leaf functions may omit a frame pointer, and
an exception frame has a different layout from an AAPCS64 call frame.  When
diagnosing an EL1 fault, first identify which frame is an exception frame and
which registers were saved by the vector code before interpreting `x29` or
`x30`.

CoreSight trace hardware can connect instruction, exception, and software
trace sources to sinks such as an on-chip buffer or an external trace port.
Availability, security routing, and buffer ownership are implementation
defined.  SMOS's software `ktrace` and tracing-provider records are not a
substitute for CoreSight instruction trace; use the hardware path only when the
board exposes and authorizes it.

## Learning path for SMOS bring-up

Use the following order when learning or debugging a new arm64 board:

1. Confirm the entry EL, execution state, stack alignment, and vector base.
2. Read `SCTLR_EL1`, `TCR_EL1`, `TTBR0_EL1`, `TTBR1_EL1`, and `MAIR_EL1` after
   MMU enable to verify translation and memory attributes.
3. Validate GIC distributor/redistributor state before debugging a driver IRQ.
4. Check cache ownership and barriers before blaming a DMA or SMMU translation.
5. Correlate scheduler, exception, and device trace records by CPU and time.

This sequence moves from architectural invariants to platform routing and then
to workload behavior.  It prevents a symptom at EL0 from being diagnosed as a
driver or hypervisor problem before the EL1 translation and interrupt state is
known.

## SMOS arm64 mapping

| ARM64 mechanism | SMOS use |
| --- | --- |
| EL0/EL1 | dash and components at EL0; Zircon at EL1 |
| VM/VMAR/page tables | process isolation, BootFS mappings, and VMO-backed memory |
| GICv3 | QEMU physical IRQ delivery to Zircon and drivers |
| PCI ECAM | userspace PCI root and virtio device discovery |
| SMMU/IOMMU | DMA isolation when the platform supplies an SMMU |
| EL2 | optional arm64 hypervisor host for guest VMs |
| virtio-vsock | opt-in host file export through `vsock` on port 4050 |
| EL3/TrustZone | firmware and secure monitor outside the default product |

For boot order and image construction, see [`SMOS.md`](SMOS.md) and
[`Workflow.md`](Workflow.md).  For the user-facing dash commands, see
[`sdk/docs/man.txt`](../docs/man.txt).

The educational summaries above are derived from *ARM Cortex-A Series
Programmer's Guide for ARMv8-A*, ARM DEN0024A (2015), especially Chapters 3--6,
8--18.  The PDF remains the authoritative source for architectural details;
the SMOS mappings and product limitations in this document are maintained from
the local Zircon and QEMU sources.

---

Hustle Embedded OS, 2026.
