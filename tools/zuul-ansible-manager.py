#!/usr/bin/env python3

from pathlib import Path
from pydantic import BaseModel, Field, Extra, validate_arguments
import ruamel.yaml.constructor
from ruamel.yaml import YAML
from typing import Iterator, Optional, Any
import argparse
import requests
from datetime import datetime
from datetime import timedelta

from collections import UserList, UserDict

parser = argparse.ArgumentParser(prog="Ansible-Zuul manager")
subparsers = parser.add_subparsers(dest="function_name", required=True)
parser_refresh_aws_periodical_jobs = subparsers.add_parser(
    "refresh-aws-periodical-jobs",
    help="Read the list of the integration test targets from amazon.aws to generate the periodical jobs.",
)
subparsers.add_parser(
    "refresh-aws-integration-jobs",
    help="Refresh the AWS integration slots for community.aws and amazon.aws",
)
parser_refresh = subparsers.add_parser(
    "refresh", help="Alias to call all the refresh actions"
)
parser_refresh.add_argument(
    "--amazon-aws-repo-dir",
    type=Path,
    required=True,
    help="Localtion of a local copy of the amazon.aws collection, e.g: ~/.ansible/collections/ansible_collections/amazon/aws/",
)
parser_refresh_aws_periodical_jobs.add_argument(
    "--amazon-aws-repo-dir",
    type=Path,
    required=True,
    help="Localtion of a local copy of the amazon.aws collection, e.g: ~/.ansible/collections/ansible_collections/amazon/aws/",
)
subparsers.add_parser("check", help="Sanity check")
subparsers.add_parser(
    "check_slow", help="Sanity check that are slower to run (10 minutes)"
)

args = parser.parse_args()
to_skip = {"disabled", "unsupported"}


class ZuulMaybeList(UserList):
    def __init__(self, v):
        if isinstance(v, str):
            self.data = [v]
        else:
            self.data = v

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, str):
            return [v]
        elif isinstance(v, list):
            return v
        else:
            raise TypeError(f"string or list required, not {v}")

    def __repr__(self):
        return f"ZuulMaybeList({super().__repr__()})"


class ZuulBranches(ZuulMaybeList):
    pass


class MyBaseModel(BaseModel):
    class Config:
        extra = Extra.forbid
        validate_assignment = True


class RequiredProject(MyBaseModel):
    name: str
    override_checkout: Optional[str] = Field(None, alias="override-checkout")


class RequiredProjectAsText(MyBaseModel):
    __root__: str


class JobDependency(MyBaseModel):
    name: str
    soft: Optional[bool] = None


class JobDependencyAsText(MyBaseModel):
    __root__: str


class Nodeset(MyBaseModel):
    name: Optional[str] = None
    nodes: list
    groups: Optional[list[dict]] = None


class NodesetName(MyBaseModel):
    __root__: str


class NodesetMapping(MyBaseModel):
    nodeset: Nodeset


class Job(MyBaseModel):
    name: Optional[str] = None
    abstract: Optional[bool] = None
    branches: Optional[ZuulBranches] = None
    description: Optional[str] = None
    parent: Optional[str] = None
    nodeset: NodesetName = NodesetName(__root__="container-ansible")
    dependencies: Optional[list[JobDependency | JobDependencyAsText]] = None
    pre_run: Optional[ZuulMaybeList] = Field(
        alias="pre-run",
    )
    post_run: Optional[ZuulMaybeList] = Field(
        alias="post-run",
    )

    run: Optional[ZuulMaybeList]
    files: Optional[list] = None
    required_projects: Optional[list[RequiredProject | RequiredProjectAsText]] = Field(
        None,
        alias="required-projects",
    )
    requires: Optional[list[str]] = None
    timeout: int = 3600
    host_vars: dict = Field({}, alias="host-vars")
    vars: dict = {}
    extra_vars: dict = Field({}, alias="extra-vars")
    semaphore: Optional[str] = None
    voting: Optional[bool] = None
    irrelevant_files: Optional[list[str]] = Field(None, alias="irrelevant-files")
    nodeset: Optional[Nodeset | NodesetName] = None
    roles: Optional[list[dict]] = None
    secrets: Optional[list[str | dict]] = None
    allowed_projects: Optional[list[str]] = Field(None, alias="allowed-projects")
    final: Optional[bool] = None
    protected: Optional[bool] = None


