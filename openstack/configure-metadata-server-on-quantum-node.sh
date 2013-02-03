#!/usr/bin/env bash
#
# Note: This script is to be run on the Quantum server host
# when the Quantum server is on a different host from the Meta-data
# server host.
# 
# Supported Ubuntu version: 12.10
# Big Switch Plugin: https://github.com/bigswitch/quantum/tree/folsom/master
# 
# @author: Sumit Naiksatam, Big Switch Networks, Inc.
# @date: Februaryy 02 2013
#
# See usage below:
USAGE="$0 <metadata_server_ip> <metadata_server_port, usually 8775>"

set -x

METADATA_SERVER_IP=$1
METADATA_SERVER_PORT=$2

# Validate args
if [ "${METADATA_SERVER_IP}"x = ""x ] ; then
    echo "ERROR: metadata_server_ip not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi
if [ "${METADATA_SERVER_PORT}"x = ""x ] ; then
    echo "ERROR: metadata_server_port not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi

iptables -t nat -A PREROUTING -d 169.254.169.254/32 -p tcp -m tcp --dport 80 -j DNAT --to-destination $METADATA_SERVER_IP:$METADATA_SERVER_PORT

echo "Done."
