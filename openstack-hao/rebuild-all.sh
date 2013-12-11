#!/bin/bash

# Run this script on neutron.bigswitch.com to rebuild entire hos cluster
# It is assumed that cobbler already has system profiles for all nodes. It is just they may use either eth1 for Ubuntu 12.04.3 or em1 for 13.10.

set -e -x

# Ensure all nodes have interface name "em1", and profile "saucy-controller" or "saucy-compute".
MAC=$(sudo cobbler system report --name=hos:controller | egrep "^MAC Address" | sed -e 's/^MAC Address.*: //')
INTERFACE=$(sudo cobbler system report --name=hos:controller | egrep "^Interface ==" | sed -e 's/^Interface ==.*: //')
sudo cobbler system edit --name=hos:controller --interface=$INTERFACE --delete-interface
sudo cobbler system edit --name=hos:controller --interface=em1 --mac=$MAC --profile=saucy-controller

for i in hos:compute-1 hos:compute-2 hos:compute-3; do
    MAC=$(sudo cobbler system report --name=$i | egrep "^MAC Address" | sed -e 's/^MAC Address.*: //')
    INTERFACE=$(sudo cobbler system report --name=$i | egrep "^Interface ==" | sed -e 's/^Interface ==.*: //')
    sudo cobbler system edit --name=$i --interface=$INTERFACE --delete-interface
    sudo cobbler system edit --name=$i --interface=em1 --mac=$MAC --profile=saucy-compute
done

# Start rebuilding.
for i in hos:controller hos:compute-1 hos:compute-2 hos:compute-3; do
    sudo cobbler system edit --name=$i --netboot-enabled=1 
    sudo cobbler system reboot --name=$i
done
