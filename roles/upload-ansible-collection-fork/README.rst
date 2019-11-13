Upload ansible collections to Ansible Galaxy

**Role Variables**

.. zuul:rolevar:: ansible_galaxy_info

   Complex argument which contains the information about the galaxy
   server as well as the authentication information needed. It is
   expected that this argument comes from a `Secret`.

  .. zuul:rolevar:: token

     The Ansible Galaxy API key.

  .. zuul:rolevar:: url

     The Galaxy API server URL.

.. zuul:rolevar:: ansible_galaxy_collection_path 
   :default: {{ ansible_user_dir }}/{{ zuul.project.src_dir }}/*.tar.gz

   Path containing artifacts to upload.

.. zuul:rolevar:: ansible_galaxy_executable
   :default: twine

   Path to ansible-galaxy executable.
