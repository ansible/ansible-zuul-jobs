#!/usr/bin/env python3

import argparse
import ast
import json
from pathlib import PosixPath
import sys
import subprocess
import yaml


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


def list_pyimport(collection_name, module_content):
    root = ast.parse(module_content)
    for node in ast.iter_child_nodes(root):
        if isinstance(node, ast.Import):
            yield node.names[0].name
        elif isinstance(node, ast.ImportFrom):
            module = node.module.split(".")
            prefix = (
                f"ansible_collections.{collection_name}.plugins."
                if node.level == 2
                else ""
            )
            yield f"{prefix}{'.'.join(module)}"


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


class Target:
    def __init__(self, path):
        self.path = path
        self.lines = [l.split("#")[0] for l in path.read_text().split("\n") if l]
        self.name = path.parent.name

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


class Collection:
    def __init__(self, path):
        self.collection_path = path
        self._my_test_plan = []
        self.collection_name = lambda: read_collection_name(path)

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

    def cover_module_utils(self, pymod):
        """Track the targets to run follow up to a module_utils changed."""
        for m in self.collection_path.glob("plugins/modules/*"):
            for i in list_pyimport(self.collection_name(), m.read_text()):
                if pymod == i:
                    self.add_target_to_plan(m.stem)

    def slow_targets_to_test(self):
        return sorted(list(set([t.name for t in self._my_test_plan if t.is_slow()])))

    def regular_targets_to_test(self):
        return sorted(
            list(set([t.name for t in self._my_test_plan if not t.is_slow()]))
        )


class ElGrandeSeparator:
    def __init__(self, collections):
        self.collections = collections
        self.total_jobs = 13  # aka slot
        self.targets_per_slot = 14

    def output(self):
        batches = []
        for c in collections:
            slots = [
                f"integration-{c.collection_name()}-{i+1}"
                for i in range(self.total_jobs)
            ]
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

    egs = ElGrandeSeparator(collections)
    egs.output()
