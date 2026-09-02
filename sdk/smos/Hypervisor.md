# SMOS as Hypervisor

## Hypervisor fundamentals

The SMOS virtualization boundary follows Fuchsia's Type-2 model: Zircon owns
the hypervisor kernel objects, while a user-space VMM owns guest policy,
emulated devices, and the guest lifecycle. A component must receive the
`HypervisorResource` capability before it can create guest or vCPU objects.
This capability route is the product's authorization boundary.

### vCPU execution and exits

`zx_vcpu_create` binds a vCPU object to the creating thread. That same thread
must perform vCPU state reads/writes and call `zx_vcpu_enter`. Entering the
vCPU is a blocking host operation: the return marks a transition back to the
host because the guest executed a VM exit. `zx_vcpu_kick` requests such a
return from another host control path.

```text
VMM thread
 │
 ├──► zx_vcpu_create(guest, entry)
 ├──► zx_vcpu_write_state(vcpu, state)
 ╰──► zx_vcpu_enter(vcpu)
       ├──► guest executes
       ├──► VM exit -> kernel classifies reason
       ╰──► return to VMM with exit state
```

The kernel handles architectural state and protected entry/exit. The VMM
interprets configured traps and emulates devices in user space. FIDL is not an
EL2 interface and is not used from the kernel exit handler.

### Guest memory and two-stage translation

`zx_guest_create` returns a guest object and a VMAR representing guest physical
address space. The VMM maps a VMO into that VMAR to provide guest RAM. Hardware
then performs two translations: the guest page tables translate guest virtual
addresses (GVA) to guest physical addresses (GPA), and Stage-2 translation
maps GPA to host physical addresses (HPA). A missing Stage-2 mapping can be
reported through a configured trap for emulation or policy handling.

```text
guest instruction
 │
 ╰──► guest page tables: GVA -> GPA
       │
       ╰──► Stage-2 tables: GPA -> HPA
             │
             ╰──► host RAM or configured trap
```

The guest VMAR is a capability-bearing mapping boundary; it does not grant the
guest arbitrary host VMOs or host address-space access. VMO rights, guest VMAR
permissions, and the VMM's handle ownership all remain part of the isolation
contract.

### Traps and virtual interrupts

`zx_guest_set_trap` lets the VMM register MMIO, port, or bell traps. A guest
MMIO access that is not backed by a Stage-2 mapping exits to the kernel, which
delivers the configured event to the VMM. The VMM emulates the access and may
inject a virtual interrupt before resuming the vCPU. Virtual timer and GIC
state are maintained by the architecture-specific hypervisor implementation.

```text
guest MMIO access
 │
 ╰──► Stage-2 miss / trap match
       │
       ╰──► port packet to VMM
             ├──► emulate device access
             ├──► update vCPU or device state
             ╰──► inject virtual interrupt and re-enter
```

These mechanisms are implemented under `zircon/kernel/object/guest_dispatcher.cc`,
`vcpu_dispatcher.cc`, and `zircon/kernel/arch/arm64/hypervisor/`. The current
SMOS product uses ARM64 QEMU and the C++ VMM described in the following
sections; the generic Fuchsia guest list is intentionally not part of this
document.

## Original Implementation

### Scope

The current SMOS virtualization runtime is the `smos_boot`
ARM64 implementation.  Its bootfs package is `smos-virtualization-host`.
It combines a C++ VMM and guest manager with Rust lifecycle, CLI, and virtio
device components.  This is a mixed-language component system, not a Rust
VMM with C++ libraries linked into the same process.

This is a Type-2 design: the SMOS kernel is the host kernel, and the C++
`vmm` component is a hosted user-space VMM.  The VMM obtains
`HypervisorResource`, creates guest and vCPU kernel objects, and services VM
exits and devices from user space.  ARM64 EL2 is used by the kernel while a
vCPU is executing, but EL2 is not yet the system-wide owning layer for host
and guest domains.

### Component Topology

