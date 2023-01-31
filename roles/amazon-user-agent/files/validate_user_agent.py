#!/usr/bin/env python3

import argparse
from pathlib import PosixPath
import sys
import yaml
import os

parser = argparse.ArgumentParser(
    description="Validate that version hard-coded in aligned with the value from galaxy.yml."
)
parser.add_argument(
    "-c",
    "--collection-path",
    type=PosixPath,
    required=True,
    help="Path to the collection to test"
)

parser.add_argument(
    "-n",
    "--variable-name",
    type=str,
    required=True,
    help="Variable name where the collection version is hard-coded (e.g. AMAZON_AWS_COLLECTION_VERSION)"
)


def parse_args(raw_args):
    return parser.parse_args(raw_args)


def has_variable(path, var_name):
    regex = f"{var_name} = "
    with path.open() as fd:
        for d in fd.read().split("\n"):
            if d.startswith(regex):
                return d.replace(regex, "").replace("'", "").replace('"', "")


def locate_variable(path, var_name):

    def listdir_files(src, var_n):
        result = []
        if src.is_dir():
            for d in src.iterdir():
                result.extend(listdir_files(d, var_n))
        elif str(src).endswith(".py"):
            var_set = has_variable(src, var_n)
            if var_set:
                result.append((src, var_set))
        return result

    return listdir_files(path / "plugins", var_name)


def read_collection_version(path):
    with (path / "galaxy.yml").open() as fd:
        return yaml.safe_load(fd)["version"]


def main():
    args = parse_args(sys.argv[1:])
    
    collection_version = read_collection_version(args.collection_path)

    errors = []
    for path, version in locate_variable(args.collection_path, args.variable_name):
        if version != collection_version:
            errors.append(f"{os.path.relpath(path, start=str(args.collection_path))} has variable set to '{version}' instead of '{collection_version}'")

    if errors:
        sys.stderr.write("%s\n" % "\n".join(errors))
        sys.exit(1)

if __name__ == "__main__":

    main()
