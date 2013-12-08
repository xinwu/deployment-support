#!/bin/bash

set -e
set -x

N=coke
CIDR=10.203.10.0/24

# ----------------------------------------------------------------------------
# Clean up
# ----------------------------------------------------------------------------

set +e

export OS_USERNAME=$N
export OS_PASSWORD=$N
export OS_TENANT_NAME=$N

nova delete $N-vm2
nova delete $N-vm1

nova secgroup-delete-rule default icmp -1 -1 0.0.0.0/0
nova secgroup-delete-rule default tcp 22 22 0.0.0.0/0

nova keypair-delete $N-key

neutron router-interface-delete $N-router $N-subnet
neutron router-delete $N-router
neutron subnet-delete $N-subnet
neutron net-delete $N-network

export OS_USERNAME=admin
export OS_PASSWORD=ADMIN_PASS
export OS_TENANT_NAME=admin

keystone user-delete $N
keystone tenant-delete $N

# ----------------------------------------------------------------------------
# Test
# ----------------------------------------------------------------------------

set -e

export OS_USERNAME=admin
export OS_PASSWORD=ADMIN_PASS
export OS_TENANT_NAME=admin

keystone tenant-create --name $N
keystone user-create --name $N --tenant $N --pass $N --email $N@bigswitch.com

export OS_USERNAME=$N
export OS_PASSWORD=$N
export OS_TENANT_NAME=$N

neutron net-create $N-network
neutron subnet-create --name $N-subnet $N-network $CIDR
neutron router-create $N-router
neutron router-interface-add $N-router $N-subnet

test -f ~/.ssh/id_rsa || ssh-keygen -t rsa -N '' -f ~/.ssh/id_rsa
nova keypair-add --pub_key ~/.ssh/id_rsa.pub $N-key

nova secgroup-add-rule default tcp 22 22 0.0.0.0/0
nova secgroup-add-rule default icmp -1 -1 0.0.0.0/0
nova secgroup-list-rules default

nova boot --flavor m1.small --image Ubuntu-12.04 --key_name $N-key $N-vm1
nova boot --flavor m1.small --image Ubuntu-12.04 --key_name $N-key $N-vm2

