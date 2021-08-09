#!/usr/bin/env python3

from pathlib import PosixPath
import getopt
import json
import sys

try:
    opts, args = getopt.getopt(sys.argv[1:],"ht:j:p:")
except getopt.GetoptError:
    print('split_targets.py -t <targets> -j <total_jobs> -p <job_prefix>')
    sys.exit(2)

targets = ""
job_prefix = "job"
job_count = 10

for opt, arg in opts:
    if opt == '-h':
        print('split_targets.py -t <targets> -j <total_jobs> -p <job_prefix>')
        sys.exit(0)
    if opt == '-p':
        job_prefix = arg
    if opt == '-t':
        targets_from_cli = arg
    if opt == '-j':
        job_count = int(arg)

if targets:
    targets_from_cli = targets.split(" ")
else:
    targets_from_cli = []

jobs = [f"{job_prefix}{i}" for i in range(job_count)]
total_jobs = job_count
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

batches.sort()
regular_targets.sort()
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
