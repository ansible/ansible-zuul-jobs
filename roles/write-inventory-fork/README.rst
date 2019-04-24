Write an abbreviated version of the Zuul inventory to a file

This writes the minimal information about hosts from the current Zuul
inventory to a file.  It may be used to subsequently invoke Ansible
with the inventory for the job.

**Role Variables**

.. zuul:rolevar:: write_inventory_dest

   The path of the inventory file to write.

.. zuul:rolevar:: write_inventory_include_hostvars
   :type: list

   A list of facts about the host to include.  By default this
   parameter is omitted and all variables about a host will be
   included.  To only include certain variables, list them here.  The
   empty list will cause no variables to be included.

.. zuul:rolevar:: write_inventory_exclude_hostvars
   :type: list

   A list of facts about the host to exclude.  By default, all
   variables about a host will be included.  To exclude certain
   variables, list them here.
