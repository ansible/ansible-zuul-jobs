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


def test_read_collection_name():
    m_galaxy_file = MagicMock()
    m_galaxy_file.open = lambda: io.BytesIO(b"name: b\nnamespace: a\n")
    m_path = MagicMock()
    m_path.__truediv__.return_value = m_galaxy_file
    assert read_collection_name(m_path) == "a.b"


def test_list_pyimport():
    assert list(list_pyimport("amazon.aws", my_module)) == [
        "ansible_collections.amazon.aws.plugins.module_utils.core",
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
        PosixPath("plugins/modules/ec2.py"),
    ]
    assert list(whc.modules()) == [PosixPath("plugins/modules/ec2.py")]
    assert list(whc.module_utils()) == [
        (
            PosixPath("plugins/module_utils/core.py"),
            "ansible_collections.a.b.plugins.module_utils.core",
        )
    ]


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
    # but the unstable is ok
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
    print(c.slow_targets_to_test())
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
    print(c.slow_targets_to_test())
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


def test_splitter_basic():
    c = build_collection([build_alias("a", "ec2\n")])
    egs = ElGrandeSeparator(c)
    with pytest.raises(StopIteration):
        first = next(egs.build_up_batches(["slot1"], c))
        assert first == ("slot1", ["ec2"])


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
    egs = ElGrandeSeparator(c)
    result = list(egs.build_up_batches([f"slot{i}" for i in range(4)], c))
    assert result == [
        ("slot0", ["slow-bob"]),
        ("slot1", ["slow-jim"]),
        ("slot2", ["a", "regular-dude"]),
    ]


@patch("subprocess.check_output")
def test_what_changed_git_call(m_check_output):
    m_check_output.return_value = b"plugins/modules/foo.py\n"
    whc = WhatHaveChanged(PosixPath("a"), "stable-2.1")
    whc.collection_name = lambda: "a.b"
    whc.changed_files()
    m_check_output.assert_called_with(
        ["git", "diff", "origin/stable-2.1", "--name-only"], cwd=PosixPath("a")
    )
