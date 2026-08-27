// Copyright 2026 The Fuchsia Authors.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include <fidl/fuchsia.kernel/cpp/wire.h>
#include <lib/component/incoming/cpp/protocol.h>
#include <lib/zx/guest.h>
#include <lib/zx/resource.h>
#include <lib/zx/result.h>
#include <lib/zx/vmar.h>
#include <zircon/status.h>

#include <cstdio>

namespace virtcheck {

const char* MarkerForGuestStatus(zx_status_t status) {
#if defined(__riscv)
  return "VIRTUALIZATION:RISCV64:UNSUPPORTED";
#else
  if (status == ZX_OK) {
    return "VIRTUALIZATION:ARM64:PASS";
  }
  if (status == ZX_ERR_NOT_SUPPORTED || status == ZX_ERR_PEER_CLOSED) {
    return "VIRTUALIZATION:ARM64:NO_NESTED_EL2";
  }
  return "VIRTUALIZATION:ARM64:FAIL";
#endif
}

bool IsExpectedGuestStatus(zx_status_t status) {
#if defined(__riscv)
  return true;
#else
  return status == ZX_OK || status == ZX_ERR_NOT_SUPPORTED || status == ZX_ERR_PEER_CLOSED;
#endif
}

}  // namespace virtcheck

#if !defined(VIRTCHECK_NO_MAIN)
int main() {
#if defined(__riscv)
  std::puts(virtcheck::MarkerForGuestStatus(ZX_ERR_NOT_SUPPORTED));
  return 0;
#else
  auto client = component::Connect<fuchsia_kernel::HypervisorResource>();
  if (client.is_error()) {
    std::printf("VIRTUALIZATION:ARM64:RESOURCE_UNAVAILABLE:%s\n",
                zx_status_get_string(client.error_value()));
    return 1;
  }

  auto resource_result = fidl::WireCall(*client)->Get();
  if (!resource_result.ok()) {
    const zx_status_t status = resource_result.status();
    std::puts(virtcheck::MarkerForGuestStatus(status));
    return virtcheck::IsExpectedGuestStatus(status) ? 0 : 1;
  }

  zx::guest guest;
  zx::vmar vmar;
  const zx_status_t status = zx::guest::create(resource_result.value().resource, 0, &guest, &vmar);
  std::puts(virtcheck::MarkerForGuestStatus(status));
  return virtcheck::IsExpectedGuestStatus(status) ? 0 : 1;
#endif
}
#endif
