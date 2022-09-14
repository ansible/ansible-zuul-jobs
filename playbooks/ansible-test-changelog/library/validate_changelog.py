#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2022, Aubin Bikouo <@abikouo>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""

module: validate_changelog

short_description: Validate that a pull request contains changelog fragments when required.

author:
    - "Aubin Bikouo (@abikouo)"

description:
  - This module validates that each PR defines a valid changelog fragment as requested.
  - Refer to U(https://docs.ansible.com/ansible/latest/community/development_process.html#creating-changelog-fragments) for
    more information about changelog.

options:
  repository:
    description:
    - Path to git repository.
    type: str
    required: true
    aliases:
    - path
  branch:
    description:
    - the default branch to test against.
    type: str
    default: main
"""

EXAMPLES = r"""
- name: Test changelog against master branch
  validate_changelog:
    repository: path_to_the_repository
    branch: master
"""

RETURN = r"""
"""

import re
import os
from collections import defaultdict

from ansible.module_utils.basic import AnsibleModule
import yaml


def is_valid_change_log(ref):
    return re.match("^changelogs/fragments/(.*)\.(yaml|yml)$", ref)


def is_module_or_plugin(ref):
    prefix_list = (
        "plugins/modules",
        "plugins/action",
        "plugins/inventory",
        "plugins/lookup",
        "plugins/filter",
        "plugins/connection",
        "plugins/become",
        "plugins/cache",
        "plugins/callback",
        "plugins/cliconf",
        "plugins/httpapi",
        "plugins/netconf",
        "plugins/shell",
        "plugins/strategy",
        "plugins/terminal",
        "plugins/test",
        "plugins/vars",
    )
    return ref.startswith(prefix_list)


def is_documentation_file(ref):
    prefix_list = (
        "docs/",
        "plugins/doc_fragments",
    )
    return ref.startswith(prefix_list)


class ValidateChangeLog(AnsibleModule):

    def __init__(self):

        argument_spec=dict(
            repository=dict(type="path", required=True, aliases=["path"]),
            branch=dict(type="str", default="main"),
        )
        super(ValidateChangeLog, self).__init__(argument_spec=argument_spec)

        self.git_path = self.get_bin_path("git", required=True)
        self.execute_module()

    def list_files(self):
        cmd = "{0} diff origin/{1} --name-status".format(
            self.git_path,
            self.params.get("branch")
        )

        rc, stdout, stderr = self.run_command(cmd, cwd=self.params.get("repository"))
        if rc != 0:
            self.fail_json(msg=stderr, stdout=stdout, rc=rc)

        self.git_changes = defaultdict(list)
        for file in stdout.split("\n"):
            v = file.split("\t")
            if len(v) == 2:
                self.git_changes[v[0]].append(v[1])

    def is_added_module_or_plugin_or_documentation_changes(self):

        # Validate Pull request add new modules and plugins
        if any([is_module_or_plugin(x) for x in self.git_changes["A"]]):
            return True

        # Validate documentation changes only
        all_files = self.git_changes["A"] + self.git_changes["M"] + self.git_changes["D"]
        if all([is_documentation_file(x) for x in all_files]):
            return True

    def validate_changelog(self, path):

        try:
            # https://github.com/ansible-community/antsibull-changelog/blob/main/docs/changelogs.rst#changelog-fragment-categories
            changes_type = (
                "release_summary",
                "breaking_changes",
                "major_changes",
                "minor_changes",
                "removed_features",
                "deprecated_features",
                "security_fixes",
                "bugfixes",
                "known_issues",
                "trivial",
            )
            with open(path, "rb") as f:
                result = list(yaml.safe_load_all(f))

            for section in result:
                for key in section.keys():
                    if key not in changes_type:
                        self.fail_json(
                            msg="Unexpected changelog section {0} from file {1}".format(
                                key,
                                os.path.basename(path)
                            )
                        )
                    if not isinstance(section[key], list):
                        self.fail_json(
                            msg="Changelog section {0} from file {1} must be a list, {2} found instead.".format(
                                key,
                                os.path.basename(path),
                                type(section[key])
                            )
                        )
        except (IOError, yaml.YAMLError) as exc:
            self.fail(
                msg="Error loading changelog file {0}: {1}".format(
                    os.path.basename(path),
                    exc
                )
            )

    def execute_module(self):

        self.list_files()
        # self.exit_json(files=self.git_changes)
        self.changelog = [x for x in self.git_changes["A"] if is_valid_change_log(x)]
        if len(self.changelog) == 0:
            if not self.is_added_module_or_plugin_or_documentation_changes():
                self.fail_json(
                    msg="Missing changelog fragment. This is not required only if "\
                        "PR adds new modules and plugins or contain only documentation changes."
                )
            self.exit_json(
                msg="Changelog not required as PR adds new modules and/or plugins or "\
                    "contain only documentation changes."
            )

        for f in self.changelog:
            self.validate_changelog(os.path.join(self.params.get("repository"), f))

        self.exit_json(msg="Changelog validation successful.")


def main():

    ValidateChangeLog()

if __name__ == "__main__":
    main()
