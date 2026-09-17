# Process

## NAME

process - Process abstraction

## SYNOPSIS

A zircon process is an instance of a program in the traditional
sense: a set of instructions that will be executed by one or more
threads, along with a collection of resources.

## DESCRIPTION

The process object is a container of the following resources:

### Handles

Handles are kernel constructs that allow user-mode programs to
reference a kernel object. A handle can be thought of as a session
or connection to a particular kernel object.

It is often the case that multiple processes concurrently access
the same object via different handles. However, a single handle
can only be either bound to a single process or be bound to the
kernel.

When it is bound to the kernel we say it's 'in-transit'.

In user mode a handle is simply a specific number returned by
some syscall. Only handles that are not in-transit are visible
to user-mode.

The integer that represents a handle is only meaningful for that
process. The same number in another process might not map to any
handle or it might map to a handle pointing to a completely
different kernel object.

The integer value for a handle is any 32-bit number except the value
corresponding to **ZX_HANDLE_INVALID** which will always have the
value of 0.  In addition to this, the integer value of a valid handle
will always have two least significant bits of the handle set.  The
mask representing these bits may be accessed using
**ZX_HANDLE_FIXED_BITS_MASK**

For kernel mode, a handle is a C++ object that contains three
logical fields:

* A reference to a kernel object
* The rights to the kernel object
* The process it is bound to (or if it's bound to the kernel)

### VMAR (Virtual Memory Address Regions)

Virtual Memory Address Regions (VMARs) represent contiguous parts of a virtual
address space.

VMARs are used by the kernel and userspace to represent the allocation of an
address space.

Every process starts with a single VMAR (the root VMAR) that spans the entire
address space (see [`zx_process_create()`]).  Each VMAR
can be logically divided up into any number of non-overlapping parts, each
representing a child VMARs, a virtual memory mapping, or a gap.  Child VMARs
are created using [`zx_vmar_allocate()`].  VM mappings
are created using [`zx_vmar_map()`].

VMARs have a hierarchical permission model for allowable mapping permissions.
For example, the root VMAR allows read, write, and executable mapping.  One
could create a child VMAR that only allows read and write mappings, in which
it would be illegal to create a child that allows executable mappings.

When a VMAR is created using [`zx_vmar_allocate()`], its parent VMAR retains a reference
to it.  Because of this, if all handles to the child VMAR are closed, the child
and its descendants will remain active in the address space.  In order to
disconnect the child from the address space, [`zx_vmar_destroy()`]
must be called on a handle to the child.

By default, all allocations of address space are randomized.  At VMAR
creation time, the caller can choose which randomization algorithm is used.
The default allocator attempts to spread allocations widely across the full
width of the VMAR.  The alternate allocator, selected with
**ZX_VM_COMPACT**, attempts to keep allocations close together within the
VMAR, but at a random location within the range.  It is recommended to use
the default allocator.

VMARs optionally support a fixed-offset mapping mode (called specific mapping).
This mode can be used to create guard pages or ensure the relative locations of
mappings.  Each VMAR may have the **ZX_VM_CAN_MAP_SPECIFIC** permission,
regardless of whether or not its parent VMAR had that permission.

 - [`zx_vmar_allocate()`] - create a new child VMAR
 - [`zx_vmar_map()`] - map a VMO into a process
 - [`zx_vmar_unmap()`] - unmap a memory region from a process
 - [`zx_vmar_protect()`] - adjust memory access permissions
 - [`zx_vmar_destroy()`] - destroy a VMAR and all of its children

A Virtual Memory Object (VMO) represents a contiguous region of virtual memory
that may be mapped into multiple address spaces.

VMOs are used in the kernel and userspace to represent both paged and physical memory.
They are the standard method of sharing memory between processes, as well as between the kernel and
userspace.

VMOs are created with [`zx_vmo_create()`] and basic I/O can be
performed on them with [`zx_vmo_read()`] and [`zx_vmo_write()`].
A VMO's size may be set using [`zx_vmo_set_size()`].
Conversely, [`zx_vmo_get_size()`] will retrieve a VMO's current size.

The size of a VMO will be rounded up to the next page size boundary by the kernel.

Pages are committed (allocated) for VMOs on demand through [`zx_vmo_read()`], [`zx_vmo_write()`], or by writing to a mapping of the VMO created using [`zx_vmar_map()`]. Pages can be committed and decommitted from a VMO manually by calling
[`zx_vmo_op_range()`] with the **ZX_VMO_OP_COMMIT** and **ZX_VMO_OP_DECOMMIT**
operations, but this should be considered a low level operation. [`zx_vmo_op_range()`] can also be used for cache and locking operations against pages a VMO holds.

Processes with special purpose use cases involving cache policy can use
[`zx_vmo_set_cache_policy()`] to change the policy of a given VMO.
This use case typically applies to device drivers.

 - [`zx_vmo_create()`] - create a new vmo
 - [`zx_vmo_create_child()`] - create a new child vmo
 - [`zx_vmo_create_physical()`] - create a new physical vmo
 - [`zx_vmo_get_size()`] - obtain the size of a vmo
 - [`zx_vmo_op_range()`] - perform an operation on a range of a vmo
 - [`zx_vmo_read()`] - read from a vmo
 - [`zx_vmo_replace_as_executable()`] - make an executable version of a vmo
 - [`zx_vmo_set_cache_policy()`] - set the caching policy for pages held by a vmo
 - [`zx_vmo_set_size()`] - adjust the size of a vmo
 - [`zx_vmo_write()`] - write to a vmo

<br>

 - [`zx_vmar_map()`] - map a VMO into a process
 - [`zx_vmar_unmap()`] - unmap memory from a process

### Threads

The thread object is the construct that represents a time-shared CPU execution
context. Thread objects live associated to a particular Process Object, which
provides the memory and the handles to other objects necessary for I/O and computation.

Threads are created by calling [`zx_thread_create()`], but only start executing
when either [`zx_thread_start()`] or [`zx_process_start()`] are called. Both syscalls
take as an argument the entrypoint of the initial routine to execute.

The thread passed to [`zx_process_start()`] should be the first thread to start execution
on a process.

A thread terminates execution:
+ by calling [`zx_thread_exit()`]
+ by calling [`zx_vmar_unmap_handle_close_thread_exit()`]
+ by calling [`zx_futex_wake_handle_close_thread_exit()`]
+ when the parent process terminates
+ by calling [`zx_task_kill()`] with the thread's handle
+ after generating an exception for which there is no handler or the handler
decides to terminate the thread.

Returning from the entrypoint routine does not terminate execution. The last
action of the entrypoint should be to call [`zx_thread_exit()`] or one of the
above mentioned `_exit()` variants.

Closing the last handle to a thread does not terminate execution. In order to
forcefully kill a thread for which there is no available handle, use
[`zx_object_get_child()`] to obtain a handle to the thread. This method is strongly
discouraged. Killing a thread that is executing might leave the process in a
corrupt state.

Fuchsia native threads are always *detached*. That is, there is no *join()* operation
needed to do a clean termination. However, some runtimes above the kernel, such as
C11 or POSIX might require threads to be joined.

Threads provide the following signals:

+ `ZX_THREAD_TERMINATED`
+ `ZX_THREAD_SUSPENDED`
+ `ZX_THREAD_RUNNING`

When a thread is started `ZX_THREAD_RUNNING` is asserted. When it is suspended
`ZX_THREAD_RUNNING` is deasserted, and `ZX_THREAD_SUSPENDED` is asserted. When
the thread is resumed `ZX_THREAD_SUSPENDED` is deasserted and
`ZX_THREAD_RUNNING` is asserted. When a thread terminates both
`ZX_THREAD_RUNNING` and `ZX_THREAD_SUSPENDED` are deasserted and
`ZX_THREAD_TERMINATED` is asserted.

Note that signals are OR'd into the state maintained by the [`zx_object_wait_*()`]
family of functions thus you may see any combination of requested signals when
they return.

 - [`zx_thread_create()`] - create a new thread within a process
 - [`zx_thread_exit()`] - exit the current thread
 - [`zx_thread_read_state()`] - read register state from a thread
 - [`zx_thread_start()`] - cause a new thread to start executing
 - [`zx_thread_write_state()`] - modify register state of a thread

<br>

 - [`zx_task_create_exception_channel()`] - listen for task exceptions
 - [`zx_task_kill()`] - cause a task to stop running

In general, it is associated with code, which it is executing until it is
forcefully terminated or the program exits.

Processes are owned by [jobs](#Jobs) and allow an application that is
composed by more than one process to be treated as a single entity, from the
perspective of resource and permission limits, as well as lifetime control.

### Jobs

A job is a group of processes and possibly other (child)
jobs. Jobs are used to track privileges to perform kernel operations (i.e., make
various syscalls, with various options), and track and limit basic resource
(e.g., memory, CPU) consumption. Every process belongs to a single job. All the
jobs on a Fuchsia system form a tree, with every job, except the root job,
belonging to a single (parent) job.

A job is an object consisting of the following:

+ a reference to a parent job
+ a set of child jobs (each of which has this job as its parent)
+ a set of member processes
+ a set of policies

Jobs allow "applications" that are composed of more than one process to be
controlled as a single entity.

 - [`zx_job_create()`] - create a new child job.
 - [`zx_job_set_critical()`] - set a process as critical to a job.
 - [`zx_job_set_policy()`] - set policy for new processes in the job.
 - [`zx_process_create()`] - create a new process within a job.
 - [`zx_task_create_exception_channel()`] - listen for task exceptions
 - [`zx_task_kill()`] - cause a task to stop running.

### Lifetime

A process is created via [`zx_process_create()`] and its execution begins with
[`zx_process_start()`].

The process stops execution when:

+ the last thread is terminated or exits
+ the process calls [`zx_process_exit()`]
+ the parent job terminates the process
+ the parent job is destroyed

The call to [`zx_process_start()`] cannot be issued twice. New threads cannot
be added to a process that was started and then its last thread has exited.

## SYSCALLS

 - [`zx_process_create()`] - create a new process within a job
 - [`zx_process_read_memory()`] - read from a process's address space
 - [`zx_process_start()`] - cause a new process to start executing
 - [`zx_process_write_memory()`] - write to a process's address space
 - [`zx_process_exit()`] - exit the current process

<br>

 - [`zx_job_create()`] - create a new job within a parent job

<br>

 - [`zx_task_create_exception_channel()`] - listen for task exceptions

<br>

 - [`zx_vmar_map()`] - Map memory into an address space range
 - [`zx_vmar_protect()`] - Change permissions on an address space range
 - [`zx_vmar_unmap()`] - Unmap memory from an address space range

---

SMOS [Microkernel]
