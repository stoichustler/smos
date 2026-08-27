This directory contains configuration information that is read from several
scripts ot locations.

- main_workspace_top_dir:

  The `BAZEL_TOPDIR` for the main workspace, relative to the Ninja output
  directory. See `//release/bazel/README.md` for details.

  Format:  A single line of text for the path.
  Used by: `//release/bazel/bazel_workspace.gni`
  Used by: `//tools/devshell/lib/bazel_utils.sh`
  Used by: `//release/bazel/scripts/parse-workspace-event-log.py`
  Used by: `//release/bazel/scripts/workspace_utils.py`
