#!/usr/bin/env bash
#
# Note: This script is to be run on the Quantum host and when the Nova API
# server is running on a different host, so as to set up the Quantum
# host as a NAT Proxy to the Metadata server.
# 
# @author: Mandeep Dhami, Big Switch Networks, Inc.
# @author: Sumit Naiksatam, Big Switch Networks, Inc.
# @date: Feb 11 2013
#
# See usage below:
USAGE="$0 <quantum_ip> <nova_ip> [<quantum_to_nova_interface> <metadata_server_port>]"

set -x

QUANTUM_IP=$1
NOVA_IP=$2
QUANTUM_TO_NOVA_IF=${3:-'eth0'}
NOVA_PORT=${4:-'8775'}

# Validate args
if [ "${QUANTUM_IP}"x = ""x ] ; then
    echo "ERROR: quantum_ip not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi
if [ "${NOVA_IP}"x = ""x ] ; then
    echo "ERROR: nova_ip is not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi

echo "Using quantum_ip: $QUANTUM_IP, nova_ip: $NOVA_IP, quantum_to_nova_interface: $QUANTUM_TO_NOVA_IF, nova_port: $NOVA_PORT"

echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -t nat -I PREROUTING 1 -d 169.254.169.254/32 -p tcp -m tcp --dport 80 -j DNAT --to-destination $NOVA_IP:$NOVA_PORT
iptables -t nat -A POSTROUTING -o $QUANTUM_TO_NOVA_IF -j SNAT --to-source $QUANTUM_IP
iptables -t nat -A POSTROUTING -j MASQUERADE

echo "IP forwarding was enabled on this host."
echo "Done."
