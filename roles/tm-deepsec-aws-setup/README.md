Role Name
=========

Role for bringing up TrendMicro Deepsecurity instance silently over AWS instance.

Requirements
------------

This Role in it's current form requires Ansible 2.9.* to run as expected

Role Variables
--------------

- defaults/main.yml, this includes all of the dependent file packages that's needed to function the respective role as expected
- vars/main.yml, this includes the path to postgresql-11 package rpms

Dependencies
------------

This role was tested over TM-DEEPSECURITY AWS latest AMI: ami-0a6a9952851789e2e

Example Playbook
----------------

    - hosts: tm-deepsec-servers
      roles:
         - { role: tm_silent_setup }

License
-------

BSD

Author Information
------------------

Ansible Security Automation Team (@justjais) <https://github.com/ansible-security>.
