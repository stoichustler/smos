// Copyright 2026 The Fuchsia Authors.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

//! Static metric identifiers retained by the compact power-manager build.

pub mod power_manager_metrics {
    pub const PROJECT_ID: u32 = 3;
    pub const RAW_TEMPERATURE_MIGRATED_INT_BUCKETS_FLOOR: i64 = 20;
    pub const RAW_TEMPERATURE_MIGRATED_INT_BUCKETS_NUM_BUCKETS: u32 = 80;
    pub const RAW_TEMPERATURE_MIGRATED_INT_BUCKETS_STEP_SIZE: u32 = 1;
    pub const THERMAL_LIMIT_RESULT_MIGRATED_METRIC_ID: u32 = 105;
    pub const RAW_TEMPERATURE_MIGRATED_METRIC_ID: u32 = 106;

    #[repr(u32)]
    #[derive(Clone, Copy, PartialEq, PartialOrd, Eq, Ord, Debug, Hash)]
    pub enum ThermalLimitResultMigratedMetricDimensionResult {
        Mitigated = 0,
        Shutdown = 1,
    }
}
