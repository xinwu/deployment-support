#!/bin/bash

# This script must be able to be re-executed again and again. That is, you
# can't assume it is run on a freshly installed OS. That makes it easier
# to test changes made to this script.
#
# Basic assumptions:
# 1. All controller functions, database are all hosted by a single host named
#    $HOSTNAME_CONTROLLER. This hostname is either in DNS, or in /etc/hosts,
#    on all hosts within this OpenStack cluster.

set -e -x

if [ $(id -u) != 0 ]; then
   echo "ERROR: Must run as root"
   exit 1
fi

# Definitions that can be customized per installation

# This hostname should resolve to the IP of the interface on management
# network, often em1.
HOSTNAME_CONTROLLER=controller

# Do NOT use any non-alphanumerical characters that require quoting in
# passwords below. They would break this script.
CINDER_DB_PASSWORD=CINDER_DBPASS
CINDER_ADMIN_PASSWORD=CINDER_PASS

# http://docs.openstack.org/havana/install-guide/install/apt/content/cinder-node.html

install_extra_packages() {
    apt-get -y install cinder-volume lvm2
}

prep_lvm() {
    if ! vgdisplay cinder-volumes; then
        pvcreate -ff /dev/sdb
        vgcreate cinder-volumes /dev/sdb
    fi
}

install_cinder_node() {
    cat > /etc/cinder/cinder.conf <<EOF
[DEFAULT]
rootwrap_config = /etc/cinder/rootwrap.conf
api_paste_confg = /etc/cinder/api-paste.ini
iscsi_helper = tgtadm
volume_name_template = volume-%s
volume_group = cinder-volumes
verbose = True
auth_strategy = keystone
state_path = /var/lib/cinder
lock_path = /var/lock/cinder
volumes_dir = /var/lib/cinder/volumes
rpc_backend = cinder.openstack.common.rpc.impl_kombu
rabbit_host = $HOSTNAME_CONTROLLER
rabbit_port = 5672
rabbit_userid = guest
rabbit_password = guest

[database]
connection = mysql://cinder:$CINDER_DB_PASSWORD@$HOSTNAME_CONTROLLER/cinder
EOF

    cat > /etc/cinder/api-paste.ini <<EOF
[filter:authtoken]
paste.filter_factory=keystoneclient.middleware.auth_token:filter_factory
auth_host=$HOSTNAME_CONTROLLER
auth_port=35357
auth_protocol=http
admin_tenant_name=service
admin_user=cinder
admin_password=$CINDER_ADMIN_PASSWORD
EOF

    service cinder-volume restart; sleep 1
    service tgt restart; sleep 1
}

# Execution starts here

install_extra_packages
prep_lvm
install_cinder_node
