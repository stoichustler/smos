// Copyright 2026 The Fuchsia Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef ZIRCON_KERNEL_LIB_ARCH_INCLUDE_LIB_ARCH_INTRIN_H_
#define ZIRCON_KERNEL_LIB_ARCH_INCLUDE_LIB_ARCH_INTRIN_H_

// [smos] (20260822) Host intrinsic placeholder
// Host-side header generators only parse architecture register declarations;
// target toolchains resolve this include to their arm64 or riscv64 header.

#ifndef __ASSEMBLER__
#include <stdint.h>

#ifdef __cplusplus
namespace arch {

inline void Yield() {}
inline void DeviceMemoryBarrier() {}
inline void ThreadMemoryBarrier() {}
inline void SerializeInstructions() {}
inline uint64_t Cycles() { return 0; }

}  // namespace arch
#endif  // __cplusplus
#endif  // !__ASSEMBLER__

#endif  // ZIRCON_KERNEL_LIB_ARCH_INCLUDE_LIB_ARCH_INTRIN_H_
