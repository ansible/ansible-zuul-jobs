#!/usr/bin/env python3

from pathlib import PosixPath

ignore = set(["unsupported", "disabled", "unstable", "hidden"])

targets_to_test = []
targets_dir = PosixPath("tests/integration/targets")
for t in targets_dir.iterdir():
    aliases = t / "aliases"
    if not aliases.is_file():
        continue
    alias_content = aliases.read_text().split("\n")
    if not ignore.isdisjoint(set(alias_content)):
        continue
    targets_to_test.append(t.stem)

print(" ".join(targets_to_test))
