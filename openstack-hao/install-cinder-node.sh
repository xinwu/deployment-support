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
install_cinder_node() {
    apt-get -y install cinder-api cinder-scheduler
    if ! egrep -qs '^\[database\]' /etc/cinder/cinder.conf; then
        cat >> /etc/cinder/cinder.conf <<EOF
rpc_backend = cinder.openstack.common.rpc.impl_kombu
rabbit_host = $HOSTNAME_CONTROLLER
rabbit_port = 5672
rabbit_userid = guest
rabbit_password = guest

[database]
connection = mysql://cinder:$CINDER_DB_PASSWORD@$HOSTNAME_CONTROLLER/cinder
EOF
    fi

    sed -i \
        -e "s|^auth_host = .*$|auth_host = $HOSTNAME_CONTROLLER|" \
        -e "s|%SERVICE_TENANT_NAME%|service|" \
        -e "s|%SERVICE_USER%|cinder|" \
        -e "s|%SERVICE_PASSWORD%|$CINDER_ADMIN_PASSWORD|" \
        /etc/cinder/api-paste.ini

    service cinder-volume restart; sleep 1
    service tgt restart; sleep 1
}

# Execution starts here

install_cinder_node
