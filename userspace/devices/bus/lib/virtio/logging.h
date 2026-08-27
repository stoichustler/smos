// Copyright 2024 The Fuchsia Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef SRC_DEVICES_BUS_LIB_VIRTIO_LOGGING_H_
#define SRC_DEVICES_BUS_LIB_VIRTIO_LOGGING_H_

#include <zircon/compiler.h>

#include <cstdarg>
#include <cstdint>

namespace virtio::internal {

enum class DriverLogSeverity : uint8_t {
  kTRACE = 0x10,
  kDEBUG = 0x20,
  kINFO = 0x30,
  kWARNING = 0x40,
  kERROR = 0x50,
  kFATAL = 0x60,
};

bool IsLogSeverityEnabled(DriverLogSeverity severity);
void LogVariadicArgs(DriverLogSeverity severity, const char* file, int line, const char* format,
                     va_list args);

inline void __PRINTFLIKE(4, 5)
    Log(DriverLogSeverity severity, const char* file, int line, const char* format, ...) {
  va_list args;
  va_start(args, format);
  LogVariadicArgs(severity, file, line, format, args);
  va_end(args);
}

}  // namespace virtio::internal

#endif  // SRC_DEVICES_BUS_LIB_VIRTIO_LOGGING_H_
