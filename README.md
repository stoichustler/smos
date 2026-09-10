# SMOS (Zircon Microkernel)

SMOS is a compact, console-only Fuchsia/Zircon server profile for `arm64`
and `riscv64`. It keeps the Zircon dash shell, core process and storage
primitives, component and driver frameworks, QEMU console/block/RTC/random
devices, virtio socket, and the arm64 virtualization host stack.

```text
       )
 (    (     (  (
 )\   )\  ' )\ )\
((_)_((_)) ((_|(_)
(_-< '  \() _ (_-<
/__/_|_|_|\___/__/

```

## Quick Start

The build uses a standalone SDK. Set `SMOS_SDK_ROOT` to a validated SDK before
configuring or building:

```sh
export SMOS_SDK_ROOT=[PATH]/smos-sdk
make build
make verify
```

[`smos-sdk` baidu net-disk link](https://pan.baidu.com/s/1pp3QYEmQ4r7NMsNDXF8gIQ?pwd=wukm)

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
