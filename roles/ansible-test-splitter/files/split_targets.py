#!/usr/bin/env python3

from pathlib import PosixPath
import sys
import json
import argparse
import os


total_jobs = 6


def get_job_list(prefix, total_jobs):
    return [f"{prefix}{i}" for i in range(total_jobs)]


def to_skip_because_unstable(lines):
    if "unstable" in lines:
        return True
    return False


def to_skip_because_disabled(lines):
    if "disabled" in lines:
        return True
    return False


def is_slow(lines):
    if "slow" in lines or "# reason: slow" in lines:
        return True
    return False


def get_all_targets(collection_path):
    """Return all the targets from a directory."""
    targets_dir = PosixPath(os.path.join(collection_path, "tests/integration/targets/"))
    targets = {}
    for target in targets_dir.glob("*"):
        aliases = target / "aliases"
        if not target.is_dir():
            continue
        if not aliases.is_file():
            continue
        lines = aliases.read_text().split("\n")
        targets[target.name] = lines
    return targets


def to_skip_because_of_targets_parameters(target_name, lines, targets_from_cli):
    """--targets parameter is in use, we skip the targets not part of the list."""
    combined = lines + [target_name]
    if targets_from_cli and not set(combined) & set(targets_from_cli):
        return True
    return False


def get_targets_to_run(targets, targets_from_cli):
    slow_targets = []
    regular_targets = []
    for target_name, lines in targets.items():
        if to_skip_because_of_targets_parameters(target_name, lines, targets_from_cli):
            continue
        if to_skip_because_disabled(lines):
            continue
        if to_skip_because_unstable(lines) and target_name not in targets_from_cli:
            continue
        if is_slow(lines):
            slow_targets.append(target_name)
        else:
            regular_targets.append(target_name)
    return slow_targets, regular_targets


def build_up_batches(slow_targets, regular_targets, total_jobs):
    remaining_jobs = max(total_jobs - len(slow_targets), 1)
    # Slow targets is a list of slow targets so we need to wrap each entry in a
    # list
    batches = [[i] for i in slow_targets]
    for x in range(remaining_jobs):
        batch = regular_targets[x::remaining_jobs]
        if batch:
            batches.append(batch)
    return batches


def build_result_struct(jobs, batches):
    result = {
        "data": {
            "zuul": {"child_jobs": jobs[0 : len(batches)]},
            "child": {"targets_to_test": batches},
        }
    }
    return result


def get_args(sys_argv):
    def raw_targets(string):
        return [x for x in string.split(" ") if x != ""]

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-t",
        "--targets",
        help="list of targets for integration testing. example: 'ec2_tag ami_info ec2_instance'",
        default=[],
        type=raw_targets,
    )
    parser.add_argument(
        "-p", "--prefix", help="list of targets for integration testing", default="job_"
    )
    parser.add_argument(
        "-c", "--collection_path", help="path to the collection.", default=os.getcwd()
    )

    return parser.parse_args(sys_argv[1:])


if __name__ == "__main__":

    args = get_args(sys.argv)
    jobs = get_job_list(args.prefix, total_jobs)

    targets = get_all_targets(args.collection_path)
    slow_targets, regular_targets = get_targets_to_run(targets, args.targets)
    batches = build_up_batches(slow_targets, regular_targets, total_jobs)
    result = build_result_struct(jobs, batches)

    print(json.dumps(result))
