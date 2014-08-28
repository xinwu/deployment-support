#!/bin/bash
# a script to create 25 networks and routers and check the port status
source ~/openrc
for i in {1..25}; do
  neutron router-interface-delete $i $i
  neutron router-delete $i
  neutron subnet-delete $i
  neutron net-delete $i
done
for i in {1..25}; do
  neutron net-create $i
  neutron subnet-create $i 88.77.$i.0/24 --name $i
  neutron router-create $i
  neutron router-interface-add $i $i
done
for i in {1..25}; do
  neutron port-show $(neutron router-port-list $i | grep '|' | awk -F '|' '{ print $2 }' | grep -v id) | grep status
done
