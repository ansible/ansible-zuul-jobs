#!/usr/bin/env python3

import pytest
import io
from pathlib import PosixPath
from unittest.mock import MagicMock, patch
from list_changed_targets import (
    Collection,
    ElGrandeSeparator,
    WhatHaveChanged,
    list_pyimport,
    parse_args,
    read_collection_name,
)

my_module = """
from ..module_utils.core import AnsibleAWSModule
from ipaddress import ipaddress
import time
import botocore.exceptions
"""

my_module_2 = """
import ansible_collections.kubernetes.core.plugins.module_utils.k8sdynamicclient

def main():
    mutually_exclusive = [
        ("resource_definition", "src"),
    ]
    module = AnsibleModule(
        argument_spec=argspec(),
    )
    from ansible_collections.kubernetes.core.plugins.module_utils.common import (
        K8sAnsibleMixin,
        get_api_client,
    )

    k8s_ansible_mixin = K8sAnsibleMixin(module)
"""

my_module_3 = """
from .modules import AnsibleAWSModule
from ipaddress import ipaddress
import time
import botocore.exceptions
"""


def test_read_collection_name():
    m_galaxy_file = MagicMock()
    m_galaxy_file.open = lambda: io.BytesIO(b"name: b\nnamespace: a\n")
    m_path = MagicMock()
    m_path.__truediv__.return_value = m_galaxy_file
    assert read_collection_name(m_path) == "a.b"


def test_list_pyimport():
    assert list(
        list_pyimport("ansible_collections.amazon.aws.plugins.", "modules", my_module)
    ) == [
        "ansible_collections.amazon.aws.plugins.module_utils.core",
        "ipaddress",
        "time",
        "botocore.exceptions",
    ]

    assert list(
        list_pyimport(
            "ansible_collections.kubernetes.core.plugins.", "modules", my_module_2
        )
    ) == [
        "ansible_collections.kubernetes.core.plugins.module_utils.k8sdynamicclient",
        "ansible_collections.kubernetes.core.plugins.module_utils.common",
    ]

    assert list(
        list_pyimport(
            "ansible_collections.amazon.aws.plugins.", "module_utils", my_module_3
        )
    ) == [
        "ansible_collections.amazon.aws.plugins.module_utils.modules",
        "ipaddress",
        "time",
        "botocore.exceptions",
    ]


def test_what_changed_files():
    whc = WhatHaveChanged(PosixPath("a"), "b")
    whc.collection_name = lambda: "a.b"
    whc.changed_files = lambda: [
        PosixPath("tests/something"),
        PosixPath("plugins/module_utils/core.py"),
        PosixPath("plugins/plugin_utils/base.py"),
        PosixPath("plugins/connection/aws_ssm.py"),
        PosixPath("plugins/modules/ec2.py"),
        PosixPath("plugins/lookup/aws_test.py"),
        PosixPath("tests/integration/targets/k8s_target_1/action.yaml"),
        PosixPath("tests/integration/targets/k8s_target_2/file.txt"),
        PosixPath("tests/integration/targets/k8s_target_3/tasks/main.yaml"),
    ]
    assert list(whc.modules()) == [PosixPath("plugins/modules/ec2.py")]
    assert list(whc.plugin_utils()) == [
        (
            PosixPath("plugins/plugin_utils/base.py"),
            "ansible_collections.a.b.plugins.plugin_utils.base",
        )
    ]
    assert list(whc.module_utils()) == [
        (
            PosixPath("plugins/module_utils/core.py"),
            "ansible_collections.a.b.plugins.module_utils.core",
        )
    ]
    assert list(whc.lookup()) == [PosixPath("plugins/lookup/aws_test.py")]
    assert list(whc.targets()) == [
        "k8s_target_1",
        "k8s_target_2",
        "k8s_target_3",
    ]
    assert list(whc.connection()) == [PosixPath("plugins/connection/aws_ssm.py")]


def build_collection(aliases):
    c = Collection(PosixPath("nowhere"))
    m_c_path = MagicMock()
    c.collection_path = m_c_path
    m_c_path.glob.return_value = aliases
    return c


def build_alias(name, text):
    m_alias_file = MagicMock()
    m_alias_file.read_text.return_value = text
    m_alias_file.parent.name = name
    return m_alias_file


def test_c_targets():
    c = build_collection([])
    assert list(c._targets()) == []

    c = build_collection([build_alias("a", "ec2\n")])
    assert len(list(c._targets())) == 1
    assert list(c._targets())[0].name == "a"
    assert list(c._targets())[0].is_alias_of("ec2")

    c = build_collection([build_alias("a", "#ec2\n")])
    assert len(list(c._targets())) == 1
    assert list(c._targets())[0].name == "a"
    assert list(c._targets())[0].execution_time() == 180

    c = build_collection([build_alias("a", "time=30\n")])
    assert len(list(c._targets())) == 1
    assert list(c._targets())[0].name == "a"
    assert list(c._targets())[0].execution_time() == 30


