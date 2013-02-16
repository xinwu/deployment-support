#!/bin/sh
#
# Note: This script is to be run on each OpenStack Compute Node,
# and the Quantum Server node. It cleans up the following:
# qvb* - vnet devices corresponding to the VIF
# qbr* - Linux Bridge created for each VIF
# qvo* - Internal Port on OVS
# tap* - Tap device for each network's DHCP server
#
# WARNING: The script cleans all devices which start with
# the above prefix. If you have manually created a device
# with the above prefix, it will be lost.
# 
# @author: Sumit Naiksatam, Big Switch Networks, Inc.
# @date: February 16 2013

set -e

for qvb in `ifconfig -a | grep qvb | cut -d' ' -f1`
do
    `sudo ip link set $qvb down`
    `sudo ip link delete $qvb`
done
for qbr in `ifconfig -a | grep qbr | cut -d' ' -f1`
do
    `sudo ip link set $qbr down`
    `sudo ip link delete $qbr`
done
for qvo in `ifconfig -a | grep qvo | cut -d' ' -f1`
do
    `sudo ovs-vsctl del-port br-int $qvo`
done
for tap in `ifconfig -a | grep tap | cut -d' ' -f1`
do
    `sudo ip link set $tap down`
    `sudo ovs-vsctl del-port br-int $tap`
done
