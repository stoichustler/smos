# SMOS (Zircon Microkernel)

SMOS is a compact, console-only Fuchsia/Zircon server profile for `arm64`
and `riscv64`. It keeps the Zircon dash shell, core process and storage
primitives, component and driver frameworks, QEMU console/block/RTC/random
devices, virtio socket, and the arm64 virtualization host stack.

```text

 .d888b,  88bd8b,d88b  d8888b  .d888b,
 ?8b,     88P'`?8P'?8bd8P' ?88 ?8b,
   `?8b  d88  d88  88P88b  d88   `?8b
`?888P' d88' d88'  88b`?8888P'`?888P'

```

## Quick Start

The build uses a standalone SDK. Set `SMOS_SDK_ROOT` to a validated SDK before
configuring or building:

```sh
export SMOS_SDK_ROOT=[PATH]/smos-sdk
make build
make verify
```

[`smos-sdk` BaiduNetDisk Link](https://pan.baidu.com/s/1pp3QYEmQ4r7NMsNDXF8gIQ?pwd=wukm)

This builds and automatically boot-tests the default `arm64` image. Start an
interactive QEMU console with `make run`; additional QEMU options can be passed
with `make run QEMU_ARGS='-d guest_errors'`.

## Common Commands

```sh
make help                       # list available targets
make build ARCH=riscv64         # build the RISC-V console image
make run ARCH=riscv64           # start the RISC-V QEMU console
make build-all                  # build arm64 and riscv64
make verify-all                 # automated arm64 verification
make clean                      # remove generated output
```

Build artifacts are written under `out/smos-boot-<arch>/`, including
`smos.zbi`, build logs, and `artifacts.env` for QEMU launching.
`riscv64` remains a build target; its QEMU validation is interactive rather
than automated.

See [SMOS.md](sdk/smos/SMOS.md) for SDK creation and validation, direct-script
workflows, retained-component inventory, source-size requirements, and
virtualization scope.
