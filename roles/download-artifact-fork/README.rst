Download artifacts from a completed build of a Zuul job

Given a change, downloads artifacts from a previous build (by default
of the current change) into the work directory.  This will download as
many artifacts as match the selection criteria.

**Role Variables**

.. zuul:rolevar:: download_artifact_api

   The Zuul API endpoint to use.  Example: ``https://zuul.example.org/api/tenant/{{ zuul.tenant }}``

.. zuul:rolevar:: download_artifact_pipeline

   The pipeline in which the previous build ran.

.. zuul:rolevar:: download_artifact_job

   The job of the previous build.

.. zuul:rolevar:: download_artifact_type

   The artifact type.  This is the value of the ``type`` field in the
   artifact metadata. This can be a string or a list of strings.

.. zuul:rolevar:: download_artifact_query
   :default: change={{ zuul.change }}&patchset={{ zuul.patchset }}&pipeline={{ download_artifact_pipeline }}&job_name={{ download_artifact_job }}

   The query to use to find the build.  Normally the default is used.

.. zuul:rolevar:: download_artifact_directory
   :default: {{ zuul.executor.work_root }}

   The directory in which to place the downloaded artifacts.