class JobMapping(MyBaseModel):
    job: Job


class Jobs(MyBaseModel):
    jobs: list[JobMapping]


class Queue(MyBaseModel):
    queue: Optional[str] = None
    ptjobs: Optional[list[str | dict[str, Job]]] = Field(alias="jobs")
    fail_fast: Optional[bool] = Field(alias="fail-fast")


class ProjectTemplate(MyBaseModel):
    name: str
    description: Optional[str] = None
    merge_mode: Optional[str] = Field(alias="merge-mode")
    check: Optional[Queue] = None
    gate: Optional[Queue] = None
    ondemand: Optional[Queue] = None
    periodic: Optional[Queue] = None
    third_party_check: Optional[Queue] = Field(alias="third-party-check")
    pre_release: Optional[Queue] = Field(alias="pre-release")
    post_release: Optional[Queue] = Field(alias="post-release")
    release: Optional[Queue] = None
    post: Optional[Queue] = None
    unlabel_on_push: Optional[Queue] = Field(alias="unlabel-on-push")
    lgtm: Optional[Queue] = None


class ProjectTemplateMapping(MyBaseModel):
    project_template: ProjectTemplate = Field(alias="project-template")


class Semaphore(MyBaseModel):
    name: str
    max: int


class SemaphoreMapping(MyBaseModel):
    semaphore: Semaphore


class Project(BaseModel):
    name: Optional[str] = None
    check: Optional[dict] = None
    gate: Optional[dict] = None
    post: Optional[dict] = None
    templates: Optional[list[str]] = None
    semaphore: Optional[str] = None


class ProjectMapping(BaseModel):
    project: Project


class MappingList(BaseModel):
    __root__: list[
        JobMapping
        | ProjectTemplateMapping
        | SemaphoreMapping
        | NodesetMapping
        | ProjectMapping
    ]


@validate_arguments
def write_config(config_file: Path, config: MappingList):
    class PushRootLeft:
        def __call__(self, s):
            result = []
            for line in s.splitlines(True):
                if line.startswith("---"):
                    result.append("# Generated by tools/zuul-ansible-manager.py\n")
                    result.append(line)
                else:
                    # lines start with 2 empty spaces because of the offset=2
                    result.append(line[2:])
            return "".join(result)

    yaml = YAML()

    def _ZuulMaybeList(representer, data):
        if isinstance(data.data, str):
            return representer.represent_str(data.data)
        elif isinstance(data.data, list) and len(data.data) == 1:
            return representer.represent_str(data.data[0])
        elif isinstance(data.data, list):
            return representer.represent_list(data.data)
        else:
            raise ValueError

    yaml.representer.add_representer(ZuulMaybeList, _ZuulMaybeList)
    yaml.indent(sequence=4, offset=2)
    yaml.explicit_start = True  # type: ignore
    yaml.dump(
        config.dict(by_alias=True, exclude_none=True)["__root__"],
        config_file,
        transform=PushRootLeft(),
    )


def list_targets(repo_dir: Path) -> Iterator[str]:
    targets_dir = repo_dir / "tests" / "integration" / "targets"
    if not targets_dir.is_dir():
        raise Exception(f"{targets_dir} doesnt exist")
    for alias in targets_dir.glob("*/aliases"):
        skip_reason = set(alias.read_text().split("\n")) & to_skip
        if skip_reason:
            # print(f"Skipping {alias.parent.stem} because {skip_reason}")
            continue
        yield alias.parent.stem


