ansible-zuul-jobs
=================

Zuul job definitions for Ansible tenant.

Best practices
--------------

1. Try to use create new role when possible
    - Role should NOT use `Zuul` specific variables internally
    - It should be easy to run a role one a local machine to validate it.
2. New changes should be another PR through a `Depends-On:`.
3. Don't run non-voting jobs during the gating, this is a waste of resources.
