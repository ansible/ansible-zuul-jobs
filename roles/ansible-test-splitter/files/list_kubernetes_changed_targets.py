#!/usr/bin/env python3

import argparse
import json
from pathlib import PosixPath
import sys
import subprocess
import yaml
import os

parser = argparse.ArgumentParser(
    description="Evaluate which targets need to be tested."
)
parser.add_argument(
    "--branch", type=str, default="main", help="the default branch to test against"
)

parser.add_argument(
    "--test-all-the-targets",
    dest="test_all_the_targets",
    action="store_true",
    default=False,
    help="list all the target available in the the collection",
)

parser.add_argument(
    "--test-changed",
    dest="test_changed",
    action="store_true",
    default=False,
    help=("only test the targets impacted by the changes"),
)

parser.add_argument(
    "--number-job",
    default=3,
    type=int,
    help="number of job",
)

parser.add_argument(
    "--release",
    nargs="+",
    default=["devel", "milestone", "2.9", "2.10", "with-turbo"],
    help="release version to test on generated jobs",
)

parser.add_argument(
    "collection_to_test",
    default=os.getcwd(),
    nargs="?",
    type=PosixPath,
    help="the location of the collections to test. e.g: ~/.ansible/collections/ansible_collections/kubernetes/core",
)

targets_to_test = []
targets_dir = PosixPath("tests/integration/targets")


def parse_args(raw_args):
    return parser.parse_args(raw_args)


def read_collection_name(path):
    with (path / "galaxy.yml").open() as fd:
        content = yaml.safe_load(fd)
        return f'{content["namespace"]}.{content["name"]}'


class WhatHaveChanged:
    def __init__(self, path, branch):
        assert isinstance(path, PosixPath)
        self.collection_path = path
        self.branch = branch
        self.files = None

    def changed_files(self):
        """List of changed files

        Returns a list of pathlib.PosixPath
        """
        if self.files is None:
            self.files = [
                PosixPath(p)
                for p in (
                    subprocess.check_output(
                        [
                            "git",
                            "diff",
                            f"origin/{self.branch}",
                            "--name-only",
                        ],
                        cwd=self.collection_path,
                    )
                    .decode()
                    .split("\n")
                )
            ]
        return self.files

    def modules(self):
        """List the modules plugins impacted by the change"""
        for d in self.changed_files():
            if str(d).startswith("plugins/modules/"):
                yield PosixPath(d)

    def inventory(self):
        """List the inventory plugins impacted by the change"""
        for d in self.changed_files():
            if str(d).startswith("plugins/inventory/"):
                yield PosixPath(d)

    def lookup(self):
        """List the lookup plugins impacted by the change"""
        for d in self.changed_files():
            if str(d).startswith("plugins/lookup/"):
                yield PosixPath(d)

    def targets(self):
        """List the test targets impacted by the change"""
        targets = []
        for d in self.changed_files():
            if str(d).startswith("tests/integration/targets/"):
                t = str(d).replace("tests/integration/targets/", "").split("/")[0]
                if t not in targets:
                    targets.append(t)
        return targets

    def common(self):
        """
        return true is any module_utils (other than helm) or the following module: k8s, k8s_info
        are impacted by the change
        """
        file_path = [
            "plugins/module_utils/",
            "plugins/doc_fragments/",
            "plugins/action/",
        ]
        for d in self.changed_files():
            if any([str(d).startswith(x) for x in file_path]) and not d.stem.startswith(
                "helm"
            ):
                return True
        return False

    def helm(self):
        """
        Return true if any helm file (modules, module_utils, doc_fragments, action)
        is impacted by the change
        """
        file_path = [
            "plugins/modules/",
            "plugins/module_utils/",
            "plugins/doc_fragments/",
            "plugins/action/",
        ]
        for d in self.changed_files():
            if any([str(d).startswith(x) for x in file_path]) and d.stem.startswith(
                "helm"
            ):
                return True
        return False


class Target:
    def __init__(self, path):
        self.path = path
        self.lines = [l.split("#")[0] for l in path.read_text().split("\n") if l]
        self.name = path.parent.name

    def is_alias_of(self, name):
        return name in self.lines or self.name == name

    def is_disabled(self):
        if "disabled" in self.lines:
            return True
        return False

    def is_slow(self):
        if "slow" in self.lines or "# reason: slow" in self.lines:
            return True
        return False

    def is_ignored(self):
        """Show the target be ignored by default?"""
        ignore = set(["unsupported", "disabled", "unstable", "hidden"])
        return not ignore.isdisjoint(set(self.lines))


class Collection:
    def __init__(self, path):
        self.collection_path = path
        self._my_test_plan = []
        self.collection_name = read_collection_name(path)

        self.timers = {}
        timer_file = PosixPath(path / "tests/integration/timer.json")
        if timer_file.exists():
            with timer_file.open() as fd:
                self.timers = json.loads(fd.read())

    def _targets(self):
        for a in self.collection_path.glob("tests/integration/targets/*/aliases"):
            yield Target(a)

    def add_target_to_plan(self, target_name):
        for t in self._targets():
            if t.is_disabled():
                continue
            if t.is_alias_of(target_name):
                self._my_test_plan.append(t)

    def cover_all(self):
        """Cover all the targets available."""
        for t in self._targets():
            if t.is_ignored():
                continue
            self.add_target_to_plan(t.name)

    def add_target_for_module(self, k8smod):
        """Track the targets to run follow up to a module changed."""
        self.add_target_to_plan(f"module/{k8smod}")

    def split_target_per_jobs(self, nb_jobs, releases):
        if len(self._my_test_plan) == 0:
            self.cover_all()

        targets = [(t.name, self.timers.get(t.name, 0)) for t in self._my_test_plan]
        sorted_targets = sorted(targets, key=lambda x: x[1], reverse=True)

        slots = [{"total": 0, "targets": []} for _ in range(nb_jobs)]

        def _get_index_lowest():
            lowest = 0
            idx = 1
            while idx < len(slots):
                if slots[idx]["total"] < slots[lowest]["total"]:
                    lowest = idx
                idx += 1
            return lowest

        for t in sorted_targets:
            insert_at = _get_index_lowest()
            slots[insert_at]["total"] += t[1]
            slots[insert_at]["targets"].append(t[0])

        # build result
        result = {
            "data": {
                "zuul": {"child_jobs": []},
                "child": {"targets_to_test": {}},
            }
        }

        for rel in releases:
            job_name = "ansible-test-kubernetes-core-%s" % rel
            result["data"]["zuul"]["child_jobs"].append(job_name)
            result["data"]["child"]["targets_to_test"][job_name] = [
                " ".join(s["targets"]) for s in slots
            ]
        return result


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    collection = Collection(args.collection_to_test)

    if args.test_all_the_targets:
        collection.cover_all()
    else:
        whc = WhatHaveChanged(args.collection_to_test, args.branch)
        if whc.common():
            collection.cover_all()
        else:
            for path in whc.modules():
                collection.add_target_for_module(path.stem.replace(".py", ""))
            for path in whc.inventory():
                collection.add_target_to_plan(f"inventory_{path.stem}")
            for path in whc.lookup():
                collection.add_target_to_plan(f"lookup_{path.stem}")
            for t in whc.targets():
                collection.add_target_to_plan(t)
            if whc.helm():
                collection.add_target_to_plan("helm")

    result = collection.split_target_per_jobs(args.number_job, args.release)
    print(json.dumps(result))
