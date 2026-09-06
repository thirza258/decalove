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

echo "resolver ${nameservers}valid=30s ipv6=off;" > /etc/nginx/conf.d/00-resolver.conf
echo "decalove: resolver ${nameservers}"
