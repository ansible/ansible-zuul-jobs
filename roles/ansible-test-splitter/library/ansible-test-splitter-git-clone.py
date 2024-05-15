#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2022, Aubin Bikouo <@abikouo>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""

module: ansible-test-splitter-git-clone

short_description: clone repositories using the full tree.

author:
    - "Aubin Bikouo (@abikouo)"

description:
  - This module will clone the repository and set the current branch to the expected checkout branch.
  - It uses both configuration from zuul.projects variable and ansible_test_splitter__check_for_changes_in configuration.

options:
  changes_src_dir:
    description:
    - The list of directories to check changes in.
    type: list
    elements: str
    required: true
  zuul_projects:
    description:
    - The list of zuul projects.
    type: dict
    required: true
  dest_dir:
    description:
    - The directory where to checkout repositories.
    type: str
    required: true
"""

EXAMPLES = r"""
"""

RETURN = r"""
"""

from typing import Dict
import os

from ansible.module_utils.basic import AnsibleModule


class AnsibleTestSplitterGitClone(AnsibleModule):

    def __init__(self):

        argument_spec=dict(
            changes_src_dir=dict(type="list", elements="str", required=True),
            zuul_projects=dict(type="dict", required=True),
            dest_dir=dict(type="str", required=True),
        )
        super(AnsibleTestSplitterGitClone, self).__init__(argument_spec=argument_spec)

        self.git_path = self.get_bin_path("git", required=True)
        self.execute_module()

    def checkout_repository(self, repo: Dict[str, str]) -> str:
        path = os.path.join(self.params.get("dest_dir"), repo["src_dir"])
        parent = os.path.dirname(path)
        # create parent directory
        os.makedirs(parent, exist_ok=True)

        # clone repository
        cmd = "git clone https://{0} {1}".format(repo["canonical_name"], os.path.basename(path))
        rc, stdout, stderr = self.run_command(cmd, cwd=parent)
        if rc != 0:
            self.fail_json(msg=stderr, stdout=stdout, rc=rc)

        # checkout expected branch
        cmd = "git checkout {0}".format(repo["checkout"])
        rc, stdout, stderr = self.run_command(cmd, cwd=path)
        if rc != 0:
            self.fail_json(msg=stderr, stdout=stdout, rc=rc)
        return path

    def execute_module(self) -> None:
        paths = []
        for src_d in self.params.get("changes_src_dir"):
            for key, val in self.params.get("zuul_projects").items():
                if val["src_dir"] == src_d:
                    paths.append(self.checkout_repository(val))

        self.exit_json(paths=" ".join(paths))


def main():

    AnsibleTestSplitterGitClone()


if __name__ == "__main__":
    main()