```text
                         bootstrap component manager
                                      |
        +-----------------------------+-----------------------------+
        | offers HypervisorResource, VmexResource, SysInfo, roles   |
        v                             v                             |
+----------------------+    +---------------------------+           |
| vmm_launcher (Rust)  |    | zircon_guest_manager      |           |
| exposes              |    | (C++)                     |           |
| GuestLifecycle       |    | connects static vmm child |           |
| creates VMM children |    | reads guest configuration |           |
+----------+-----------+    | exposes ZirconGuestManager|           |
           |                +-------------+-------------+           |
           | Realm.CreateChild / OpenExposedDir          |          |
           v                                             |          |
  +-------------------------+                 +----------v----------+
  | vmm-N (C++, alternate)  |                 | vmm (C++, current)  |
  | VmmController + Vmm     |                 | VmmController + Vmm |
  | exposes GuestLifecycle  |                 | exposes Guest and   |
  +-----+-------+-------+---+                 | GuestLifecycle      |
                                              +-----+-------+-------+
        |       |       |                                           |
        |       |       +-- dynamic component/FIDL --> virtio_vsock   (Rust)
        |       +---------- dynamic component/FIDL --> virtio_rng     (Rust)
        +------------------ dynamic component/FIDL --> virtio_block   (Rust)
        +------------------ dynamic component/FIDL --> virtio_console (Rust)
```

`console-launcher` receives `ZirconGuestManager` from the bootstrap
component and uses the C++ guest manager to launch the packaged Zircon guest.
The current SMOS `zircon_guest_manager` has a static `vmm` child in its
component declaration. The package also contains `vmm_launcher`, which is an
alternate adapter that creates dynamic `vmm-N` children for other guest-manager
implementations. Each VMM instance includes the Rust virtio device components.

### GuestManager Framework

The SMOS product assembles the virtualization host as one bootfs package and
adds two bootstrap children. `zircon_guest_manager` owns guest policy and
configuration and connects to its static `vmm` child. `vmm_launcher` is a
separate bootstrap child that owns a dynamic VMM collection; it is an
independent lifecycle adapter and does not sit between either current manager
implementation and its static VMM child.

```text
SMOS bootstrap realm
        |
        | fuchsia.kernel.HypervisorResource, VmexResource
        | fuchsia.scheduler.RoleManager, SysInfo
        +------------------------------+
        |                              |
        v                              v
zircon_guest_manager             vmm_launcher
        |                              |
        | GuestManager                 | Realm.CreateChild
        | reads /guest_pkg/data/       | collection: virtual_machine_managers
        | zircon guest.cfg             v
        |                         vmm-N (C++)
        |                              |
        | GuestLifecycle.Create/Bind/Run
        |                              v
        |                         Vmm + VmmController
        |                              |
        |                              +--> virtio_console (Rust)
        |                              +--> virtio_block (Rust)
        |                              +--> virtio_rng (Rust)
        |                              +--> virtio_vsock (Rust)
        |
        +---- ZirconGuestManager --> console-launcher / guest CLI
```

The capability boundary is deliberate. The bootstrap realm offers the
hypervisor and executable-memory resources to the manager and launcher, while
the launcher offers those resources to each dynamic `vmm-N` child. The
`zircon_guest_manager` component receives the guest package directory and the
`GuestLifecycle` service from its static `vmm` child. The CML route in
`platform/products/smos_boot/meta/virtualization.bootstrap_shard.cml` exposes
only `ZirconGuestManager` to `console-launcher`.

The current product uses the C++ manager in
`userspace/virtualization/bin/guest_manager`. The Rust implementation in
`userspace/virtualization/bin/guest_manager_rs` follows the same FIDL contract
and is useful for tests and alternate products, but it is not the manager
selected by the SMOS bootstrap shard.

### GuestManager State Machine

