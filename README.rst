ansible-zuul-jobs
=================

Zuul job definitions for Ansible tenant.

How to test a zuul change, (a.k.a How to use Depends-On)
--------------------------------------------------------

Changes on ansible-zuul-jobs will impact the execution of the
CI jobs, and it's sometime hard to understand what a PR can actually break.

A way to address this is to use ``Depends-On`` in a another PR.
``Depends-On`` keyword can be used to cherry-pick an specific
dependency during a job execution.
This feature is documented upstream here: `Zuul gating`_.

For instance, I've got an ansible-zuul-jobs that I would like
to validate. ansible-zuul-jobs's CI does not run all the CI jobs to
validate my change for performance reason. But I can use the
``Depends-On`` key-work in a PR for another repository to force
Zuul to use my PR during the test execution.

For example:

I prepare a nice ansible-zuul-jobs PR,
e.g: https://github.com/ansible/ansible-zuul-jobs/pull/432. I know my
PR will impact the `VMware collection`_, but may also impact some other jobs.

I will reuse a existing PR from the VMware collection repository,
and add a ``Depends-On: https://github.com/ansible/ansible-zuul-jobs/pull/432``
in the top of its description. e.g: https://github.com/ansible-collections/vmware/pull/35.

This way, the next time Zuul [#recheck]_ test my VMware PR, it will
cherry-pick my ansible-zuul-jobs first.
If the tests pass, it means that my change won't break the jobs of
this repository.

.. [#recheck] You can ask Zuul to retest a PR with the ``recheck`` command.
    Just type ``recheck`` in a Github PR comment, and it will trigger a new
    run.
.. _VMware collection: https://github.com/ansible-collections/vmware
.. _Zuul gating: https://zuul-ci.org/docs/zuul/discussion/gating.html
