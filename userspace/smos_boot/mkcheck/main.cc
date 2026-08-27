// Copyright 2026 The Fuchsia Authors.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "userspace/smos_boot/mkcheck/checks.h"

#include <cstdio>

int main() {
  struct Check {
    const char* name;
    zx_status_t (*run)();
  };
  constexpr Check kChecks[] = {
      {"THREAD", mkcheck::CheckThread},
      {"VMO", mkcheck::CheckVmo},
      {"CHANNEL", mkcheck::CheckChannel},
      {"EVENT", mkcheck::CheckEvent},
      {"TIMER", mkcheck::CheckTimer},
  };

  bool all_passed = true;
  for (const auto& check : kChecks) {
    const zx_status_t status = check.run();
    if (status == ZX_OK) {
      std::printf("MKCHECK:%s:PASS\n", check.name);
    } else {
      std::printf("MKCHECK:%s:FAIL:%d\n", check.name, status);
      all_passed = false;
    }
  }

  if (all_passed) {
    std::printf("MKCHECK:ALL:PASS\n");
    return 0;
  }
  return 1;
}