```text
NOT_STARTED -- valid Launch --> STARTING -- Create OK --> RUNNING
     |                            |                         |
     | invalid config             | Create error            | guest exit / Run result
     v                            v                         v
NOT_STARTED                   STOPPED                  STOPPED

RUNNING -- ForceShutdown --> STOPPING -- Run completion --> STOPPED

STARTING or RUNNING -- lifecycle channel error --> VMM_UNEXPECTED_TERMINATION
VMM_UNEXPECTED_TERMINATION -- next Launch/reconnect --> STARTING
STOPPED -- valid Launch ---------------------------> STARTING
```

`STARTING`, `RUNNING`, and `STOPPING` all count as "started" for duplicate
launch and reconnect checks. A successful `Create` changes the state to
`RUNNING` before the `Launch` reply is sent; the asynchronous `Run` reply later
drives the state to `STOPPED`. A failed `Create` is reported to the caller as
`START_FAILURE` and also records the VMM error as the stop reason. A lifecycle
channel error is treated as an unexpected VMM termination and causes the next
launch to open a fresh lifecycle channel.

| Operation | Allowed state | Manager action | Reply timing |
| --- | --- | --- | --- |
| `Launch` | not started/stopped/VMM unexpected termination | Read and merge config, create VMM, bind guest controller, start `Run` | After `Create` succeeds; `Run` remains pending |
| `Connect` | starting/running/stopping | Forward another guest controller to `GuestLifecycle.Bind` | Immediately after bind is sent |
| `ForceShutdown` | any | Send `GuestLifecycle.Stop`, mark `STOPPING` | After the pending `Run` completes and cleanup runs |
| `GetInfo` | any | Return state, uptime, config snapshot, stop error, and diagnostics | Immediately; network and memory-pressure checks may query services |

### Launch and Device Flow

```text
Guest client       zircon_guest_manager          static vmm / Vmm
    |                       |                         |
    | Launch(config,        |                         |
    |  guest_controller)    |                         |
    |---------------------->|                         |
    |                       | if already started:     |
    |                       |   ALREADY_RUNNING       |
    |                       |                         |
    |                       | connect static vmm      |
    |                       |------------------------>|
    |                       |                         |
    |                       | Read guest.cfg and merge user config       |
    |                       | Apply memory/CPU defaults, MAC, cmdline    |
    |                       | state = STARTING                           |
    |                       |                         |                  |
    |                       | GuestLifecycle.Create(config)              |
    |                       |------------------------------------------->|
    |                       | GuestLifecycle.Bind(guest_controller)      |
    |                       |------------------------------------------->|
    |                       |                         | Vmm.Initialize   |
    |                       |                         | guest memory,    |
    |                       |                         | vCPUs, devices   |
    |                       |<-------------------------------------------|
    |                       | Create OK; state = RUNNING                 |
    |<----------------------| Launch OK                                  |
    |                       | GuestLifecycle.Run()                       |
    |                       |------------------------------------------->|
    |                       |                         | StartPrimaryVcpu |
    |                       |                         | and serve I/O    |
    |                       |                         |                  |
    |                       |                         | virtio children  |
    |                       |                         | receive StartInfo|
    |                       |                         | and signal Ready |
```

The `Launch` reply means that VMM creation and guest-controller binding have
completed; it does not mean that the guest has exited. `GuestLifecycle.Run` is
kept pending until the primary vCPU exits or teardown is requested. The C++
VMM creates guest memory, vCPUs, interrupt/UART/PCI state, and the configured
virtio controllers during `Initialize`. Each controller creates its matching
Rust child and exchanges `StartInfo`, queue configuration, and readiness over
the device-specific FIDL protocol.

### Dynamic VMM Creation (Alternate Path)

```text
Lifecycle client              VmmLauncher                  component manager
    |                              |                               |
    | Connect(GuestLifecycle)      |                               |
    |----------------------------->|                               |
    |                              | Realm.CreateChild(vmm-N)      |
    |                              |------------------------------>|
    |                              |                               | start vmm-N lazily
    |                              | Realm.OpenExposedDir(vmm-N)   |
    |                              |------------------------------>|
    |                              |<------------------------------|
    |                              | connect exposed GuestLifecycle|
    |                              |------------------------------>|
    |<-----------------------------|                               |
    | Create/Bind/Run now target vmm-N                             |
```

