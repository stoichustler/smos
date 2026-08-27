# Copyright 2026 Hustler Lo. All rights reserved.

ARCH ?= arm64
MILESTONE_SDK ?= 27
TOOLCHAIN_PATH ?= tools/smos-boot
CTAGS ?= ctags

ifeq ($(V),1)
Q :=
else
Q := @
endif

.DEFAULT_GOAL := help

.PHONY: help configure build verify run all configure-all build-all verify-all \\
	clean tags

help: ## Show available build and verification targets.
	$(Q)awk 'BEGIN { FS = ":.*##" } /^[a-zA-Z][a-zA-Z0-9_-]*:.*##/ { printf "  %-16s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

configure: ## Generate the GN build directory for ARCH (default: arm64).
	$(Q)$(TOOLCHAIN_PATH)/configure.sh $(ARCH)

build: configure ## Build the console image for ARCH.
	$(Q)$(TOOLCHAIN_PATH)/build.sh $(ARCH)

verify: build ## Boot-test ARCH in QEMU (arm64 is automated).
	$(Q)$(TOOLCHAIN_PATH)/verify.sh $(ARCH)

run: build ## Build and start an interactive QEMU console; set QEMU_ARGS as needed.
	$(Q)$(TOOLCHAIN_PATH)/run-qemu.sh $(ARCH) -- $(QEMU_ARGS)

configure-all: ## Generate GN build directories for arm64 and riscv64.
	$(Q)$(TOOLCHAIN_PATH)/configure.sh arm64
	$(Q)$(TOOLCHAIN_PATH)/configure.sh riscv64

build-all: configure-all ## Build console images for arm64 and riscv64.
	$(Q)$(TOOLCHAIN_PATH)/build.sh arm64
	$(Q)$(TOOLCHAIN_PATH)/build.sh riscv64

verify-all: build-all ## Run automated verification for the supported targets.
	$(Q)$(TOOLCHAIN_PATH)/verify.sh all

all: verify-all ## Configure, build, and verify both supported architectures.

clean: ## Remove generated build output.
	$(Q)rm -rf out

tags: ## Generate C/C++/assembly tags for the retained source tree.
	$(Q)$(CTAGS) --languages=Asm,C,C++ -R zircon userspace sdk third_party

# End of Makefile
