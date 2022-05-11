#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2022, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: wait_cluster_readiness
short_description: Wait for Openshift cluster
author:
  - Aubin Bikouo (@abikouo)
requirements:
  - "oc"
description:
  - Wait for Openshift cluster installation to complete
options:
  binary_path:
    description:
      - Path to the oc executable.
    type: path
    required: true
  kubeconfig:
    description:
      - Path to the kubeconfig file allowing access to the cluster.
    type: path
    required: true
"""

EXAMPLES = r"""
"""

RETURN = r"""
"""


from ansible.module_utils.basic import AnsibleModule
import json


def test_cluster_readiness(module):
    cmd = [module.params.get("binary_path"), "get", "clusterversion", "-o", "json"]
    rc, out, err = module.run_command(cmd, environ_update=dict(KUBECONFIG=module.params.get("kubeconfig")))
    if rc != 0:
        return False, err
    result = json.loads(out)["items"][0]
    history = result["status"]["history"][0]
    if history.get("state") == "Completed":
        return True, "Installation completed"
    else:
        return False, "".join([x["message"] for x in result["status"]["conditions"] if x["type"] == "Progressing"])


def main():
    module = AnsibleModule(
        argument_spec=dict(
            kubeconfig=dict(type="path", required=True),
            binary_path=dict(type="path", required=True),
        ),
    )

    completed, msg = test_cluster_readiness(module)
    module.exit_json(completed=completed, msg=msg)


if __name__ == "__main__":
    main()
