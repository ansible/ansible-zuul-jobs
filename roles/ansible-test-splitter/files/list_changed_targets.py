#!/usr/bin/env python3

import argparse
import ast
import json
from pathlib import PosixPath
import sys
import subprocess
import yaml
import re
from collections import defaultdict


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
    "--total-job",
    default=13,
    type=int,
    help="total job to share targets on.",
)

parser.add_argument(
    "--ansible-releases",
    nargs="+",
    default=[],
    help="ansible release version to test for each jobs",
)

parser.add_argument(
    "collection_to_tests",
    default=[],
    nargs="+",
    type=PosixPath,
    help="the location of the collections to test. e.g: ~/.ansible/collections/ansible_collections/amazon/aws",
)

targets_to_test = []
targets_dir = PosixPath("tests/integration/targets")


def parse_args(raw_args):
    return parser.parse_args(raw_args)


def read_collection_name(path):
    with (path / "galaxy.yml").open() as fd:
        content = yaml.safe_load(fd)
        return f'{content["namespace"]}.{content["name"]}'


def list_pyimport(prefix, module_content):
    root = ast.parse(module_content)
    for node in ast.walk(root):
        if isinstance(node, ast.Import) and node.names[0].name.startswith(prefix):
            yield node.names[0].name
        elif isinstance(node, ast.ImportFrom):
            module = node.module.split(".")
            prefix = prefix if node.level == 2 else ""
            yield f"{prefix}{'.'.join(module)}"


def build_import_tree(collection_path, collection_name):
    """
    This function will generate import dependencies for the modules and the module_utils.
    Let say we have the following input:

        modules: ec2_mod1
            import a_py_mod
            import ansible.basic
        modules: ec2_mod2
            import another_py_mod
            import ansible_collections.amazon.aws.plugins.module_utils.core
        modules: ec2_mod3
            import ansible_collections.amazon.aws.plugins.module_utils.tagging
            import ansible_collections.amazon.aws.plugins.module_utils.waiters

        module_utils: waiters
            import some_py_mod
            import ansible_collections.amazon.aws.plugins.module_utils.core
        module_utils: tagging
            import some_py_tricky_mod
            import ansible_collections.amazon.aws.plugins.module_utils.core
        module_utils: core
            import some_py_fancy_mod

    This will generated the following dicts (list only import part of this collection):

    modules_imports
        {
            "ec2_mod1": [],
            "ec2_mod2": [
                "ansible_collections.amazon.aws.plugins.module_utils.core",
            ],
            "ec2_instance_info": [
                "ansible_collections.amazon.aws.plugins.module_utils.tagging",
                "ansible_collections.amazon.aws.plugins.module_utils.waiters"
            ],
        }

    utils_import
        {
            "ansible_collections.amazon.aws.plugins.module_utils.core": [
                "ansible_collections.amazon.aws.plugins.module_utils.waiters"
                "ansible_collections.amazon.aws.plugins.module_utils.tagging"
            ]
        }
    """
    modules_import = defaultdict(list)
    prefix = f"ansible_collections.{collection_name}.plugins."
    utils_to_visit = []
    for mod in collection_path.glob("plugins/modules/*"):
        for i in list_pyimport(prefix, mod.read_text()):
            if i.startswith(prefix) and i not in modules_import[mod.stem]:
                modules_import[mod.stem].append(i)
                if i not in utils_to_visit:
                    utils_to_visit.append(i)

    utils_import = defaultdict(list)
    visited = []
    while utils_to_visit:
        utils = utils_to_visit.pop()
        if utils in visited:
            continue
        visited.append(utils)
        try:
            utils_path = collection_path / PosixPath(
                utils.replace(f"ansible_collections.{collection_name}.", "").replace(
                    ".", "/"
                )
                + ".py"
            )
            for i in list_pyimport(prefix, utils_path.read_text()):
                if i.startswith(prefix) and utils not in utils_import[i]:
                    utils_import[i].append(utils)
                    if i not in visited:
                        utils_to_visit.append(i)
        except:
            pass
    return modules_import, utils_import


class WhatHaveChanged:
    def __init__(self, path, branch):
        assert isinstance(path, PosixPath)
        self.collection_path = path
        self.branch = branch
        self.collection_name = lambda: read_collection_name(path)
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
        """List the modules impacted by the change"""
        for d in self.changed_files():
            if str(d).startswith("plugins/modules/"):
                yield PosixPath(d)

    def inventory(self):
        """List the inventory plugins impacted by the change"""
        for d in self.changed_files():
            if str(d).startswith("plugins/inventory/"):
                yield PosixPath(d)

    def module_utils(self):
        """List the Python modules impacted by the change"""
        for d in self.changed_files():
            if str(d).startswith("plugins/module_utils/"):
                yield (
                    PosixPath(d),
                    f"ansible_collections.{self.collection_name()}.plugins.module_utils.{d.stem}",
                )

    def lookup(self):
        """List the lookup plugins impacted by the change"""
        for d in self.changed_files():
            if str(d).startswith("plugins/lookup/"):
                yield PosixPath(d)

    def targets(self):
        """List the test targets impacted by the change"""
        for d in self.changed_files():
            if str(d).startswith("tests/integration/targets/"):
                yield str(d).replace("tests/integration/targets/", "").split("/")[0]


class Target:
    def __init__(self, path):
        self.path = path
        self.lines = [l.split("#")[0] for l in path.read_text().split("\n") if l]
        self.name = path.parent.name
        self.exec_time = None

    def is_alias_of(self, name):
        return name in self.lines or self.name == name

    def is_unstable(self):
        if "unstable" in self.lines:
            return True
        return False

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

    def execution_time(self):
        if self.exec_time is None:
            self.exec_time = 0
            for u in self.lines:
                m = re.match(r"^time=([0-9]+)$", u)
                if m:
                    self.exec_time = int(m.group(1))
        return self.exec_time


