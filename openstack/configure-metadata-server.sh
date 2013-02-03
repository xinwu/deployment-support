#!/usr/bin/env bash
#
# Note: This script is to be run on the host on which the Meta-data
# server runs.
# This script configures OpenStack Meta-data server IP and port
# 
# Supported Ubuntu version: 12.10
# Big Switch Plugin: https://github.com/bigswitch/quantum/tree/folsom/master
# 
# @author: Sumit Naiksatam, Big Switch Networks, Inc.
# @date: January 29 2013
#
# See usage below:
USAGE="$0 <management_interface, usually eth0> <metadata_server_port, usually 8775>"

set -x

MANAGEMENT_INTERFACE=$1
METADATA_SERVER_PORT=$2

# Validate args
if [ "${MANAGEMENT_INTERFACE}"x = ""x ] ; then
    echo "ERROR: management_interface not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi
if [ "${METADATA_SERVER_PORT}"x = ""x ] ; then
    echo "ERROR: metadata_server_port not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi

ip addr add 169.254.169.254/32 scope link dev $MANAGEMENT_INTERFACE

iptables -t nat -A PREROUTING -d 169.254.169.254/32 -p tcp -m tcp --dport 80 -j DNAT --to-destination 169.254.169.254:$METADATA_SERVER_PORT

echo "Done."
