#!/usr/bin/env python3

import sys
import yaml


converge_file = sys.argv[1]
with open(converge_file) as file:
    for data in yaml.safe_load(file):
        if data.get("name", None) == "Converge" and "tasks" in data and isinstance(data.get("tasks"), list):
            excluded_tags = ("k8s", "always")
            tags = []
            for role in data.get("roles", []):
                local_tag = role.get('tags', None)
                name = role.get("role")
                if not local_tag:
                    raise Exception(f"role '{name}' should define at least one tag.")
                tags.append(",".join([x for x in local_tag if x not in excluded_tags]))

            for task in [x for x in data.get("tasks") if "include_tasks" in x ]:
                local_tag = task["include_tasks"]["apply"]["tags"]
                tags.append(",".join([x for x in local_tag if x not in excluded_tags]))
            print(" ".join(tags))
            sys.exit(0)

sys.exit(1)