class Collection:
    def __init__(self, path):
        self.collection_path = path
        self._my_test_plan = []
        self.collection_name = lambda: read_collection_name(path)
        self.modules_import = None
        self.utils_import = None
        self.test_groups = None

    def _targets(self):
        for a in self.collection_path.glob("tests/integration/targets/*/aliases"):
            yield Target(a)

    def _is_target_already_added(self, target_name):
        """Return true if the target is already part of the test plan"""
        for t in self._my_test_plan:
            if t.is_alias_of(target_name):
                return True
        return False

    def add_target_to_plan(self, target_name):
        if not self._is_target_already_added(target_name):
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

    def cover_module_utils(self, pymod):
        """Track the targets to run follow up to a module_utils changed."""
        if self.modules_import is None or self.utils_import is None:
            self.modules_import, self.utils_import = build_import_tree(
                self.collection_path, self.collection_name()
            )

        u_candidates = [pymod]
        for u in self.utils_import:
            # add as candidates all module_utils which include this module_utils
            if pymod in self.utils_import.get(u):
                u_candidates.append(u)

        for mod in self.modules_import:
            intersect = [x for x in u_candidates if x in self.modules_import.get(mod)]
            if intersect:
                self.add_target_to_plan(mod)

    def slow_targets_to_test(self):
        return sorted(list(set([t.name for t in self._my_test_plan if t.is_slow()])))

    def regular_targets_to_test(self):
        return sorted(
            list(set([t.name for t in self._my_test_plan if not t.is_slow()]))
        )


class ElGrandeSeparator:
    def __init__(self, collections, total_jobs=13, ansible_releases=[]):
        self.collections = collections
        self.total_jobs = total_jobs  # aka slot
        self.targets_per_slot = 20
        self.releases = ansible_releases

        total_targets = sum([len(c._my_test_plan) for c in self.collections])
        if total_targets == 0:
            # Worst case: no targets test found for any collection
            for c in self.collections:
                c.cover_all()

    def output(self):
        batches = []
        rels = [""]
        if self.releases:
            rels = self.releases
        for r in rels:
            for c in self.collections:
                job_prefix = (
                    f"integration-{c.collection_name()}"
                    if len(r) == 0
                    else f"integration-{c.collection_name()}-{r}"
                )
                slots = [f"{job_prefix}-{i+1}" for i in range(self.total_jobs)]
                if any([t.execution_time() > 0 for t in c._my_test_plan]):
                    for b in self.build_up_batches_by_time(slots, c):
                        batches.append(b)
                else:
                    for b in self.build_up_batches(slots, c):
                        batches.append(b)
        result = self.build_result_struct(batches)
        print(json.dumps(result))

    def build_up_batches(self, slots, c):
        slow_targets = c.slow_targets_to_test()
        regular_targets = c.regular_targets_to_test()
        my_slot_available = [s for s in slots]
        for i in slow_targets:
            my_slot = my_slot_available.pop(0)
            yield (my_slot, [i])

        while regular_targets:
            my_slot = my_slot_available.pop(0)
            yield (my_slot, regular_targets[0 : self.targets_per_slot])
            for _ in range(self.targets_per_slot):
                if regular_targets:
                    regular_targets.pop(0)

    def build_up_batches_by_time(self, slots, c):
        if c.test_groups is None:
            sorted_targets = sorted(
                c._my_test_plan, key=lambda x: x.execution_time(), reverse=True
            )
            c.test_groups = [{"total": 0, "targets": []} for _ in range(len(slots))]

            def _lowest():
                low = 0
                idx = 1
                while idx < len(c.test_groups):
                    if c.test_groups[idx]["total"] < c.test_groups[low]["total"]:
                        low = idx
                    idx += 1
                return low

            for t in sorted_targets:
                at = _lowest()
                c.test_groups[at]["total"] += t.execution_time()
                c.test_groups[at]["targets"].append(t.name)

        for group in c.test_groups:
            if group["targets"] == []:
                break
            my_slot = slots.pop(0)
            yield (my_slot, group["targets"])

    def build_result_struct(self, batches):
        result = {
            "data": {
                "zuul": {"child_jobs": []},
                "child": {"targets_to_test": {}},
            }
        }

        for job, targets in batches:
            result["data"]["zuul"]["child_jobs"].append(job)
            result["data"]["child"]["targets_to_test"][job] = " ".join(targets)
        return result


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    collections = [Collection(i) for i in args.collection_to_tests]

    if args.test_all_the_targets:
        for c in collections:
            c.cover_all()
    else:
        for whc in [WhatHaveChanged(i, args.branch) for i in args.collection_to_tests]:
            for path in whc.modules():
                for c in collections:
                    c.add_target_to_plan(path.stem)
            for path in whc.inventory():
                for c in collections:
                    c.add_target_to_plan(f"inventory_{path.stem}")
            for path, pymod in whc.module_utils():
                for c in collections:
                    c.add_target_to_plan(f"module_utils_{path.stem}")
                    c.cover_module_utils(pymod)
            for path in whc.lookup():
                for c in collections:
                    c.add_target_to_plan(f"lookup_{path.stem}")
            for t in whc.targets():
                for c in collections:
                    c.add_target_to_plan(t)

    egs = ElGrandeSeparator(collections, args.total_job, args.ansible_releases)
    egs.output()
