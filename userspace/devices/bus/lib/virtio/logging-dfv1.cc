// Copyright 2024 The Fuchsia Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include <lib/ddk/debug.h>
#include <lib/ddk/driver.h>
#include <zircon/assert.h>

#include "userspace/devices/bus/lib/virtio/logging.h"

namespace virtio::internal {
namespace {

fx_log_severity_t ToFxLogSeverity(DriverLogSeverity severity) {
  switch (severity) {
    case DriverLogSeverity::kTRACE:
      return FX_LOG_TRACE;
    case DriverLogSeverity::kDEBUG:
      return FX_LOG_DEBUG;
    case DriverLogSeverity::kINFO:
      return FX_LOG_INFO;
    case DriverLogSeverity::kWARNING:
      return FX_LOG_WARNING;
    case DriverLogSeverity::kERROR:
      return FX_LOG_ERROR;
    case DriverLogSeverity::kFATAL:
      return FX_LOG_FATAL;
  }
  ZX_DEBUG_ASSERT_MSG(false, "Invalid driver log severity: %d", static_cast<int>(severity));
}

}  // namespace

bool IsLogSeverityEnabled(DriverLogSeverity severity) {
  const zx_driver_t* driver = __zircon_driver_rec__.driver;
  return driver_log_severity_enabled_internal(driver, ToFxLogSeverity(severity));
}

void LogVariadicArgs(DriverLogSeverity severity, const char* file, int line, const char* format,
                     va_list args) {
  const zx_driver_t* driver = __zircon_driver_rec__.driver;
  const fx_log_severity_t log_severity = ToFxLogSeverity(severity);
  if (driver_log_severity_enabled_internal(driver, log_severity)) {
    driver_logvf_internal(driver, log_severity, nullptr, file, line, format, args);
  }
}

}  // namespace virtio::internal
