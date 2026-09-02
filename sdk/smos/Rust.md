<!--
SMOS Rust/C++ and kernel linkage notes.
Keep the paths and target names in this document aligned with the tree.
-->

# SMOS Rust Quick Start and End-to-End Paths

This document follows the teaching approach of
[Comprehensive Rust](https://google.github.io/comprehensive-rust/): establish
Rust fundamentals first, then move into systems development and C/C++
interoperability. The examples are adapted to code that is actually encountered
when developing SMOS commands.

The second half uses the Rust `uname` command under
`userspace/sys/smos-bin` to explain how a Rust executable passes
through GN, `rustc`, LLD, C++ shared libraries, FIDL/VDSO, and finally reaches
Zircon's low-level facilities. This gives both a quick language introduction
and a complete view of where the code lands in SMOS.

## 0. Learning Path

```text
Step 1  Read Rust code
  variables/types -> functions/expressions -> if/loop/match
        |
Step 2  Write safe code
  ownership -> borrowing -> slices -> Option/Result
        |
Step 3  Organize code
  struct/enum -> impl -> trait -> generics -> module/crate
        |
Step 4  Write system commands
  std::fs/std::io/std::process -> unit tests -> BUILD.gn
        |
Step 5  Integrate with SMOS
  FFI/C ABI -> fdio/zxio -> FIDL -> VDSO -> Zircon
```

You do not need to learn the entire language before starting. Use a
"read one part, change one thing, run once" loop, returning to
`userspace/sys/smos-bin/src` after each concept and modifying one
command.

## 1. Write a First Command in Ten Minutes

### 1.1 Minimal Program

```rust
fn main() {
    println!("hello, SMOS");
}
```

`fn main()` is the entry point of a binary crate. `println!` is a macro (the
trailing `!` denotes a macro invocation); it formats its arguments and appends a
newline. Rust statements usually end with `;`, but the final expression can omit
the semicolon and become the return value.

### 1.2 A Minimal Argument-Based `echo`

```rust
fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    println!("{}", args.join(" "));
}
```

The corresponding SMOS command target is:

```gn
rustc_binary("echo_bin") {
  output_name = "echo"
  edition = "2021"
  source_root = "src/echo.rs"
  sources = [ "src/echo.rs" ]
  configs += [ "//release/config/rust:bootfs" ]
  with_unit_tests = true
}
```

### 1.3 First Test

```rust
#[cfg(test)]
mod tests {
    #[test]
    fn joins_arguments() {
        let values = ["a", "b"];
        assert_eq!(values.join(" "), "a b");
    }
}
```

`with_unit_tests = true` makes GN generate a test target for the same crate.
Test functions can use `assert_eq!`; failures are reported by the test runner
instead of becoming silent command failures at runtime.

## 2. Rust Syntax Cheatsheet

### 2.1 Variables, Mutability, and Type Inference

```rust
let name = "uname";       // immutable binding, type is &str
let mut count: u32 = 0;   // explicit type, mutable binding
count += 1;
let bytes = name.as_bytes();
```

Immutability by default is part of Rust's safety model. Use `mut` only when a
value really needs to change. Types are usually inferred; spell them out at
command boundaries, FFI boundaries, and public interfaces.

### 2.2 Functions Are Expressions

```rust
fn exit_code(ok: bool) -> i32 {
    if ok { 0 } else { 1 }
}

fn square(value: i32) -> i32 {
    value * value
}
```

The final expression without a semicolon is the function's return value.
`return` is useful for early returns or error handling; prefer a trailing
expression for ordinary calculations.

### 2.3 Control Flow

```rust
for arg in std::env::args() {
    if arg == "--" {
        break;
    }
}

let label = match code {
    0 => "ok",
    1..=125 => "command failed",
    _ => "unknown",
};
```

`match` must cover every possible value. Use `_` for the remaining cases; do not
replace important state decisions with a chain of `if` branches that may omit a
case.

### 2.4 Common Types

```rust
let text: &str = "borrowed string slice";
let owned: String = text.to_owned();
let path: std::path::PathBuf = "/tmp/file".into();
let list: Vec<u8> = vec![1, 2, 3];
let pair: (i32, bool) = (7, true);
```

`&str` is a borrowed UTF-8 string slice, while `String` owns heap memory.
Use `Path`/`PathBuf` for paths instead of manually concatenating strings;
`Vec<T>` is a growable array. Prefer `args_os()` and `OsString` for command
arguments so non-UTF-8 filenames are not lost.

## 3. Ownership, Borrowing, and Lifetimes

> **Ownership** Rules:
>
> ➊ Each value in Rust has an owner.
>
> ➋ There can only be one owner at a time.
>
> ➌ When the owner goes out of scope, the value will be dropped.

Ownership is the most important difference between Rust and C/C++. Every value
has an owner, and the value is released automatically when the owner leaves its
scope. Assignment moves by default; automatic copying applies only to simple
types that implement `Copy`.

```rust
let path = String::from("/boot/bin/uname");
let moved = path;
// println!("{path}"); // compile error: path was moved to moved
println!("{moved}");
```

Borrow the value when it must remain usable:

```rust
fn basename(path: &str) -> &str {
    path.rsplit('/').next().unwrap_or(path)
}

let path = String::from("/boot/bin/uname");
assert_eq!(basename(&path), "uname");
println!("{path}"); // path is still owned by the caller
```

At most one `&mut T` may exist at a time. Multiple immutable borrows are allowed,
but they cannot overlap a mutable borrow:

```rust
fn append_newline(text: &mut String) {
    text.push('\n');
}

let mut output = String::from("done");
append_newline(&mut output);
```

Lifetimes are normally inferred. Write an explicit lifetime only when a returned
reference comes from multiple input references and the inference rules cannot
determine the relationship:

```rust
fn longer<'a>(left: &'a str, right: &'a str) -> &'a str {
    if left.len() >= right.len() { left } else { right }
}
```

### 3.1 Comparison with C/C++

```text
C/C++                         Rust
───────────────────────────────────────────────────────────────
malloc/free                  ownership + automatic Drop
const char*                  &str / &[u8]
char* + length               &[u8] / &mut [u8]
nullable pointer             Option<&T> / Option<NonNull<T>>
error return + errno         Result<T, E>
tagged union                 enum
virtual interface            trait
```

Rust's borrow checker prevents use-after-free, multiple mutable access, and
dangling references at compile time. This is not runtime garbage collection,
and functions do not need a manual `free` call.

### 3.2 Memory Model: Stack, Heap, and Drop

```text
thread stack                  heap
─────────────────────         ─────────────────────────────────
let count: u64 = 1;            String { ptr, len, cap }
let path: PathBuf;       ---->  [ '/', 'b', 'o', 'o', ... ]
function locals               contiguous `Vec<u8>` buffer
scope-based cleanup            released when the owner Drops
```

The value itself may live on the stack, or the stack may hold only a descriptor
pointing to heap data. The value owns the heap buffers of `String` and `Vec<T>`;
when the scope ends, the compiler inserts `drop`, which eventually calls the
type's `Drop::drop` implementation if one exists. This is deterministic
scope-based cleanup, not a tracing garbage collector:

```rust
fn make_path() -> std::path::PathBuf {
    let path = std::path::PathBuf::from("/boot/bin/uname");
    path // ownership moves to the caller; heap data remains valid after return
}

let path = make_path();
// path releases its buffer when it leaves the current scope
```

### 3.3 Move, Copy, and Clone

```rust
let a = String::from("owned");
let b = a;              // move: b takes over ptr/len/cap
// println!("{a}");     // error: a is no longer a valid owner

let x: u32 = 7;
let y = x;              // Copy: both x and y remain usable
assert_eq!(x + y, 14);

let c = b.clone();      // deep copy: allocate and copy the string bytes
```

`Copy` applies only to simple types where bitwise copying cannot cause a double
free. `String`, `Vec<T>`, and file handles are normally not `Copy`. `clone()` is
explicit and may be expensive; commands processing large files or byte buffers
should borrow or move values instead of cloning unconditionally.

### 3.4 Borrowing Rules

```text
At any moment, a value can be in only one of the following states:

  multiple immutable borrows       one mutable borrow
  &value  &value  &value        &mut value
       \       |       /              |
        read-only                    read/write

  The two states cannot overlap:
  &value + &mut value  -> compile error
  two &mut value        -> compile error
```

```rust
let mut buffer = vec![1, 2, 3];
let view = &buffer[..];       // buffer cannot change while view is borrowed
assert_eq!(view[0], 1);

// buffer.push(4);           // error: view is still alive
drop(view);                  // end the borrow
buffer.push(4);              // modification is now allowed
```

Slices `&[T]`/`&mut [T]` are "pointer + length" pairs and do not own the backing
memory. They are useful for passing file buffers, network frames, or FIDL
payloads without copying an entire `Vec`.

### 3.5 Choosing Smart Pointers

| Type | Ownership/use | Threads | Typical SMOS scenario |
| --- | --- | --- | --- |
| `Box<T>` | unique ownership, heap allocation | `Send/Sync` depends on `T` | recursive types, explicit heap objects |
| `Rc<T>` | single-thread shared ownership, reference counted | not cross-thread | single-thread parse trees or caches |
| `Arc<T>` | atomic reference-counted shared ownership | cross-thread when `T: Send + Sync` | read-only config shared by workers |
| `Cell<T>` | single-thread interior mutability, value replacement | not cross-thread | small `Copy` state |
| `RefCell<T>` | single-thread runtime borrow checking | not cross-thread | mutation through `&self` |
| `Mutex<T>` | mutual exclusion for shared mutable state | commonly paired with `Arc` | cross-thread counters and state tables |
| `Weak<T>` | non-owning weak reference | paired with `Rc/Arc` | avoiding parent/child reference cycles |

```rust
use std::sync::{Arc, Mutex};
use std::thread;

let count = Arc::new(Mutex::new(0_u32));
let worker_count = Arc::clone(&count);
let worker = thread::spawn(move || {
    let mut value = worker_count.lock().expect("counter not poisoned");
    *value += 1;
});
worker.join().unwrap();
assert_eq!(*count.lock().unwrap(), 1);
```

`Arc` only allows multiple threads to own the same object; it does not prevent
data races inside the object. Mutable data still needs `Mutex`, `RwLock`, or an
atomic type. `Rc<RefCell<T>>` is a common single-thread combination, while
`Arc<Mutex<T>>` is its cross-thread counterpart. Do not return a `RefCell` or
`MutexGuard` after the protected object has gone out of scope.

## 4. Data Modeling: struct, enum, Option, and Result

### 4.1 Structs and Methods

```rust
struct Command {
    name: String,
    status: i32,
}

impl Command {
    fn succeeded(&self) -> bool {
        self.status == 0
    }
}

let command = Command { name: "uname".into(), status: 0 };
assert!(command.succeeded());
```

The receiver determines how a method uses its object:

```rust
struct Buffer {
    bytes: Vec<u8>,
}

impl Buffer {
    fn new() -> Self { Self { bytes: Vec::new() } } // associated function, no self
    fn len(&self) -> usize { self.bytes.len() }     // immutable borrow
    fn push(&mut self, byte: u8) { self.bytes.push(byte); } // mutable borrow
    fn into_bytes(self) -> Vec<u8> { self.bytes }   // consume and move self
}

let mut buffer = Buffer::new();
buffer.push(b'R');
assert_eq!(buffer.len(), 1);
let bytes = buffer.into_bytes();
```

The call `buffer.push(...)` is syntactic sugar: the compiler borrows it as
`Buffer::push(&mut buffer, ...)`. `self` consumes ownership, `&self` is an
immutable borrow, and `&mut self` is a mutable borrow. Objects are commonly
created with associated functions such as `new`, not a special constructor
keyword.

### 4.2 Enums Express State

```rust
enum Input {
    Stdin,
    File(std::path::PathBuf),
}

fn describe(input: Input) -> String {
    match input {
        Input::Stdin => "read stdin".into(),
        Input::File(path) => format!("read {}", path.display()),
    }
}
```

Each enum variant can carry different data. This is useful for representing the
state after command parsing instead of encoding implicit states with several
booleans.

### 4.3 `Option<T>`: May Be Absent

```rust
fn hostname() -> Option<String> {
    std::env::var("HOSTNAME").ok()
}

match hostname() {
    Some(name) => println!("host={name}"),
    None => println!("host is unavailable"),
}
```

Avoid null pointers for absence. `Option` forces callers to handle both `Some`
and `None`.

### 4.4 `Result<T, E>`: May Fail

```rust
fn read_first_line(path: &std::path::Path) -> std::io::Result<String> {
    let text = std::fs::read_to_string(path)?;
    Ok(text.lines().next().unwrap_or_default().to_owned())
}
```

`?` means "return the error to the caller on failure"; it does not swallow the
error. A command entry point normally converts `Result` into diagnostics and a
process exit code:

```rust
fn run() -> Result<(), String> {
    // ...
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("uname: {error}");
        std::process::exit(1);
    }
}
```

## 5. Collections, Iterators, and Closures

```rust
let names = ["cat", "env", "uname"];
let selected: Vec<_> = names
    .iter()
    .filter(|name| name.starts_with('u'))
    .map(|name| name.to_uppercase())
    .collect();
assert_eq!(selected, ["UNAME"]);
```

Iterators are lazy: `filter` and `map` describe transformations, while
`collect` actually consumes the iterator. Prefer iterators over manually
maintained indexes when processing directories, arguments, and byte streams.

```rust
fn list_dir() -> std::io::Result<()> {
    for entry in std::fs::read_dir(".")? {
        let entry = entry?;
        println!("{}", entry.path().display());
    }
    Ok(())
}
```

Closures can capture their environment:

```rust
let prefix = String::from("file:");
let label = |name: &str| format!("{prefix}{name}");
assert_eq!(label("a"), "file:a");
```

## 6. Traits, Generics, and Modules

### 6.1 Traits Define Capabilities

```rust
trait Render {
    fn render(&self) -> String;
}

struct Text(String);

impl Render for Text {
    fn render(&self) -> String { self.0.clone() }
}

fn print_rendered(value: &impl Render) {
    println!("{}", value.render());
}
```

`trait` describes behavior and `impl` implements that behavior for a concrete
type. With a parameter written as `&impl Render`, callers can pass any type that
implements the trait.

A trait can contain default methods, associated types, and associated constants:

```rust
trait Summary {
    type Output;
    const KIND: &'static str;

    fn summarize(&self) -> Self::Output;

    fn label(&self) -> &'static str {
        Self::KIND
    }
}

struct BuildInfo(String);

impl Summary for BuildInfo {
    type Output = String;
    const KIND: &'static str = "build";

    fn summarize(&self) -> String { self.0.clone() }
}
```

A trait can be dispatched in two ways:

```rust
fn static_dispatch<T: Render>(value: &T) -> String {
    value.render() // generic monomorphization; target chosen at compile time
}

fn dynamic_dispatch(value: &dyn Render) -> String {
    value.render() // trait object; runtime dispatch through a vtable
}
```

Prefer generics or `impl Trait`. Use `dyn Trait` only when different concrete
types must share a collection and the implementation is selected at runtime.
`dyn Trait` requires the trait to satisfy object-safety rules; for example, a
method returning `Self` cannot be called directly through a trait object.

Common derived traits:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ExitCode(u8);

assert_eq!(format!("{:?}", ExitCode(0)), "ExitCode(0)");
```

`#[derive]` generates implementations at compile time and is appropriate for
value objects. Do not blindly derive `Copy` or `Clone` for resource handles,
locks, or external ABI types.

### 6.2 Generics Reduce Repetition

```rust
fn first<T>(values: &[T]) -> Option<&T> {
    values.first()
}
```

Generics are monomorphized at compile time and normally have no dynamic
dispatch cost. Use a trait object such as `Box<dyn Render>` for runtime
polymorphism; this introduces a vtable and an indirect call.

### 6.3 Module Boundaries

```text
src/uname.rs       crate root / binary entry
src/format.rs      mod format;
src/format/tests   #[cfg(test)] tests
```

```rust
mod format;

fn main() {
    println!("{}", format::join_words(["Fuchsia", "aarch64"]));
}
```

SMOS GN `sources` must list files discovered by the Rust compiler through
`mod` declarations. Use `pub` to expose library APIs; keeping items private by
default reduces coupling.

## 7. Error Handling and Command-Line Conventions

Commands should distinguish three error classes: argument errors, input/output
errors, and child-command exit statuses.

```rust
fn parse_depth(value: &str) -> Result<usize, String> {
    value.parse::<usize>().map_err(|_| format!("invalid depth: {value}"))
}

fn run(args: &[String]) -> Result<i32, String> {
    let depth = args.first().map(|v| parse_depth(v)).transpose()?;
    println!("depth={depth:?}");
    Ok(0)
}
```

Recommended conventions:

- Print usage and argument errors to stderr and return `1`.
- Include the command name and path in file or service errors.
- Return `127` when a child process does not exist and `126` when it cannot be executed.
- Do not use `unwrap()` for user input, files, or FIDL results.
- Use `expect("invariant")` only for genuinely unavoidable internal invariants.

## 8. Concurrency, Async, and `unsafe`

### 8.1 Threads and Shared State

```rust
use std::sync::{Arc, Mutex};
use std::thread;

let total = Arc::new(Mutex::new(0));
let worker_total = Arc::clone(&total);
let worker = thread::spawn(move || {
    *worker_total.lock().unwrap() += 1;
});
worker.join().unwrap();
assert_eq!(*total.lock().unwrap(), 1);
```

The `Send` and `Sync` traits let the compiler check whether values can be sent
between threads or shared safely. SMOS services commonly use `fuchsia-async`,
FIDL executors, and futures; ownership, borrowing, and `Send/Sync` constraints
remain the foundation of async code.

### 8.2 The Boundary of `unsafe`

```rust
#[repr(C)]
struct StringView {
    data: *const u8,
    length: usize,
}

unsafe extern "C" {
    fn zx_system_get_version_string() -> StringView;
}

// SAFETY: The Zircon VDSO returns a read-only UTF-8 view with an explicit length.
let view = unsafe { zx_system_get_version_string() };
```

`unsafe` does not disable checking; it marks conditions that the caller must
prove. Every unsafe block should document its ABI, pointer validity,
concurrency, and lifetime assumptions.

## 9. Rust/C++ FFI Quick Template

C++ side:

```cpp
// api.h
extern "C" int smos_add(int left, int right);

// api.cc
extern "C" int smos_add(int left, int right) {
  return left + right;
}
```

Rust side:

```rust
unsafe extern "C" {
    fn smos_add(left: i32, right: i32) -> i32;
}

fn main() {
    // SAFETY: The C++ function uses the C ABI, takes two i32 values, and stores no Rust references.
    let result = unsafe { smos_add(2, 3) };
    println!("{result}");
}
```

The GN Rust target must depend on the C/C++ target that provides the symbol, and
the final linker must be able to find the static or shared library. Structs,
callbacks, strings, and ownership are more error-prone than simple integers;
prefer existing bindings or FIDL over hand-written ABI glue.

## 10. Integrating Rust into SMOS

Rust is integrated into SMOS as an ordinary Fuchsia target. The Rust compiler
does not own packaging, component startup, capability routing, or boot image
assembly. Those responsibilities remain in GN, component manifests, and the
SMOS product graph.

```text
Rust source
    |
    | crate root + mod declarations
    v
GN rustc_binary / rustc_library / rustc_test
    |
    | Rust toolchain, target, sysroot, configs, deps
    v
rustc -> LLVM -> LLD
    |
    +--> executable or library
    +--> unit-test target (optional)
    `--> C ABI / FIDL / VDSO dependencies
             |
             v
bootfs_files_for_assembly or fuchsia_package
    |
    v
product assembly -> ZBI/BootFS/package set -> component manager/dash
```

The integration boundary is a graph of build and runtime contracts:

| Layer | Contract | SMOS owner |
| --- | --- | --- |
| Source | crate root, modules, Rust edition, target cfgs | Rust source tree |
| Build | `rustc_*` target, `sources`, `deps`, configs | `BUILD.gn` and `release/rust/*.gni` |
| Link | Rust std, fdio, FIDL bindings, C ABI, VDSO | GN dependency graph and linker |
| Runtime | startup handles, `/svc`, directories, channels, VMOs | component manager and `.cml` manifests |
| Packaging | bootfs file, package binary, component declaration | assembly targets and product graph |
| Validation | compile, unit test, image build, QEMU command | `Makefile` and `tools/smos-boot` |

### 10.1 Choose the integration shape

Start by deciding what the Rust code is. This determines its GN target and its
runtime ownership:

| Rust code shape | Use when | Typical SMOS target |
| --- | --- | --- |
| Command binary | A dash command has one process entry point and exit code | `rustc_binary("uname_bin")` |
| Internal library | Several binaries or components share Rust logic | `rustc_library("component")` |
| Component executable | Component manager launches the process | `rustc_binary("bin")` + `fuchsia_package` |
| BootFS utility | The binary must be present in the early image file set | `bootfs_files_for_assembly("bootfs")` |
| Package utility | The binary is delivered as a resolvable package | `fuchsia_package("<name>_pkg")` |
| Unit/integration test | The code needs an isolated test target | `with_unit_tests = true` or `rustc_test` |
| FIDL client/server | The API crosses a component boundary | generated Rust bindings + channel capability |
| C/C++ adapter | An existing ABI is required | small `extern "C"` wrapper target |

Do not make every Rust file a binary. A command should own argument parsing and
exit status; reusable parsing, formatting, or protocol code belongs in a Rust
library. A component should own its service loop and capability requests, while
kernel or driver implementation remains behind FIDL or an existing safe wrapper.

### 10.2 Source layout and crate boundaries

For a new SMOS command, keep the crate small and colocated with its command
family:

```text
userspace/sys/tools/<tool>/
  BUILD.gn
  src/
    main.rs       crate root for a binary
    args.rs       argument parsing
    format.rs     pure formatting logic
  meta/           component/package manifests when required
```

The existing dash command family uses one source file per command:

```text
userspace/sys/smos-bin/
  BUILD.gn
  src/cat.rs
  src/date.rs
  src/du.rs
  src/env.rs
  src/find.rs
  src/pwd.rs
  src/time.rs
  src/uname.rs
```

`source_root` is the crate root. Rust follows `mod` declarations from that file,
so a module is compiled because the crate imports it, not because GN treats
every `.rs` file as a separate binary. Keep the module in the GN `sources` list
as well: GN uses that list for hermetic input tracking and source validation.

For a library crate, use `src/lib.rs` as the root. For a binary crate, use
`src/main.rs` or a command-specific root such as `src/uname.rs`. Do not put a
second `main` function in a library, and do not put process startup code in a
library merely to make it reusable.

### 10.3 Minimal GN integration

The smallest SMOS BootFS command target looks like this:

```gn
import("//release/assembly/bootfs_files_for_assembly.gni")
import("//release/rust/rustc_binary.gni")

rustc_binary("hello_bin") {
  visibility = [ ":*" ]
  output_name = "hello"
  edition = "2021"
  source_root = "src/main.rs"
  sources = [
    "src/main.rs",
    "src/format.rs",
  ]
  configs += [ "//release/config/rust:bootfs" ]
  with_unit_tests = true
}

bootfs_files_for_assembly("bootfs") {
  deps = [ ":hello_bin" ]
}
```

The important details are:

1. Import the GN template that matches the artifact type.
2. Set a stable output name; dash resolves the installed command by this name.
3. Set one crate root and list every source input required by the GN manifest.
4. Apply the SMOS `bootfs` config for the intended Fuchsia profile.
5. Add the binary to `bootfs_files_for_assembly` only when it must be in the image.
6. Keep `with_unit_tests = true` for command-local tests unless a separate
   `rustc_test` target is more appropriate.

The existing command family uses the same pattern in
`userspace/sys/smos-bin/BUILD.gn`, with a loop for `date`, `du`,
`find`, `pwd`, `time`, and `uname`. Reuse that pattern instead of inventing a
new package macro for another small command.

### 10.4 Library and component integration

Shared Rust code should be a library target with a narrow public API:

```gn
import("//release/rust/rustc_library.gni")

rustc_library("lib") {
  edition = "2021"
  source_root = "src/lib.rs"
  sources = [
    "src/lib.rs",
    "src/protocol.rs",
  ]
  deps = [ "//sdk/rust/zx" ]
  with_unit_tests = true
}
```

For a component executable, keep the Rust binary, package target, and component
manifest separate:

```gn
import("//release/components.gni")
import("//release/rust/rustc_binary.gni")

rustc_binary("bin") {
  output_name = "service"
  edition = "2021"
  source_root = "src/main.rs"
  sources = [ "src/main.rs" ]
  deps = [ ":lib" ]
  with_unit_tests = true
}

fuchsia_package("service") {
  package_name = "service"
  deps = [ ":bin" ]
}
```

The `.cml` manifest, not Rust code, declares required protocols, directories,
storage, runners, and startup handles. A Rust component should request a
capability through the standard Fuchsia client API; it should not assume that a
service exists merely because the host build produced its library.

```text
Rust component
  |
  | startup / namespace / channel request
  v
component manager capability route
  |
  +--> /svc protocol -> FIDL server
  +--> directory      -> fshost/devfs/package namespace
  +--> VMO/channel    -> transferred Zircon handle
  `--> runner         -> process and job creation
```

When a service call blocks, inspect `.cml` offers/exposes, the component
namespace, startup mode, and product package graph before changing Rust control
flow. A successful `rustc` link proves only that symbols are available; it does
not prove that a runtime capability route exists.

### 10.5 Dependencies: GN labels, Rust crates, and FIDL

SMOS uses GN labels as the authoritative build dependency graph. A Rust
`use` statement tells rustc which crate items are needed; a GN `deps` entry tells
the build which crate, generated binding, library, or package must be produced
first.

```text
Rust `use foo::Bar`
        |
        v
crate dependency inside rustc
        ^
        |
GN `deps = [ "//path/to:foo" ]`
        |
        v
Ninja edge: build foo metadata/library before this target
```

For FIDL, depend on the repository's generated binding target rather than
writing wire layouts manually. The normal flow is:

```text
FIDL library
  -> fidlc / FIDL IR
  -> generated Rust bindings
  -> Rust target `deps`
  -> channel client/server code
  -> component capability route
```

Keep FIDL protocol calls at the component boundary. Inside one crate, prefer a
typed Rust function or trait. At a driver boundary, use the existing driver or
FIDL Rust library so handle rights, channel ownership, and asynchronous
dispatch are consistent with the framework.

### 10.6 Platform configuration and supported architectures

The SMOS verification product builds `arm64` and `riscv64`. Use target cfgs
for genuinely platform-specific code, and keep the common command path shared:

```rust
#[cfg(target_os = "fuchsia")]
fn system_value() -> &'static str {
    "from Zircon"
}

#[cfg(not(target_os = "fuchsia"))]
fn system_value() -> &'static str {
    "host fallback"
}
```

When the difference is architecture-specific, use `target_arch = "aarch64"` or
`target_arch = "riscv64"`. Do not silently retain an x86-only implementation in
an SMOS path whose supported targets are arm64 and riscv64. If an architecture
requires a different kernel syscall or device protocol, expose the same Rust
API and return the standard unsupported status where the platform cannot
provide the operation.

For code under `zircon/`, the repository's `SMOS_HYPER` constraint still
applies: new Zircon code must be guarded without changing the original
non-Hyper path. Rust code in user space does not need that kernel macro, but it
must still preserve the product's compact service boundary.

### 10.7 Packaging and product assembly

A compiled binary is not automatically available in the SMOS shell. It must
be connected to one of the product's delivery paths:

```text
rustc_binary
    |
    +--> bootfs_files_for_assembly -> bootfs file set -> dash lookup
    |
    `--> fuchsia_package -> package manifest/FAR -> component/package resolver
                                      |
                                      `--> component manager launch
```

For a dash command, add the binary to the command's bootfs group or package
target, then add that target to the relevant assembly bundle. For a component,
add its package and manifest to the product graph and ensure its required
capabilities are offered. Do not add a package only to a local test target and
assume it will appear in `smos.zbi`.

The final product path is:

```text
Rust source -> GN target -> ELF -> package/bootfs -> assembly manifest
    -> smos.zbi / BootFS -> userboot/component manager
    -> dash command or component process
```

### 10.8 Tests and incremental development loop

Use the narrowest target while editing, then validate the assembled image:

```sh
export SMOS_SDK_ROOT=/path/to/smos-sdk
make configure ARCH=arm64
ninja -C out/smos-boot-arm64 'userspace/sys/smos-bin:uname_bin'
ninja -C out/smos-boot-arm64 'userspace/sys/smos-bin:uname_bin_test'
make build ARCH=arm64
make verify ARCH=arm64
```

Use `gn desc` to inspect dependencies and outputs:

```sh
gn desc out/smos-boot-arm64 //userspace/sys/smos-bin:uname_bin deps
gn desc out/smos-boot-arm64 //userspace/sys/smos-bin:uname_bin outputs
ninja -C out/smos-boot-arm64 'userspace/sys/smos-bin:uname_bin' -v
```

When the source changes, Ninja should rebuild the affected Rust action and its
downstream package/image actions. When `BUILD.gn`, product assembly, board
configuration, or package manifests change, rerun `make configure ARCH=<arch>`
so GN regenerates the graph. Keep `out/smos-boot-arm64` and `out/smos-boot-riscv64`
separate; do not copy artifacts between architectures.

### 10.9 Integration checklist

Before considering a Rust feature integrated into SMOS, verify all of these
layers:

- crate root and module files are listed in `sources`;
- the correct `rustc_binary`, `rustc_library`, or `rustc_test` target is used;
- GN `deps` include every Rust library, FIDL binding, C ABI, and generated input;
- `//release/config/rust:bootfs` is applied where the binary is part of BootFS;
- FFI uses a documented `extern "C"`/`#[repr(C)]` boundary or an existing wrapper;
- component `.cml` manifests provide every runtime capability;
- the binary is connected to `bootfs_files_for_assembly` or `fuchsia_package`;
- the product assembly includes the bootfs/package target;
- unit tests pass for the narrow target;
- arm64 and riscv64 compile paths are checked when the code is shared;
- `make build ARCH=<arch>` and the appropriate QEMU verification are complete;
- `git diff --check` and the relevant documentation tests pass.

## 11. Overview

```text
Rust source
  |
  |  BUILD.gn: rustc_binary()
  v
GN template expansion
  |
  |  rustc_artifact + Rust toolchain + implicit fdio dependency
  v
rustc
  |-- parsing, borrow checking, monomorphization, code generation
  |-- emit .rmeta, .d, and an unstripped ELF
  `-- invoke LLD
        |
        |  target: aarch64-unknown-fuchsia
        |  --sysroot=gen/zircon/public/sysroot
        |  -ldylib=fdio
        v
dynamic ELF: uname
  |
  |  userboot / dynamic linker ld.so.1
  |  load Rust std, libfdio.so, and other shared libraries
  v
Rust runtime and std
  |\
  | `std::fs`/`std::io`/`std::process`
  |       |
  |       `--> fdio / zxio / FIDL / Zircon syscall
  |
  `-- this command explicitly calls zx_system_get_version_string
          |
          `--> Zircon VDSO (no FIDL service required)
```

Key point: Rust does not "compile C++ source files into a Rust crate". The Rust
crate first produces its own machine code, and the linker then connects C++
shared libraries at the ABI boundary. At runtime, the dynamic linker maps those
libraries into the same process address space.

## 12. From BUILD.gn to rustc

The entry point for the current command set is
[`userspace/sys/smos-bin/BUILD.gn`](../../userspace/sys/smos-bin/BUILD.gn):

```gn
rustc_binary("${command}_bin") {
  output_name = command
  edition = "2021"
  source_root = "src/${command}.rs"
  sources = [ "src/${command}.rs" ]
  configs += [ "//release/config/rust:bootfs" ]
  with_unit_tests = true
}
```

The processing order is:

1. `rustc_binary` (defined in `release/rust/rustc_binary.gni`) converts the binary
   target into a `rustc_artifact` target.
2. `source_root` is the crate root. Rust follows `mod` declarations from this
   file to discover sources; `sources` is used for GN's strict source manifest
   validation.
3. `edition`, `configs`, and the toolchain variant form the final `rustc` arguments.
4. Fuchsia executables automatically add
   `//userspace/lib/fdio/rust:fdio_for_rust_stdlib` because the Fuchsia Rust
   standard library has an implicit link attribute for `libfdio.so`.
5. `with_unit_tests = true` also creates a `<name>_test` target; it does not
   change the production binary's link path.

`fdio_for_rust_stdlib` is defined in
[`userspace/lib/fdio/rust/BUILD.gn`](../../userspace/lib/fdio/rust/BUILD.gn):

```gn
rustc_link_attribute("fdio_for_rust_stdlib") {
  lib_shared_target = "//sdk/lib/fdio"
}
```

This explains a common observation: even when `uname.rs` has no `use fdio`, the
final Rust executable still links `libfdio.so` because `std` needs fdio for file
descriptors, directories, processes, and standard input/output.

## 13. What Happens During the rustc Stage

The important parts of a Fuchsia arm64 compilation command look like this:

```text
rustc --crate-name uname src/uname.rs --crate-type bin
  --target aarch64-unknown-fuchsia --edition=2021
  --sysroot=.../prebuilt/third_party/rust/linux-x64
  -L gen/zircon/public/sysroot/lib
  -Clinker=.../clang/linux-x64/bin/lld
  -Clink-arg=--sysroot=gen/zircon/public/sysroot
  -ldylib=fdio
  -Clink-arg=-dynamic-linker=ld.so.1
  --emit=dep-info=uname.d,link,metadata=exe.unstripped/uname.rmeta
```

Purpose of each output:

| Output | Purpose |
| --- | --- |
| `uname.rmeta` | crate metadata used by dependencies and incremental compilation |
| `uname.d` | dependency file used by Ninja to detect source changes |
| `exe.unstripped/uname` | ELF containing debug information and a link map |
| `uname` | release ELF processed by `llvm-objcopy` |
| `uname.build-id.stamp` | build ID used for packaging, debug symbols, and distribution manifests |

The build configuration also enables `panic=abort`, ThinLTO, the Fuchsia API
level cfg, `-Dwarnings`, and target architecture features. GN configs provide
these parameters; do not duplicate them manually in source files.

## 14. How C++ Enters the Final ELF

### 14.1 C++ Target

`//sdk/lib/fdio:fdio` is a `zx_library` whose source list includes:

```text
sdk/lib/fdio/fdio.cc
sdk/lib/fdio/fdio_unistd.cc
sdk/lib/fdio/uname.cc
sdk/lib/fdio/zxio.cc
sdk/lib/fdio/namespace/*.cc
```

It also depends on FIDL C++ bindings, `zxio`, `fbl`, and Zircon user libraries.
Each `.cc` is compiled into an arm64 object by Clang, then LLD produces
`libfdio.so`. Rust does not need to know the C++ classes, templates, or FIDL
types; it only needs the exported C ABI symbols and the fdio ABI expected by
Rust std.

### 14.2 ABI Boundary

C++ functions can be called directly from Rust only when they satisfy the
following contract:

```cpp
extern "C" int example(int value);
```

The corresponding Rust declaration is:

```rust
unsafe extern "C" {
    fn example(value: i32) -> i32;
}
```

Preserve all of the following:

- The `extern "C"` calling convention must match.
- Integers, pointers, and structs must use `#[repr(C)]` and matching widths.
- Strings must explicitly specify NUL termination or `(ptr, len)` representation.
- Ownership, thread safety, error codes, and lifetimes must be defined on both sides.
- C++ exceptions must not cross the Rust ABI boundary.

Rust cannot safely pass C++ `std::string`, `std::vector`, or virtual objects as
ordinary Rust types. Production code should use a C ABI, FIDL bindings, or a
safe interface provided by an existing Rust crate.

## 15. Two Runtime Descent Paths

### 15.1 Rust Standard-Library Path: Rust -> fdio C++ -> zxio/FIDL/syscall

For example, `std::fs::File::open()` follows this path:

```text
Rust command
  -> Rust std::fs / std::sys::pal::fuchsia
  -> fdio Rust/stdlib ABI
  -> libfdio.so (C++)
  -> fdio namespace / zxio
  -> FIDL for a remote directory or a local vnode
  -> Zircon handles such as channel/socket/VMO
  -> Zircon syscall
  -> fshost, devfs, or another service
```

Standard input and output follow the same path. `println!` eventually writes to
an fd; fdio determines whether that fd represents a remote file, socket,
debuglog, PTY, or another object.

### 15.2 This Command's Version Path: Rust -> VDSO -> Zircon

The current `uname.rs` no longer calls libc `uname()`; it declares and calls:

```rust
unsafe extern "C" {
    fn zx_system_get_version_string() -> StringView;
}
```

The symbol is exported by the Zircon VDSO and returns a read-only
`(data, length)` string view:

```text
uname.rs
  -> zx_system_get_version_string
  -> Zircon VDSO entry
  -> kernel version string
```

This path does not connect to a FIDL service and therefore does not wait for
`fuchsia.device.NameProvider`. It is appropriate for read-only, non-blocking
VDSO interfaces provided directly by the kernel. A VDSO call is not an ordinary
shared-library call: userboot and the dynamic-loading flow establish the mapping
when the process starts, and the call normally lands directly in VDSO code in the
process address space.

## 16. Why libc `uname` Can Block

The current Fuchsia implementation in `sdk/lib/fdio/uname.cc` is approximately:

```text
uname(utsname*)
  -> get_client<fuchsia.device.NameProvider>()
  -> NameProvider.GetDeviceName()
  -> fill nodename
  -> sysname = "Fuchsia"
  -> release/version = ""
```

`get_client` and the synchronous FIDL call require an available `NameProvider`
service in the component namespace. If a shell command runs without that
capability or service instance, the call may wait indefinitely. Empty
`release/version` fields and waiting are separate issues: the former is an
implementation choice, while the latter is a service dependency or runtime
wiring problem.

Debug in this order:

1. Confirm that the process entered `main`; add debug output before and after the FIDL call.
2. Check whether the component `.cml` offers `fuchsia.device.NameProvider`.
3. Check whether `device-name-provider` is in the product's bootstrap/package graph.
4. Check that the service appears in the process `/svc` namespace and that the capability route is complete.
5. If the command only needs the kernel version, avoid `NameProvider` and use the VDSO version interface.

## 17. ELF Loading and Startup

Successful linking only proves that symbols and relocations can be produced. At
runtime the process still goes through:

```text
userboot
  -> read ELF program headers
  -> map the Rust executable
  -> load interpreter: ld.so.1
  -> dynamically load libfdio.so and dependencies
  -> resolve PLT/GOT and TLS
  -> establish fdio namespace, stdio, and startup handles
  -> jump to Rust runtime / main
```

After Rust `main` returns, the runtime performs cleanup and exits through the
Fuchsia process-exit path. A missing shared library usually appears as a loading
failure; a missing service with valid symbols usually appears as an error or
wait at the first call.

## 18. How a Command Enters the Image

After compilation and linking, the command still passes through GN package and
assembly:

```text
uname_bin
  -> uname_pkg
  -> on_demand package
  -> shell_commands: { package = "uname", components = [ "uname" ] }
  -> assembly manifest / package set
  -> bootfs or package resolver
  -> dash starts uname by command name
```

The `bootfs` target places the command in the bootfs file set, while the
`fuchsia_package` target creates a resolvable package. They serve different
purposes: bootfs is directly available during early startup, while packages
provide runtime content through package organization and component manifests.

## 19. Locating Path Failures

### Build Time

```sh
gn desc out/smos-boot-arm64 //userspace/sys/smos-bin:uname_bin deps
ninja -C out/smos-boot-arm64 'userspace/sys/smos-bin:uname_bin' -v
readelf -Ws out/smos-boot-arm64/uname | rg 'fdio|zx_system_get_version_string'
readelf -d out/smos-boot-arm64/uname
```

Check the following:

- whether the `uname` target was generated;
- whether rustc uses `aarch64-unknown-fuchsia`;
- whether `libfdio.so` is linked;
- whether `zx_system_get_version_string` remains a resolvable symbol;
- whether the ELF interpreter is `ld.so.1`.

### Runtime

```sh
tools/smos-boot/run-qemu.sh arm64
```

In the shell, run:

```sh
uname
uname -r
uname -a
```

If `uname` blocks while the Rust version-interface command prints nothing, first
use minimal debug output to distinguish the stages:

```text
main entered
before version call
after version call
before stdout write
after stdout write
```

If no line appears after `before version call`, the block is in the service or
low-level call. If the complete output appears but the shell does not return,
inspect stdout fdio, process exit, and the dash wait path.

## 20. Complete Code-Level Flow Diagrams

The diagrams below expand "which file calls which file" down to the function
level. Solid lines represent calls or links within one process; dashed lines
represent build dependencies or runtime service boundaries.

### 20.1 GN Build Dependency Graph

```text
userspace/sys/smos-bin/BUILD.gn
        |
        | foreach(command = "uname")
        v
rustc_binary("uname_bin")
        |
        | template expansion
        v
release/rust/rustc_binary.gni::rustc_binary
        |
        +--> release/rust/rustc_artifact.gni::rustc_artifact
        |       |
        |       +--> source_root = src/uname.rs
        |       +--> edition = 2021
        |       +--> target = aarch64-unknown-fuchsia
        |       +--> configs = rust:bootfs + edition_2021
        |       `--> emits rustc Ninja action
        |
        `--> implicit executable dependency
                |
                v
userspace/lib/fdio/rust:fdio_for_rust_stdlib
                |
                | rustc_link_attribute
                v
sdk/lib/fdio:fdio (zx_library)
                |
                +--> Clang: fdio.cc, fdio_unistd.cc, uname.cc, zxio.cc
                +--> FIDL C++ bindings
                +--> Zircon zx/fbl/zxio libraries
                `--> LLD: libfdio.so
```

### 20.2 Rust Source Control Flow

The corresponding file is
[`userspace/sys/smos-bin/src/uname.rs`](../../userspace/sys/smos-bin/src/uname.rs):

```text
process start
    |
    v
main()
    |
    +--> std::env::args()
    |       |
    |       +--> "-a" -> m,n,r,s,v = true
    |       +--> "-m" -> machine only
    |       `--> invalid option -> usage() -> exit(1)
    |
    +--> if no selector: s = true
    |
    +--> nodename
    |       |
    |       +--> getenv("zircon.nodename")
    |       +--> fallback getenv("HOSTNAME")
    |       `--> missing -> ""
    |
    +--> system_version()
    |       |
    |       +--> target_os = fuchsia
    |       |       |
    |       |       +--> zx_system_get_version_string()
    |       |       +--> StringView { data, length }
    |       |       `--> from_raw_parts(data, length) -> &str
    |       |
    |       `--> host build -> "unknown"
    |
    +--> machine()
    |       `--> target_arch cfg -> x86_64/aarch64/riscv64
    |
    +--> values = [sysname, nodename, release, version, machine]
    |
    +--> selected values
    |       `--> print!("{value}") + stdout newline
    |
    `--> return from main -> process exit
```

### 20.3 Code Path for `zx_system_get_version_string`

This is the intentionally non-blocking path selected by the command:

```text
src/uname.rs::system_version()
    |
    | unsafe extern "C"
    v
zx_system_get_version_string()
    |
    | symbol supplied by Zircon VDSO
    v
zircon/kernel/lib/userabi/vdso/zx_system_get_version_string.cc
    |
    +--> _zx_system_get_version_string()
    +--> read kernel version::VersionString()
    `--> VDSO_INTERFACE_FUNCTION(zx_system_get_version_string)
            |
            v
userboot-generated VDSO symbol table
            |
            v
running process address space
            |
            `--> { pointer, length } -> Rust &str
```

There is no `fdio`, `/svc`, or FIDL request here. The `StringView` layout must
exactly match `zx_string_view_t`; Rust only reads the read-only bytes returned by
the kernel and never frees or writes them.

### 20.4 Rust Standard-Output Code Path

`print!` does not call C++ directly, but it eventually uses Fuchsia std's fd
implementation:

```text
print!("{value}")
    |
    v
std::io::_print / stdout handle
    |
    v
std::io::Write::write_fmt
    |
    v
Fuchsia std fd implementation
    |
    | implicit #[link] to fdio_for_rust_stdlib
    v
libfdio.so: fdio_fd_write / zxio write path
    |
    +--> local fdio object
    |       `--> zxio / channel / socket write
    |
    `--> remote fdio object
            `--> FIDL I/O request through a Zircon channel
                    |
                    v
              console / PTY / dash launcher
```

The exact std internal function names may change with the Rust toolchain
version. During debugging, use the final `rustc -v` command and `libfdio.so`
symbols as the source of truth. The stable boundaries are fds, handles,
channels, and FIDL protocols, not private std module names.

### 20.5 Complete Path When Calling libc `uname()`

This diagram explains why the old implementation could wait for a service:

```text
Rust/C/C++ caller
    |
    v
libc uname(utsname*)
    |
    v
sdk/lib/fdio/uname.cc::uname()
    |
    +--> get_client<fuchsia_device::NameProvider>()
    |       |
    |       `--> connect to /svc/fuchsia.device.NameProvider
    |
    +--> NameProvider.GetDeviceName()
    |       |
    |       +--> Zircon channel call
    |       +--> component_manager routes capability
    |       `--> device-name-provider replies with nodename
    |
    +--> copy nodename into utsname
    +--> sysname = "Fuchsia"
    +--> release/version = ""
    `--> return 0

Missing `/svc` route or `device-name-provider`:

get_client / channel call
    `--> no reply or unavailable service -> caller appears blocked
```

### 20.6 ELF Startup and the First Rust Instruction

```text
dash resolves command "uname"
    |
    v
package resolver / bootfs lookup
    |
    v
userboot::LoadElf(uname)
    |
    +--> map PT_LOAD segments (text/data/rodata)
    +--> read PT_INTERP = "ld.so.1"
    `--> create process startup handles and namespace
            |
            v
        ld.so.1
            |
            +--> load Rust dynamic std dependencies
            +--> load libfdio.so
            +--> resolve zx_system_get_version_string via VDSO
            +--> apply RELA / PLT / GOT relocations
            `--> call ELF entry / Rust runtime
                    |
                    +--> initialize argc/argv/env/stdin/stdout/stderr
                    +--> invoke main()
                    `--> exit(status)
```

## 21. Maintenance Rules

- Prefer the standard library for new Rust commands; check for an existing Rust
  wrapper before adding C/C++ dependencies.
- When adding a C ABI, submit the C/C++ declaration, the Rust `extern "C"`
  declaration, and layout tests together.
- When calling VDSO directly, verify that the symbol comes from `zircon/vdso`
  and do not treat VDSO as an ordinary FIDL service.
- After changing `BUILD.gn`, validate the binary, package, bootfs, and assembly
  targets.
- Treat the actual Ninja `-v` rustc command as authoritative; do not infer
  Fuchsia linking behavior from a host Linux link command.
