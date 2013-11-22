#!/bin/bash

set -e
set -x

# http://docs.openstack.org/havana/install-guide/install/apt/content/install-neutron.configure-networks.html
# http://docs.openstack.org/havana/install-guide/install/apt/content/demo_per_tenant_router_network_config.html

# This IP on PROD network should be assigned by Hao
EXT_IP=10.192.64.36
EXT_GW=10.192.64.1
EXT_CIDR=10.192.64.0/18

neutron router-gateway-clear ext-to-int || :
neutron router-interface-delete ext-to-int demo-subnet-100 || :
neutron router-delete ext-to-int || :
neutron subnet-delete demo-subnet-100 || :
neutron net-delete demo-net || :
neutron subnet-delete prod || :
neutron net-delete ext-net || :

#neutron net-create ext-net -- --router:external=True --provider:network_type gre --provider:segmentation_id 2
#neutron subnet-create ext-net $EXT_CIDR --allocation-pool start=$EXT_IP,end=$EXT_IP --gateway=$EXT_GW --disable-dhcp --name prod
neutron net-create ext-net --router:external true --provider:network_type local
neutron subnet-create ext-net $EXT_CIDR --disable-dhcp --name prod
ip addr add $EXT_CIDR dev br-ex
ip link set br-ex up


neutron router-create ext-to-int
neutron router-gateway-set ext-to-int ext-net

sed -i -e 's/^gateway_external_network_id = .*$/gateway_external_network_id = ext-net/' \
       -e 's/^router_id = .*$/router_id = ext-to-int/' /etc/neutron/l3_agent.ini
service neutron-l3-agent restart


# Without specifying --tenant, the network will be owned by $OS_TENANT_NAME.

#TENANT=admin
#neutron net-create --tenant-id $TENANT demo-net
#neutron subnet-create --tenant-id $TENANT demo-net 10.203.100.0/24 --gateway 10.203.100.1 --name demo-subnet-100
neutron net-create demo-net
neutron subnet-create demo-net 10.203.100.0/24 --gateway 10.203.100.1 --name demo-subnet-100
neutron router-interface-add ext-to-int demo-subnet-100



