#!/usr/bin/env python3

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]

ACTIVE_GN_FILES = (
    ROOT / "release/sdk/BUILD.gn",
    ROOT / "sdk/BUILD.gn",
    ROOT / "userspace/BUILD.gn",
    ROOT / "release/BUILD.gn",
)
COMPACT_VMM_BUILD_FILES = (
    ROOT / "userspace/virtualization/bin/vmm/BUILD.gn",
    ROOT / "userspace/virtualization/bin/vmm/device/BUILD.gn",
)
DEVICE_BUILD = ROOT / "userspace/virtualization/bin/vmm/device/BUILD.gn"
HARDWARE_FIDL_FILES = (
    ROOT / "sdk/fidl/fuchsia.virtualization.hardware/BUILD.gn",
    ROOT / "sdk/fidl/fuchsia.virtualization.hardware/device.fidl",
)
CTF_GENERATOR = ROOT / "sdk/ctf/build/generate_ctf_tests.gni"
CTF_TESTS = ROOT / "sdk/ctf/tests/BUILD.gn"
BUNDLES_TOOLS = ROOT / "release/platform/bundles/tools/BUILD.gn"
AIB_TEMPLATE = ROOT / "release/assembly/assembly_input_bundle.gni"
CRITICAL_SERVICES_BUILD = ROOT / "userspace/bringup/bin/critical-services/BUILD.gn"
CONFIG_SCHEMA_BUILD = ROOT / "userspace/lib/assembly/config_schema/BUILD.gn"
FFX_TOOLS_BUILD = ROOT / "userspace/developer/ffx/tools/BUILD.gn"
ASSEMBLY_BUNDLES = ROOT / "release/platform/bundles/assembly/BUILD.gn"
PLATFORM_AIBS = ROOT / "release/platform/bundles/assembly/platform_aibs.gni"
QEMU_ARM64_MANIFEST = (
    ROOT / "userspace/devices/board/drivers/qemu-arm64/meta/qemu-arm64.cml"
)
DRIVER_INDEX_MAIN = ROOT / "userspace/devices/bin/driver-index/src/main.rs"
DRIVER_COMPONENT_SHARD = ROOT / "sdk/lib/driver_component/driver.shard.cml"
COMPAT_DRIVER = ROOT / "userspace/devices/misc/drivers/compat/driver.cc"
COMPONENT_MANAGER_MAIN = ROOT / "userspace/sys/component_manager/src/main.rs"
KEEP_MANIFEST = ROOT / "out/smos-keep.json"
BUILDCONFIG = ROOT / "release/config/BUILDCONFIG.gn"
SMOS_SDK_CONFIG = ROOT / "release/config/smos_sdk.gni"
SDK_CONFIG = ROOT / "sdk/config.gni"
FFX_SDK_BUILD = ROOT / "userspace/developer/ffx/lib/sdk/BUILD.gn"
FFX_SDK_SOURCE = ROOT / "userspace/developer/ffx/lib/sdk/src/lib.rs"
PYTHON_INTERPRETER = ROOT / "release/config/python_interpreter.gni"
CORE_TOOLCHAIN_CONFIGS = (
    ROOT / "release/config/clang/clang_prefix.gni",
    ROOT / "release/config/BUILD.gn",
    ROOT / "release/toolchain/zircon/clang.gni",
    ROOT / "release/toolchain/zircon/gcc.gni",
    ROOT / "release/rust/config.gni",
    ROOT / "release/config/sysroot.gni",
    ROOT / "release/toolchain/buildidtool.gni",
    ROOT / "release/go/go_build.gni",
    ROOT / "userspace/lib/llvm/BUILD.gn",
)
FUCHSIA_CONFIG = ROOT / "release/config/fuchsia/BUILD.gn"
ICU_BUILD_CONFIG = ROOT / "release/icu/build_config.gni"
ICU_CONFIG = ROOT / "release/icu/config.gni"
VERIFY_PRODUCT = ROOT / "release/platform/products/smos_boot.gni"
FIDL_GO_BUILD = ROOT / "third_party/golibs/BUILD.gn"
MYPY_ROOT = ROOT / "third_party/pylibs"
DART_PACKAGES = ROOT / "third_party/dart-pkg"
SDK_BUILD = ROOT / "sdk/BUILD.gn"
MYPY_CHECKER = ROOT / "release/python/mypy_checker.py"
HONEYDEW_BUILD = ROOT / "userspace/testing/end_to_end/honeydew/BUILD.gn"
PROTOBUF_BUILD = ROOT / "release/secondary/third_party/protobuf/BUILD.gn"
PROTOC_MAIN = ROOT / "third_party/protobuf/src/google/protobuf/compiler/main.cc"
ACTIVE_EXTERNAL_INPUT_OWNERS = (
    ROOT / "release/api/BUILD.gn",
    ROOT / "release/bazel/BUILD.gn",
    ROOT / "release/bazel/bazel_content_hashes.gni",
    ROOT / "release/bazel/bazel_fuchsia_sdk.gni",
    ROOT / "release/config/python/BUILD.gn",
    ROOT / "release/images/tools/fastboot.gni",
    ROOT / "release/python/BUILD.gn",
    ROOT / "release/python/python_mobly_test.gni",
    ROOT / "release/prebuilt/BUILD.gn",
    ROOT / "release/rust/rust_auxiliary.gni",
    ROOT / "release/sdk/plasa/clang_doc.gni",
    ROOT / "release/toolchain/breakpad.gni",
    ROOT / "userspace/developer/ffx/plugins/emulator/BUILD.gn",
    ROOT / "userspace/storage/fxfs/unicode/BUILD.gn",
    ROOT / "zircon/tools/zbi/BUILD.gn",
)