@validate_arguments
def aws_periodical_jobs(amazon_aws_repo_dir: Path) -> None:
    jobs = [
        JobMapping(
            job=AWSWorkerJob.from_target_name(
                collection="amazon.aws",
                name=f"integration-amazon.aws-target-{target}",
                nodeset="container-ansible",
                target=target,
            )
        )
        for target in sorted(list(list_targets(amazon_aws_repo_dir)))
    ]

    build_ansible_collection = {
        "build-ansible-collection": {
            "required-projects": [
                RequiredProject(name="github.com/ansible-collections/amazon.aws"),
                RequiredProject(name="github.com/ansible-collections/ansible.utils"),
                RequiredProject(
                    name="github.com/ansible-collections/ansible.netcommon"
                ),
                RequiredProject(name="github.com/ansible-collections/community.aws"),
                RequiredProject(
                    name="github.com/ansible-collections/community.general"
                ),
                RequiredProject(name="github.com/ansible-collections/community.crypto"),
            ]
        }
    }

    project_template = ProjectTemplate(
        name="ansible-collections-amazon-aws-each-target",
        # we actually depend on ansible-test-splitter, but
        # it's listed in ansible-test-cloud-integration-aws
        #  dependency list
        periodic=Queue(
            jobs=[build_ansible_collection] + [job.job.name for job in jobs],
            queue="integrated-aws",
        ),
    )

    zuul_config_file = Path("zuul.d/amazon-aws-periodical-jobs.yaml")
    print(f"## Refreshing {zuul_config_file}")
    zuul_config = jobs + [
        ProjectTemplateMapping(**{"project-template": project_template})
    ]
    write_config(zuul_config_file, MappingList(__root__=zuul_config))


class AWSWorkerJob(Job):
    parent = "ansible-core-ci-aws-session"
    nodeset = NodesetName(__root__="fedora-36-1vcpu")
    dependencies: list[JobDependency] = [
        JobDependency(name="build-ansible-collection"),
    ]
    pre_run: ZuulMaybeList = Field(
        [
            "playbooks/ansible-test-base/pre.yaml",
            "playbooks/ansible-cloud/aws/pre.yaml",
        ],
        alias="pre-run",
    )

    run = ZuulMaybeList("playbooks/ansible-test-base/run.yaml")

    files = ["^plugins/.*$", "^tests/integration/.*$"]
    required_projects: list[RequiredProject] = Field(
        [
            RequiredProject(
                **{
                    "name": "github.com/ansible/ansible",
                    "override-checkout": "milestone",
                }
            ),
            RequiredProject(
                **{"name": "github.com/ansible-collections/community.aws"},
            ),
        ],
        alias="required-projects",
    )

    vars = {
        "ansible_test_command": "integration",
        "ansible_test_python": 3.9,
        "ansible_test_retry_on_error": True,
        "ansible_test_requirement_files": [
            "requirements.txt",
            "test-requirements.txt",
            "tests/integration/requirements.txt",
        ],
        "ansible_test_constraint_files": ["tests/integration/constraints.txt"],
    }
    semaphore = "ansible-test-cloud-integration-aws"

    @classmethod
    def from_target_name(cls, collection: str, target: str, **kwargs) -> "Job":
        new_instance = cls(**kwargs)
        new_instance.vars["ansible_test_integration_targets"] = target
        new_instance.vars[
            "ansible_collections_repo"
        ] = f"github.com/ansible-collections/{ collection }"
        return new_instance


@validate_arguments
def build_aws_worker(collection: str, idx: int) -> Job:
    new = AWSWorkerJob.from_target_name(
        name=f"integration-{collection}-{idx+1}",
        collection=collection,
        target="{{ child.targets_to_test[zuul.job] }}",
    )
    new.dependencies.append(JobDependency(name="ansible-test-splitter"))
    return new


