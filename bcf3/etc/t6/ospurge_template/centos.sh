#!/bin/bash

source %(openrc)s
keystone tenant-list
if [[ $? != 0 ]]; then
    echo 'Unable to establish connection for ospurge'
    exit 1
fi

# by default delete all networks using vxlan
nets_string=$(neutron net-list | awk '$2 != "id" {print $2}' | awk 'NF && $1!~/^#/')
nets=(${nets_string// / })
subnets_string=$(neutron net-list | awk '$6 != "subnets" {print $6}' | awk 'NF && $1!~/^#/')
subnets=(${subnets_string// / })
declare -A subnet_to_net
for i in "${!nets[@]}"; do
    net="${nets[$i]}"
    subnet="${subnets[$i]}"
    neutron net-show $net | grep vlan
    if [[ $? == 0 ]]; then
        continue
    fi
    subnet_to_net[$subnet]=$net
done

# delete router interfaces using vxlan
routers=$(neutron router-list | awk '$2 != "id" {print $2}' | awk 'NF && $1!~/^#/')
for router in $routers; do
    # delete all subnets that have interface on router
    subnets=$(neutron router-port-list $router | awk '$0 ~ /.*subnet_id.*/ {print $0}' | awk '{print $(NF - 3)}' | tr -d ,| tr -d \")
    for subnet in $subnets; do
        if [[ ${subnet_to_net[$subnet]} != '' ]]; then
            neutron router-interface-delete $router $subnet
        fi
    done
done

# delete all vxlan subnets
for subnet in "${!subnet_to_net[@]}"; do
    neutron subnet-delete $subnet
done

# delete all vxlan nets
for subnet in "${!subnet_to_net[@]}"; do
    neutron net-delete ${subnet_to_net[$subnet]}
done

