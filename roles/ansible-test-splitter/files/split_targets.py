#!/usr/bin/env python3

from pathlib import PosixPath
import sys
import json
import subprocess

job_prefix = sys.argv[1]
print(sys.argv[2])
if len(sys.argv) == 3:
    targets_from_cli = sys.argv[2].split(" ")
else:
    targets_from_cli = []
# NOTE(pabelanger): Hardcode this to 6 because that is the semaphore in zuul.
jobs = [f"{job_prefix}{i}" for i in range(6)]
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

slow_jobs = len(batches)
remaining_jobs = total_jobs - slow_jobs

for x in range(remaining_jobs):
    batch = regular_targets[x::remaining_jobs]
    if batch:
        batches.append(batch)

result = {
    "data": {
        "zuul": {"child_jobs": jobs[0:len(batches)]},
        "child": {"targets_to_test": batches},
    }
}

print(json.dumps(result))
