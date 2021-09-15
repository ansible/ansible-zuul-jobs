#!/usr/bin/env python3

from pathlib import PosixPath
import sys
import subprocess

targets_to_test = []
targets_dir = PosixPath("tests/integration/targets")
zuul_branch = sys.argv[1]
diff = subprocess.check_output(
    ["git", "diff", f"origin/{zuul_branch}", "--name-only"]
).decode()
module_files = [PosixPath(d) for d in diff.split("\n") if d.startswith("plugins/")]
for i in module_files:
    if not i.is_file():
        continue
    target_name = i.stem

    for t in targets_dir.iterdir():
        aliases = t / "aliases"
        if not aliases.is_file():
            continue
        # There is a target with the module name, let's take that
        if t.name == target_name:
            targets_to_test.append(target_name)
            break
        alias_content = aliases.read_text().split("\n")
        # The target name is in the aliases file
        if target_name in alias_content:
            targets_to_test.append(target_name)
            break

target_files = [
    PosixPath(d) for d in diff.split("\n") if d.startswith("tests/integration/targets/")
]
for i in target_files:
    splitted = str(i).split("/")
    if len(splitted) < 5:
        continue
    target_name = splitted[3]
    aliases = targets_dir / target_name / "aliases"
    if aliases.is_file():
        targets_to_test.append(target_name)

print(" ".join(list(set(targets_to_test))))
