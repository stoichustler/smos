#!/bin/bash

# Copyright 2016 The Fuchsia Authors
# Copyright (c) 2015 Travis Geiselbrecht
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT

readonly OUTFILE="$1"
readonly CHECKOUT_ROOT="$2"

set -e

# The --no-optional-locks option ensures git read-only operations do
# not refresh the index (https://fxbug.dev/42175708).  A compact SMOS source
# tree may intentionally omit the original checkout's Git metadata, so retain
# the imported revision next to this script as a deterministic fallback.
if CHECKOUT_REV="$(git --no-optional-locks -C "$CHECKOUT_ROOT" rev-parse HEAD 2>/dev/null)"; then
  GIT_REV="git-${CHECKOUT_REV}"
  if [ -n "$(git --no-optional-locks -C "$CHECKOUT_ROOT" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    GIT_REV+="-dirty"
  fi
else
  readonly REVISION_FILE="$(dirname "$0")/git-revision"
  CHECKOUT_REV="$(<"$REVISION_FILE")"
  if [[ ! "$CHECKOUT_REV" =~ ^[0-9a-f]{40}$ ]]; then
    echo "invalid pinned revision in $REVISION_FILE" >&2
    exit 1
  fi
  GIT_REV="git-${CHECKOUT_REV}"
fi

# Update the existing file only if it's changed.
if [ ! -r "$OUTFILE" ] || [ "$(<"$OUTFILE")" != "$GIT_REV" ]; then
  # Make sure not to include a trailing newline!
  printf '%s' "$GIT_REV" > "$OUTFILE"
fi
