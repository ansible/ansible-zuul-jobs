An ansible role to dynamically configure DNS forwarders for the
``unbound`` caching service.  IPv6 will be preferred when there is a
usable IPv6 default route, otherwise IPv4.

.. note:: This is not a standalone unbound configuration role.  Base
          setup is done during image builds in
          ``project-config:nodepool/elements/nodepool-base/finalise.d/89-unbound``;
          here we just do dynamic configuration of forwarders based on
          the interfaces available on the actual host.

**Role Variables**

.. zuul:rolevar:: unbound_primary_nameserver_v4
   :default: 208.67.222.222 (OpenDNS)

   The primary IPv4 nameserver for fowarding requests

.. zuul:rolevar:: unbound_secondary_nameserver_v4
   :default: 8.8.8.8 (Google)

   The secondary IPv4 nameserver for fowarding requests

.. zuul:rolevar:: unbound_primary_nameserver_v6
   :default: 2620:0:ccc::2 (OpenDNS)

   The primary IPv6 nameserver for fowarding requests

.. zuul:rolevar:: unbound_secondary_nameserver_v6
   :default: 2001:4860:4860::8888 (Google)

   The seconary IPv6 nameserver for fowarding requests

.. zuul:rolevar:: unbound_cache_max_ttl
   :default: 86400

   Maximum TTL in seconds to keep successful queries cached for.

   This TTL will have precedence if the DNS record TTL is higher.
   For example, a TTL of 90000 would be reduced to 86400.

.. zuul:rolevar:: unbound_cache_min_ttl
   :default: 0

   Minimum TTL in seconds to keep queries cached for.
   Note that this is effective for both successful and failed queries.

   This TTL will have precedence if the DNS record TTL is lower.
   For example, a TTL of 60 would be raised to 900.
