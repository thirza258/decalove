#!/bin/sh
# Give nginx a resolver, taken from the container's own /etc/resolv.conf.
#
# Needed because the API upstream is a variable (see nginx.conf.template): nginx then
# resolves it per request and needs to be told how. Hard-coding Docker's embedded DNS
# at 127.0.0.11 would work on a compose network and nowhere else, so this reads whatever
# this container was actually given.
set -eu

nameservers=$(awk '/^nameserver/ { print $2 }' /etc/resolv.conf | grep -v ':' | tr '\n' ' ')

if [ -z "$nameservers" ]; then
    # No resolver available. An IP-address or same-host upstream still works; a DNS name
    # would not, and saying so now beats a 502 with no explanation later.
    echo "decalove: no IPv4 nameserver in /etc/resolv.conf; a hostname upstream will not resolve"
    exit 0
fi

# valid=10s, not the 30s this used to cache for: a restarted API container comes back on
# a new address, and until the entry expires every /api/ request is proxied at an IP that
# nothing is listening on any more. That window is a redeploy's worth of 502s, and Docker's
# embedded DNS is a local lookup -- three times as many of them costs nothing measurable.
#
# resolver_timeout so a DNS server that stops answering fails the request in 5s instead of
# holding it for nginx's 30s default, which is long enough to look like a hang and long
# enough to pile up connections while it does.
{
    echo "resolver ${nameservers}valid=10s ipv6=off;"
    echo "resolver_timeout 5s;"
} > /etc/nginx/conf.d/00-resolver.conf
echo "decalove: resolver ${nameservers}(valid=10s, timeout=5s)"
