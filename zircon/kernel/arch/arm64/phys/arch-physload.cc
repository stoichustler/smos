// Copyright 2025 The Fuchsia Authors
//
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file or at
// https://opensource.org/licenses/MIT

#include <lib/arch/arm64/system.h>
#include <phys/stdio.h>

#include "physload.h"

void ArchPhysloadBeforeInitMemory() {
  // Ensure we drop to EL1 first so that we set up our address space there so
  // we can hand that off to the kernel proper without reconstruction.
  const unsigned prev_el = static_cast<unsigned>(arch::ArmCurrentEl::Read().el());
  arch::ArmDropToEl1WithoutEl2Monitor();
  const unsigned post_el = static_cast<unsigned>(arch::ArmCurrentEl::Read().el());
  printf("physload: Running SMOS [ARM64] El%u -> El%u\n", prev_el, post_el);
}