The standalone Rust launcher allocates monotonically increasing names
(`vmm-1`, `vmm-2`, ...) in the `virtual_machine_managers` single-run collection.
Realm creation or exposed-directory failures close the lifecycle channel with
an epitaph, which causes its lifecycle client to report a start failure. This
path is separate from the static `vmm` child used by the current SMOS C++ and
Rust manager implementations.

### Stop, Exit, and Recovery Flow

```text
Guest client       GuestManager          VmmController/Vmm         vmm component
    |                  |                         |                       |
    | ForceShutdown    |                         |                       |
    |----------------->| state = STOPPING        |                       |
    |                  | GuestLifecycle.Stop()   |                       |
    |                  |------------------------>|                       |
    |                  |                         | post teardown task    |
    |                  |                         | NotifyClientsShutdown |
    |                  |                         | destroy Vmm           |
    |                  |<------------------------| Run error/complete    |
    |                  | state = STOPPED         |                       |
    |<-----------------| complete pending shutdown callbacks             |
    |                  |                         |                       |
    | guest exits or   |                         |                       |
    | VMM reports err  |                         | ScheduleVmmTeardown   |
    |                  |<------------------------|                       |
    |                  | Handle Run result       |                       |
    |                  | state = STOPPED         |                       |
    |                  |                         |                       |
    | VMM process dies | lifecycle channel error |                       |
    |                  | state = VMM_UNEXPECTED_TERMINATION              |
    |                  | next Launch opens a new lifecycle channel       |
```

`VmmController::Stop` schedules teardown and acknowledges the stop request;
the manager deliberately delays `ForceShutdown` completion until the pending
`Run` callback has observed teardown. When a guest exits, the VMM posts the
same teardown path with the guest error, notifies guest clients, destroys its
`Vmm` object, and completes `Run`. Closing the lifecycle channel is separate:
it means the VMM component itself terminated, so the manager records
`VMM_UNEXPECTED_TERMINATION` and reconnects on the next launch.

### Rust/C++ Boundary

Rust and C++ are connected by component capabilities and FIDL over Zircon
channels.  They are built as separate ELF binaries and do not use an in-process
FFI boundary.

```text
C++ GuestManager -- fuchsia.virtualization.GuestLifecycle --> C++ VMM
Rust guest manager -- fuchsia.virtualization.GuestLifecycle --> Rust VmmLauncher
Rust VmmLauncher -- Realm child lifecycle ------------------> C++ VMM
C++ virtio controller -- fuchsia.virtualization.hardware.Virtio* --> Rust backend
```

- The Rust `vmm_launcher` only manages dynamic VMM component instances.  It
  does not create a guest, vCPUs, address space, or virtual hardware.  The
  current SMOS C++ manager connects directly to the static `vmm` child instead.
- The C++ VMM owns guest execution and the virtio controllers.  For example,
  `VirtioConsole::Start` creates `virtio_console` and sends its `StartInfo`
  through `fuchsia.virtualization.hardware.VirtioConsole`.
- Rust virtio components implement the device-side FIDL servers.  They consume
  the `StartInfo`, configure virtio queues, and process device I/O.

Consequently, retaining only the current Rust binaries and libraries is not a
complete virtualization stack.  The C++ VMM remains required until an
equivalent Rust implementation replaces guest creation, vCPU execution,
ARM64 platform emulation, PCI/virtio controllers, and guest management.

### Source and Capability Map

