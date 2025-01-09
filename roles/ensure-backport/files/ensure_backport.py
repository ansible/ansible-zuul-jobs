#!/usr/bin/env python3

import argparse
import os
import re
import sys

import requests


class RequestError(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(
        description="Ensure a Pull request contains one of 'backport-*' or 'do_not_backport' labels."
    )
    parser.add_argument(
        "--pr-id", type=int, required=True, help="The pull request number."
    )
    parser.add_argument(
        "--project-name",
        type=str,
        required=True,
        help="The Github project name, e.g: 'ansible-collections/amazon.aws'.",
    )
    args = parser.parse_args(sys.argv[1:])
    # Get list of labels attached to the pull requests
    # ansible_github_token = os.environ.get("GH_TOKEN")
    response = requests.get(
        f"https://api.github.com/repos/{args.project_name}/issues/{args.pr_id}/labels",
        headers={
            "Accept": "application/vnd.github+json",
            # "Authorization": f"Bearer {ansible_github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if not response.ok:
        raise RequestError(response.reason)

    print(
        "*** INFO *** Pull request labels = {0}".format(
            [i["name"] for i in response.json()]
        )
    )

    do_not_backport = any(i["name"] == "do_not_backport" for i in response.json())
    has_backport_label = any(
        re.match("^backport-[0-9]*$", i["name"]) for i in response.json()
    )
    if do_not_backport and has_backport_label:
        raise RequestError(
            "Pull request cannot contain both 'do_not_backport' and 'backport-*' labels."
        )
    if not do_not_backport and not has_backport_label:
        raise RequestError(
            "Pull request must contain one of the 'do_not_backport' or 'backport-*' labels."
        )


if __name__ == "__main__":
    main()
