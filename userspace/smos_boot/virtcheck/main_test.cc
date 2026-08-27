// Copyright 2026 The Fuchsia Authors.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include <zircon/errors.h>

#include <string_view>

#include <zxtest/zxtest.h>

namespace virtcheck {
const char* MarkerForGuestStatus(zx_status_t status);
bool IsExpectedGuestStatus(zx_status_t status);
}  // namespace virtcheck

TEST(Virtcheck, ArchitectureStatusMarkers) {
#if defined(__riscv)
  EXPECT_EQ(std::string_view("VIRTUALIZATION:RISCV64:UNSUPPORTED"),
            virtcheck::MarkerForGuestStatus(ZX_ERR_NOT_SUPPORTED));
  EXPECT_TRUE(virtcheck::IsExpectedGuestStatus(ZX_ERR_INTERNAL));
#else
  EXPECT_EQ(std::string_view("VIRTUALIZATION:ARM64:PASS"), virtcheck::MarkerForGuestStatus(ZX_OK));
  EXPECT_EQ(std::string_view("VIRTUALIZATION:ARM64:NO_NESTED_EL2"),
            virtcheck::MarkerForGuestStatus(ZX_ERR_NOT_SUPPORTED));
  EXPECT_EQ(std::string_view("VIRTUALIZATION:ARM64:NO_NESTED_EL2"),
            virtcheck::MarkerForGuestStatus(ZX_ERR_PEER_CLOSED));
  EXPECT_TRUE(virtcheck::IsExpectedGuestStatus(ZX_OK));
  EXPECT_TRUE(virtcheck::IsExpectedGuestStatus(ZX_ERR_NOT_SUPPORTED));
  EXPECT_TRUE(virtcheck::IsExpectedGuestStatus(ZX_ERR_PEER_CLOSED));
  EXPECT_FALSE(virtcheck::IsExpectedGuestStatus(ZX_ERR_INTERNAL));
#endif
}