| Layer | Current SMOS source | Responsibility |
| --- | --- | --- |
| Product topology | `platform/products/smos_boot/meta/virtualization.bootstrap_shard.cml` | Starts `vmm_launcher` and `zircon_guest_manager`; routes resources and `ZirconGuestManager` |
| Guest manager | `userspace/virtualization/bin/guest_manager/guest_manager.cc` | Loads `/guest_pkg/data/guest.cfg`, merges overrides, tracks state, and owns lifecycle callbacks |
| Manager component | `platform/products/smos_boot/virtualization/meta/zircon_guest_manager.cml` | Provides `GuestManager`, mounts the guest package, and uses the static `vmm` child |
| VMM controller | `userspace/virtualization/bin/vmm/vmm_controller.cc` | Implements `Create`, `Bind`, `Run`, `Stop`, and asynchronous teardown |
| VMM component | `platform/products/smos_boot/virtualization/meta/vmm.cml` | Publishes `Guest`/`GuestLifecycle`, owns dynamic virtio collections, and receives hypervisor resources |
| Dynamic launcher | `userspace/virtualization/bin/vmm_launcher/src/vmm_launcher.rs` | Alternate `Realm`-based creation of `vmm-N` children |
| Kernel boundary | `zircon/kernel/object/guest_dispatcher.cc`, `zircon/kernel/object/vcpu_dispatcher.cc`, `zircon/kernel/arch/arm64/hypervisor/` | Guest/vCPU handles, Stage-2 mappings, traps, EL2 entry, and VM exits |

The authoritative control contract is
`sdk/fidl/fuchsia.virtualization/guest_manager.fidl`. Guest manager requests
cross the component boundary as FIDL channels; guest memory, vCPU handles,
interrupt state, and VM-exit handling remain below that boundary in the C++
VMM and Zircon kernel.


## Future Implementation

### Direction and Non-goal

The intended direction is a Type-1, EL2-first design based on the existing
ARM64 kernel implementation under `zircon/kernel/arch/arm64/hypervisor/`.
The Type-1 data plane owns CPU virtualization, Stage-2 translation, virtual
interrupt injection, and VM-exit dispatch at EL2.  SMOS user space remains
the control plane and device-backend environment.

This is a design target, not a statement that the current source tree already
boots SMOS as an EL1 management domain.  Reusing the current `Guest`,
`Vcpu`, and EL2 entry code through the existing guest syscalls alone remains a
hosted Type-2 arrangement.  The Type-1 transition additionally requires EL2
ownership from boot, explicit host/guest domain policy, and a stable
kernel-to-control-plane ABI.

### Existing Kernel Building Blocks

The future work should extend, rather than duplicate, the ARM64 hypervisor
implementation already present in Zircon.

```text
Kernel object and syscall layer
  sys_guest_create / sys_guest_set_trap / sys_vcpu_create / sys_vcpu_enter
                                  |
                                  v
GuestDispatcher / VcpuDispatcher
                                  |
                                  v
zircon/kernel/arch/arm64/hypervisor
  Guest::Create        -> VMID + GuestPhysicalAspace + Stage-2 mappings
  Guest::SetTrap       -> TrapMap and port-delivered MMIO/bell exits
  Vcpu::Create         -> per-vCPU El2State, HCR_EL2, GIC state
  Vcpu::Enter          -> arm64_el2_enter(vttbr, el2_state, hcr)
  vmexit_handler       -> PSCI, system-register, abort, timer, and trap paths
  GICv2/GICv3 support  -> virtual interrupt list-register management
```

`Guest::Create` allocates a VMID and guest physical address space.  A guest
VMAR is exposed through the guest object so that the controlling domain can
map guest RAM.  `Vcpu::Enter` derives `VTTBR_EL2` from that guest address
space, enters EL2, tracks guest GIC list registers, and invokes the VM-exit
handler after returning to the host kernel.  The existing VM-exit path already
handles or reports WFI/WFE, PSCI, selected system registers, instruction and
data aborts, virtual timer events, and virtual interrupts.

### Target Type-1 Topology

