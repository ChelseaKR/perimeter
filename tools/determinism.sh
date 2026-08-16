#!/usr/bin/env bash
#
# Compare two build trees and exit non-zero unless they are byte-identical.
#
# This exists as a script, rather than as four lines inlined in a workflow, for one
# reason: a gate has to be able to fail, and the only way to know that is to run it
# against inputs that should fail it. tests/test_determinism_gate.py does exactly that,
# so the determinism claim in README.md rests on a check whose failure modes are
# themselves tested.
#
# The inlined version this replaces could not fail in two ways:
#
#   find "$dir" -type f | sort | xargs shasum -a 256 > first.txt
#
# `find` on a missing directory exits 1, but under `bash -e` without `pipefail` the
# pipeline's status is xargs', so the step stayed green. And with no files to hash both
# sides came out identical, so an empty build passed the determinism check.
#
# Exit codes:
#   0  the two trees are byte-identical
#   1  the two trees differ (the diff is printed)
#   2  a tree is missing, is not a directory, or holds no files
#
# Usage: tools/determinism.sh <tree-a> <tree-b>

set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <tree-a> <tree-b>" >&2
  exit 2
fi

hash_tree() {
  root="$1"
  if [ ! -d "$root" ]; then
    echo "determinism: $root is not a directory" >&2
    exit 2
  fi
  count=$(find "$root" -type f | wc -l | tr -d '[:space:]')
  if [ "$count" -eq 0 ]; then
    echo "determinism: $root holds no files; the build produced nothing to compare" >&2
    exit 2
  fi
  # Relative paths, so the two trees compare on content and layout rather than on where
  # they happen to live. NUL-delimited, so a path with a space in it cannot split.
  ( cd "$root" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 )
}

a=$(hash_tree "$1")
b=$(hash_tree "$2")

if [ "$a" = "$b" ]; then
  echo "determinism: $1 and $2 are byte-identical ($(printf '%s\n' "$a" | wc -l | tr -d '[:space:]') files)"
  exit 0
fi

echo "determinism: $1 and $2 differ" >&2
diff <(printf '%s\n' "$a") <(printf '%s\n' "$b") >&2 || true
exit 1
