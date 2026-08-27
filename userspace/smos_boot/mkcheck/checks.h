// Copyright 2026 The Fuchsia Authors.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef SRC_VERIFY_MICROKERNEL_MKCHECK_CHECKS_H_
#define SRC_VERIFY_MICROKERNEL_MKCHECK_CHECKS_H_

#include <zircon/types.h>

namespace mkcheck {

zx_status_t CheckThread();
zx_status_t CheckVmo();
zx_status_t CheckChannel();
zx_status_t CheckEvent();
zx_status_t CheckTimer();

}  // namespace mkcheck

#endif  // SRC_VERIFY_MICROKERNEL_MKCHECK_CHECKS_H_
