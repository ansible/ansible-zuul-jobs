#!/usr/bin/env python

import pytest
from unittest.mock import patch

from split_targets import (
    get_job_list,
    to_skip_because_disabled,
    is_slow,
    get_args,
    to_skip_because_of_targets_parameters,
    build_up_batches,
    build_result_struct,
)


def test_get_job_list():
    assert get_job_list("my_jobs", 4) == [
        "my_jobs0",
        "my_jobs1",
        "my_jobs2",
        "my_jobs3",
    ]


def test_to_skip():
    assert to_skip_because_disabled(["slow", "# disabled", "no_unstable"]) is False
    assert to_skip_because_disabled(["# really unstable", "unstable"]) is True


def test_is_slow():
    assert is_slow(["slow", "# disabled", "no_unstable"]) is True
    assert is_slow(["noslow", "# reason: slow"]) is True
    assert is_slow(["noslow", "# reason: noslow"]) is False


def test_get_args_targets_with_parameters():
    args = get_args([None, "-t", "foo bar", "-p", "my_prefix", "-c", "my_collection"])
    assert args.targets == ["foo", "bar"]
    assert args.prefix == "my_prefix"
    assert args.collection_path == "my_collection"


def test_get_args_targets_naked():
    with patch("os.getcwd", return_value="here"):
        args = get_args([None])
    assert args.targets == []
    assert args.prefix == "job_"
    assert args.collection_path == "here"


@pytest.mark.parametrize(
    "target,lines,targets_from_cli,expected",
    [
        ("ec2_eni", [], ["ec2_vol"], True),
        ("ec2_eni", [], ["ec2_eni"], False),
        ("ec2_eni", [], [], False),
        ("ec2_eni", ["ec2_vol"], ["ec2_vol"], False),
    ],
)
def test_to_skip_because_of_targets_parameters_skip(
    target, lines, targets_from_cli, expected
):
    assert (
        to_skip_because_of_targets_parameters(target, lines, targets_from_cli)
        == expected
    )


@pytest.mark.parametrize(
    "slow_targets,regular_targets,total_jobs,expected",
    [
        ([], [], 6, []),
        (["slow1", "slow2"], [], 6, [["slow1"], ["slow2"]]),
        # NOTE: this situation should be improved. It don't make any
        # sence to start 1 target per job. We should instead group the
        # two targets.
        ([], ["reg1", "reg2"], 6, [["reg1"], ["reg2"]]),
        (
            [],
            [f"reg{i}" for i in range(100)],
            3,
            [
                [f"reg{i}" for i in range(0, 100, 3)],
                [f"reg{i}" for i in range(1, 100, 3)],
                [f"reg{i}" for i in range(2, 100, 3)],
            ],
        ),
    ],
)
def test_build_up_batches(slow_targets, regular_targets, total_jobs, expected):
    assert build_up_batches(slow_targets, regular_targets, total_jobs) == expected


@pytest.mark.parametrize(
    "jobs,batches,expected",
    [
        (
            [],
            [],
            {"data": {"zuul": {"child_jobs": []}, "child": {"targets_to_test": []}}},
        ),
        (
            ["job_1", "job_2"],
            [["a1", "b1", "c2"], ["b1", "c1", "c3"]],
            {
                "data": {
                    "zuul": {"child_jobs": ["job_1", "job_2"]},
                    "child": {
                        "targets_to_test": [["a1", "b1", "c2"], ["b1", "c1", "c3"]]
                    },
                }
            },
        ),
    ],
)
def test_build_result_struct(jobs, batches, expected):
    assert build_result_struct(jobs, batches) == expected