def aws_integration_jobs(number_of_workers: int):
    amazon_aws_worker_jobs = [
        build_aws_worker("amazon.aws", idx) for idx in range(number_of_workers)
    ]
    community_aws_workder_jobs = [
        build_aws_worker("community.aws", idx) for idx in range(number_of_workers)
    ]

    build_ansible_collection = {
        "build-ansible-collection": {
            "required-projects": [
                RequiredProject(name="github.com/ansible-collections/ansible.utils"),
                RequiredProject(name="github.com/ansible-collections/amazon.aws"),
                RequiredProject(
                    name="github.com/ansible-collections/ansible.netcommon"
                ),
                RequiredProject(name="github.com/ansible-collections/community.aws"),
                RequiredProject(
                    name="github.com/ansible-collections/community.general"
                ),
                RequiredProject(name="github.com/ansible-collections/community.crypto"),
            ]
        }
    }

    @validate_arguments
    def ansible_test_splitter(collections: list[str], only_test_changed: bool = True):
        ansible_test_splitter__check_for_changes_in = [
            f"~/{{{{ zuul.projects['github.com/ansible-collections/{ c }'].src_dir }}}}"
            for c in sorted(collections)
        ]

        return {
            "ansible-test-splitter": {
                "required-projects": [
                    RequiredProject(name=f"github.com/ansible-collections/{ c }")
                    for c in sorted(collections)
                ],
                "vars": {
                    "ansible_test_splitter__test_changed": only_test_changed,
                    "ansible_test_splitter__check_for_changes_in": ansible_test_splitter__check_for_changes_in,
                    "ansible_test_splitter__total_job": number_of_workers,
                },
            }
        }

    worker_jobs = amazon_aws_worker_jobs + community_aws_workder_jobs
    amazon_aws_project_template = ProjectTemplate(
        name="ansible-collections-amazon-aws-integration",
        # we actually depend on ansible-test-splitter, but
        # it's listed in ansible-test-cloud-integration-aws
        #  dependency list
        check=Queue(
            jobs=[
                build_ansible_collection,
                ansible_test_splitter(collections=["community.aws", "amazon.aws"]),
            ]
            + [job.name for job in worker_jobs],
            queue="integrated-aws",
        ),
        gate=Queue(
            jobs=[
                build_ansible_collection,
                ansible_test_splitter(collections=["community.aws", "amazon.aws"]),
            ]
            + [job.name for job in worker_jobs],
            queue="integrated-aws",
        ),
        ondemand=Queue(
            jobs=[
                build_ansible_collection,
                ansible_test_splitter(
                    collections=["community.aws", "amazon.aws"], only_test_changed=False
                ),
            ]
            + [job.name for job in worker_jobs],
            queue="integrated-aws",
        ),
    )

    community_aws_project_template = ProjectTemplate(
        name="ansible-collections-community-aws-integration",
        # we actually depend on ansible-test-splitter, but
        # it's listed in ansible-test-cloud-integration-aws
        #  dependency list
        check=Queue(
            jobs=[
                build_ansible_collection,
                ansible_test_splitter(collections=["community.aws", "amazon.aws"]),
            ]
            + [job.name for job in community_aws_workder_jobs],
            queue="integrated-aws",
        ),
        gate=Queue(
            jobs=[
                build_ansible_collection,
                ansible_test_splitter(collections=["community.aws", "amazon.aws"]),
            ]
            + [job.name for job in community_aws_workder_jobs],
            queue="integrated-aws",
        ),
        ondemand=Queue(
            jobs=[
                build_ansible_collection,
                ansible_test_splitter(
                    only_test_changed=False, collections=["community.aws", "amazon.aws"]
                ),
            ]
            + [job.name for job in community_aws_workder_jobs],
            queue="integrated-aws",
        ),
    )
    zuul_config = MappingList(
        __root__=[JobMapping(job=job) for job in worker_jobs]
        + [
            ProjectTemplateMapping(**{"project-template": amazon_aws_project_template}),
            ProjectTemplateMapping(
                **{"project-template": community_aws_project_template}
            ),
        ]
    )
    zuul_config_file = Path("zuul.d/aws-integration-worker-jobs.yaml")
    print(f"## Updating the AWS worker jobs in {zuul_config_file}")
    write_config(zuul_config_file, zuul_config)


@validate_arguments
def find_base_playbooks(cur_dir: Path) -> Iterator[Path]:
    return cur_dir.glob("*/*.yaml")


def has_been_run_recently(job_name):
    r = requests.get(
        f"https://ansible.softwarefactory-project.io/zuul/api/builds?complete=true&job_name={job_name}&skip=0&limit=1&result=SUCCESS"
    )
    result = r.json()
    if not result:
        return False
    end_time = datetime.fromisoformat(result[0]["end_time"])
    return bool(end_time + timedelta(days=365) > datetime.now())


