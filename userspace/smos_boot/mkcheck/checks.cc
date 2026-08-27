// Copyright 2026 The Fuchsia Authors.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "userspace/smos_boot/mkcheck/checks.h"

#include <lib/zx/channel.h>
#include <lib/zx/event.h>
#include <lib/zx/time.h>
#include <lib/zx/timer.h>
#include <lib/zx/vmo.h>
#include <threads.h>
#include <zircon/status.h>
#include <zircon/syscalls.h>

#include <array>
#include <atomic>
#include <cstring>

namespace mkcheck {
namespace {

constexpr zx::duration kWaitTimeout = zx::sec(1);

int ThreadEntry(void* context) {
  static_cast<std::atomic_bool*>(context)->store(true);
  return 7;
}

}  // namespace

zx_status_t CheckThread() {
  std::atomic_bool ran = false;
  thrd_t thread;
  if (thrd_create(&thread, ThreadEntry, &ran) != thrd_success) {
    return ZX_ERR_NO_RESOURCES;
  }

  int result = 0;
  if (thrd_join(thread, &result) != thrd_success) {
    return ZX_ERR_INTERNAL;
  }
  return ran.load() && result == 7 ? ZX_OK : ZX_ERR_IO_DATA_INTEGRITY;
}

zx_status_t CheckVmo() {
  zx::vmo vmo;
  zx_status_t status = zx::vmo::create(zx_system_get_page_size(), 0, &vmo);
  if (status != ZX_OK) {
    return status;
  }

  constexpr std::array<uint8_t, 8> kWritten = {0x5a, 0x69, 0x72, 0x63,
                                                0x6f, 0x6e, 0x21, 0x00};
  std::array<uint8_t, kWritten.size()> read = {};
  status = vmo.write(kWritten.data(), 0, kWritten.size());
  if (status != ZX_OK) {
    return status;
  }
  status = vmo.read(read.data(), 0, read.size());
  if (status != ZX_OK) {
    return status;
  }
  return read == kWritten ? ZX_OK : ZX_ERR_IO_DATA_INTEGRITY;
}

zx_status_t CheckChannel() {
  zx::channel sender;
  zx::channel receiver;
  zx_status_t status = zx::channel::create(0, &sender, &receiver);
  if (status != ZX_OK) {
    return status;
  }

  constexpr char kMessage[] = "channel-ok";
  status = sender.write(0, kMessage, sizeof(kMessage), nullptr, 0);
  if (status != ZX_OK) {
    return status;
  }

  zx_signals_t observed = 0;
  status = receiver.wait_one(ZX_CHANNEL_READABLE, zx::deadline_after(kWaitTimeout), &observed);
  if (status != ZX_OK) {
    return status;
  }

  std::array<char, sizeof(kMessage)> read = {};
  uint32_t actual_bytes = 0;
  uint32_t actual_handles = 0;
  status = receiver.read(0, read.data(), nullptr, read.size(), 0, &actual_bytes, &actual_handles);
  if (status != ZX_OK) {
    return status;
  }
  if (actual_bytes != sizeof(kMessage) || actual_handles != 0 ||
      std::memcmp(read.data(), kMessage, sizeof(kMessage)) != 0) {
    return ZX_ERR_IO_DATA_INTEGRITY;
  }
  return ZX_OK;
}

zx_status_t CheckEvent() {
  zx::event event;
  zx_status_t status = zx::event::create(0, &event);
  if (status != ZX_OK) {
    return status;
  }
  status = event.signal(0, ZX_USER_SIGNAL_0);
  if (status != ZX_OK) {
    return status;
  }

  zx_signals_t observed = 0;
  return event.wait_one(ZX_USER_SIGNAL_0, zx::deadline_after(kWaitTimeout), &observed);
}

zx_status_t CheckTimer() {
  zx::timer timer;
  zx_status_t status = zx::timer::create(0, ZX_CLOCK_MONOTONIC, &timer);
  if (status != ZX_OK) {
    return status;
  }
  status = timer.set(zx::deadline_after(zx::msec(1)), zx::duration(0));
  if (status != ZX_OK) {
    return status;
  }

  zx_signals_t observed = 0;
  return timer.wait_one(ZX_TIMER_SIGNALED, zx::deadline_after(kWaitTimeout), &observed);
}

}  // namespace mkcheck
