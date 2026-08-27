// Copyright 2024 The Fuchsia Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef SRC_DEVICES_BUS_LIB_VIRTIO_ZXLOGF_H_
#define SRC_DEVICES_BUS_LIB_VIRTIO_ZXLOGF_H_

#include "userspace/devices/bus/lib/virtio/logging.h"

#ifdef zxlogf
#error "zxlogf() already defined"
#endif

#ifdef zxlog_level_enabled
#error "zxlog_level_enabled() already defined"
#endif

#define zxlog_level_enabled(severity) \
  ::virtio::internal::IsLogSeverityEnabled(::virtio::internal::DriverLogSeverity::k##severity)

#define zxlogf(severity, format...)                                                     \
  ::virtio::internal::Log(::virtio::internal::DriverLogSeverity::k##severity, __FILE__, \
                          __LINE__, format)

#endif  // SRC_DEVICES_BUS_LIB_VIRTIO_ZXLOGF_H_
