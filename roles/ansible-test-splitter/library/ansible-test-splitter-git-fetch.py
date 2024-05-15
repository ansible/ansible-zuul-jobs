#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2022, Aubin Bikouo <@abikouo>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""

module: ansible-test-splitter-git-fetch

short_description: Fetch repository tree.

author:
    - "Aubin Bikouo (@abikouo)"

description:
  - Run `git fetch` on repositories where the splitter will be executed in order to have to full branches locally.

options:
  paths:
    description:
    - The list of directories.
    type: list
    elements: str
    required: true
"""

EXAMPLES = r"""
"""

RETURN = r"""
"""

import os

from ansible.module_utils.basic import AnsibleModule


class AnsibleTestSplitterGitFetch(AnsibleModule):

    def __init__(self):

        argument_spec=dict(
            paths=dict(type="list", elements="str", required=True),
        )
        super(AnsibleTestSplitterGitFetch, self).__init__(argument_spec=argument_spec)

        self.git_path = self.get_bin_path("git", required=True)
        self.execute_module()

    def gitfetch(self, path: str) -> None:
        cmd = "git fetch --no-tags --progress --depth=1 origin"
        rc, stdout, stderr = self.run_command(cmd, cwd=os.path.join('~/', path))
        if rc != 0:
            self.fail_json(msg=stderr, stdout=stdout, rc=rc)

    def execute_module(self) -> None:
        changed = False
        for path in self.params.get("paths"):
            self.gitfetch(path)
            changed = True

        self.exit_json(changed=changed)


def main():

    AnsibleTestSplitterGitFetch()


if __name__ == "__main__":
    main()
