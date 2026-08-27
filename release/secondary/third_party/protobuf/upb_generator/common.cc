// Copyright 2025 The Fuchsia Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
#include <string>

namespace upb {
namespace generator {

// This function is called by src/google/protobuf/compiler/rust/message.cc
// even though the protoc library does not use upb_generator. Trying to depend
// or compiler //third_party/protobuf/upb_generator fails due to the lack of
// auto-generated headers and pulls in abseil-cpp link-time dependencies.
//
// It is just simpler to make an empty version here to get the protoc compiler
// compiled properly in GN.
void MessageInit(std::string_view) {}

}  // namespace generator
}  // namespace upb
