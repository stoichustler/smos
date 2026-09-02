# SMOS Memory Model

This document adapts the Fuchsia address-space, memory-reclamation, and kernel
memory-usage guides to the compact SMOS profile. It describes the mechanisms
implemented by Zircon and the observations available to SMOS developers; it
does not imply that every full Fuchsia memory service is included in SMOS.

## Address spaces

An address space is the virtual-address range through which a process accesses
memory. SMOS isolates processes with a root `VmAddressRegion` (VMAR). A VMAR
contains child VMARs and VM mappings; a mapping connects a virtual range to a
`VmObject` (VMO). The kernel's VMM maintains this hierarchy and programs the
architecture-specific page tables.

```text
process root VMAR
 │
 ├──► child VMAR
 │     ╰──► mapping -> VMO -> physical pages
 │
 ╰──► mapping -> VMO -> physical pages
```

VMARs describe where a mapping may live and which permissions it may have.
Mappings describe the virtual range that is currently backed by a VMO. VMOs
own byte ranges and page state; the same VMO may be mapped into more than one
address space. A handle's rights and the VMAR permissions jointly constrain
what a process can do.

The kernel implementation is split across `zircon/kernel/vm/`,
`VmAddressRegionDispatcher`, and `VmObjectDispatcher`. The corresponding user
APIs are `zx_vmar_allocate`, `zx_vmar_map`, `zx_vmar_unmap`,
`zx_vmar_protect`, `zx_vmo_create`, and `zx_vmo_op_range`.

## VMM and PMM

The virtual memory manager (VMM) maintains VMAR trees, mappings, access
protections, and hardware page tables. Address-space layout randomization may
place new VMARs at different virtual addresses, so callers must use returned
addresses rather than assumptions about layout.

The physical memory manager (PMM) divides available RAM into pages and supplies
them to VMOs. Most VMOs are demand populated: a read can use the shared zero
page, while a write commits a private physical page. Pager-backed VMOs obtain
their contents from a userspace pager, which is how executable and filesystem
data can be faulted in on demand.

## Mapping and first access

The following call chain is the normal path for a newly mapped VMO. The exact
fault handler names vary by architecture, but the ownership boundaries are
stable.

```text
zx_vmar_map(vmar, vmo)
 │
 ╰──► VmAddressRegionDispatcher::Map()
       │
       ╰──► VmAddressRegion::CreateVmMapping()
             │
             ╰──► VmMapping records virtual range + VMO offset
                   │
                   ╰──► first access raises page fault
                         │
                         ├──► VmAspace finds VmMapping in VMAR tree
                         ├──► VmObject supplies or commits a physical page
                         ╰──► ArchVmAspace installs the page-table entry
                               │
                               ◄── retry the faulting instruction
```

The VMO and mapping outlive a single page fault. Unmapping removes the virtual
translation, while closing the last VMO reference can release its pages when
no other mapping, child VMO, or kernel owner retains them.

## Memory reclamation

SMOS inherits the kernel mechanisms needed to keep free pages available:

- Pager-backed pages can be evicted and read back from their pager source.
- Anonymous VMOs can share the singleton zero page until a write occurs.
- Unused page-table mappings can be rebuilt from the VMAR and VMO metadata.
- Discardable VMOs may release unlocked pages under pressure; clients must
  reinitialize contents after observing that pages were discarded.

Reclamation is a kernel policy decision. A userspace component can provide
discard hints with `zx_vmo_op_range` or respond to a memory-pressure capability
when that capability is present in the product. It must not assume that a hint
immediately frees pages.

When reclaimable memory is insufficient, the system may terminate a process or
reboot according to the product's OOM policy. SMOS's compact product boundary
does not add a separate graphical memory-pressure service.

## Observing memory

Use the kernel object and VM diagnostics already present in the source tree to
distinguish virtual size from committed physical memory:

- `DumpProcessVmObjects` reports VMOs associated with a process.
- `DumpAllVmObjects` reports mapped, hidden, and kernel-owned VMOs.
- `GetVmarMaps` walks VMAR and mapping relationships.
- `VmObject::GetAttributedMemory` provides attribution counts used by reports.

These implementations are in `zircon/kernel/object/diagnostics.cc`. The exact
shell command that exposes them depends on the selected console/debug build;
the functions are not a promise of an always-present userspace command.

## SMOS boot example

`userboot_init` creates the initial process root VMAR, maps the userboot image
and vDSO, allocates the initial stack VMO, and starts the first thread. See the
detailed call chain in [SMOS.md](SMOS.md#detailed-userboot_init-call-flow).
That path demonstrates the same VMAR/VMO ownership rules used by later
components: the kernel creates and maps objects, then transfers restricted
handles through the bootstrap channel.

## Source map

| Topic | SMOS source |
| --- | --- |
| VMAR allocation and mapping | `zircon/kernel/vm/`, `vm_address_region_dispatcher.cc` |
| VMO dispatch and rights | `zircon/kernel/object/vm_object_dispatcher.cc` |
| Physical page allocation | `zircon/kernel/vm/pmm.cc` |
| VM diagnostics | `zircon/kernel/object/diagnostics.cc` |
| Initial process address space | `zircon/kernel/lib/userabi/userboot.cc` |

The conceptual material is adapted from Fuchsia's `address_spaces.md`,
`memory_reclamation.md`, and kernel `memory.md` under the Fuchsia BSD license.
