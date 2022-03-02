#!/usr/bin/env python3

from pathlib import PosixPath
from list_kubernetes_changed_targets import (
    WhatHaveChanged,
    parse_args,
)


def test_what_changed_files():
    whc = WhatHaveChanged(PosixPath("a"), "b")
    whc.changed_files = lambda: [
        PosixPath("tests/something"),
        PosixPath("plugins/modules/k8s_json_patch.py"),
        PosixPath("plugins/modules/k8s_drain.py"),
        PosixPath("plugins/inventory/k8s_services.py"),
        PosixPath("plugins/inventory/k8s_pods.py"),
        PosixPath("plugins/inventory_utils/k8s_utils.py"),
        PosixPath("plugins/lookup/k8s_balancer.py"),
        PosixPath("plugins/lookup/k8s_node.py"),
        PosixPath("tests/integration/targets/k8s_target_1/action.yaml"),
        PosixPath("tests/integration/targets/k8s_target_2/file.txt"),
        PosixPath("tests/integration/targets/k8s_target_3/tasks/main.yaml"),
    ]
    assert list(whc.modules()) == [
        PosixPath("plugins/modules/k8s_json_patch.py"),
        PosixPath("plugins/modules/k8s_drain.py"),
    ]
    assert list(whc.inventory()) == [
        PosixPath("plugins/inventory/k8s_services.py"),
        PosixPath("plugins/inventory/k8s_pods.py"),
    ]
    assert list(whc.lookup()) == [
        PosixPath("plugins/lookup/k8s_balancer.py"),
        PosixPath("plugins/lookup/k8s_node.py"),
    ]
    assert list(whc.targets()) == [
        "k8s_target_1",
        "k8s_target_2",
        "k8s_target_3",
    ]
    assert not whc.common()


def test_what_changed_files_helm():
    whc_helm = WhatHaveChanged(PosixPath("a"), "b")
    whc_helm.changed_files = lambda: [
        PosixPath("plugins/modules/test_0.py"),
        PosixPath("plugins/module_utils/common.py"),
    ]
    assert not whc_helm.helm()

    whc_helm = WhatHaveChanged(PosixPath("a"), "b")
    whc_helm.changed_files = lambda: [
        PosixPath("plugins/modules/helm.py"),
    ]
    assert whc_helm.helm()

    whc_helm = WhatHaveChanged(PosixPath("a"), "b")
    whc_helm.changed_files = lambda: [
        PosixPath("plugins/module_utils/helm_common.py"),
    ]
    assert whc_helm.helm()

    whc_helm = WhatHaveChanged(PosixPath("a"), "b")
    whc_helm.changed_files = lambda: [
        PosixPath("plugins/doc_fragments/helm_fragment.py"),
    ]
    assert whc_helm.helm()

    whc_helm = WhatHaveChanged(PosixPath("a"), "b")
    whc_helm.changed_files = lambda: [
        PosixPath("plugins/action/helm_action.py"),
    ]
    assert whc_helm.helm()


def test_what_changed_files_common():
    whc = WhatHaveChanged(PosixPath("a"), "b")
    whc.changed_files = lambda: [
        PosixPath("plugins/module_utils/helm.py"),
    ]
    assert not whc.common()

    whc = WhatHaveChanged(PosixPath("a"), "b")
    whc.changed_files = lambda: [
        PosixPath("plugins/module_utils/common.py"),
    ]
    assert whc.common()

    whc = WhatHaveChanged(PosixPath("a"), "b")
    whc.changed_files = lambda: [
        PosixPath("plugins/action/common.py"),
    ]
    assert whc.common()

    whc = WhatHaveChanged(PosixPath("a"), "b")
    whc.changed_files = lambda: [
        PosixPath("plugins/doc_fragments/common.py"),
    ]
    assert whc.common()


def test_argparse():
    args = parse_args("my_collection_path --release 2.9 2.10".split(" "))
    print(args)
    assert args.collection_to_test == PosixPath("my_collection_path")
    assert args.release == [
        "2.9",
        "2.10",
    ]
