# SMOS Architecture Guide

<img src="assets/SMOS.png" alt="smos" width="750">


SMOS is a console-only Fuchsia/Zircon server profile. It retains the original
Zircon dash shell, process and storage primitives, component and driver
frameworks, diagnostics, QEMU serial/block/RTC/random devices, virtio socket,
and the arm64 virtualization host stack. Runtime graphics, UI, netstack,
physical network drivers, WLAN, Bluetooth, audio, camera, update, and recovery
packages are deliberately absent. Virtio socket remains as a virtualization
transport and does not install a conventional network stack.

The compact source tree must remain below 500,000 KiB (524,288,000 bytes), not
counting `.git/`, generated `out/`, or the separately measured standalone SDK
`prebuilt/` payload.

## Microkernel architecture

<img src="assets/zircon-microkernel.png" alt="smos" width="750">


A microkernel keeps the privileged kernel small and moves policy-heavy services
to user space. The kernel provides mechanisms that must be trusted by every
process: CPU scheduling, virtual memory, address spaces, kernel objects,
capability-bearing handles, interrupt delivery, and the syscall entry path.
Higher-level policy is implemented by isolated processes and components that
communicate through channels and framework protocols.

```text
┌──────────────────────────── SMOS user space ──────────────────────────────┐
│ component_manager │ drivers │ fshost │ console │ VMM │ dash               │
│      FIDL channels, namespaces, devfs, files, and user policy             │
└──────────────────────────────────┬────────────────────────────────────────┘
                                   │
                    handles + rights + IPC messages
                                   │
┌──────────────────────────────────▼────────────────────────────────────────┐
│                              Zircon kernel                                │
│ processes/threads │ VMOs/VMARs │ channels/sockets │ ports │ syscalls      │
│ jobs/handles      │ interrupts │ timers/signals   │ VM    │ object rights │
└──────────────────────────────────┬────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼────────────────────────────────────────┐
│                       hardware, firmware, and monitors                    │
│              UART │ QEMU virtio │ GIC/PLIC │ EL2/EL3 monitor              │
└───────────────────────────────────────────────────────────────────────────┘
```

The boundary is a separation of authority, not merely a directory split. A
user-space driver cannot directly modify another process's address space, and a
component receives only the handles and namespace entries offered to it by the
component framework. A request crosses the boundary through a syscall or an
IPC message; the kernel validates the caller's handle rights and memory ranges
before performing the operation. This keeps the trusted computing base focused
and makes service failure more containable: restarting a driver-host does not
restart the kernel or unrelated components.

