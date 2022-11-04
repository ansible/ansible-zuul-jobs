#!/usr/bin/env python3

from pathlib import Path
from pydantic import BaseModel
from ruamel.yaml import YAML
from ruamel.yaml.comments import Comment
from typing import Iterator
import argparse
import json

yaml = YAML()
yaml.indent(sequence=4, offset=2)
yaml.explicit_start = True  # type: ignore

parser = argparse.ArgumentParser()
parser.add_argument("repo_dir", type=Path, help="Location of the amazon.aws collection")

args = parser.parse_args()
to_skip = {"disabled", "unsupported"}


def list_targets(repo_dir: Path) -> Iterator[str]:
    targets_dir = repo_dir / "tests" / "integration" / "targets"
    for alias in targets_dir.glob("*/aliases"):
        skip_reason = set(alias.read_text().split("\n")) & to_skip
        if skip_reason:
            print(f"Skipping {alias.parent.stem} because {skip_reason}")
            continue
        yield alias.parent.stem


class Job(BaseModel):
    name: str
    nodeset: str = "container-ansible"
    parent: str = "ansible-test-cloud-integration-aws"
    vars: dict

    @classmethod
    def from_target_name(cls, target: str) -> "Job":
        return cls(
            name=f"integration-amazon.aws-target-{target}",
            vars={"ansible_test_integration_targets": target},
        )


class JobMapping(BaseModel):
    job: Job


class Jobs(BaseModel):
    jobs: list[JobMapping]


class Queue(BaseModel):
    jobs: list[str]


class ProjectTemplate(BaseModel):
    name: str
    periodic: Queue


jobs = Jobs(
    jobs=[
        JobMapping(job=Job.from_target_name(target))
        for target in list_targets(args.repo_dir)
    ]
)

project_template = ProjectTemplate(
    name="ansible-collections-amazon-aws-each-target",
    # we actually depend on ansible-test-splitter, but
    # it's listed in ansible-test-cloud-integration-aws
    #  dependency list
    periodic=Queue(
        jobs=["build-ansible-collection"] + [job.job.name for job in jobs.jobs]
    ),
)


class PushRootLeft:
    def __call__(self, s):
        result = []
        for line in s.splitlines(True):
            if line.startswith("---"):
                result.append("# Generated by tools/refresh-aws-periodical-jobs.py\n")
                result.append(line)
            else:
                # lines start with 2 empty spaces because of the offset=2
                result.append(line[2:])
        return "".join(result)


zuul_config_file = Path("zuul.d/amazon-aws-periodical-jobs.yaml")
yaml.dump(
    [job.dict() for job in jobs.jobs]
    + [{"project-template": json.loads(project_template.json())}],
    zuul_config_file,
    transform=PushRootLeft(),
)