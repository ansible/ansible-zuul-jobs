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
    default=18,
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


def parse_args(raw_args):
    return parser.parse_args(raw_args)


def read_collection_name(path):
    with (path / "galaxy.yml").open() as fd:
        content = yaml.safe_load(fd)
        return f'{content["namespace"]}.{content["name"]}'


def list_pyimport(prefix, subdir, module_content):
    root = ast.parse(module_content)
    for node in ast.walk(root):
        if isinstance(node, ast.Import):
            yield node.names[0].name
        elif isinstance(node, ast.ImportFrom):
            module = node.module.split(".")
            if node.level == 1:
                current_prefix = f"{prefix}{subdir}."
            elif node.level == 2:
                current_prefix = f"{prefix}"
            else:
                current_prefix = ""
            full_path = f"{current_prefix}{'.'.join(module)}"
            yield full_path
            # ensure we also catch any modules being imported using "from x.y import z"
            for name in node.names:
                yield f"{full_path}.{name.name}"


def build_import_tree(collection_path, collection_name, collections_names):
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
    all_prefixes = [f"ansible_collections.{n}.plugins." for n in collections_names]
    utils_to_visit = []
    for mod in collection_path.glob("plugins/modules/*"):
        for i in list_pyimport(prefix, "modules", mod.read_text()):
            if (
                any(i.startswith(p) for p in all_prefixes)
                and i not in modules_import[mod.stem]
            ):
                modules_import[mod.stem].append(i)
                if i not in utils_to_visit:
                    utils_to_visit.append(i)

    inventories_import = defaultdict(list)
    prefix = f"ansible_collections.{collection_name}.plugins."
    all_prefixes = [f"ansible_collections.{n}.plugins." for n in collections_names]
    utils_to_visit = []
    for mod in collection_path.glob("plugins/inventory/*"):
        for i in list_pyimport(prefix, "inventory", mod.read_text()):
            if (
                any(i.startswith(p) for p in all_prefixes)
                and i not in inventories_import[mod.stem]
            ):
                inventories_import[mod.stem].append(i)
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
            for i in list_pyimport(prefix, "module_utils", utils_path.read_text()):
                if i.startswith(prefix) and i not in utils_import[utils]:
                    utils_import[utils].append(i)
                    if i not in visited:
                        utils_to_visit.append(i)
        except:
            pass
    return modules_import, utils_import, inventories_import


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

    def targets(self):
        """List the test targets impacted by the change"""
        for d in self.changed_files():
            if str(d).startswith("tests/integration/targets/"):
                # These are a special case, we only care that 'something' changed in that test
                yield str(d).replace("tests/integration/targets/", "").split(
                    "/", maxsplit=1
                )[0]

    def _path_matches(self, base_path):
        # Simplest case, just a file name
        for d in self.changed_files():
            if str(d).startswith(base_path):
                yield PosixPath(d)

    def connection(self):
        """List the connection plugins impacted by the change"""
        yield from self._path_matches("plugins/connection/")

    def inventory(self):
        """List the inventory plugins impacted by the change"""
        yield from self._path_matches("plugins/inventory/")

    def lookup(self):
        """List the lookup plugins impacted by the change"""
        yield from self._path_matches("plugins/lookup/")

    def modules(self):
        """List the modules impacted by the change"""
        yield from self._path_matches("plugins/modules/")

    def _util_matches(self, base_path, import_path):
        # We care about the file, but we also need to find what potential side effects would be for
        # our change
        base_path = PosixPath(base_path)
        for d in self.changed_files():
            try:
                relative_path = d.relative_to(base_path)
                parts = [*relative_path.parts[:-1]]
                if d.stem != "__init__":
                    parts.append(d.stem)
                relative_module = ".".join(parts)
                yield (
                    PosixPath(d),
                    f"ansible_collections.{self.collection_name()}.plugins.{import_path}.{relative_module}",
                    relative_module,
                )
            except ValueError:
                pass

    def module_utils(self):
        """List the Python modules impacted by the change"""
        yield from self._util_matches("plugins/module_utils/", "module_utils")

    def plugin_utils(self):
        """List the Python modules impacted by the change"""
        yield from self._util_matches("plugins/plugin_utils/", "plugin_utils")


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
        # NOTE: Should be replaced by time=3000
        if "slow" in self.lines or "# reason: slow" in self.lines:
            return True
        return False

    def is_ignored(self):
        """Show the target be ignored by default?"""
        ignore = set(["unsupported", "disabled", "unstable", "hidden"])
        return not ignore.isdisjoint(set(self.lines))

    def execution_time(self):
        if self.exec_time:
            return self.exec_time

        self.exec_time = 3000 if self.is_slow() else 180
        for u in self.lines:
            if m := re.match(r"^time=([0-9]+)s\S*$", u):
                self.exec_time = int(m.group(1))
            elif m := re.match(r"^time=([0-9]+)m\S*$", u):
                self.exec_time = int(m.group(1)) * 60
            elif m := re.match(r"^time=([0-9]+)\S*$", u):
                self.exec_time = int(m.group(1))

        return self.exec_time


