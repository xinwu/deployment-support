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

# The interface on openstack management network.
MANAGEMENT_IF=em1
MANAGEMENT_IP=$(ifconfig $MANAGEMENT_IF | sed -n 's/^.*inet addr:\([0-9\.]\+\).*$/\1/p')

# Do NOT use any non-alphanumerical characters that require quoting in
# passwords below. They would break this script.
NOVA_DB_PASSWORD=NOVA_DBPASS
NOVA_ADMIN_PASSWORD=NOVA_PASS


configure_network() {
    # FIXME: Test that $HOSTNAME_CONTROLLER is reachable.
    # FIXME: Make sure MANAGEMENT_IP is valid.
    echo
}

install_extra_packages() {
    apt-get -y install vim-nox debconf-utils python-mysqldb curl
}

# http://docs.openstack.org/havana/install-guide/install/apt/content/nova-compute.html
install_nova_compute() {
    apt-get -y install nova-compute-kvm python-guestfs
    chmod 0644 /boot/vmlinuz*

    if ! egrep -qs '^\[database\]' /etc/nova/nova.conf; then
        cat >> /etc/nova/nova.conf <<EOF
my_ip=$MANAGEMENT_IP
vncserver_listen=0.0.0.0
vncserver_proxyclient_address=$MANAGEMENT_IP
rpc_backend=nova.rpc.impl_kombu
rabbit_host=$HOSTNAME_CONTROLLER
glance_host=$HOSTNAME_CONTROLLER

[database]
connection = mysql://nova:$NOVA_DB_PASSWORD@$HOSTNAME_CONTROLLER/nova
EOF
    fi
    rm -f /var/lib/nova/nova.sqlite

    sed -i \
        -e "s|^auth_host = .*$|auth_host = $HOSTNAME_CONTROLLER|" \
        -e "s|%SERVICE_TENANT_NAME%|service|" \
        -e "s|%SERVICE_USER%|nova|" \
        -e "s|%SERVICE_PASSWORD%|$NOVA_ADMIN_PASSWORD|" \
        /etc/nova/api-paste.ini

    service nova-compute restart; sleep 1
}

# Execution starts here

configure_network
install_extra_packages
install_nova_compute

