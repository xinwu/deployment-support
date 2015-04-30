#!/bin/bash

# This template deletes all network related resources for fresh installation.
# We are not using it anywhere for now, but keep it hear for future uses.

source %(openrc)s

# delete all routers
routers=$(neutron router-list | awk '$2 != "id" {print $2}' | awk 'NF && $1!~/^#/')
for router in $routers; do
    # delete all subnets that have interface on router
    subnets=$(neutron router-port-list $router | awk '$0 ~ /.*subnet_id.*/ {print $0}' | awk '{print $(NF - 3)}' | tr -d ,| tr -d \")
    for subnet in $subnets; do
        neutron router-interface-delete $router $subnet
    done
    neutron router-delete $router
done

# delete floating ips
floatingips=$(neutron floatingip-list | awk '$2 != "id" {print $2}' | awk 'NF && $1!~/^#/')
for floatingip in $floatingips; do
    neutron floatingip-delete $floatingip
done

# delete neutron ports
ports=$(neutron port-list | awk '$2 != "id" {print $2}' | awk 'NF && $1!~/^#/')
for port in $ports; do
    neutron port-delete $port
done

# delete all subnets
subnets=$(neutron subnet-list | awk '$2 != "id" {print $2}' | awk 'NF && $1!~/^#/')
for subnet in $subnets; do
    neutron subnet-delete $subnet
done

# delete all networks
nets=$(neutron net-list | awk '$2 != "id" {print $2}' | awk 'NF && $1!~/^#/')
for net in $nets; do
    neutron net-delete $net
done