class Collection:
    def __init__(self, path):
        self.collection_path = path
        self._my_test_plan = []
        self.collection_name = lambda: read_collection_name(path)
        self.modules_import = None
        self.utils_import = None
        self.inventories_import = None
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

    def add_target_to_plan(self, target_name, is_direct=True):
        if not self._is_target_already_added(target_name):
            for t in self._targets():
                if t.is_disabled():
                    continue
                # For indirect targets we want to skip "ignored" tests
                if not is_direct and t.is_ignored():
                    continue
                if t.is_alias_of(target_name):
                    self._my_test_plan.append(t)

    def cover_all(self):
        """Cover all the targets available."""
        for t in self._targets():
            self.add_target_to_plan(t.name, is_direct=False)

    def cover_module_utils(self, pymod, collections_names):
        """Track the targets to run follow up to a module_utils changed."""
        if (
            self.modules_import is None
            or self.utils_import is None
            or self.inventories_import is None
        ):
            (
                self.modules_import,
                self.utils_import,
                self.inventories_import,
            ) = build_import_tree(
                self.collection_path, self.collection_name(), collections_names
            )

        u_candidates = [pymod]
        for u in self.utils_import:
            # add as candidates all module_utils which include this module_utils
            if pymod in self.utils_import.get(u):
                u_candidates.append(u)

        for mod in self.modules_import:
            intersect = [x for x in u_candidates if x in self.modules_import.get(mod)]
            if intersect:
                self.add_target_to_plan(mod, is_direct=False)

        for inv in self.inventories_import:
            intersect = [
                x for x in u_candidates if x in self.inventories_import.get(inv)
            ]
            if intersect:
                c.add_target_to_plan(f"inventory_{inv}")

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
        self.targets_per_slot = 10
        self.releases = ansible_releases

    def output(self, changes):
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
                for b in self.build_up_batches(slots, c):
                    batches.append(b)
        result = self.build_result_struct(batches)
        # add collection imports
        result["imports"] = {}
        for c in self.collections:
            result["imports"][c.collection_name()] = {
                "modules": c.modules_import,
                "utils": c.utils_import,
                "inventories": c.inventories_import,
            }
        result["what_have_changes"] = changes
        print(json.dumps(result, indent=2))

    def build_up_batches(self, slots, c):
        if c.test_groups is None:
            sorted_targets = sorted(
                c._my_test_plan, key=lambda x: x.execution_time(), reverse=True
            )
            c.test_groups = [{"total": 0, "targets": []} for _ in range(len(slots))]
            c.test_groups = split_into_equally_sized_chunks(sorted_targets, len(slots))

            # def _selector(bet):
            #     for idx, cur_group in enumerate(c.test_groups):
            #         if cur_group["total"] > 46 * 60:
            #             continue
            #         if cur_group["total"] + bet.execution_time() > 50 * 60:
            #             continue
            #         return idx
            #     else:
            #         raise ValueError("Not enough slots available!")

            # for t in sorted_targets:
            #     at = _selector(t)
            #     c.test_groups[at]["total"] += t.execution_time()
            #     c.test_groups[at]["targets"].append(t.name)

        for group in c.test_groups:
            if group["targets"] == []:
                continue
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


def split_into_equally_sized_chunks(targets, nbchunks):
    total_time = sum(x.execution_time() for x in targets)
    time_per_chunk = int(total_time / nbchunks) + 1
    chunks = [{"total": 0, "targets": []} for _ in range(nbchunks)]

    def _findslot(t):
        if t.execution_time() >= time_per_chunk:
            # find first slot with total_time=0
            for i, d in enumerate(chunks):
                if d["total"] == 0:
                    return i
        else:
            # find the appropriate slot
            for i, d in enumerate(chunks):
                if t.execution_time() + d["total"] <= time_per_chunk:
                    return i
        return 0

    for t in targets:
        at = _findslot(t)
        chunks[at]["total"] += t.execution_time()
        chunks[at]["targets"].append(t.name)
    return chunks


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    collections = [Collection(i) for i in args.collection_to_tests]
    collections_names = [c.collection_name() for c in collections]

    changes = {}
    if args.test_all_the_targets:
        for c in collections:
            c.cover_all()
    else:
        for whc in [WhatHaveChanged(i, args.branch) for i in args.collection_to_tests]:
            changes[whc.collection_name()] = {
                "modules": [],
                "inventory": [],
                "connection": [],
                "module_utils": [],
                "plugin_utils": [],
                "lookup": [],
                "targets": [],
            }
            for path in whc.modules():
                changes[whc.collection_name()]["modules"].append(path.stem)
                for c in collections:
                    c.add_target_to_plan(path.stem)
            for path in whc.inventory():
                changes[whc.collection_name()]["inventory"].append(path.stem)
                for c in collections:
                    c.add_target_to_plan(f"inventory_{path.stem}")
            for path in whc.connection():
                changes[whc.collection_name()]["connection"].append(path.stem)
                for c in collections:
                    c.add_target_to_plan(f"connection_{path.stem}")
            for path, pymod, stem in whc.module_utils():
                changes[whc.collection_name()]["module_utils"].append(stem)
                for c in collections:
                    c.add_target_to_plan(f"module_utils_{stem.replace('.', '_')}")
                    c.cover_module_utils(pymod, collections_names)
            for path, pymodi, stem in whc.plugin_utils():
                changes[whc.collection_name()]["plugin_utils"].append(stem)
                for c in collections:
                    c.add_target_to_plan(f"plugin_utils_{stem.replace('.', '_')}")
                    c.cover_module_utils(pymodi, collections_names)
            for path in whc.lookup():
                changes[whc.collection_name()]["lookup"].append(path.stem)
                for c in collections:
                    c.add_target_to_plan(f"lookup_{path.stem}")
            for t in whc.targets():
                changes[whc.collection_name()]["targets"].append(t)
                for c in collections:
                    c.add_target_to_plan(t)

    egs = ElGrandeSeparator(collections, args.total_job, args.ansible_releases)
    egs.output(changes)
