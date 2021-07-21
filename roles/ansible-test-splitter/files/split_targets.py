#!/usr/bin/env python3

from pathlib import PosixPath
import random
import sys
import json

job_prefix = sys.argv[1]
if len(sys.argv) == 3:
    targets_from_cli = sys.argv[2].split(" ")
else:
    targets_from_cli = []
jobs = [f"{job_prefix}{i}" for i in range(10)]
targets_per_job = 20
slow_targets = []
regular_targets = []

batches = []

targets = PosixPath("tests/integration/targets/")
for target in targets.glob("*"):
    aliases = target / "aliases"
    if not target.is_dir():
        continue
    if not aliases.is_file():
        continue
    if targets_from_cli and target.name not in targets_from_cli:
        continue
    lines = aliases.read_text().split("\n")
    if "disabled" in lines:
        continue
    if "unstable" in lines:
        continue
    if "slow" in lines or "# reason: slow" in lines:
        batches.append([target.name])
    else:
        regular_targets.append(target.name)

random.shuffle(regular_targets)

splitted_targets = len(regular_targets) % targets_per_job

splitted_targets = []
while regular_targets:
    batches.append(
        [regular_targets.pop() for i in range(targets_per_job) if regular_targets]
    )


result = {
    "data": {
        "zuul": {"child_jobs": jobs[0:len(batches)]},
        "child": {"targets_to_test": batches},
    }
}

print(json.dumps(result))