```text
                         Firmware / secure firmware
                                      |
                                      v
+---------------------------------------------------------------------+
| EL2: Zircon hypervisor core                                         |
|                                                                     |
|  early EL2 ownership  | Stage-2 GPA | VMID/vCPU | GIC virtualization|
|  exception vectors    | TrapMap     | VM-exit   | timer/interrupts  |
+-----------------------+-------------------------+-------------------+
                        |                         |
                        | control/event ABI       | guest EL1 entry
                        v                         v
+--------------------------------+     +------------------------------+
| EL1 management domain          |     | EL1 guest domain(s)          |
| SMOS kernel and user space     |     | Zircon or another guest OS   |
|                                |     |                              |
| C++ guest policy / lifecycle   |     | guest vCPUs and guest RAM    |
| Rust/C++ virtio backends       |     | virtio frontends             |
+----------------+---------------+     +------------------------------+
                 |
                 | FIDL only in the management domain
                 v
        component manager, vmm launcher, device components
```

The target does not move FIDL, component-manager lifecycle, or Rust virtio
code into EL2.  EL2 must not depend on user-space IPC or component execution.
Instead, it exposes a bounded event and handle interface to the management
domain; that domain decides guest policy and interacts with device backends.

### Target Execution Flow

```text
1. Boot
   Firmware enters Zircon with EL2 ownership retained by the hypervisor core.
   EL2 installs exception vectors and initializes CPU-local EL2 state.

2. Guest construction
   Management domain requests a guest and maps guest RAM.
   EL2 assigns a VMID, creates Stage-2 mappings, and creates vCPU EL2 state.

3. Guest entry
   EL2 loads VTTBR_EL2, HCR_EL2, guest registers, timer, and virtual GIC state.
   The selected vCPU runs the guest at EL1.

4. VM-exit
   EL2 classifies the exit:
     - handle locally: interrupt bookkeeping, timer, supported register state;
     - deliver to control plane: configured trap, MMIO/bell, vCPU startup,
       unsupported or policy-controlled operation.

5. Device service and resume
   The management domain maps the event to a virtio controller/backend request.
   Rust or C++ backend code completes I/O and requests a virtual interrupt.
   EL2 records/injects the interrupt through GIC list registers and resumes vCPU.
```

For the device path, the kernel-facing boundary should be based on the existing
guest trap and port model, or an explicitly designed successor with equivalent
rights and lifetime rules.  A direct EL2-to-FIDL path is out of scope: FIDL
continues after the event reaches the EL1 management domain.

### Type-2 to Type-1 Migration

```text
Phase 0  Document and test current Type-2 guest boot, console, block, RNG,
         vsock, lifecycle, and failure behavior.

Phase 1  Stabilize kernel interfaces already used by the VMM: guest memory,
         traps, vCPU state, port packets, interrupt injection, and teardown.

Phase 2  Reuse and validate the existing ARM64 EL2 code in isolation:
         Guest/Stage-2, Vcpu/El2State, GICv2/GICv3, and VM-exit handling.
         This phase can still be Type-2.

Phase 3  Add EL2-first boot and exception ownership.  Define the management
         domain contract and ensure only the EL2 core owns global EL2 state.

Phase 4  Move guest execution to the Type-1 domain model while retaining the
         user-space lifecycle and virtio backends behind the control/event ABI.

Phase 5  Validate guest boot, vCPU lifecycle, Stage-2 isolation, VM-exit
         coverage, interrupt delivery, and every retained virtio backend.
```

### Required Decisions Before Implementation

- Define whether SMOS itself is the EL1 management domain or whether a
  smaller dedicated management domain is introduced.
- Define the early boot handoff that preserves EL2 ownership across firmware,
  boot-shim, and Zircon initialization.
- Define the control-plane event ABI, including trap payloads, memory/handle
  rights, interrupt injection, cancellation, and teardown ordering.
- Define isolation and recovery semantics when a user-space virtio backend or
  management component fails while a guest is running.
- Define the supported ARM64 hardware profile, including GIC version,
  virtualization extensions, timer behavior, PSCI behavior, and multi-vCPU
  limits.

Until these decisions and their tests are complete, the shipped implementation
remains the Type-2 architecture described above.


---

SMOS [microkernel]