DELETED_LABELS = (
    "//userspace/graphics/",
    "//userspace/camera/",
    "//userspace/media/",
    "//userspace/ui/",
    "//userspace/fonts/",
    "//third_party/Vulkan-",
)


def read_all(paths: tuple[pathlib.Path, ...]) -> str:
    return "\n".join(path.read_text() for path in paths)


class SourceScopeTest(unittest.TestCase):
    def test_external_sdk_is_available_before_toolchain_discovery(self) -> None:
        buildconfig = BUILDCONFIG.read_text()
        self.assertTrue(SMOS_SDK_CONFIG.is_file())
        sdk_config = SMOS_SDK_CONFIG.read_text()
        python_config = PYTHON_INTERPRETER.read_text()

        sdk_import = 'import("//release/config/smos_sdk.gni")'
        self.assertIn(sdk_import, buildconfig)
        self.assertLess(buildconfig.index(sdk_import), buildconfig.index("clang_toolchain_info.gni"))
        self.assertIn('smos_sdk_root = ""', sdk_config)
        self.assertIn('smos_sdk_milestone = "27"', sdk_config)
        self.assertIn("smos_prebuilt_root", sdk_config)
        self.assertIn('${smos_prebuilt_root}/third_party/python3/', python_config)
        self.assertNotIn('python_exe_src = "//prebuilt/', python_config)

    def test_sdk_milestone_does_not_depend_on_integration_checkout(self) -> None:
        self.assertIn("smos_sdk_milestone", SDK_CONFIG.read_text())
        self.assertNotIn("//integration/MILESTONE", SDK_CONFIG.read_text())
        self.assertIn('"SMOS_SDK_MILESTONE=$smos_sdk_milestone"', FFX_SDK_BUILD.read_text())
        self.assertIn('env!("SMOS_SDK_MILESTONE")', FFX_SDK_SOURCE.read_text())
        self.assertNotIn("integration/MILESTONE", FFX_SDK_SOURCE.read_text())

    def test_core_toolchains_derive_from_external_sdk(self) -> None:
        for path in CORE_TOOLCHAIN_CONFIGS:
            text = path.read_text()
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn("smos_prebuilt_root", text)
                self.assertNotIn('"//prebuilt/', text)

        rust_config = (ROOT / "release/rust/config.gni").read_text()
        self.assertIn('${rustc_prefix}/.versions/rust.cipd_version', rust_config)

    def test_inactive_toolchain_does_not_require_stripped_libunwind(self) -> None:
        config = FUCHSIA_CONFIG.read_text()
        self.assertRegex(
            config,
            r'(?s)config\("libunwind"\).*?'
            r'if \(clang_target_toolchain_info\.libunwind_so != ""\)',
        )

    def test_compact_product_does_not_initialize_icu(self) -> None:
        self.assertIn("smos_without_icu = true", VERIFY_PRODUCT.read_text())
        self.assertIn("if (smos_without_icu)", ICU_BUILD_CONFIG.read_text())
        self.assertIn('default = "disabled"', ICU_BUILD_CONFIG.read_text())
        self.assertIn("if (!smos_without_icu)", ICU_CONFIG.read_text())
        self.assertIn("if (!smos_without_icu)", FUCHSIA_CONFIG.read_text())
        self.assertIn("user_platform_aib_names -= _icu_user_platform_aib_names", PLATFORM_AIBS.read_text())
        self.assertFalse((ROOT / "third_party/icu").exists())
        self.assertTrue(FIDL_GO_BUILD.is_file())

    def test_compact_product_keeps_mypy_and_excludes_dart(self) -> None:
        self.assertTrue((MYPY_ROOT / "mypy/src/mypy/__main__.py").is_file())
        self.assertTrue((MYPY_ROOT / "mypy_extensions/src/mypy_extensions.py").is_file())
        self.assertTrue((MYPY_ROOT / "typing_extensions/src/src/typing_extensions.py").is_file())
        self.assertFalse(DART_PACKAGES.exists())
        self.assertFalse((ROOT / "third_party/pypng").exists())
        self.assertIn("if (!smos_minimal_assembly)", SDK_BUILD.read_text())
        self.assertIn('"PYTHONDONTWRITEBYTECODE": "1"', MYPY_CHECKER.read_text())
        self.assertIn("library_deps -= [ \"//third_party/pypng\" ]", HONEYDEW_BUILD.read_text())

    def test_compact_product_keeps_only_cpp_and_rust_protoc_generators(self) -> None:
        protobuf_build = PROTOBUF_BUILD.read_text()
        protoc_main = PROTOC_MAIN.read_text()

        self.assertIn("SMOS_PROTOC_CPP_RUST_ONLY", protobuf_build)
        self.assertIn("SMOS_PROTOC_CPP_RUST_ONLY", protoc_main)
        for language in ("csharp", "java", "objectivec", "php", "python", "ruby"):
            with self.subTest(language=language):
                self.assertIn(f"compiler/{language}/*", protobuf_build)
                self.assertIn(
                    f"compiler/{language}/",
                    protoc_main,
                )
                self.assertFalse(
                    (ROOT / f"third_party/protobuf/src/google/protobuf/compiler/{language}").exists()
                )

    def test_active_prebuilt_inputs_derive_from_external_sdk(self) -> None:
        for path in ACTIVE_EXTERNAL_INPUT_OWNERS:
            text = path.read_text()
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn("smos_prebuilt_root", text)
                self.assertNotIn('"//prebuilt/', text)

    @unittest.skipUnless(KEEP_MANIFEST.is_file(), "source inventory not generated")
    def test_source_tree_has_no_unretained_top_level_domains(self) -> None:
        import json

        retained_paths = [
            item["path"] for item in json.loads(KEEP_MANIFEST.read_text())["paths"]
        ]
        retained_domains = {
            "/".join(path.split("/")[:2]) for path in retained_paths if "/" in path
        }
        for top_level in ("third_party", "userspace"):
            unused = [
                path.relative_to(ROOT).as_posix()
                for path in sorted((ROOT / top_level).iterdir())
                if path.is_dir()
                and path.relative_to(ROOT).as_posix() not in retained_domains
            ]
            with self.subTest(top_level=top_level):
                self.assertEqual([], unused)

        retained_top_levels = {item.split("/", 1)[0] for item in retained_paths}
        unused_root_domains = [
            path.name
            for path in sorted(ROOT.iterdir())
            if path.is_dir()
            and path.name not in {".git", "out", "prebuilt"}
            and path.name not in retained_top_levels
        ]
        self.assertEqual([], unused_root_domains)

    @unittest.skipUnless(KEEP_MANIFEST.is_file(), "source inventory not generated")
    def test_source_tree_has_no_unretained_nested_domains(self) -> None:
        import json

        manifest_paths = [
            item["path"].split("/")
            for item in json.loads(KEEP_MANIFEST.read_text())["paths"]
        ]
        scopes = ((ROOT / "userspace", 2, 3), (ROOT / "third_party", 3, 4))
        for scope, relative_depth, total_depth in scopes:
            retained = {
                "/".join(parts[:total_depth])
                for parts in manifest_paths
                if len(parts) > total_depth
            }
            unused = []
            for path in sorted(scope.rglob("*")):
                if not path.is_dir() or len(path.relative_to(scope).parts) != relative_depth:
                    continue
                relative = path.relative_to(ROOT).as_posix()
                if relative not in retained:
                    unused.append(relative)
            with self.subTest(scope=scope.name):
                self.assertEqual([], unused)

    @unittest.skipUnless(KEEP_MANIFEST.is_file(), "source inventory not generated")
    def test_third_party_contains_only_retained_files(self) -> None:
        import json

        retained = {
            item["path"]
            for item in json.loads(KEEP_MANIFEST.read_text())["paths"]
            if item["path"].startswith("third_party/")
        }
        actual = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "third_party").rglob("*")
            if path.is_file() or path.is_symlink()
        }
        self.assertEqual([], sorted(actual - retained))

    def test_active_gn_owners_do_not_reference_deleted_domains(self) -> None:
        active_gn_text = read_all(ACTIVE_GN_FILES)
        for label in DELETED_LABELS:
            with self.subTest(label=label):
                self.assertNotIn(label, active_gn_text, label)

    def test_compact_vmm_builds_exclude_graphics_runtimes(self) -> None:
        compact_runtime_text = read_all(COMPACT_VMM_BUILD_FILES).lower()
        for token in ("virtio_gpu", "virtio_magma", "goldfish", "wayland", "scenic"):
            with self.subTest(token=token):
                self.assertNotIn(token, compact_runtime_text, token)

    def test_minimal_vmm_define_propagates_to_header_consumers(self) -> None:
        vmm_build = COMPACT_VMM_BUILD_FILES[0].read_text()
        self.assertIn('config("smos_minimal_vmm")', vmm_build)
        self.assertIn('public_configs += [ ":smos_minimal_vmm" ]', vmm_build)

    def test_common_device_library_does_not_depend_on_mesa(self) -> None:
        device_build = DEVICE_BUILD.read_text()
        self.assertNotIn("//third_party/mesa", device_build)

    def test_virtualization_hardware_fidl_does_not_import_ui(self) -> None:
        hardware_fidl_text = read_all(HARDWARE_FIDL_FILES)
        self.assertNotIn("fuchsia.ui", hardware_fidl_text)

    def test_minimal_ctf_does_not_import_vulkan_environment(self) -> None:
        ctf_generator = CTF_GENERATOR.read_text()
        self.assertIn("if (smos_minimal_assembly)", ctf_generator)
        self.assertIn("vulkan_envs = []", ctf_generator)
        self.assertIn("magma_libvulkan_hardware_envs = []", ctf_generator)

    def test_minimal_ctf_does_not_load_removed_test_domains(self) -> None:
        ctf_tests = CTF_TESTS.read_text()
        self.assertIn("if (smos_minimal_assembly)", ctf_tests)
        self.assertIn("deps = []", ctf_tests)

    def test_minimal_tools_bundle_does_not_load_optional_domains(self) -> None:
        tools_bundle = BUNDLES_TOOLS.read_text()
        self.assertIn("if (smos_minimal_assembly)", tools_bundle)
        self.assertIn("public_deps = []", tools_bundle)

    def test_minimal_aib_template_ignores_unselected_platform_bundles(self) -> None:
        template = AIB_TEMPLATE.read_text()
        self.assertIn("_smos_skip_bundle", template)
        self.assertIn("bringup_platform_aib_names", template)

    def test_compact_sdk_does_not_collect_all_board_visitors(self) -> None:
        sdk_build = (ROOT / "sdk/BUILD.gn").read_text()
        self.assertNotIn("all-driver-visitors_sdk", sdk_build)
        self.assertIn("if (smos_minimal_assembly)", sdk_build)
        self.assertIn("# SMOS has no target-interaction SDK tools.", sdk_build)

    def test_headless_critical_services_does_not_require_ui_hid_parser(self) -> None:
        build = CRITICAL_SERVICES_BUILD.read_text()
        self.assertIn("SMOS_HEADLESS_CRITICAL_SERVICES=1", build)
        self.assertIn("if (!smos_minimal_assembly)", build)

    def test_assembly_schema_owns_its_input_device_enum(self) -> None:
        build = CONFIG_SCHEMA_BUILD.read_text()
        ui_config = (
            ROOT / "userspace/lib/assembly/config_schema/src/platform_config/ui_config.rs"
        ).read_text()
        self.assertNotIn("//userspace/ui/lib/input-device-constants", build)
        self.assertIn("pub enum InputDeviceType", ui_config)

    def test_minimal_build_does_not_expand_ffx_plugin_suite(self) -> None:
        build = FFX_TOOLS_BUILD.read_text()
        self.assertIn("if (smos_minimal_assembly)", build)
        self.assertIn("_tools = []", build)

    def test_headless_bootstrap_excludes_sysmem(self) -> None:
        bundles = ASSEMBLY_BUNDLES.read_text()
        self.assertRegex(
            bundles,
            r'(?s)assembly_input_bundle\("bootstrap"\).*?'
            r'if \(smos_minimal_assembly\).*?'
            r'bootfs_packages\s*-=' + r'.*?//userspace/sysmem/server:pkg',
        )
        self.assertRegex(
            bundles,
            r'(?s)if \(smos_minimal_assembly\).*?shards\s*-=' +
            r'.*?sysmem\.bootstrap_shard\.cml',
        )

    def test_empty_base_driver_set_does_not_resolve_packages(self) -> None:
        driver_index = DRIVER_INDEX_MAIN.read_text()
        self.assertRegex(
            driver_index,
            r'(?s)if base_drivers\.is_empty\(\).*?load_base_repo\(vec!\[\]\).*?return Ok\(\(\)\)',
        )

    def test_arm_board_does_not_request_ioport_resource(self) -> None:
        self.assertNotIn("fuchsia.kernel.IoportResource", QEMU_ARM64_MANIFEST.read_text())

    def test_root_compat_parent_is_optional_and_not_a_warning(self) -> None:
        shard = DRIVER_COMPONENT_SHARD.read_text()
        compat = COMPAT_DRIVER.read_text()
        self.assertRegex(
            shard,
            r"(?s)use:\s*\[.*?fuchsia\.driver\.compat\.Service.*?availability:\s*['\"]optional['\"]",
        )
        self.assertIn('node_name().value_or("") == "dev"', compat)
        self.assertNotIn("const auto severity", compat)
        self.assertRegex(
            compat,
            r'(?s)node_name\(\)\.value_or\(""\) == "dev".*?'
            r'logger_->log\(fdf::INFO.*?else.*?logger_->log\(fdf::WARN',
        )

    def test_invalid_component_manager_cli_exits_before_becoming_critical(self) -> None:
        main = COMPONENT_MANAGER_MAIN.read_text()
        self.assertNotIn('unwrap_or_else(|err| panic!("{}\\n{}"', main)
        self.assertIn("process::exit(2)", main)
        parse = main.index("startup::Arguments::from_args()")
        critical = main.index("set_critical(JobCriticalOptions::RETCODE_NONZERO")
        self.assertLess(parse, critical)


if __name__ == "__main__":
    unittest.main()