In SMOS, the boot-shim and the Zircon physical loader prepare the kernel and
its boot items. `userboot` then starts `component_manager`, which constructs the
user-space component graph. `driver_manager` and `driver_index` discover and
launch user-mode drivers, while `console-launcher` starts the interactive dash
shell. The detailed physical hand-off and component startup sequence is
documented in [Boot-to-driver flow](#boot-to-driver-flow) and [Complete Zircon
boot-to-userspace code path](#complete-zircon-boot-to-userspace-code-path).


### Zircon microkernel introduction

Zircon is the low-level kernel used by Fuchsia and by SMOS. It is an
object-based microkernel:

> kernel resources are represented by **typed objects**, and processes access those
> objects through **local handles** with **explicit rights**.

The handle model is the common substrate for component startup, FIDL IPC,
driver capabilities, memory mappings, and asynchronous waits.

The kernel's primary responsibilities are:

| Area | Zircon responsibility | SMOS consequence |
| --- | --- | --- |
| Tasks | jobs, processes, threads, scheduling, and task lifecycle | components and `driver-host` instances remain isolated processes |
| Memory | VMOs, VMARs, page mapping, faults, and pager hooks | BootFS, executable images, stacks, and shared buffers use the standard VM model |
| IPC and waiting | channels, sockets, ports, events, signals, and timers | FIDL services and console/driver event loops share one kernel object model |
| Hardware boundary | interrupts, MMIO/resource checks, BTI/IOMMU and architecture entry paths | user-mode drivers receive only the hardware capabilities they are offered |
| ABI and diagnostics | `zx_*` syscalls, vDSO entry points, debuglog, and exception delivery | SMOS keeps the standard Zircon syscall and object ABI |

Zircon does not provide the product's policy services. It does not resolve
component URLs, match driver bind rules, mount a user-facing filesystem, or
implement the dash command language. Those functions belong to
`component_manager`, the driver framework, storage services, and user-space
programs. The kernel supplies the process, memory, IPC, and capability
mechanisms on which those services depend.

This distinction matters when reading the SMOS source tree. Changes under
`zircon/kernel/` modify trusted kernel mechanisms and must preserve the
standard Zircon ABI. Changes under `userspace/` usually modify policy,
protocols, or product assembly. SMOS reduces the user-space graph for a
console-only server profile; it does not fork Zircon into a separate server
kernel. The following runtime diagram and boot sections show how the two
halves join at `userboot` and `component_manager`.

## Runtime architecture

SMOS follows the standard Zircon/Fuchsia boot contract, but the product graph
only starts the console and the drivers needed by the headless server profile.
The boundary between kernel facilities and user-space drivers is important: the
kernel owns scheduling, VM, handles, interrupts, and syscall/object primitives;
the driver framework starts most concrete device drivers in isolated user-mode
`driver-host` components, where device protocols are published to clients.

```
SMOS runtime layers (logical view; boxes are components or subsystems):

    +------------------------ BOOT / PHYSICAL MODE -------------------------+
    | Firmware or QEMU                                                      |
    |        |                                                              |
    |        v                                                              |
    | Architecture boot-shim (arm64 / riscv64)                              |
    |        | parses DTB, cmdline; adds UART/memory/CPU/platform boot items|
    |        v                                                              |
    | ZBI: kernel + data ZBI                                                |
    +-------------------------------+---------------------------------------+
                                    |
                                    v
    +--------------------------- ZIRCON KERNEL -----------------------------+
    | phys hand-off -> Zircon kernel -> jobs/processes/VMOs/channels        |
    |                              -> interrupts and syscalls               |
    +-------------------------------+---------------------------------------+
                                    |
                                    v
    +------------------------- BOOTSTRAP COMPONENTS ------------------------+
    | userboot -> component_manager (root and bootstrap realms)             |
    |                         |                    |                        |
    |                         |                    +--> console + launcher  |
    |                         +--> fshost / storage                         |
    |                         +--> driver_manager                           |
    +-------------------------+--------------------+------------------------+
                              |                    |
                              v                    v
    +---------------------- USER-SPACE DRIVERS -----------------------------+
    | driver_index --bind rules--> driver-host --starts--> user-mode drivers|
    |       (match)                 (isolated)      (QEMU board, serial,    |
    |                                                 block, RTC, RNG)      |
    |                                   |                                   |
    |                                   +--------------+                    |
    |                                                  v                    |
    |                         devfs (/dev, /dev-topological)                |
    +--------------------------------------------------+--------------------+
                                                       |
                                                       v
    +------------------------------ CLIENTS --------------------------------+
    | console -> dash shell -> open/connect device protocols or FIDL        |
    +-----------------------------------------------------------------------+
```

These diagrams are a logical view, not a single process tree. `driver_manager`,
`driver_index`, `devfs`, and `driver-host` are components connected through FIDL
and framework protocols. A device node is matched by `driver_index`, launched by
`driver_manager`, and then exported by the driver to `devfs`; a shell command or
another component consumes that device through the published protocol.

### Boot-to-driver flow

The following sequence describes the path exercised by the SMOS QEMU images.
The arm64 and riscv64 shims both parse the incoming devicetree, populate boot
items, and transfer control to the ZBI; architecture-specific items differ
(GIC/PSCI/timer on arm64, PLIC/timer on riscv64).

The phys handoff has two distinct `PhysMain` implementations in two different
ELF images.  The boot-shim `PhysMain` prepares the incoming ramdisk and calls
`BootZbi::Boot()`.  The Zircon `kernel.phys` image is then entered separately;
its `PhysMain` calls `ZbiMain`, which loads the next phys module and hands off to
the Zircon kernel.  The boot-shim `PhysMain` does not call `ZbiMain` directly.

```
Boot-to-driver sequence:

    1. Firmware/QEMU
       |
       | enters with DTB, cmdline and ramdisk
       v
    2. boot-shim (phys)
       |-- linux-arm64-boot-shim PhysMain (arm64)
       |-- initialize memory and UART
       |-- parse devicetree
       |-- append UART, memory, CPU and platform boot items
       |-- BootZbi::Boot() transfers control to the ZBI kernel
       v
    3. Zircon phys handoff
       |-- kernel.phys PhysMain (zbi-main.cc)
       |-- ZbiMain parses the ZBI and loads the next phys module
       |-- PhysLoad hands off to the Zircon kernel image
       v
    4. Zircon + userboot
       |-- create kernel objects, VM and early services
       v
    5. component_manager
       |-- starts driver_manager, driver_index and devfs
       |-- starts console and console-launcher
       v
    6. Driver framework
       |-- discovers device nodes and evaluates bind rules
       |-- asks driver_index for a matching driver
       v
    7. driver-host
       |-- launches the matching user-mode driver component
       |-- driver publishes node/protocol and lifecycle state
       v
    8. devfs + console/dash
       |-- driver is exposed through /dev or /dev-topological
       `-- dash opens the device or calls its FIDL protocol
```

For a direct ZBI boot without a boot-shim, step 2 is omitted and the ZBI
kernel's `PhysMain` is entered directly.  The arm64 boot-shim source is
`zircon/kernel/arch/arm64/phys/boot-shim/linux-arm64-boot-shim.cc`; the ZBI
kernel entry is supplied by `zircon/kernel/phys/zbi-main.cc` through the
`zbi_executable` build target.

At the end of this path the interactive prompt is available as `smos:\> `.
The shell is a client of the component and device services; it is not the
driver manager and does not load drivers itself.

### Complete Zircon boot-to-userspace code path

The path below follows the real ELF and function boundaries. The boot-shim
`PhysMain` and the `kernel.phys` `PhysMain` belong to different physical
images: the former prepares the ZBI, while the latter parses it and loads the
next physical module. Zircon kernel C++ initialization starts only after the
handoff reaches `zircon/kernel/top/main.cc`.

```text
QEMU -kernel boot-shim -initrd data.zbi
  |
  +-- arch boot-shim PhysMain(fdt)
  |     linux-*-boot-shim.cc
  |     |-- InitMemory(fdt, nullptr)
  |     |-- DevicetreeBootShim::Init()         # UART/memory/CPU/interrupt ZBI items
  |     |-- BootZbi::Init(ramdisk)
  |     |-- BootZbi::Load(...)
  |     |-- BootZbi::AppendItems(data_zbi)
  |     `-- BootZbi::Boot() -> ZbiBoot(kernel_entry, data_zbi)
  |
  +-- kernel.phys PhysMain(zbi, ticks)
  |     zircon/kernel/phys/zbi-main.cc
  |     |-- SetBootOptions() / SetUartConsole()
  |     |-- InitMemory(zbi, &aspace)
  |     |-- KernelStorage::Init()              # unpack STORAGE_KERNEL/BOOTFS
  |     |-- ElfImage::Init(bootfs, phys_next)
  |     |-- ElfImage::Load() / Relocate()
  |     `-- ElfImage::Handoff<PhysLoadHandoffFunction>()
  |
  +-- physboot / kernel ELF  PhysLoadHandoff()
  |     zircon/kernel/phys/physload-module.cc
  |     |-- restore log, BootOptions, address-space and allocator state
  |     `-- PhysLoadModuleMain() -> BootZircon()
  |           |-- load "physzircon" from bootfs
  |           |-- HandoffPrep::DoHandoff()
  |           `-- kernel.Handoff(PhysHandoff*) -> PhysbootHandoff
  |
  +-- Zircon kernel entry  PhysbootHandoff -> lk_main(handoff_paddr)
  |     zircon/kernel/arch/{arm64,riscv64}/start.S
  |     |-- HandoffFromPhys()
  |     |-- thread_init_early(), dlog_init_early()
  |     |-- arch_early_init(), platform_early_init()
  |     |-- vm_init_preheap(), heap_init(), vm_init()
  |     |-- topology_init(), kernel_init()
  |     |-- bootstrap2() creates and schedules the kernel init thread
  |     `-- kernel_shell_init() (when enabled)
  |
  +-- kernel creates the first user process  userboot_init(HandoffEnd)
  |     zircon/kernel/top/main.cc -> zircon/kernel/lib/userabi/userboot.cc
  |     |-- ProcessDispatcher::Create(root_job, "userboot")
  |     |-- bootstrap_vmos(): ZBI, vDSO, resources and root-job handles
  |     |-- UserbootImage::Map(): userboot rodso + vDSO
  |     |-- create the initial stack and ThreadDispatcher
  |     `-- thread->Start(entry, sp, bootstrap_channel, vdso_base)
  |
  +-- userspace userboot  _start(arg)
  |     zircon/kernel/lib/userabi/userboot/start.cc
  |     |-- Bootstrap(channel) reads the kernel bootstrap message
  |     |-- GetBootfsFromZbi() / GetOptionsFromZbi()
  |     |-- default userboot.next = bin/component_manager+--boot
  |     |-- elf_load_bootfs() + elf_load_vdso()
  |     |-- build zx_proc_args_t, /svc, BOOTFS/VMO and resource handles
  |     |-- zx_channel_write() sends the child bootstrap message
  |     `-- zx_process_start() starts bin/component_manager
  |
  `-- userspace component_manager  main()
        userspace/sys/component_manager/src/main.rs
        |-- parse --boot and RuntimeConfig/root_component_url
        |-- BuiltinEnvironmentBuilder::build()
        |     `-- receive fuchsia.boot.Userboot and mount BootFS as /boot
        |-- BuiltinEnvironment::run_root()
        |     |-- bind_service_fs_to_out()
        |     |-- Model::start()
        |     `-- root.ensure_started(StartReason::Root)
        `-- resolve/start root CML; eager children continue with console and drivers
```

#### 1. boot-shim to `kernel.phys`

The arm64 entry point is
`zircon/kernel/arch/arm64/phys/boot-shim/linux-arm64-boot-shim.cc:53`,
and the riscv64 entry point is
`zircon/kernel/arch/riscv64/phys/boot-shim/linux-riscv64-boot-shim.cc:49`.
Both call `InitMemory` without an MMU, then use `DevicetreeBootShim` to turn
devicetree data into ZBI items. They then execute
`BootZbi::Init`, `Load` and `AppendItems`, ending at `BootZbi::Boot` in
`zircon/kernel/phys/boot-zbi.cc:450`, which jumps to the physical kernel entry.

```text
BootZbi::Boot()
  |
  `-- BootZbi::ZbiBoot() -> arch::ZbiBoot()
                              |
                              `-- arch::ZbiBootRaw()
```

- [zbi-boot.h][1]

The entered `kernel.phys` entry point is
`zircon/kernel/phys/zbi-main.cc:19`. It performs common physical-stage setup
(relocation, command line and UART), and then
calls `ZbiMain`. At `zircon/kernel/phys/physload.cc:47`, `ZbiMain` initializes
an identity-mapped address space, unpacks the kernel package, and loads the
next ELF named by `kernel.phys.next`. `PhysLoadHandoff`
(`zircon/kernel/phys/physload-module.cc:28`) takes over the state;
`PhysLoadModuleMain`/`BootZircon` loads `physzircon`,
`HandoffPrep::DoHandoff` (`zircon/kernel/phys/handoff-prep.cc:359`) constructs
`PhysHandoff`, and the architecture-specific `PhysbootHandoff` entry is called.

- [handoff-prep.cc][2]

#### 2. Kernel initialization and scheduler startup

The arm64 assembly entry is
`zircon/kernel/arch/arm64/start.S:63`; the riscv64 counterpart is
`zircon/kernel/arch/riscv64/start.S:23`. They set the boot
stack, preserve the `PhysHandoff` address, and call `lk_main`. `lk_main` at
`zircon/kernel/top/main.cc:66` imports the phys handoff, initializes the thread
context, debuglog, architecture/platform, VM, heap, topology and kernel
subsystems, and creates the `bootstrap2` thread. `bootstrap2` at `:169`
completes late initialization, ends the handoff, runs the optional kernel shell,
and calls `userboot_init` at `:204-205`.

#### 3. How the kernel creates and starts userspace `userboot`

`userboot_init` is at `zircon/kernel/lib/userabi/userboot.cc:308`. It creates
the `userboot` process and root VMAR under the root job, prepares startup
handles for the vDSO, ZBI VMO, BootOptions, root job, and MMIO/IRQ/SMC/System
resources (`bootstrap_vmos`). It creates a channel for the kernel to write the
bootstrap message and for user space to receive it, then maps the userboot code,
vDSO, and initial stack, creates a thread, and enters user space at `:409-412`
with `ThreadDispatcher::Start(entry, sp, hv, vdso_base)`.

- [userboot.cc][3]

Here `hv` is the channel handle passed to the user-space `_start`; it is not a
file descriptor, but a Zircon channel carrying `zx_proc_args_t` and capability
handles.

### Detailed `userboot_init` call flow

```text
bootstrap2(handoff)
 │
 ╰──► EndHandoff()
       │
       ╰──► userboot_init(handoff_end)
             │
             ├──► MessagePacket::Create(..., kHandleCount)
             │
             ├──► ProcessDispatcher::Create(root_job, "userboot")
             │     ├──► install process + root VMAR handles
             │     ╰──► get_resource_handle(MMIO, IRQ, SMC*, SYSTEM)
             │
             ├──► get_job_handle() -> root job handle
             │
             ├──► bootstrap_vmos(handoff_end, handles)
             │     ├──► InstrumentationData::GetVmos()
             │     ├──► copy extra physical VMOs + ZBI handle
             │     ├──► VDso::Create(vdso, time_values, variants)
             │     ├──► crashlog_to_vmo()
             │     │     ╰──► crashlog.Recover() + crashlog_stash()
             │     ├──► BootOptions::Show() -> get_vmo_handle()
             │     ╰──► CounterDesc/CounterArena -> get_vmo_handle()
             │
             ├──► ChannelDispatcher::Create(user_handle, kernel_handle)
             ├──► kernel_handle.Write(msg)
             ├──► MapHandleToValue(user_handle) -> hv
             ├──► UserbootImage::Map(vmar, &vdso_base, &entry)
             │     ├──► root_vmar->Allocate()
             │     ├──► RoDso::Map(userboot image)
             │     ╰──► VDso::Map()
             │
             ├──► VmObjectPaged::Create(stack)
             │     ╰──► vmar->Map(stack) -> sp
             ├──► ThreadDispatcher::Create(process, "userboot")
             ├──► thread->Initialize()
             ├──► StartRootJobObserver()
             ╰──► thread->Start(entry, sp, hv, vdso_base)
                   ╰──► userboot::_start(hv) -> Bootstrap(hv)
```

The call order above follows `userboot.cc:308-417`; `bootstrap2` supplies the
handoff at `zircon/kernel/top/main.cc:169-205`. `bootstrap_vmos` consumes the
physical handoff before the root VMAR is used, then returns the mapped userboot
image and vDSO state. `SMC*` is populated only on arm64; the other resource
handles follow the architecture-independent path.

Every status check in this kernel path is guarded by `ASSERT` or `ZX_ASSERT`.
A failed allocation, mapping, channel write, or thread start therefore stops
the kernel path instead of returning an error to a caller. After the final
`ThreadDispatcher::Start`, `hv` is the user-side channel handle carrying the
bootstrap message, `sp` is the ABI-compliant initial stack pointer, and
`vdso_base` identifies the mapped vDSO used by userboot.

#### 4. Userspace `userboot` loads `userboot.next`

The first user-space instruction is at
`zircon/kernel/lib/userabi/userboot/start.cc:568`: `_start(arg)` calls
`Bootstrap(zx::channel{arg})`. `Bootstrap` reads the kernel message, decompresses
the ZBI's `ZBI_TYPE_STORAGE_BOOTFS`, and parses `userboot.*` command-line
options in `GetOptionsFromZbi`. The option definitions are in `option.cc:16-28`;
the default when no value is supplied is `bin/component_manager+--boot`.

`launch_process` calls `StartChildProcess`, which uses `elf_load_bootfs` to
load the ELF/interpreter and `elf_load_vdso` to map the vDSO, allocates a stack,
places `/svc`, the BootFS VMO, debuglog, process/VMAR/thread self handles and
resource handles into `ChildMessageLayout`, sends the message at
`start.cc:369-376`, and calls `zx_process_start`. Thus the final kernel ABI
operation from the kernel to the first ordinary user-space process is
`zx_process_start`, not a Rust call inside component manager.


#### 5. `component_manager` establishes the userspace root

The `bin/component_manager` entry point is
`userspace/sys/component_manager/src/main.rs:49`. It parses startup arguments,
loads `RuntimeConfig`, and constructs `BuiltinEnvironment`. At
`userspace/sys/component_manager/src/builtin_environment.rs:306-350`, it
consumes the `fuchsia.boot.Userboot` startup handle, receives BootFS entries and
`SvcStash`, creates and binds the `/boot` VFS, and registers builtin ELF runners,
resolvers and framework capabilities.

`main` finally calls `BuiltinEnvironment::run_root` (`builtin_environment.rs:1782`),
which binds the outgoing service FS and calls `Model::start`. `Model::start`
(`userspace/sys/component_manager/src/model/model.rs:99-128`) resolves and
starts the root component through `root.ensure_started(StartReason::Root)`;
the root URL comes from `RuntimeConfig.root_component_url`. From this point,
component manager owns component ELF runners, startup arguments, namespaces and
capability routing, while Zircon continues to provide process/thread/VMO/channel
objects and the syscall ABI.

The endpoint is not "the kernel loading a shell." The shell, console, driver
manager, and driver-host are later user-space components in the root component
graph. They start through component-manager-routed FIDL/channels and devfs
capabilities, after which the `smos:\> ` prompt becomes available.

### Boot-shim build, image, and launch linkage

The build is deliberately split into two artifacts. The boot-shim is the
QEMU `-kernel` image, while the assembled ZBI is passed as QEMU `-initrd`.
The boot-shim is therefore not the final Zircon kernel and the ZBI is not a
generic Linux initrd; the Linux boot protocol is only the transport used to
enter the Zircon physical loader.

```text
Makefile
  |
  +-- make configure ARCH=arm64|riscv64
  |     `-- tools/smos-boot/configure.sh ARCH
  |           |-- validate standalone SDK
  |           |-- select release/platform/boards/smos-qemu-<arch>.gni
  |           |-- import release/platform/products/smos_boot.gni
  |           `-- gn gen out/smos-boot-<arch>
  |
  +-- make build ARCH=ARCH
  |     `-- tools/smos-boot/build.sh ARCH
  |           |-- ninja release/images/fuchsia:fuchsia_assembly
  |           |-- ninja kernel.phys_ARCH/linux-ARCH-boot-shim.bin
  |           |-- ninja userspace/smos_boot/virtcheck:virtcheck_test
  |           `-- artifacts.py -> out/smos-boot-ARCH/artifacts.env
  |
  `-- make run ARCH=ARCH
        `-- tools/smos-boot/run-qemu.sh ARCH
              `-- zircon/scripts/run-zircon
                    `-- qemu -kernel <boot-shim> -initrd <ZBI>
```

`configure.sh` accepts exactly one architecture. It validates the SDK for both
supported architectures before generating the selected output directory, so a
missing file in the standalone SDK is reported before GN runs. The generated
`out/smos-boot-<arch>/args.gn` contains the board import, product import, SDK root,
`smos_boot_build = true`, `smos_minimal_assembly = true`, and the
small set of verification labels. It does not create or link a source-root
`prebuilt/` directory.

The product import in `release/platform/products/smos_boot.gni` selects the bootstrap
assembly with a curated platform-AIB allowlist, FVM ramdisk storage, and the
minimal SMOS source profile. In
`release/images/fuchsia/BUILD.gn`, the assembly records
`qemu_boot_shim.path` as its `qemu_kernel`. For arm64 and riscv64 the default
`qemu_boot_format` is `linuxboot`, which resolves to:

| Architecture | GN boot-shim target | Built file |
| --- | --- | --- |
| arm64 | `//zircon/kernel/arch/arm64/phys/boot-shim:linux-arm64-boot-shim` | `out/smos-boot-arm64/kernel.phys_arm64/linux-arm64-boot-shim.bin` |
| riscv64 | `//zircon/kernel/arch/riscv64/phys/boot-shim:linux-riscv64-boot-shim` | `out/smos-boot-riscv64/kernel.phys_riscv64/linux-riscv64-boot-shim.bin` |

The image assembly builds the ZBI from the Zircon kernel item and the selected
BootFS/data items. `build.sh` does not guess the ZBI path: `artifacts.py`
queries GN metadata for `//release/images/fuchsia:fuchsia.copy_zbi`, reads the
`qemu_kernel` field from the product assembler's `image_assembly.json`, and
writes canonical, in-tree paths to `out/smos-boot-<arch>/artifacts.env`:

```sh
cat out/smos-boot-arm64/artifacts.env
# QEMU_KERNEL=/.../out/smos-boot-arm64/kernel.phys_arm64/linux-arm64-boot-shim.bin
# ZBI=/.../out/smos-boot-arm64/smos.zbi
```

This metadata step matters when the assembly output name changes. Launching a
stale ZBI by hand can otherwise pair a new boot-shim with an old user-space
image.

### Image Loading

`run-qemu.sh` first runs `preflight.sh`, checks `artifacts.env`, and rejects
artifact paths outside the source tree. It then invokes
`zircon/scripts/run-zircon` with the following SMOS-specific arguments:

```sh
zircon/scripts/run-zircon \
  -a arm64 \
  -t out/smos-boot-arm64/kernel.phys_arm64/linux-arm64-boot-shim.bin \
  -z out/smos-boot-arm64/smos.zbi \
  -m 2048 -s 8 --no-kvm --no-virtio --gic=3 \
  -q "$SMOS_SDK_ROOT/prebuilt/third_party/qemu/linux-x64/bin"
```

`run-zircon` converts `-t` to QEMU `-kernel` and `-z` to QEMU `-initrd`.
For arm64 it selects `qemu-system-aarch64`, `virt,highmem-ecam=off`, and the
requested GIC version. For riscv64 it selects `qemu-system-riscv64`, the
`virt` machine, and the `rv64` CPU with the required vector/SVPBMT features.
The script also appends `kernel.entropy-mixin` and
`kernel.halt-on-panic=true` to the kernel command line.

The resulting handoff is:

```text
QEMU Linux boot protocol
  |
  | -kernel linux-<arch>-boot-shim.bin
  | -initrd smos.zbi
  v
<arch> boot-shim PhysMain(fdt)
  |-- InitMemory(fdt, nullptr): early physical allocator, no MMU
  |-- DevicetreeBootShim::Init(): UART, memory, CPU, timer, interrupt items
  |-- BootZbi::Init(ramdisk): validate ZBI and locate kernel item
  |-- BootZbi::Load(): place the Zircon kernel and data ZBI
  |-- BootZbi::AppendItems(): append boot-shim-generated ZBI items
  `-- BootZbi::Boot(): architecture-specific entry handoff
        |
        v
kernel.phys PhysMain -> zbi-main.cc -> ZbiMain
  |-- parse kernel command line and configure the UART
  |-- create identity-mapped physical-loader address space
  |-- read kernel.phys.next from the ZBI BootFS
  |-- load and relocate the next ELF physical module
  `-- PhysLoadHandoff -> Zircon kernel entry
```

The arm64 shim is implemented in
`zircon/kernel/arch/arm64/phys/boot-shim/linux-arm64-boot-shim.cc`; the riscv64
counterpart is
`zircon/kernel/arch/riscv64/phys/boot-shim/linux-riscv64-boot-shim.cc`.
Both use the shared `BootZbi` implementation, but their devicetree item sets
are different: arm64 adds GIC/PSCI/timer information, while riscv64 adds
PLIC/timer and boot-hart topology information. The shared Zircon physical
handoff is implemented by `zircon/kernel/phys/zbi-main.cc` and
`zircon/kernel/phys/physload.cc`.

### SMOS runtime boundary

Retained runtime pieces are the Zircon kernel, component framework, storage
and diagnostics primitives, console/dash, QEMU serial/block/RTC/random devices,
virtio socket, and the arm64 virtualization host support. Graphics and UI,
netstack and physical network drivers, WLAN, Bluetooth, audio, camera, update,
recovery, virtio-gpu, display input, virtual sound, Wayland, Magma, Mesa, and
Vulkan are outside this product's runtime graph. Virtio socket is a transport;
it does not imply that a conventional network stack is installed.

## Kernel modules

SMOS does not replace the Zircon kernel with a special server kernel. Its
product configuration selects a smaller user-space assembly while retaining
the kernel's fundamental resource model. The sections below describe the
kernel mechanisms a console process or user-space driver uses; "modules" here
means logical subsystems, not dynamically loaded kernel objects.

### SMOS syscall implementation

<img src="assets/kernel/overview.png" alt="overview" width="750">

SMOS does not define a second syscall ABI or a private syscall table. User
processes use the standard Zircon `zx_*` interface, and the product graph only
changes which user-space clients and kernel features are packaged. The retained
`zx_smc_call` syscall is a useful example because it crosses from a user process
to the arm64 Secure Monitor Calling Convention (SMCCC) implementation.

```text
user code
   |
   | zx_smc_call(resource, parameters, result)
   v
zircon/vdso/smc.fidl
   |
   | Zither generates declarations, syscall number and wrappers
   v
arm64 vDSO: syscalls-arm64.S
   |
   | x16 = syscall number, x0-x7 = arguments, svc #0
   v
arm64 EL0 exception path: exceptions.S
   |
   | bounds check -> .Lsyscall_table -> wrapper_smc_call
   v
kernel syscall veneer: syscalls.cc
   |
   | PC validation, tracing, CPU statistics, argument marshalling
   v
sys_smc_call(): kernel/lib/syscalls/driver.cc
   |
   | copy_from_user -> SMC resource/range validation
   v
arch_smc_call(): driver_arm64.cc
   |
   `--> arm_smccc_smc() -> smc #0 -> EL3/secure monitor
```

The interface definition is the source of the public contract:
`zircon/vdso/smc.fidl` describes `zx_smc_call`, its parameter/result records,
and error behavior. The Zither build generates the C declarations under
`zircon/syscalls/internal`, syscall numbers, `kernel.inc`, and the vDSO wrapper
assembly. The generated `kernel.inc` is included by both the arm64 exception
table and the kernel syscall veneer, so the numeric ID, dispatch entry, and
kernel prototype remain synchronized.

On arm64, the generated vDSO wrapper places the syscall number in `x16`, leaves
up to eight arguments in `x0` through `x7`, and executes `svc #0`. The exception
handler rejects an out-of-range ID, indexes a 16-byte syscall jump table, and
branches to the generated `wrapper_smc_call`. The common veneer in
`zircon/kernel/lib/syscalls/syscalls.cc` verifies that the return PC is an
approved vDSO call site, records tracing/statistics, invokes the typed kernel
entry point, and writes the status back to the saved iframe before returning to
EL0.

`sys_smc_call` in `zircon/kernel/lib/syscalls/driver.cc` then performs the
security boundary checks. It rejects null pointers, copies the parameter record
from user memory, extracts the SMCCC service number from `func_id`, and checks
that the caller's resource handle authorizes that service range. Only after
these checks does `driver_arm64.cc` call `arm_smccc_smc`, copy `x0`-`x3` and
`x6` into `zx_smc_result_t`, and copy the result back to user memory. The
riscv64 implementation returns `ZX_ERR_NOT_SUPPORTED`, so the syscall remains
ABI-compatible while its architecture-specific operation is unavailable.

The SMC resource is not an unrestricted user capability: userboot receives the
SMC resource handle, and the kernel's resource allocator defines the permitted
service-call ranges. A wrong handle, unauthorized service number, invalid user
pointer, or unsupported architecture fails before entering the monitor.

This path is separate from a kernel console command. A command sent through
`k ...` travels through DebugBroker and `console_run_script`; it does not enter
the EL0 `svc` syscall table. Likewise, `zx_smc_call` executes an SMC conduit on
arm64; it is not an HVC call to the EL2 monitor.

<img src="assets/kernel/vdso_loading.png" alt="smos" width="750">


### Zircon Object Model

Zircon is an object-based kernel. A user process does not receive a raw pointer
to a kernel subsystem; it receives a process-local handle that names a kernel
object and carries a set of rights. SMOS keeps this standard Zircon contract,
so component framework protocols, driver framework capabilities, dash services,
and the `zx_*` API all ultimately use the same object and handle machinery.

The object reference used by a handle is not the same thing as a component or a
file descriptor. A component capability may be implemented by a FIDL channel,
and a libc file descriptor may wrap a channel, socket, VMO, or another object.
The kernel only enforces the underlying object type, handle rights, signals,
and task/capability boundaries.

Read the model from containment to authority: a **job** governs processes, a
**process** owns an address space and handle table, and a **thread** executes
within that process. A **handle** is the process-local name for a kernel
**object**; its **rights** determine which operations the holder may request.
Transferring a handle changes where that name is installed, not the identity of
the underlying object.

#### Object taxonomy in the SMOS profile

The following table follows the categories in the official
[Zircon kernel objects reference](https://fuchsia.dev/fuchsia-src/reference/kernel_objects/objects)
and maps them to the SMOS runtime. “Available” means the Zircon primitive is
part of the retained kernel ABI; it does not mean every component receives a
handle to it automatically.

| Category | Objects | Typical SMOS role | Access boundary |
| --- | --- | --- | --- |
| Tasks | job, process, thread | component manager, console, driver-host lifecycle and execution | job policy, task rights, process handle table |
| IPC | channel, socket, FIFO, stream, IOBuffer | FIDL/framework messages, virtio socket transport, buffered data paths | channel/socket rights and transferred handles |
| Signaling | event, eventpair, counter, futex | one-shot notifications, peer closure, user-space synchronization | signal rights; futex also checks the user address |
| Waiting | port, timer | aggregate async events, timer deadlines, interrupt packets | wait/queue rights and port ownership |
| Memory | VMO, VMAR, pager | process address spaces, BootFS/file-backed data, shared buffers | VMO/VMAR rights, mapping flags, pager protocol |
| Scheduling | profile | priority/deadline configuration for selected threads | profile creation and task-set-profile rights |
| Time | clock | monotonic and UTC time sources used by libc/component services | clock read/update rights and capability routing |
| Drivers | interrupt, MSI, resource, BTI, pinned memory token, IOMMU | QEMU/device interrupts, MMIO and DMA setup | privileged resource handles; normally passed by driver framework |
| Diagnostics | debuglog, exception | kernel/driver logging and controlled crash observation | debug/resource/exception rights and policy |
| Virtualization | guest, VCPU, virtual interrupt | arm64 VMM/guest-manager support | hypervisor capability; QEMU SMOS path has no nested EL2 |

The object framework can be viewed as four cooperating planes rather than a
flat list of syscalls:

```text
┌────────────────────────────────────────────────────────────────────────┐
│ SMOS user space                                                        │
│ component manager, console, fshost, driver-host, VMM                   │
│ channels, sockets, VMOs, events, ports, task handles                   │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ handles + rights + signals
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Zircon kernel                                                          │
│ syscall veneer → dispatcher → object lifetime → scheduler / VM / IRQ   │
│ tasks | IPC | wait/signal | memory | driver/hypervisor                 │
│ job/process/thread | channel/port | VMO/VMAR | IRQ/resource/guest      │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ authorized hardware operation
                                   ▼
╭────────────────────────────────────────────────────────────────────────╮
│ QEMU devices, GIC/PLIC, and EL2/EL3 monitor                            │
╰────────────────────────────────────────────────────────────────────────╯
```

The upper plane expresses a capability through a handle; the middle plane
checks the handle and implements the object; the lower plane is reached only by
objects with an appropriate driver, resource, interrupt, or hypervisor right.
This is why a FIDL protocol and a driver interrupt can use the same wait/handle
mechanism even though they end at different hardware boundaries.

The compact product deliberately excludes unrelated user-space services, but
does not replace these kernel object types with SMOS-specific variants. A
removed network stack, for example, does not remove the kernel channel or socket
object; it only means that no conventional network service is assembled around
those primitives.

#### Handle table, rights, and object identity

A handle value is meaningful only inside the process that owns it. Internally,
the handle table entry contains a reference to the object, the rights mask, and
the owning process; another process may use a different integer for the same
object. Two handles in one process may refer to the same object while carrying
different rights.

```text
┌─────────────────────────────┐       ┌─────────────────────────────┐
│ Process A handle table      │       │ Process B handle table      │
│ 0x100: X + READ | WAIT      │       │ 0x208: X + READ             │
│ 0x104: X + READ | WRITE     │       └──────────────┬──────────────┘
└──────────────┬──────────────┘                      │ names X
               │ names X                             │
               └──────────────────┬──────────────────┘
                                  ▼
              ╭───────────────────────────────────────╮
              │ One kernel object X                   │
              │ channel, VMO, event, or another type  │
              ╰───────────────────────────────────────╯
```

The normal handle operations are:

| Operation | Syscall | Effect |
| --- | --- | --- |
| Create | `zx_*_create` | Creates an object and returns its first handle |
| Duplicate | `zx_handle_duplicate` | Creates another handle to the same object; rights may only be retained or reduced according to the requested mask |
| Replace | `zx_handle_replace` | Returns a new handle, usually with reduced rights, and invalidates the old handle |
| Transfer | `zx_channel_write` / `zx_channel_call` | Moves a handle into a channel message; it becomes in-transit until the receiver reads it |
| Close | `zx_handle_close` / `zx_handle_close_many` | Removes the process's handle reference |
| Inspect | `zx_object_get_info` / `zx_object_get_property` | Reads object metadata or properties allowed by the handle |

Rights are the security boundary for an object operation. The object itself
does not decide that one process is trusted; the handle passed to the syscall
does. This is why a FIDL service can safely receive a VMO with read-only rights
even when the sender owns a read/write handle to the same VMO.

The complete handle path is easiest to reason about as a sequence. The numeric
value changes when a handle is installed in another process; the underlying
object does not:

```text
╭──────────────────╮  ╭─────────────────────────╮  ╭──────────────────╮
│ Client process   │  │ Zircon channel / kernel │  │ Server process   │
╰────────┬─────────╯  ╰────────────┬────────────╯  ╰────────┬─────────╯
         │                         │                        │
         │ zx_channel_create()     │                        │
         ├────────────────────────►│ create channel pair    │
         │◄────────────────────────┤ h_client, h_server     │
         │                         │                        │
         │ zx_channel_write(bootstrap, h_server)            │
         ├────────────────────────►│ h_server in transit    │
         │                         │ queue message + ref    │
         │                         ├───────────────────────►│
         │                         │                        │ zx_channel_read()
         │                         │◄───────────────────────┤
         │                         │ install h_server'      │
         │                         │                        │
         │ zx_handle_close(h_client)                        │
         ├────────────────────────►│ last active peer closes│
         │                         ├───────────────────────►│ PEER_CLOSED
```

If the message is discarded before the receiver reads it, the kernel closes
the in-transit handle as part of message destruction. A server must therefore
either consume or explicitly close every received handle, including handles it
does not recognize.

<img src="assets/kernel/ipc.png" alt="smos" width="750">

#### Object lifetime and peer closure

Zircon objects are reference-counted. Creating an object creates the first
handle; closing that handle does not necessarily destroy the object because
other handles, in-transit handles, child objects, or kernel references may keep
it alive.

```text
┌──────────────────────────────────────────┐
│Create object + first process-local handle│
└─────────────────────┬────────────────────┘
                      │ duplicate, transfer, mapping, or child relation
                      ▼
┌──────────────────────────────────────────┐
│ One or more live object references       │
└─────────────────────┬────────────────────┘
                      │ close a handle
                      ▼
              ┌───────┴────────┐
              │references left?│
              └───┬─────────┬──┘
                 yes        no
                  ▼         ▼
┌───────────────────────┐  ╭───────────────────────────────────╮
│ Object remains alive  │  │ Destroy or defer reclamation      │
└───────────────────────┘  ╰───────────────────────────────────╯
```

Parent/child relationships also extend lifetime. A live thread keeps its
process and its job lineage alive; a live process keeps its address space and
threads alive; a VMAR mapping keeps its VMO relationship relevant. A channel
message containing a handle keeps that object alive until the message is read,
closed, or the endpoint is destroyed.

Channel, socket, FIFO, eventpair, and IOBuffer are *peered* objects. They are
created in pairs. When the peer's active handle count reaches zero, the other
endpoint observes its type-specific `ZX_*_PEER_CLOSED` signal, and operations
such as `zx_channel_write` return `ZX_ERR_PEER_CLOSED`. This is the normal
shutdown signal for component and driver connections; it is not a kernel crash.

#### Tasks: job, process, and thread

Tasks form a containment tree:

```text
╭──────────────────────────────────────────────────╮
│ Root job                                         │
╰───────────────────────┬──────────────────────────╯
                        │ contains child jobs and processes
          ┌─────────────┴─────────────┐
          ▼                           ▼
┌──────────────────────────┐  ┌───────────────────────────────┐
│ Component-manager job    │  │ Console, fshost, service jobs │
└─────────────┬────────────┘  └───────────────────────────────┘
              │ contains
      ┌───────┴────────┐
      ▼                ▼
┌───────────────┐  ┌────────────────┐
│ Component     │  │ Driver-host    │
│ process       │  │ process        │
└───────┬───────┘  └───────┬────────┘
        │ owns threads     │ owns threads
        ▼                  ▼
╭───────────────╮       ╭────────────────╮
│ Runnable      │       │ Driver threads │
│ threads       │       ╰────────────────╯
╰───────────────╯
```

- A **job** contains child jobs and processes. Job policies, critical-process
  behavior, and kill operations provide lifecycle containment.
- A **process** owns a handle table, a private `VmAspace`, mappings, and threads.
  It is the unit used for address-space and handle isolation.
- A **thread** is the scheduler's runnable unit. It executes in a process
  address space and can block on a channel, port, event, timer, page fault, or
  driver protocol.
- A **task** is the common syscall view used by operations that accept a job,
  process, or thread handle, such as suspend, kill, and exception-channel setup.

In SMOS, component manager starts processes and their jobs, but it does not
replace the kernel task model. Restarting a driver-host normally closes its
process handles and signals peer endpoints while leaving the Zircon kernel and
unrelated driver-host jobs alive.

#### IPC and synchronization objects

The primary IPC object is the **channel**. It provides ordered message passing
and is the transport used by FIDL. A message can contain bytes and handles, so
one channel call can both request a service and transfer a VMO/event/channel
capability. The receiver must consume the handles or close them; otherwise the
message keeps them in transit.

**Sockets** provide byte-stream or datagram-style transport and are retained as
kernel primitives for the virtio-socket path. A socket is not a conventional IP
network interface, and SMOS does not assemble a netstack around it.

**FIFO** and **stream** objects provide specialized byte or record operations;
they are useful when a protocol does not need FIDL's typed channel messages.
**Event**, **eventpair**, **counter**, and **futex** provide signaling or
user-space synchronization. **Port** combines waits from multiple sources into
packets, which is why driver and async service loops can wait on channels,
interrupts, and timers through one dispatcher.

```text
┌────────────────────────────────────────────────────┐
│ Driver or component thread                         │
└────────────────────────┬───────────────────────────┘
                         │ selects a blocking operation
           ┌─────────────┼─────────────┬──────────────┐
           ▼             ▼             ▼              ▼
┌────────────────┐ ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
│ channel_call   │ │ wait_one     │ │ port_wait   │ │ futex_wait   │
│ FIDL reply     │ │ signal/peer  │ │ many events │ │ lock wait    │
└────────────────┘ └──────────────┘ └─────────────┘ └──────────────┘
```

An asynchronous service loop usually binds several objects to one port. The
port packet identifies the source with a user-selected key; the object-specific
dispatcher remains responsible for the signal or packet semantics:

```text
┌──────────────────────────────────────────────────────┐
│ Bind channel (key 1), interrupt (key 2), and timer   │
│ to one port                                          │
└──────────────────────────┬───────────────────────────┘
                           │ zx_port_wait(port)
                           ▼
                 ┌─────────┴─────────┐
                 │ Port packet key   │
                 └───┬───────────┬───┘
                     1           2             timer
                     ▼           ▼               ▼
   ┌──────────────────┐ ┌────────────────────┐ ┌──────────────────────┐
   │ Read FIDL message│ │ Acknowledge IRQ and│ │ Run timeout handler  │
   └──────────────────┘ │ schedule work      │ └──────────────────────┘
                        └────────────────────┘
```

This pattern is used at the framework boundary: a driver-host can wait for a
protocol request, a device interrupt, and a timeout without spinning on any of
them.

#### VMO, VMAR, and pager relationship

<img src="assets/kernel/vmar_mappings_vmos.png" alt="vmar" width="750">

A **VMO** is a kernel-managed range of memory or a backing object. A **VMAR**
is an address-region object belonging to a process address space. Mapping a VMO
into a VMAR creates a process virtual-address view; it does not turn the VMO
into a raw physical pointer.

```text
┌────────────────────────────────────────────┐
│ VMO: pages, file backing, or shared buffer │
└────────────────────┬───────────────────────┘
                     │ zx_vmar_map(vmar, vmo, ...)
                     ▼
┌────────────────────────────────────────────┐
│ Process VMAR and page-table mapping        │
└────────────────────┬───────────────────────┘
                     │ translates load/store
                     ▼
╭────────────────────────────────────────────╮
│ Process virtual address                    │
╰────────────────────────────────────────────╯
```

VMO rights control read/write/execute and mapping-related operations. VMAR
rights control whether a mapping can be created, changed, or destroyed. A VMO
can be shared by transferring a reduced-rights handle over a channel, which is
the normal path for driver buffers and framework data. A **pager** supplies
pages on demand for pager-backed VMOs; it is a protocol between a pager owner
and the kernel, not a replacement for the VMO handle.

<img src="assets/kernel/vmo_address_in_vmar_address_range.png" alt="vmar" width="750">

SMOS boot memory follows a separate early path: the boot-shim contributes
physical-memory and platform ZBI items, `kernel.phys` establishes the initial
physical-loader mappings, and the final process VMAR/VMO objects are created
only after the Zircon kernel and userboot have started.

<img src="assets/kernel/vmo_to_root_vmar.png" alt="vmar" width="750">


#### Driver and virtualization objects

An **interrupt** handle represents a hardware or virtual interrupt source and
can be waited on directly or bound to a port. An **MSI** is the message-signaled
variant. A **resource** handle authorizes a restricted hardware range or kernel
service; it is not a general-purpose capability. A **BTI** and pinned-memory
token participate in safe DMA setup, while an **IOMMU** object controls address
translation for devices.

These objects normally arrive through driver framework capability routing rather
than `zx_*_create` from an ordinary process. For SMOS QEMU drivers, the board
and driver-host configuration determines which MMIO, IRQ, and protocol handles
are offered. The `zx_smc_call` path described above similarly requires an
authorized SMC resource handle before entering the arm64 monitor.

On arm64, **guest**, **VCPU**, and virtual-interrupt objects support the retained
hypervisor/VMM implementation. The documented QEMU boot path drops from EL2 to
EL1 before Zircon starts and reports no nested EL2; therefore these objects do
not imply that a guest can create a second EL2 monitor in this verification
environment. RISC-V keeps the console and kernel-primitives target but marks
the virtualization host unsupported.

The driver and hypervisor capability flow is intentionally explicit:

```text
┌─────────────────────────────────────────────────────────────┐
│ component_manager / driver_manager                          │
└─────────────────────────────┬───────────────────────────────┘
                              │ offers channels, VMOs, IRQ/resource/BTI handles
                ┌─────────────┴─────────────┐
                ▼                           ▼
┌──────────────────────────────┐  ┌───────────────────────────┐
│ Isolated driver-host         │  │ arm64 VMM                 │
│ call, map, and wait syscalls │  │ guest/VCPU syscalls       │
└──────────────┬───────────────┘  └─────────────┬─────────────┘
               │ devfs / FIDL                   │ hypervisor right
               ▼                                ▼
╭──────────────────────────────╮  ╭───────────────────────────╮
│ QEMU device and SMOS service │  │ EL2 monitor / virtual     │
│ endpoint                     │  │ devices                   │
╰──────────────────────────────╯  ╰───────────────────────────╯
```

The resource and interrupt handles in this diagram are not synthesized by the
driver from an integer address. They are selected by board configuration and
offered through the driver framework, so changing a bind rule or component
manifest can change which objects a driver receives without changing the
kernel object ABI.

#### Object-to-code map

When tracing an object operation from a SMOS client into Zircon, use this
mapping:

| Layer | Representative location |
| --- | --- |
| Public ABI and syscall declarations | `zircon/vdso/`; generated declarations and wrappers are emitted under `out/smos-boot-<arch>/` |
| Syscall argument/rights checks | `zircon/kernel/lib/syscalls/` |
| Handle table and common object lifetime | `zircon/kernel/object/handle_table.cc`, `handle.cc`, `dispatcher.cc` |
| Task dispatchers | `zircon/kernel/object/job_dispatcher.cc`, `process_dispatcher.cc`, `thread_dispatcher.cc` |
| IPC dispatchers | `zircon/kernel/object/channel_dispatcher.cc`, `socket_dispatcher.cc`, `port_dispatcher.cc` |
| Memory dispatchers | `zircon/kernel/object/vm_object_dispatcher.cc`, `vm_address_region_dispatcher.cc`, `pager_dispatcher.cc` |
| Driver/VM implementation | `zircon/kernel/object/interrupt_dispatcher.cc`, `zircon/kernel/vm/`, `zircon/kernel/object/` |
| User-facing framework use | `userspace/sys/component_manager`, `userspace/devices`, `userspace/virtualization` |

The practical debugging rule is to identify the handle first, then identify
its object type and rights, then trace the wait/IPC/mapping operation. A
`ZX_ERR_BAD_HANDLE`, `ZX_ERR_ACCESS_DENIED`, or `ZX_ERR_PEER_CLOSED` result
usually identifies a different class of failure from a page fault, scheduler
block, or driver bind failure.

### Memory

Memory is a kernel-owned mechanism, not a standalone SMOS service. The
boot-shim and `kernel.phys` discover usable physical ranges, the physical
memory manager (PMM) owns page allocation, and the virtual-memory (VM) layer
turns those pages into capability-protected objects and mappings. User space
sees VMOs and VMARs through handles; it never receives an unmediated pointer to
the kernel's page allocator.

#### Memory concepts and ownership

| Concept | Kernel representation | Ownership and purpose |
| --- | --- | --- |
| Physical page | `vm_page_t` managed by `Pmm::Node()` | A page-sized unit from a discovered memory arena; allocated, wired, free, or reclaimable. |
| PMM | `zircon/kernel/vm/pmm.cc` and `pmm_node.cc` | Tracks arenas and free pages, services allocation requests, and ends the phys hand-off. |
| VMO | `VmObject`/`VmObjectPaged`, exposed by `VmObjectDispatcher` | A capability-bearing byte range. Pages can be anonymous, pager-backed, contiguous, physical, pinned, or COW children. |
| VMAR | `VmAddressRegion` and `VmAddressRegionDispatcher` | A hierarchical virtual-address reservation. A mapping attaches a VMO range to one VMAR. |
| Mapping | `VmMapping` | Connects a VMO offset and length to virtual addresses and records permissions/cache policy. |
| Address space | `VmAspace` | Owns the architecture page tables for one kernel, user, or guest address space. |
| Handle | `Handle` plus an object dispatcher | Carries object identity and rights (`READ`, `WRITE`, `MAP`, `EXECUTE`, and so on) across syscalls and channels. |

#### Memory concepts relationship

The concepts form a resource-to-address pipeline. The box-drawing view below
shows which object owns or describes each part of that pipeline and where
capability checks or external page supply enter it.

```text
┌───────────────────────────────┐
│ Physical memory ranges        │  boot-shim/ZBI discovery
└───────────────┬───────────────┘
                │ initializes arenas
                ▼
┌───────────────────────────────┐
│ PMM: Pmm::Node()              │  allocates, frees, wires pages
│ arenas and page queues        │
└───────────────┬───────────────┘
                │ owns physical pages
                ▼
┌───────────────────────────────┐       ┌───────────────────────────────┐
│ VMO: VmObject/VmObjectPaged   │◄──────│ PageSource / pager            │
│ logical byte range + page map │ supply│ supplies missing pages        │
└───────────────┬───────────────┘       └───────────────────────────────┘
                │
                ├───────────────►┌───────────────────────────────┐
                │                │ VMO variants                  │
                │                │ COW, contiguous, physical,    │
                │                │ pinned, discardable           │
                │                └───────────────────────────────┘
                │ mapped VMO range
                ▼
┌───────────────────────────────┐
│ Mapping: VmMapping            │
│ VMO offset + length + perms   │
└───────────────┬───────────────┘
                │ is contained by
                ▼
┌───────────────────────────────┐
│ VMAR: VmAddressRegion         │  reserves and subdivides VA ranges
│ hierarchical address regions  │
└───────────────┬───────────────┘
                │ belongs to
                ▼
┌───────────────────────────────┐       ┌───────────────────────────────┐
│ VmAspace                      │◄──────│ Handle + dispatcher           │
│ page-table root and MMU state │ rights│ names VMO/VMAR; gates syscalls│
└───────────────┬───────────────┘       └───────────────────────────────┘
                │ translates mapping
                ▼
┌───────────────────────────────┐
│ Process virtual address       │  load/store -> page fault if absent
│ user code, stack, or buffer   │
└───────────────────────────────┘
```

Read the main vertical path as "physical capacity becomes a VMO, the VMO is
attached to a VMAR mapping, and the process `VmAspace` translates that mapping
through architecture page tables." The `Handle + dispatcher` box does not own
the bytes: it grants a process specific rights to name and operate on a VMO or
VMAR. `PageSource` can provide content when a page is absent, while COW,
pinning, and contiguous/physical variants change how the VMO obtains or keeps
its physical pages.

The ownership boundary is summarized below. Arrows describe ownership,
construction, or a handle/protocol crossing into a different process; the
labels identify which kind of relationship each edge represents.

```text
                         SMOS user space
  +----------------------------------------------------------------------------+
  | userboot | component_manager | fshost | driver-host | console | VMM        |
  |     ELF/BootFS, stacks, shared buffers, guest memory, device mappings      |
  +-----------------------------+-------------------+--------------------------+
                                |  VMO/VMAR handles, FIDL, zx_* syscalls
                                v
  +----------------------------------------------------------------------------+
  | Object layer: HandleTable -> VmObjectDispatcher / VmAddressRegionDispatcher|
  | Rights checks, lifetime, namespace and cross-process handle transfer       |
  +-----------------------------+-------------------+--------------------------+
                                |  validated object operations
                                v
  +----------------------------------------------------------------------------+
  | VM layer: VmAspace -> VmAddressRegion -> VmMapping -> VmObjectPaged        |
  | page faults, pager requests, COW, decommit, pinning, cache attributes      |
  +-----------------------------+-------------------+--------------------------+
                                |  page requests / physical addresses
                                v
  +----------------------------------------------------------------------------+
  | PMM: Pmm::Node() -> arenas -> free/loaned/wired pages -> arch MMU          |
  +-----------------------------+-------------------+--------------------------+
                                ^
                                | memory ranges and boot hand-off state
  +----------------------------------------------------------------------------+
  | boot-shim -> ZBI -> kernel.phys -> PhysHandoff -> Zircon kernel            |
  +----------------------------------------------------------------------------+
```

The boot-shim contributes memory and platform items to the ZBI; it does not
create final user address spaces. The arm64 and riscv64 shims have different
devicetree and interrupt details, but both converge on the same PMM/VM object
model after `PhysbootHandoff` enters the kernel.

#### Memory initialization code path

The initialization path establishes physical pages before any user process can
map memory. `InitMemory` at the physical stages parses the memory ZBI items and
initializes the temporary physical address space. During kernel startup,
`pmm_init` imports the discovered `memalloc::Range` values and `vm_init` builds
the kernel address space and its zero page.

```text
Firmware/QEMU DTB and data ZBI
  |
  +--> arch boot-shim PhysMain
  |      linux-arm64-boot-shim.cc / linux-riscv64-boot-shim.cc
  |      |-- InitMemory(fdt, nullptr)
  |      |-- DevicetreeBootShim::Init()
  |      |     `-- append ZBI_TYPE_MEM_CONFIG and platform items
  |      `-- BootZbi::Boot() -> kernel.phys entry
  |
  +--> kernel.phys PhysMain -> ZbiMain
  |      zircon/kernel/phys/zbi-main.cc, physload.cc
  |      |-- InitMemory(zbi, &aspace)
  |      |-- unpack kernel/BOOTFS and build PhysHandoff
  |      `-- PhysLoadModuleMain() -> BootZircon()
  |
  +--> Zircon kernel PhysbootHandoff -> lk_main
         zircon/kernel/top/main.cc
         |-- arch_early_init/platform_early_init
         |-- vm_init_preheap()
         |-- heap_init()
         |-- vm_init()
         |     |-- VmAspace::KernelAspaceInit()
         |     |-- pmm_alloc_page() for the wired zero page
         |     `-- initialize kernel image/physmap VMARs
         |-- topology_init() / kernel_init()
         `-- bootstrap2() -> userboot_init()
                `-- ProcessDispatcher creates a user VmAspace
```

The principal implementation points are `zircon/kernel/phys/zbi-memory.cc`,
`zircon/kernel/vm/pmm.cc:pmm_init`, and `zircon/kernel/vm/vm.cc`.
`vm_init_preheap` is intentionally a pre-heap hook; the global VM structures
and the kernel zero page are initialized by `vm_init` after the kernel heap is
available. The physmap maps physical pages for kernel use, while each user
process receives an isolated `VmAspace` with its own page-table root; the
creation path is in `zircon/kernel/object/process_dispatcher.cc`.

#### Runtime mapping and page-fault code path

The normal user workflow has two phases: create a logical VMO and mapping, then
materialize pages when code first touches the mapped virtual address. The
following path names both syscall entry points and the VM functions that carry
the request.

```text
User process calls zx_vmo_create(size, options)
  |
  `--> zircon/kernel/lib/syscalls/vmo.cc:sys_vmo_create
         |-- ProcessDispatcher::EnforceBasicPolicy(ZX_POL_NEW_VMO)
         |-- VmObjectDispatcher::parse_create_syscall_flags()
         |-- VmObjectPaged::Create(PMM_ALLOC_FLAG_ANY | CAN_WAIT, ...)
         |-- VmObjectDispatcher::Create()
         `-- ProcessDispatcher::MakeAndAddHandle() -> VMO handle + rights

User process calls zx_vmar_map(vmar, options, vmo, offset, len)
  |
  `--> zircon/kernel/lib/syscalls/vmar.cc:sys_vmar_map
         |-- HandleTable lookup for VMAR and VMO dispatchers
         |-- validate VMAR/VMO rights and map permissions
         `-- vmar_map_common() -> VmAddressRegion::Map()
                `-- create VmMapping and install the mapping metadata

First load/store at the returned virtual address
  |
  `--> architecture exception entry -> VmAspace::PageFault(va, flags)
         zircon/kernel/vm/vm_aspace.cc
         |-- locate the containing VmMapping
         `-- VmMapping::PageFaultLocked()
                zircon/kernel/vm/vm_mapping.cc
                |-- derive MMU permissions and VMO offset
                |-- request page from VmObject/PageSource
                |-- VmObjectPaged commits or retrieves a page
                |      (PMM allocation, pager, zero page, or COW copy)
                |-- update architecture page tables
                `-- retry the faulting instruction
```

`zx_vmo_create` allocates the VMO object and its metadata; it does not promise
that every byte has a resident physical page. A page may be supplied by a
pager, shared through a clone, represented by the global zero page until a
write, or allocated on demand by `VmObjectPaged::CommitRangeInternal`. A
mapping can therefore be large while its resident set is small. Conversely,
`ZX_VM_MAP_RANGE`-style pre-faulting, `zx_vmo_op_range`, pinning, or a
contiguous/physical VMO can make allocation happen earlier and impose stronger
PMM constraints.

The important failure exits are:

- syscall policy or handle lookup failure (`ZX_ERR_ACCESS_DENIED`,
  `ZX_ERR_BAD_HANDLE`), before the VM layer is entered;
- invalid alignment, range, permission, or overlap, rejected by
  `vmar_map_common`/`VmAddressRegion::Map`;
- an unmapped or protection-faulting address, returned from
  `VmAspace::PageFault` as a user exception;
- no available page, failed pager request, or an unsupported pin/contiguous
  request, propagated as `ZX_ERR_NO_MEMORY` or the pager's status.

#### SMOS consumers and special memory types

SMOS uses the standard Zircon objects in several constrained roles:

- `userboot` maps the ZBI/BootFS VMO, the vDSO, the next ELF image, and the
  initial stack before starting `component_manager`.
- `component_manager` and each `driver-host` receive only the VMOs and VMAR
  capabilities offered by their component manifests. FIDL messages commonly
  transfer a VMO handle for a buffer instead of copying the buffer through the
  channel.
- QEMU serial/block/RTC/random drivers map only the buffers and resources
  supplied by the driver framework. MMIO and DMA require the corresponding
  resource, BTI, and cache-policy checks; a driver cannot infer authority from
  a physical address value.
- The arm64 VMM maps guest-physical memory and device buffers through the
  hypervisor-specific capabilities documented in the virtualization sections;
  this remains an object/rights operation, not a second PMM implementation.

VMO variants explain the ownership seen in these consumers. Anonymous paged
VMOs use `VmObjectPaged` and can be copy-on-write clones. Pager-backed VMOs
delegate missing-page supply to a `PageSource`. Contiguous and physical VMOs
describe fixed physical placement and are used only where the caller has the
required rights. Pinned VMOs prevent reclamation for a bounded range. Decommit,
discardable state, compression, and the page queues can reduce resident usage
without changing the VMO's logical size.

Useful implementation and diagnostics areas:

- `zircon/kernel/phys/`: early memory discovery and phys hand-off.
- `zircon/kernel/vm/`: PMM, VM objects, mappings, page queues, pager, and faults.
- `zircon/kernel/object/`: VMO/VMAR dispatchers, handle rights, and diagnostics.
- `zircon/kernel/lib/syscalls/vmo.cc` and `vmar.cc`: user ABI validation.
- `zircon/kernel/object/diagnostics.cc`: process/VMO attribution and memory
  usage reporting used when investigating resident versus logical size.

### Scheduling

SMOS reuses the Zircon scheduler in `zircon/kernel/kernel/scheduler.cc`; there
is no separate SMOS scheduling algorithm. Scheduling decisions are made for
threads, not processes. A process supplies an address space and a handle
namespace, while each thread owns a scheduling profile, CPU affinity, runtime
accounting, and queue state in `SchedulerState`.

#### Scheduler architecture

The following map shows the ownership boundaries. Each active CPU has one
`Scheduler` instance and its own fair and deadline run queues. Wait queues are
outside the run queues; they reinsert a thread only after its wait condition is
signaled.

    +--------------------- user space -----------------------+
    | dash | component | driver | VMM/GuestManager | loadgen |
    +---------------------------+----------------------------+
                                | syscall, wait, profile, IRQ
                                v
    +---------------------- kernel --------------------------+
    | ThreadDispatcher -> Thread -> SchedulerState           |
    |                             | profile/affinity/stats   |
    |                             v                          |
    |        +-------- per-CPU Scheduler --------+           |
    |        | fair_run_queue   deadline_run_queue|          |
    |        | virtual_time     preemption timer  |          |
    |        +----------+-------------------------+          |
    |                   | dequeue / context switch           |
    |                   v                                    |
    |             running Thread                             |
    +--------------------------------------------------------+
             ^                 ^                    ^
             | Unblock         | timer tick         | interrupt/IPC
        wait queue       preempt pending       wake protocol

Relevant implementation: `SchedulerState` and the `SchedDiscipline` enum are
defined in `zircon/kernel/include/kernel/scheduler_state.h`; queue ownership
and selection APIs are declared in `zircon/kernel/include/kernel/scheduler.h`.

#### Reschedule code flow

`Scheduler::RescheduleCommon` is the common hand-off path for blocking,
preemption, exit, suspension, and migration. The flow below follows the order
in `scheduler.cc`, including the point where a current thread is returned to a
queue or removed from scheduler accounting.

    block / syscall / exception / pending preemption
                         |
                         v
              Scheduler::RescheduleCommon
                         |
                         +--> ProcessSaveStateList
                         +--> lock per-CPU queue
                         +--> UpdateTimeline(now)
                         +--> account actual runtime
                         |       |
                         |       +--> fair: consume current timeslice
                         |       `--> deadline: consume scaled capacity
                         +--> determine timeslice_expired
                         +--> NeedsMigration(current)?
                         |       `--> RemoveForTransition(Migrating)
                         +--> EvaluateNextThread
                         |       |
                         |       +--> keep current if still eligible
                         |       +--> QueueThread on expiry/preemption
                         |       `--> DequeueThread otherwise
                         +--> arm next preemption deadline
                         +--> set next thread RUNNING
                         +--> update runtime/EMA bookkeeping
                         `--> TraceContextSwitch + arch context switch

The code path is `RescheduleCommon` -> `EvaluateNextThread` ->
`DequeueThread`. The final context-switch bookkeeping updates `active_thread_`,
`last_cpu_`, migration callbacks, the preemption timer, and the trace flow
before the architecture switch is performed.

#### Run-queue selection algorithm

`DequeueThread` implements a strict selection order. Pending power work takes
the idle-power thread first. Otherwise, an eligible deadline task wins over a
fair task. If both local queues are empty, the scheduler attempts work
stealing; only then does it return the CPU's idle thread.

    DequeueThread(now)
          |
          +-- pending idle-power work? -- yes --> idle-power thread
          |
          +-- eligible deadline queue? -- yes --> earliest finish_time
          |
          +-- fair queue non-empty? ---- yes --> earliest eligible fair key
          |
          +-- StealWork from another CPU? -- yes --> stolen thread
          `-- otherwise ------------------------> idle thread

The fair queue is ordered by the thread's `(start_time, generation)` key. Its
virtual timeline advances with elapsed runtime while fair work is runnable.
`QueueThread` computes a proportional timeslice from the thread weight and the
total fair weight, then derives `finish_time = start_time + normalized
period/weight`. Kernel priorities are converted to fair weights through the
table in `SchedulerState` (priority range 0..31).

Deadline threads use a separate queue. A thread becomes eligible when its
`start_time` has arrived; among eligible entries, the earliest `finish_time`
is selected. Its profile contains `(capacity, relative_deadline)` and its
remaining capacity is replenished when insertion or preemption reaches the
period boundary. A fair thread is preempted when a deadline thread becomes
eligible. A deadline thread is preempted only by an eligible deadline thread
with an earlier finish time.

#### Fair and deadline accounting

    profile                 queue key              expiration condition
    --------------------------------------------------------------------------
    Fair(weight)            start_time + generation total runtime >= timeslice
    Deadline(capacity, d)   start_time / finish_time now >= finish_time OR
                                                    remaining capacity exhausted

Fair timeslices are calculated by `CalculateTimeslice`:

    scheduling period * thread weight
    ----------------------------------  -> at least one minimum-granularity unit
             total fair weight

`NextThreadTimeslice` arms the preemption timer. For a fair thread the target
is `now + remaining_timeslice`; for a deadline thread it is the scaled
remaining capacity clamped to `finish_time`. The timer may be armed earlier
than the ideal timeslice so a newly eligible deadline thread is not delayed.

#### Block, wake, and reschedule sequence

The sequence below is representative of a channel, event, timer, or driver
wait. The waiting object owns the wait queue, but the scheduler owns the
transition back to READY and the target CPU selection.

    Running thread       Wait queue/object       Waking thread / IRQ
         |                       |                       |
         | wait operation        |                       |
         |---------------------->| enqueue + set BLOCKED |
         | Scheduler::Block      |                       |
         |---------------------->|                       |
         | RescheduleCommon      |                       |
         |---- choose next ------|---------------------->|
         |                       |                       |
         |                       | signal/packet/timer   |
         |                       |<----------------------|
         |                       | Scheduler::Unblock    |
         |                       |---------------------->|
         |                       | FindTargetCpu         |
         |                       | Insert/QueueThread    |
         |                       | RescheduleMask(cpu)   |
         |<---------------------- context switch --------|

`Scheduler::TimerTick` itself only marks preemption pending. The architecture
or interrupt-return path subsequently enters the common reschedule path, where
the current runtime and queue state are updated under the scheduler queue lock.

#### CPU placement, migration, and stealing

`FindTargetCpu` filters CPUs by the effective hard/soft affinity mask and then
compares candidate schedulers. Fair work prefers low predicted queue time and
cache-cluster locality. Deadline work additionally considers scaled
utilization, queue time, and the CPU utilization limit. The last CPU is
examined first to preserve cache affinity. If a runnable thread cannot execute
on its current CPU, `NeedsMigration` removes it through the migration
transient state. If a CPU has no local eligible work, `StealWork` may transfer
a ready thread from another busy CPU.

    unblock / affinity change
              |
              v
       effective CPU mask
              |
              v
       FindTargetCpu candidates
              |
       +------+-------------------+
       |                          |
    suitable queue            no local work
       |                          |
       v                          v
    Insert + IPI             StealWork or idle

The relevant code is `FindTargetCpu`, `NeedsMigration`, `Unblock`, and
`RemoveForTransition` in `zircon/kernel/kernel/scheduler.cc`.

#### Priority inheritance and effective profiles

Owned wait queues participate in scheduling through priority inheritance. A
thread waiting behind an owned queue contributes either fair weight or
deadline utilization to the owner. `scheduler_pi.cc` removes a READY target
from its queue, recomputes the effective profile, updates scheduler totals, and
reinserts it so the queue ordering reflects the new pressure.

    waiter profile(s)
       | fair weight or deadline utilization
       v
    owned wait queue (aggregate inherited profile)
       |
       v
    owner thread effective profile
       |
       +--> fair_run_queue or deadline_run_queue position changes
       `--> preemption time is recalculated if owner is RUNNING

If any inherited deadline utilization is present, the effective profile uses
the deadline discipline and the minimum inherited deadline. Otherwise the
inherited fair weights are summed. Deadline profiles are always inheritable;
fair profiles carry an explicit inheritable flag. The update logic is the
`Scheduler::PiOperation` common handler and `RecomputeEffectiveProfile` path.

#### Scheduler state machine

    +---------+      wait/block       +---------+
    | RUNNING | --------------------> | BLOCKED |
    +----+----+                       +----+----+
         | preempt/                        | wake /
         | timeslice                       | signal
         v                                 v
    +---------+  dequeue/select       +---------+
    |  READY  | <-------------------- |  READY  |
    +----+----+                       +---------+
         |
         | selected by scheduler
         v
    +---------+
    | RUNNING |
    +----+----+
         |
         +--> SUSPENDED / DEAD (final reschedule)

The two READY boxes represent the same logical state at different points in
the queue lifecycle: a normal READY thread is queued, while a transient
`Rescheduling`, `Migrating`, or `Stolen` thread is temporarily detached while
locks and CPU ownership are reconciled.

#### Observing the algorithm from the SMOS console

The SMOS minimal assembly includes the existing Zircon tools, so scheduling can
be exercised without adding a new command:

    smos:\> loadgen 4
    smos:\> pistress
    smos:\> ktrace start 4
    smos:\> loadgen 4
    smos:\> ktrace stop
    smos:\> ktrace save /data/sched.ktrace

`loadgen` creates periodic compute/sleep load; `pistress` exercises priority
and priority-inheritance behavior; `ktrace` group mask `4` records scheduler
events. Access to the kernel debug resource is required for `ktrace`. The
higher-level `trace` command can collect provider and kernel records for
Perfetto, for example:

    smos:\> trace list-categories
    smos:\> trace record --duration=2 --output-file=/data/sched.fxt -- /boot/bin/loadgen 1

These commands are observability aids, not alternate schedulers. Use the
source paths above when interpreting a trace: queue events correspond to
`QueueThread`/`Dequeue*`, reschedule spans to `RescheduleCommon`, and context
switch records to `TraceContextSwitch`.

### Interrupts and timers

Hardware interrupt delivery crosses an architecture-specific entry path before
it becomes a Zircon interrupt object or a driver callback. This section uses
the arm64 SMOS QEMU path as the teaching example. The boot-shim supplies GIC,
timer, and CPU-description ZBI items; the kernel initializes the controller;
and a user-mode driver observes an interrupt through a framework-issued handle
or port packet.

#### Interrupt model and terminology

An **exception** is any control transfer into privileged exception-handling
code. An **interrupt** is the asynchronous subset: it is raised independently
of the instruction currently executing. A synchronous exception instead has a
direct instruction cause, such as an SVC syscall, page fault, breakpoint, or
illegal instruction. The CPU saves enough state to resume, chooses an entry
point, and the kernel classifies the cause before it dispatches work.

Do not confuse three related identifiers:

| Term | Meaning | Example in this path |
| --- | --- | --- |
| CPU vector entry | A fixed architecture entry address | One `VBAR_EL1` slot for an IRQ from EL0 AArch64 |
| Controller interrupt ID | A number reported by the GIC for a pending source | Timer PPI, UART SPI, or MSI-derived interrupt |
| Zircon interrupt handle | A process-local capability naming an object | Handle passed to `zx_interrupt_wait()` |

The vector entry decides which early assembly path runs; it does not identify a
PCI device or replace a Zircon handle. The GIC identifies the pending hardware
source after the CPU enters the IRQ vector, and the dispatcher maps that source
to kernel-side state and a waiting client.

#### arm64 exception vector table

At EL1, `VBAR_EL1` holds the base address of the exception vector table. The
architecture reserves 16 ordered slots: four origin/stack-context groups times
four exception classes. Each slot is `0x80` bytes, so the table occupies
`0x800` bytes. The classes are synchronous exception, IRQ, FIQ, and SError.
The groups distinguish exceptions while already at EL1 with `SP0` or `SP_ELx`,
and exceptions from a lower EL using AArch64 or AArch32 state.

```text
╭────────────────────────────────────────────────────────────╮
│ VBAR_EL1: base of the EL1 exception vector table           │
╰─────────────────────────┬──────────────────────────────────╯
                          │ group × 0x200 + class × 0x80
                          ▼
┌────────────────────────────────────────────────────────────┐
│ 16 ordered slots, each 0x80 bytes                          │
├────────────────────┬────────┬────────┬────────┬────────────┤
│ Origin / stack     │ Sync   │ IRQ    │ FIQ    │ SError     │
├────────────────────┼────────┼────────┼────────┼────────────┤
│ EL1, SP0           │ slot   │ slot   │ slot   │ slot       │
│ EL1, SP_ELx        │ slot   │ IRQ    │ slot   │ slot       │
│ Lower EL, AArch64  │ slot   │ IRQ    │ slot   │ slot       │
│ Lower EL, AArch32  │ slot   │ IRQ    │ slot   │ slot       │
└────────────────────┴────────┴────────┴────────┴────────────┘
```

The diagram is conceptual. An entry can share a later common implementation or
be filled by an invalid-exception stub; it is not a promise that every class has
a device handler in SMOS. The production table is `arm64_el1_exception` in
`zircon/kernel/arch/arm64/exceptions.S`. Its `.vbar_table` macros enforce slot
order and size at assembly time. Dedicated IRQ entries save an `iframe_t` frame
and call `arm64_irq(iframe, exception_flags)`.

`arm64_irq` in `zircon/kernel/arch/arm64/exceptions_c.cc` starts generic
interrupt accounting, records the IRQ counter, calls `platform_irq`, and checks
whether interrupt processing made preemption necessary before it returns.

#### GIC delivery and acknowledgement

The Arm Generic Interrupt Controller (GIC) arbitrates pending sources, applies
priority and CPU-target policy, and presents one selected IRQ to a CPU. The GIC
is separate from the vector table: GIC delivery causes an IRQ exception, then
the CPU executes the matching `VBAR_EL1` slot.

```text
╭───────────────────────────╮
│ QEMU device or timer      │
│ asserts an IRQ            │
╰──────────────┬────────────╯
               │ interrupt ID, priority, target CPU
               ▼
┌───────────────────────────────────────────────────┐
│ GIC: pending → enabled → selected for a CPU       │
└─────────────────────┬─────────────────────────────┘
                      │ IRQ line to selected CPU
                      ▼
┌───────────────────────────────────────────────────┐
│ Matching VBAR_EL1 IRQ vector                      │
│ save frame → arm64_irq() → platform_irq()         │
└─────────────────────┬─────────────────────────────┘
                      ▼
╭───────────────────────────────────────────────────╮
│ Claim, signal the kernel handler, and EOI/complete│
╰───────────────────────────────────────────────────╯
```

An acknowledgement tells the controller that software accepted a pending
interrupt; end-of-interrupt (EOI) and, where required, deactivation retire the
active controller state. Device acknowledgement is separate: a UART, virtio
device, or PCI function may require status to be read or cleared so it stops
asserting its source. Completing only the GIC side can lead to a repeated IRQ.

The GICv2 implementation's `gic_handle_irq` reads `GICC_IAR`, invokes the
registered handler, and writes `GICC_EOIR`; see
`zircon/kernel/dev/interrupt/gic/v2/arm_gicv2.cc`. Register details vary by GIC
version, but controller claim/complete and device-state acknowledgement remain
separate responsibilities.

#### End-to-end IRQ lifecycle

This sequence separates fast IRQ handling from the driver work that follows. A
user driver does not execute inside a CPU vector slot. It waits in its own
thread and resumes only after kernel signaling makes it runnable.

```text
╭──────────────╮  ╭──────────────╮  ╭──────────────╮  ╭──────────────╮
│ Device       │  │ GIC / CPU    │  │ Kernel       │  │ Driver       │
╰──────┬───────╯  ╰──────┬───────╯  ╰──────┬───────╯  ╰──────┬───────╯
       │                 │                 │                 │
       │ assert IRQ      │                 │                 │
       ├────────────────►│ take vector     │                 │
       │                 ├────────────────►│ arm64_irq()     │
       │                 │                 │ platform_irq()  │
       │                 │                 │ signal          │
       │                 │                 ├────────────────►│ wake / packet
       │                 │◄────────────────┤ EOI / complete  │
       │                 │                 │                 │ read state
       │◄────────────────────────────────────────────────────┤ acknowledge
```

The diagram shows logical ownership, not a requirement that a driver write a
hardware register directly. In SMOS, a driver can acknowledge device state
through mapped MMIO, a Banjo/FIDL protocol, or a framework device API. The
driver framework grants only the resource handles and protocols required by
that device. The kernel completes the controller-side IRQ before returning from
the handler; the scheduled driver thread then performs the separate device-side
acknowledgement needed to prevent a level source from immediately reasserting.

#### Interrupt objects, waiting, and ports

The syscall and dispatcher path is implemented in
`zircon/kernel/lib/syscalls/driver.cc` and
`zircon/kernel/object/interrupt_dispatcher.cc`. A driver receives an interrupt
handle through the driver framework; ordinary components cannot manufacture an
authorized hardware interrupt by guessing an IRQ number.

```text
┌────────────────────────────────────────────────────┐
│ Driver thread                                      │
└─────────────────────┬──────────────────────────────┘
                      │ zx_interrupt_wait(handle)
                      ▼
┌────────────────────────────────────────────────────┐
│ sys_interrupt_wait → InterruptDispatcher           │
│ WaitForInterrupt blocks the current thread         │
└─────────────────────┬──────────────────────────────┘
                      │ hardware handler calls InterruptHandler
                      ▼
              ┌───────┴────────┐
              │ Port bound?    │
              └───┬─────────┬──┘
                 no         yes
                  ▼         ▼
┌───────────────────────┐  ╭───────────────────────────────╮
│ Wake direct waiter    │  │ Queue zx_port_packet_t;       │
│ with IRQ timestamp    │  │ event loop selects by key     │
└───────────────────────┘  ╰───────────────────────────────╯
```

`InterruptDispatcher::InterruptHandler()` records the timestamp and either
satisfies a direct wait or queues a packet to a bound port. A port is useful
when one driver thread must wait for a channel request, an interrupt, and a
timer without polling. The driver still reads and acknowledges device state
before relying on the next edge or level assertion.

#### Interrupt context, preemption, and timers

Vector and controller-handler work must be short and non-blocking. It runs with
restricted context: sleeping, waiting for a channel reply, taking arbitrary
long-lived locks, or doing slow console I/O there can delay every interrupt on
that CPU. The normal division is to acknowledge enough state to make forward
progress, signal a waiter or queue a port packet, then let a scheduled thread
perform slower device work.

```text
┌──────────────────────────────────────────────┐
│ IRQ vector: save interrupted register state  │
└────────────────────┬─────────────────────────┘
                     │ arm64_irq → platform_irq
                     ▼
┌──────────────────────────────────────────────┐
│ Fast work: claim, account, signal, and EOI   │
└────────────────────┬─────────────────────────┘
                     │ interrupt made higher-priority work ready?
                     ▼
              ┌──────┴──────┐
              │ preempt?    │
              └───┬──────┬──┘
                 yes     no
                  ▼      ▼
╭────────────────────╮  ╭──────────────────────────────╮
│ Scheduler selects  │  │ Return to interrupted context│
│ runnable work      │  ╰──────────────────────────────╯
╰────────────────────╯
```

`int_handler_finish` informs `arm64_irq` whether a preemption check is needed;
the actual scheduling decision remains in the Zircon scheduler. A timer expiry
uses the same wake/preemption machinery: it makes a waiting thread eligible to
run rather than busy-looping in a console or driver-host.

#### arm64 source map and debugging checklist

| Question | Representative source or observation |
| --- | --- |
| Which CPU entry runs? | `zircon/kernel/arch/arm64/exceptions.S`, `arm64_el1_exception` and `.vbar_table` |
| Where are IRQ accounting and preemption checked? | `zircon/kernel/arch/arm64/exceptions_c.cc`, `arm64_irq()` |
| Where does the controller claim and EOI an IRQ? | `zircon/kernel/dev/interrupt/gic/`; GICv2 example: `arm_gicv2.cc:gic_handle_irq` |
| Where does an IRQ become a wait/port notification? | `zircon/kernel/object/interrupt_dispatcher.cc` |
| Where is the user ABI wait validated? | `zircon/kernel/lib/syscalls/driver.cc` |
| Why does a driver receive no interrupt? | Check routing, controller enable/affinity, device state, mask/acknowledge, and handle/port setup in that order. |
| Why does one IRQ repeat? | Check device-status acknowledgement separately from GIC EOI/deactivation. |
| Why is IRQ latency high? | Look for long handler work, disabled interrupts, affinity imbalance, or scheduling delay. |

> TODO: Document the riscv64 `stvec` entry, `scause` dispatch, PLIC
> claim/complete flow, and timer/IPI delivery separately. Do not infer those
> details from the arm64 `VBAR_EL1` or GIC diagrams.

### Processes, handles, and IPC

Zircon exposes kernel objects through per-process handles. Rights on a handle
control which operations a component or driver may perform. Channels transfer
messages and handles; ports aggregate asynchronous packets; jobs provide
process containment and lifecycle control.

    component A                         component B
    +-----------+                       +-----------+
    | handle A  | -- channel message -->| handle B  |
    | VMO/event | -- transferred rights | VMO/event |
    +-----------+                       +-----------+
             \                             /
              `------ kernel handle tables

This is the mechanism behind component manager capability routing and driver
framework protocols. In SMOS, `console-launcher` can access the capabilities
offered in `console.bootstrap_shard.cml`, while a `driver-host` receives only
the directories, protocols, and device resources required by its driver.
`devfs` is therefore a namespace and capability boundary, not merely a list of
kernel device files.

#### IPC code path: channel write to message delivery

For a channel send, the relevant path is `sys_channel_write` in
`zircon/kernel/lib/syscalls/channel.cc`, followed by
`ChannelDispatcher::Write`:

    client thread
       |
       | zx_channel_write(channel, bytes, handles)
       v
    sys_channel_write(...)
       |
       +--> validate user buffers and handle rights
       +--> build MessagePacket
       `--> ChannelDispatcher::Write(...)
               |
               +--> enqueue peer message
               +--> signal readable state
               `--> wake a peer waiter if present

The receiver then performs `zx_channel_read` or waits through a port/async
dispatcher. Component startup, driver framework `Node` protocols, and dash
service connections all use this capability-and-message model rather than
sharing arbitrary process memory.

### Kernel-to-driver boundary

The final division of labor is intentionally narrow:

    kernel: syscall, VM, scheduling, IRQ, handle and object primitives
       |
       | framework protocols / resources / FIDL
       v
    driver_manager -> driver_index -> driver-host
       |
       v
    user-mode driver -> devfs or FIDL service -> client

The QEMU board, serial, block, RTC, random, and virtio-socket drivers retained
by SMOS run on the user side of this boundary unless their implementation
explicitly requires a kernel primitive. This model keeps crashes and restart
scope smaller: a driver-host can be restarted by the framework without
replacing the Zircon kernel or the entire component realm.

#### Driver startup code path

The product's user-mode driver startup is coordinated by the code under
`userspace/devices/bin/driver_manager`:

    device node discovered
          |
          v
    BindManager::BindNodeToResult(...)
          |
          +--> driver_index returns matching driver metadata
          |
          v
    DriverRunner::StartDriver(...)
          |
          +--> launch driver-host component
          +--> pass framework capabilities and node handles
          `--> driver Node::StartDriver(...)
                    |
                    v
             user-mode driver publishes protocol/devfs node
                    |
                    v
             console, fshost, or another component opens it

`DriverRunner::StartDevfsDriver` handles the devfs-facing startup path, while
the bind manager handles matching and composite-node decisions. A failure in a
driver-host is therefore observed as a component/driver lifecycle failure and
does not imply a kernel memory or scheduler failure.

### Reference-derived interface contracts

The following contracts connect the kernel primitives to the interfaces used
by SMOS components. They are expressed in terms of the compact product
graph, so they remain useful after the imported reference handbook is removed.

#### FIDL and channel contract

FIDL is a typed protocol description and code-generation layer over Zircon
channels. A protocol method becomes a channel message with an ordinal, an
encoded request or response payload, and zero or more transferred handles.
Component manager and the driver framework route the channel capability; the
kernel validates channel rights, message size, handle rights, and object
lifetime.

FIDL declarations use two dimensions that matter at the SMOS boundary:

- **Value types** such as integers, strings, vectors, structs, tables, and
  unions contain data in the message representation.
- **Resource types** such as handles, channels, VMOs, events, and sockets carry
  kernel object capabilities. A resource handle is consumed from the sender's
  message and installed in the receiver's handle table.

Tables and flexible unions allow a receiver to tolerate fields or variants
introduced by a newer peer. Strict enums and unions reject unknown values so
that a protocol can fail closed when the value is part of a security or state
machine decision. SMOS protocols should choose strictness from the failure
behavior they require, rather than relying on a default encoding.

```text
FIDL declaration
       |
       | fidlc + language binding generator
       v
typed client/server API
       |
       | encode payload + transfer resource handles
       v
Zircon channel message
       |
       | component capability routing / driver framework
       v
server binding -> decode -> validate -> dispatch method
```

The channel remains the ownership boundary. A service must close or retain
every received handle deliberately, and it must treat `ZX_ERR_PEER_CLOSED` as
normal lifecycle information when a component or driver-host exits. FIDL
does not grant a server access to the sender's address space; shared data must
be represented by a VMO or another explicitly transferred object.

#### Boot command line and ZBI contract

The boot command line is data carried through the boot image, not a direct
kernel function call. The SMOS boot-shim creates or preserves ZBI items for
the platform description and command line, `kernel.phys` consumes the early
items, and userboot passes the resulting startup handles and arguments into
the component startup path.

```text
board configuration / QEMU arguments
              |
              v
        boot-shim builds ZBI
        (platform items + cmdline)
              |
              v
        Zircon physical loader
              |
              +--> kernel consumes platform and memory items
              `--> userboot preserves startup data
                           |
                           v
                bootsvc / component manager
                routes supported startup options
```

Only options used by the compact product should be added to a launch command.
For example, the console workflow may enable shell startup through the product
manifest and the QEMU runner may append a diagnostic argument, but neither
path should assume that a full netstack, graphical session, or update service
exists. When debugging startup, record the exact command line, ZBI item type,
and component that consumes the option; an option read by userboot is not
necessarily a kernel option.

#### Tracing contract

Tracing is an observation path layered on kernel objects and component events;
it does not change their ownership or scheduling semantics. User-space code
can record duration, instant, counter, asynchronous, flow, and kernel-object
events through trace macros. A trace provider writes compact records to a
buffer managed by the tracing system, while the trace manager aggregates
records from providers and kernel sources.

```text
component / driver / kernel
          |
          | TRACE_DURATION / TRACE_INSTANT /
          | TRACE_KERNEL_OBJECT
          v
trace provider -> shared trace buffer -> trace manager -> archive/tool
```

Use stable categories and names for repeated SMOS workflows: boot stages,
component startup, driver bind/start, channel calls, interrupt waits, and VMO
mapping. `TRACE_KERNEL_OBJECT` identifies a handle-backed object in the trace;
it does not expose the object to another process. Tracing must remain
diagnostic-only, with instrumentation guarded or disabled where it would alter
compact boot timing or image policy.

#### Reference-to-implementation map

| Contract | SMOS implementation path | Primary evidence |
| --- | --- | --- |
| Kernel object and handle rights | `zircon/kernel/object/`, `zircon/kernel/lib/syscalls/` | handle type, rights, signal, and status code |
| FIDL channel protocol | `sdk/fidl/`, component `.cml`, driver framework protocols | generated binding and channel message |
| Boot command line and ZBI | `zircon/kernel/phys/`, boot-shim, `tools/smos-boot/run-qemu.sh` | ZBI manifest and serial startup log |
| Driver resource capability | `release/platform/boards/`, `userspace/devices/`, driver-host manifests | bind result, capability route, devfs/FIDL publication |
| Runtime tracing | trace macros, provider, trace manager | trace archive with category/object records |

When these layers disagree, debug from the right side of the table toward the
kernel: first verify the product graph and capability route, then the channel
or handle operation, and only then the underlying object, interrupt, VM, or
scheduler implementation.

## Standalone SDK

The normal SDK location is `[PATH]/smos-sdk`. It contains a hashed
`sdk-manifest.json` and the minimum prebuilt file closure observed while both
architectures are configured, built, and boot-tested. Normal builds do not need
the source checkout from which the SDK was initially produced.

Create the SDK once from any explicitly selected compatible Fuchsia checkout.
This command removes the two generated `out/smos-boot-*` directories so strace
observes a complete clean build:

```sh
tools/smos-boot/build-independent-sdk.sh \
  --root "$PWD" \
  --source-checkout /path/to/compatible-fuchsia-checkout \
  --destination /home/beau/clot/smos-sdk
```

Select and validate it for routine work:

```sh
export SMOS_SDK_ROOT=[PATH]/smos-sdk
python3 tools/smos-boot/independent_sdk.py validate \
  --sdk "$SMOS_SDK_ROOT" --architecture arm64 --architecture riscv64
tools/smos-boot/preflight.sh --root "$PWD" arm64
tools/smos-boot/preflight.sh --root "$PWD" riscv64
```

When `SMOS_SDK_ROOT` is exported, `configure.sh` validates the SDK before running GN;
it does not create a source-root `prebuilt` directory or symlink. It passes
absolute SDK paths into GN and never links
`.cipd` or third-party Git metadata. Once SDK creation succeeds, the compatible
source checkout can be removed or made unavailable.

The validated dual-architecture snapshot currently contains 17,284 manifest
entries and 1,578,540,085 logical bytes (`du -sh`: 1.6 GiB). It excludes Go
tests and API documentation, non-x86_64 Linux sysroot libraries, unused Clang
sanitizer variants, and the unused QEMU data directory; riscv64 keeps only its
required OpenSBI firmware. All retained symlinks resolve inside the SDK.

## Configure, build, and verify

No `fx` setup is required. Build both supported console images directly:

```sh
tools/smos-boot/configure.sh arm64
tools/smos-boot/configure.sh riscv64
tools/smos-boot/build.sh arm64
tools/smos-boot/build.sh riscv64
tools/smos-boot/verify.sh all
python3 tools/smos-boot/compact.py \
  --measure . --max-bytes 524288000
du -sb /home/beau/clot/smos-sdk
```

Build outputs are `out/smos-boot-arm64/smos.zbi` and
`out/smos-boot-riscv64/smos.zbi`. `verify.sh all` automatically
boots arm64 with external QEMU through a PTY and requires the dash prompt,
completed component and driver startup, basic `/boot` commands, and passing
channel/thread/VMO/event and timer checks. RISC-V remains compiled by
`build.sh riscv64`; launch `run-qemu.sh riscv64` for its manual QEMU validation.
The interactive dash prompt is `smos:\> `.

For manual arm64 acceptance, compile and then start interactive QEMU:

```sh
export SMOS_SDK_ROOT=[PATH]/smos-sdk
tools/smos-boot/configure.sh arm64
tools/smos-boot/build.sh arm64
tools/smos-boot/run-qemu.sh arm64
```

For an interactive console, use:

```sh
tools/smos-boot/run-qemu.sh arm64
tools/smos-boot/run-qemu.sh riscv64
```

## Virtualization scope

arm64 retains Zircon hypervisor syscalls, the VMM, guest manager, guest
configuration libraries, virtio socket, and the headless guest devices for
block, console, RNG, vsock, balloon, and memory. GPU virtualization devices are removed,
including virtio-gpu, display input, virtual sound, virtio-net,
Wayland, Magma, Goldfish, Scenic, Mesa, and Vulkan integration. The current
arm64 physical loader drops QEMU from EL2 to EL1 before starting Zircon, so
`virtcheck` reports
`VIRTUALIZATION:ARM64:NO_NESTED_EL2` in this QEMU boot path; the virtualization
implementation remains compiled and packaged for an EL2-capable launch path.

riscv64 is retained as a console and microkernel-primitives build target, but
its virtualization host is explicitly unsupported and reports
`VIRTUALIZATION:RISCV64:UNSUPPORTED`.

## Rebuilding the compact inventory

After changing either product graph and completing the corresponding builds,
regenerate and stage the exact transitive source closure from the built output
directories:

```sh
python3 tools/smos-boot/inventory.py \
  --output out/smos-keep.json \
  --nul-output out/smos-keep.nul \
  --report kept-components.md \
  --external-toolchain "$SMOS_SDK_ROOT"
python3 tools/smos-boot/compact.py \
  --manifest out/smos-keep.json \
  --source "$PWD" \
  --destination ../smos-stage \
  --external-toolchain "$SMOS_SDK_ROOT" \
  --replace-staging
```

If SDK validation reports a missing file or hash mismatch, do not edit the
published SDK in place. Re-run `build-independent-sdk.sh` with a temporary
destination, validate it, then install it with `--replace`.



Some optional-domain protocol and host assembly sources remain as compile-time
inputs to common tooling. They are listed separately in the inventory and do
not install optional-domain services or drivers into the runtime BootFS.


## Virtualization

- [Hypervisor.md](Hypervisor.md)


## Rust Implementation

- [Rust.md](Rust.md)


<!-- References -->

[1]: ../../zircon/kernel/lib/arch/arm64/include/lib/arch/zbi-boot.h
[2]: ../../zircon/kernel/phys/handoff-prep.cc
[3]: ../../zircon/kernel/lib/userabi/userboot.cc

---

SMOS [microkernel]
