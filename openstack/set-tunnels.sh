#!/bin/sh
#
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2011, Big Switch Networks, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Mandeep Dhami, Big Switch Networks, Inc.
#

# USAGE
# Configure OVS on nova compute nodes to use bsn tunnels. Use as:
#   ./set-tunnels.sh <interface> <ip-address> <netmask>
#
# e.g.
#   ./set-tunnels.sh eth1 10.10.10.1 255.255.255.0
USAGE="$0 <interface> <ip-address> <netmask>"

set -e

# Process args
TUNNEL_INTERFACE=$1
TUNNEL_IPADDR=$2
TUNNEL_NETMASK=$3

echo "Using following configuration for BSN tunnels:"
echo "  Network interface: ${TUNNEL_INTERFACE}"
echo "  Network address:   ${TUNNEL_IPADDR}"
echo "  Network netmask:   ${TUNNEL_NETMASK}"

if [ "${TUNNEL_INTERFACE}"x = ""x ] ; then
    echo "USAGE: $USAGE" 2>&1
    echo "  >  No network interface specified." 1>&2
    exit 1
fi

if [ "${TUNNEL_IPADDR}"x = ""x ] ; then
    echo "USAGE: $USAGE" 2>&1
    echo "  >  No network address specified." 1>&2
    exit 2
fi

if [ "${TUNNEL_NETMASK}"x = ""x ] ; then
    echo "USAGE: $USAGE" 2>&1
    echo "  >  No network netmask specified." 1>&2
    exit 3
fi

# validate pre-conditions
if grep "${TUNNEL_INTERFACE}" /etc/network/interfaces 1>/dev/null 2>&1 ; then
    echo "  >  No network interface ${TUNNEL_INTERFACE} already specified" 1>&2
    echo "  >  (in /etc/network/interfaces).\n" 1>&2
    echo "  >  Please remove that configuration, and retry." 1>&2
    exit 4
fi

if grep "tun-loopback" /etc/network/interfaces 1>/dev/null 2>&1 ; then
    echo "  >  No network interface tun-loopback already specified" 1>&2
    echo "  >  (in /etc/network/interfaces).\n" 1>&2
    echo "  >  Please remove that configuration, and retry." 1>&2
    exit 5
fi

# Configure ubuntu host
(cat /etc/network/interfaces; cat <<EOF) | sudo tee /etc/network/interfaces

auto ${TUNNEL_INTERFACE}
iface ${TUNNEL_INTERFACE} inet manual
        up ifconfig \$IFACE up

auto tun-loopback
iface tun-loopback inet static
        address ${TUNNEL_IPADDR}
        netmask ${TUNNEL_NETMASK}

EOF

# Create tunnel end-point
echo tun-loopback | sudo tee /etc/bsn_tunnel_interface
sudo ovs-vsctl add-port br-int tun-loopback -- set interface tun-loopback type=internal
sudo ovs-vsctl add-port br-int tun-bsn -- set interface tun-bsn type=gre

# save mac-address
ifconfig -a tun-loopback | head -1 | sed 's/^.*HWaddr //' | sudo tee /etc/bsn_tunnel_mac

# Done
echo "$0 Done."
echo
