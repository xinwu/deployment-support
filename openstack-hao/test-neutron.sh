#!/bin/bash

set -e
set -x

# http://docs.openstack.org/havana/install-guide/install/apt/content/install-neutron.configure-networks.html

neutron net-create ext-net -- --router:external=True
neutron subnet-create ext-net 10.192.64.0/18  --allocation-pool start=10.192.64.36,end=10.192.64.37 --gateway=10.192.64.1 --disable-dhcp --name prod
neutron router-create ext-to-int
neutron router-gateway-set ext-to-int prod
neutron net-create --tenant-id DEMO_TENANT_ID demo-net
neutron subnet-create --tenant-id DEMO_TENANT_ID demo-net 10.203.100.0/24 --gateway 10.203.100.1 --name demo-subnet-100
neutron router-interface-add ext-to-int demo-subnet-100
