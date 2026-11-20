#!/usr/bin/env python3
"""Detect architecture review triggers and check for a new review record."""
import argparse
import re
import subprocess
from pathlib import Path

REVIEW_DIR = "architecture/reviews/"
FIELDS = ("Trigger", "Evidence", "Design", "Decision", "Verification")
RECORD_FIELD = re.compile(r"^(" + "|".join(FIELDS) + r"):[ \t]+(\S.*)$", re.MULTILINE)


def git(*args):
    return subprocess.check_output(["git", *args], text=True)


def paths(*args):
    return set(filter(None, git(*args, "-z").split("\0")))


def is_architecture_path(path):
    return (
        (path.endswith(".py") and not path.startswith("tests/"))
        or path.startswith(".github/workflows/")
    )


def review_status(base, signal):
    root = Path(git("rev-parse", "--show-toplevel").rstrip("\n"))
    # Run from the top-level checkout so Git paths and record paths have one reference point.
    if Path.cwd() != root:
        raise ValueError("run this command from the repository root")
    fork = git("merge-base", base, "HEAD").strip()
    untracked = paths("ls-files", "--others", "--exclude-standard")
    changed = paths("diff", "--name-only", "--no-renames", fork) | untracked
    relevant = sorted(path for path in changed if is_architecture_path(path))
    if not relevant and not signal:
        print("SKIP architecture review: no code or workflow changes and no reported friction")
        return 0

    print("REVIEW architecture changes or friction")
    for path in relevant:
        print(f"  {path}")
    if signal:
        print(f"  Signal: {signal}")

    added = paths("diff", "--name-only", "--diff-filter=A", "--no-renames", fork) | untracked
    for path in sorted(added):
        if not path.startswith(REVIEW_DIR) or not path.endswith(".md"):
            continue
        record = root / path
        if not record.is_file():
            continue
        fields = {field for field, _ in RECORD_FIELD.findall(record.read_text(encoding="utf-8"))}
        if fields == set(FIELDS):
            print(f"PASS architecture review record: {path}")
            return 0

    print("OPEN Add a new architecture review under architecture/reviews/ with "
          + ", ".join(FIELDS) + ". See ARCHITECTURE.md.")
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="compare from the merge base with this ref")
    parser.add_argument("--signal", help="observed friction that a Git diff cannot detect")
    args = parser.parse_args()
    try:
        return review_status(args.base, args.signal)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"FAIL {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
