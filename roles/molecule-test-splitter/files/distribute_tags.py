#!/usr/bin/env python3

import argparse
import json
from pathlib import PosixPath


def sort_tags(tags):
    slow_tag_file = PosixPath("molecule/default/slow_tags.txt")
    if slow_tag_file.is_file():
        slow_tags = slow_tag_file.read_text().split("\n")
        tags_to_sort = []
        for t in tags:
            u = 0
            if t in slow_tags:
                u = 1
            tags_to_sort.append((t, u))
            tmp = sorted(tags_to_sort, key=lambda k: k[1], reverse=True)
            sorted_tags = [x[0] for x in tmp]
    else:
        sorted_tags = sorted(tags)
    return sorted_tags


def main(job_prefix,ansible_release,number_jobs,tags):
    sorted_tags = sort_tags(tags)
    batches = {}
    for i in range(number_jobs):
        batches[i] = []
    index = 0
    for t in sorted_tags:
        batches[index%number_jobs].append(t)
        index+=1
    
    tags_to_test = [','.join(batches[x]) for x in batches if batches[x]]
    child_jobs = []
    for rel in ansible_release:
        for i in range(len(tags_to_test)):
            child_jobs.append(f"{job_prefix}-{rel}_{i}")


    result = {
        "data": {
            "zuul": {"child_jobs": child_jobs},
            "child": {"tags_to_test": tags_to_test},
    }}
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-a","--ansible-release-prefix", help="ansible release prefix",  default="29 210 devel")
    parser.add_argument("-p","--job-prefix", help="basename for generated jobs.",  default="ansible-test-molecule-kubernetes-core")
    parser.add_argument("-n","--number-jobs", help="number of jobs per ansible release.", default=5)
    parser.add_argument("-t","--tags", help="list of ansible playbook tags to distrubute.", required=True)

    args = parser.parse_args()
    main(job_prefix=args.job_prefix,
         ansible_release=args.ansible_release_prefix.split(" "),
         number_jobs=args.number_jobs,
         tags=args.tags.split(" "))