def list_unused_jobs() -> bool:
    raw_list = []
    zuul_d_path = Path("zuul.d")
    for zuul_d_config_file in zuul_d_path.glob("*.yaml"):
        yaml = YAML(typ="safe", pure=True)
        # print(f"Loading {zuul_d_config_file}")
        raw_list += yaml.load(zuul_d_config_file)
    zuul_config = MappingList(__root__=raw_list)
    jobs = [
        mapping.job
        for mapping in zuul_config.__root__
        if isinstance(mapping, JobMapping)
    ]

    print("  Pooling the status of all the jobs (slow)")
    jobs_run_recently = [job for job in jobs if has_been_run_recently(job.name)]

    jobs_to_keep = jobs_run_recently

    def get_job_by_name(name):
        for job in jobs:
            if job.name == name:
                return job

    def list_parents(job):
        while job := get_job_by_name(job.parent):
            yield job

    for job in jobs_run_recently:
        for parent in list_parents(job):
            if parent not in jobs_to_keep:
                jobs_to_keep.append(parent)

    jobs_to_remove = [j for j in jobs if j not in jobs_to_keep]
    print("## The following jobs have never been run during the last 365 days.")
    for job in jobs_to_remove:
        print(f"- {job.name}")
    return not bool(jobs_to_remove)


def unused_roles() -> bool:
    raw_list = []
    yaml = YAML(typ="safe", pure=True)
    for p in Path("playbooks").glob("**/*.yaml"):
        raw_list += yaml.load(p)

    def get_name_arg(item: dict) -> str:
        my_parameter = item.get("import_role") or item.get("include_role")
        if isinstance(my_parameter, str):
            # inline parameter
            for param in my_parameter.split(" "):
                k, v = param.split("=")
                if k == "name":
                    return v
        else:
            return my_parameter["name"]

    def walker(item: Any) -> Iterator[str]:
        if isinstance(item, list):
            for i in item:
                yield from walker(i)
        elif isinstance(item, dict):
            if "include_role" in item:
                yield get_name_arg(item)
            elif "import_role" in item:
                yield get_name_arg(item)
            else:
                yield from walker(list(item.values()))

    roles_in_use = sorted(set(list(walker(raw_list))))
    for role_name in roles_in_use:
        for p in Path(f"roles/{role_name}").glob("**/*.yaml"):
            for more_role_name in walker(yaml.load(p)):
                roles_in_use.append(more_role_name)

    roles_never_used = []
    for p in [x for x in Path("roles").iterdir() if x.is_dir()]:
        if p.stem in roles_in_use:
            continue
        roles_never_used.append(p.stem)

    if roles_never_used:
        print(
            "## The following roles from roles/ directory are not used by any playbooks"
        )
        for role in roles_never_used:
            print(f"- {role}")
    return bool(roles_never_used)


def never_called_playbooks() -> bool:
    raw_list = []
    zuul_d_path = Path("zuul.d")
    for zuul_d_config_file in zuul_d_path.glob("*.yaml"):
        yaml = YAML(typ="safe", pure=True)
        try:
            raw_list += yaml.load(zuul_d_config_file)
        except ruamel.yaml.constructor.ConstructorError:
            # Happen because of the secrets and the associated
            # !encrypted/pkcs1-oaep blocks
            # To remove later
            pass
    raw_list = [i for i in raw_list if "pipeline" not in i]
    for i in raw_list:
        MappingList(__root__=[i])
    zuul_config = MappingList(__root__=raw_list)
    jobs = [
        mapping.job
        for mapping in zuul_config.__root__
        if isinstance(mapping, JobMapping)
    ]

    playbooks = list(find_base_playbooks(Path("playbooks")))
    for job in jobs:
        commands = [
            Path(c)
            for c in (job.pre_run or []) + (job.run or []) + (job.post_run or [])
        ]
        playbooks = [p for p in playbooks if p not in commands]

    print("## None of the following playbook are called directly by any jobs:")
    for p in sorted(playbooks):
        print(f"- {p}")
    return bool(playbooks)


if __name__ == "__main__":
    exit_failure = False
    match args.function_name:
        case "refresh":
            aws_periodical_jobs(args.amazon_aws_repo_dir)
            aws_integration_jobs(number_of_workers=22)
        case "refresh-aws-periodical-jobs":
            aws_periodical_jobs(args.amazon_aws_repo_dir)
        case "refresh-aws-integration-jobs":
            aws_integration_jobs(number_of_workers=22)
        case "check_slow":
            exit_failure |= list_unused_jobs()
        case "check":
            exit_failure |= unused_roles()
            exit_failure |= never_called_playbooks()
    if exit_failure:
        print("Test failure...")
        exit(1)
