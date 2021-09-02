#!/usr/bin/env python3

from pathlib import PosixPath
import sys
import json
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument('-t', '--targets', help="list of targets for integration testing. example: 'ec2_tag ami_info ec2_instance'",default="")
parser.add_argument('-p', '--prefix', help='list of targets for integration testing', default="job_")
parser.add_argument('-c', '--collection_path', help='path to the collection.', default=os.getcwd())

args = parser.parse_args()
batches = []
# NOTE(pabelanger): Hardcode this to 6 because that is the semaphore in zuul.
total_jobs = 6
regular_targets = []

jobs = [f"{args.prefix}{i}" for i in range(total_jobs)]

targets = PosixPath(os.path.join(args.collection_path,"tests/integration/targets/"))
targets_from_cli = [ x for x in args.targets.split(" ") if x != "" ]
for target in targets.glob("*"):
    aliases = target / "aliases"
    if not target.is_dir():
        continue
    if not aliases.is_file():
        continue
    lines = aliases.read_text().split("\n")
    combined = lines + [target.name]
    if targets_from_cli and not set(combined) & set(targets_from_cli):
        continue
    if "disabled" in lines:
        continue
    if "unstable" in lines:
        continue
    if "slow" in lines or "# reason: slow" in lines:
        batches.append([target.name])
    else:
        regular_targets.append(target.name)

remaining_jobs = max(total_jobs - len(batches), 1)

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
