#!/bin/bash

set -e
set -x

N=coke

keystone tenant-create --name $N
keystone user-create --name $N --tenant $N --pass $N --email $N@bigswitch.com

# All operations below will be performed as user $N tenant $N.
export OS_USERNAME=$N
export OS_PASSWORD=$N
export OS_TENANT_NAME=$N

neutron net-create $N-network
neutron subnet-create --name $N-subnet $N-network 10.203.10.0/24
neutron router-create $N-router
neutron router-interface-add $N-router $N-subnet

if [ ! -f ~/.ssh/id_rsa ]; then
    ssh-keygen -t rsa -N '' -f ~/.ssh/id_rsa
fi

nova keypair-add --pub_key ~/.ssh/id_rsa.pub $N-key

nova boot --flavor m1.small --image Ubuntu-12.04 --key_name $N-key $N-vm1
nova boot --flavor m1.small --image Ubuntu-12.04 --key_name $N-key $N-vm2

