#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2021, Aubin Bikouo <@abikouo>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function


__metaclass__ = type


DOCUMENTATION = r'''

module: molecule_splitter

short_description: Split molecule scenario to be executed on zuul jobs.

author:
    - "Aubin Bikouo (@abikouo)"

description:
  - Basically list jobs and distribute over the number of jobs to be executed.

options:
  path:
    description: 
    - Parent directory of the molecule directory.
    - Default is the current directory.
    type: path
  jobs:
    description:
    - Number of jobs to execute.
    type: int
    default: 4
  prefix:
    description:
    - Prefix of jobs to be activated.
    default: ansible-test-molecule
  ansible_release:
    description:
    - list of ansible version to test.
    type: list
'''

EXAMPLES = r'''
- name: Split molecule scenario on 3 jobs
  molecule_splitter:
    path: ~/.ansible/collections/ansible_collections/kubernetes/core
    jobs: 3
'''

RETURN = r'''
'''

from ansible.module_utils.basic import AnsibleModule
import os
import glob


def array_split(buffer, N):
    split = [[] for _ in range(N)]
    i = 0
    while buffer:
        u = buffer.pop()
        idx = i % N
        split[idx].append(u)
        i+=1
    return [" ".join(x) for x in split if x]


def execute_module(module):
    try:
        parent_dir = module.params.get('path')
        if not parent_dir:
            parent_dir = os.getcwd()
        jobs = module.params.get('jobs')
        if jobs == 0:
            module.fail_json(msg=f"argument jobs should be greater than 0.")

        molecule_path = os.path.join(parent_dir, "molecule")
        if not os.path.isdir(molecule_path):
            module.fail_json(msg=f"Missing molecule directory from parent dir: {parent_dir}")
        

        # list all valid scenario
        scenario_list = []
        for d in glob.glob(f"{molecule_path}/*"):
            if os.path.isdir(d) and os.path.isfile(os.path.join(d,"molecule.yml")):
                scenario_list.append(os.path.basename(d))

        # split scenario
        split_scenario = array_split(scenario_list, jobs)

        # list targets
        ansible_release = module.params.get('ansible_release')
        job_prefix = module.params.get('prefix')
        targets = []
        for i in range(len(split_scenario)):
            if ansible_release:
                for rel in ansible_release:
                    targets.append(f"{job_prefix}_{rel}_{i}")
            else:
                targets.append(f"{job_prefix}_{i}")
        result = {
            "zuul": {"child_jobs": targets},
            "child": {"scenario": split_scenario},
        }
        module.exit_json(result=result, changed=False)
    except Exception as e:
        module.fail_json(msg=f"raise: {e}")

def main():
    argument_spec = {
        'jobs': {'type': 'int', 'default': 4},
        'path': {'type': 'path'},
        'prefix': {'default': 'ansible-test-molecule'},
        'ansible_release': {'type': 'list'},
    }
    module = AnsibleModule(argument_spec=argument_spec,)
    execute_module(module)


if __name__ == '__main__':
    main()