def test_2_targets_for_one_module():
    c = build_collection(
        [build_alias("a", "ec2_instance\n"), build_alias("b", "ec2_instance\n")]
    )
    assert c.regular_targets_to_test() == []
    c.add_target_to_plan("ec2_instance")
    assert c.regular_targets_to_test() == ["a", "b"]


def test_c_disabled_unstable():
    c = Collection(PosixPath("nowhere"))
    m_c_path = MagicMock()
    c.collection_path = m_c_path
    m_c_path.glob.return_value = [
        build_alias("a", "disabled\n"),
        build_alias("b", "unstable\n"),
    ]

    # all, we should ignore the disabled,unstable jobs
    c.cover_all()
    assert len(c.regular_targets_to_test()) == 0
    # if the module is targets, we continue to ignore the disabled
    c.add_target_to_plan("a")
    assert len(c.regular_targets_to_test()) == 0
    # unstable targets should not be triggered if they were pulled in as a dependency
    c.add_target_to_plan("b", is_direct=False)
    assert len(c.regular_targets_to_test()) == 0
    # but the unstable is ok when directly triggered
    c.add_target_to_plan("b")
    assert len(c.regular_targets_to_test()) == 1


def test_c_slow_regular_targets():
    c = build_collection(
        [
            build_alias("tortue", "slow\nec2\n#s3\n"),
            build_alias("lapin", "notslow\ncarrot\n\n"),
        ]
    )

    c.cover_all()
    assert len(list(c._targets())) == 2
    assert list(c._targets())[0].is_slow()
    assert not list(c._targets())[1].is_slow()
    assert len(c.slow_targets_to_test()) == 1


def test_c_inventory_targets():
    c = build_collection(
        [
            build_alias("inventory_tortue", "slow\nec2\n#s3\n"),
            build_alias("lapin", "notslow\ninventory_carrot\n\n"),
        ]
    )
    c.cover_all()
    assert len(list(c._targets())) == 2
    assert list(c._targets())[0].is_slow()
    assert not list(c._targets())[1].is_slow()
    assert len(c.slow_targets_to_test()) == 1


def test_c_with_cover():
    c = Collection(PosixPath("nowhere"))
    m_c_path = MagicMock()
    c.collection_path = m_c_path

    m_c_path.glob.return_value = [
        build_alias("tortue", "slow\nec2\n#s3\n"),
        build_alias("lapin", "carrot\n\n"),
    ]
    c.add_target_to_plan("ec2")
    assert len(c.slow_targets_to_test()) == 1
    assert c.regular_targets_to_test() == []


def test_argparse():
    args = parse_args("--test-changed somewhere somewhere-else".split(" "))
    assert args.collection_to_tests == [
        PosixPath("somewhere"),
        PosixPath("somewhere-else"),
    ]


def test_splitter_with_slow():
    c = build_collection(
        [
            build_alias("a", "ec2\n"),
            build_alias("slow-bob", "slow\n"),
            build_alias("slow-jim", "slow\n"),
            build_alias("regular-dude", "\n"),
        ]
    )
    c.cover_all()
    egs = ElGrandeSeparator([c])
    result = list(egs.build_up_batches([f"slot{i}" for i in range(4)], c))
    assert result == [
        ("slot0", ["slow-bob"]),
        ("slot1", ["slow-jim"]),
        ("slot2", ["a", "regular-dude"]),
    ]


def test_splitter_with_time():
    c = build_collection(
        [
            build_alias("a", "time=50m\n"),
            build_alias("b", "time=10m\n"),
            build_alias("c", "time=180\n"),
            build_alias("d", "time=140s  \n"),
            build_alias("e", "time=70\n"),
        ]
    )
    c.cover_all()
    egs = ElGrandeSeparator([c])
    result = list(egs.build_up_batches([f"slot{i}" for i in range(2)], c))
    assert result == [
        ("slot0", ["a"]),
        ("slot1", ["b", "c", "d", "e"]),
    ]

    c = build_collection(
        [
            build_alias("a", "time=50m\n"),
            build_alias("b", "time=50m\n"),
            build_alias("c", "time=18\n"),
            build_alias("d", "time=5m\n"),
        ]
    )
    c.cover_all()
    egs = ElGrandeSeparator([c])
    result = list(egs.build_up_batches([f"slot{i}" for i in range(4)], c))
    assert result == [("slot0", ["a"]), ("slot1", ["b"]), ("slot2", ["d", "c"])]


@patch("subprocess.check_output")
def test_what_changed_git_call(m_check_output):
    m_check_output.return_value = b"plugins/modules/foo.py\n"
    whc = WhatHaveChanged(PosixPath("a"), "stable-2.1")
    whc.collection_name = lambda: "a.b"
    whc.changed_files()
    m_check_output.assert_called_with(
        ["git", "diff", "origin/stable-2.1", "--name-only"], cwd=PosixPath("a")
    )
