// Copyright 2024 The Fuchsia Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include <lib/driver/logging/cpp/logger.h>
#include <zircon/assert.h>

#include "userspace/devices/bus/lib/virtio/logging.h"

namespace virtio::internal {
namespace {

FuchsiaLogSeverity ToFuchsiaLogSeverity(DriverLogSeverity severity) {
  switch (severity) {
    case DriverLogSeverity::kTRACE:
      return FUCHSIA_LOG_TRACE;
    case DriverLogSeverity::kDEBUG:
      return FUCHSIA_LOG_DEBUG;
    case DriverLogSeverity::kINFO:
      return FUCHSIA_LOG_INFO;
    case DriverLogSeverity::kWARNING:
      return FUCHSIA_LOG_WARNING;
    case DriverLogSeverity::kERROR:
      return FUCHSIA_LOG_ERROR;
    case DriverLogSeverity::kFATAL:
      return FUCHSIA_LOG_FATAL;
  }
  ZX_DEBUG_ASSERT_MSG(false, "Invalid driver log severity: %d", static_cast<int>(severity));
}

}  // namespace

bool IsLogSeverityEnabled(DriverLogSeverity severity) {
  return fdf::Logger::GlobalInstance()->GetSeverity() <= ToFuchsiaLogSeverity(severity);
}

void LogVariadicArgs(DriverLogSeverity severity, const char* file, int line, const char* format,
                     va_list args) {
  fdf::Logger::GlobalInstance()->logvf(ToFuchsiaLogSeverity(severity), nullptr, file, line, format,
                                       args);
}

}  // namespace virtio::internal
