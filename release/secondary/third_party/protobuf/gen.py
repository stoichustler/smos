import subprocess
import shlex
import os

# Set PRINT_GIT_LS_FILES=1 in your environment to print
# the `git ls-files` commands used during generation.
print_git_ls_files=bool(os.environ.get("PRINT_GIT_LS_FILES"))

gn_in = open("BUILD.input.gn", "rb")
gn_file = gn_in.read()
gn_in.close()

fuchsia_dir = os.environ["FUCHSIA_DIR"]
assert fuchsia_dir, "FUCHSIA_DIR environment variable should be set before calling this script!"

def get_files(paths, exclude=[], append=[]):
    cmd = ["git", "ls-files", "--"]
    for ex in exclude:
        cmd.append(":!%s" % ex)
    cmd.extend(paths)

    if print_git_ls_files:
        print(' '.join(shlex.quote(c) for c in cmd))

    git_ls = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        cwd=os.path.join(fuchsia_dir, "third_party", "protobuf"))
    sed1 = subprocess.Popen(
        ["sed", "s/^/\"/"], stdin=git_ls.stdout, stdout=subprocess.PIPE)
    result = subprocess.check_output(["sed", "s/$/\",/"], stdin=sed1.stdout)
    if append:
        for item in append:
            result += b' "' + item.encode() + b'",'
    return result


gn_file = gn_file.replace(
    b"PROTOBUF_LITE_PUBLIC",
    get_files(
        [
        "src/google/protobuf/*.h",
        "src/google/protobuf/*.inc"
        ],
        exclude=["*/compiler/*", "*/testing/*", "*/util/*"]))
gn_file = gn_file.replace(
    b"PROTOBUF_FULL_PUBLIC",
    get_files(
        [
        "src/google/protobuf/*.h",
        "src/google/protobuf/*.inc"
        ],
        exclude=["*/compiler/*", "*/testing/*"]))
gn_file = gn_file.replace(
    b"UPB_LIB_SOURCES",
    get_files(
        [
            "upb/port/*.h",
            "upb/port/*.inc",
            "upb/port/*.cc",
            "upb/base/*.h",
            "upb/base/*.cc",
            "upb/mem/*.h",
            "upb/mem/*.cc",
        ],
        exclude=["*_test.cc"],
        append=[
            # See comment in this file to see why it is needed here.
            "//release/secondary/third_party/protobuf/upb_generator/common.cc",
        ]
    )
)
gn_file = gn_file.replace(
    b"PROTOC_LIB_SOURCES",
    get_files(
        [
            "src/google/protobuf/compiler/*.cc",
        ],
        exclude=["*/main.cc", "*test*", "*mock*", "src/google/protobuf/compiler/cpp/tools/*"],
        append = [
            # This defines File::ReadFileToString used by
            # src/google/protobuf/compiler/rust/crate_mapping.cc
            # Note that this is filtered-out by the "*test*" above, hence why the value
            # is appended here.
            "src/google/protobuf/testing/file.cc"
        ]
    )
)

gn_out = open("BUILD.gn", "wb")
gn_out.write(
    b"# THIS FILE IS GENERATED FROM BUILD.input.gn BY gen.py\n# EDIT BUILD.input.gn FIRST AND THEN RUN gen.py\n#\n#\n"
)
gn_out.write(gn_file)

try:
  cmd = [fuchsia_dir + "/tools/scripts/fx", "format-code", "--files=BUILD.gn"]
  subprocess.check_output(cmd, text=True)
except subprocess.CalledProcessError as e:
  print(f"Error formatting BUILD.gn: {e}")
