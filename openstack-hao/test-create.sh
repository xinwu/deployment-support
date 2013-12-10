#!/bin/bash

# This script exercises basic OpenStack operations such as creating a network
# and two VMs within the network.

set -e
set -x

N=coke
CIDR=10.203.10.0/24

export OS_AUTH_URL=http://controller:35357/v2.0

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

nova secgroup-add-rule default tcp 1 65535 0.0.0.0/0
nova secgroup-add-rule default udp 1 65535 0.0.0.0/0
nova secgroup-add-rule default icmp -1 -1 0.0.0.0/0
nova secgroup-list-rules default

nova boot --flavor m1.small --image Ubuntu-13.10 --security-groups default --key_name $N-key $N-vm1
nova boot --flavor m1.small --image Ubuntu-13.10 --security-groups default --key_name $N-key $N-vm2
