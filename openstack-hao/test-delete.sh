#!/bin/bash

set -e
set -x

N=coke
CIDR=10.203.10.0/24

export OS_AUTH_URL=http://controller:35357/v2.0

export OS_USERNAME=$N
export OS_PASSWORD=$N
export OS_TENANT_NAME=$N

nova delete $N-vm2 || :
nova delete $N-vm1 || :

nova secgroup-delete-rule default icmp -1 -1 0.0.0.0/0 || :
nova secgroup-delete-rule default udp 1 65535 0.0.0.0/0  || :
nova secgroup-delete-rule default tcp 1 65535 0.0.0.0/0  || :

nova keypair-delete $N-key || :

neutron router-interface-delete $N-router $N-subnet || :
neutron router-delete $N-router || :
neutron subnet-delete $N-subnet || :
neutron net-delete $N-network || :

export OS_USERNAME=admin
export OS_PASSWORD=ADMIN_PASS
export OS_TENANT_NAME=admin

keystone user-delete $N || :
keystone tenant-delete $N || :
