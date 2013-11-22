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
MGMT_IF=em1
MGMT_IP=$(ifconfig $MGMT_IF | sed -n 's/^.*inet addr:\([0-9\.]\+\).*$/\1/p')

DATA_IF=em2
# FIXME: This needs to be defined in a table, and we need to bring this
# interface up.
DATA_IP=$(echo $MGMT_IP | sed 's/10\.203\.0\./10.203.1./')

# Do NOT use any non-alphanumerical characters that require quoting in
# passwords below. They would break this script.
NOVA_DB_PASSWORD=NOVA_DBPASS
NOVA_ADMIN_PASSWORD=NOVA_PASS
NEUTRON_DB_PASSWORD=NEUTRON_DBPASS
NEUTRON_ADMIN_PASSWORD=NEUTRON_PASS


keep_stock_conf() {
    CONF=$1
    if [ ! -f $CONF.stock ]; then
        mv $CONF $CONF.stock
    fi
}

configure_network() {
    # FIXME: Test that $HOSTNAME_CONTROLLER is reachable.
    # FIXME: Make sure MGMT_IP is valid.
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
my_ip=$MGMT_IP
vncserver_listen=0.0.0.0
vncserver_proxyclient_address=$MGMT_IP
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


# http://docs.openstack.org/havana/install-guide/install/apt/content/install-neutron.dedicated-compute-node.html
install_neutron_on_compute_node() {
    # FIXME: Verify that the host has at least 2 network interfaces:
    # $MGMT_IF and $DATA_IF

    apt-get -y install neutron-plugin-openvswitch-agent openvswitch-switch openvswitch-datapath-dkms

    # Disable packet destination filtering which is required for network node and compute node.
    cat > /etc/sysctl.conf <<EOF
net.ipv4.conf.all.rp_filter=0
net.ipv4.conf.default.rp_filter=0
EOF
    service procps restart; sleep 1

    # neutron.conf and api-paste.ini config which is common to all neutron installations
    # FIXME: auth_url, auth_strategy, rpc_backend, rabbit_port
    keep_stock_conf /etc/neutron/neutron.conf
    cat > /etc/neutron/neutron.conf <<EOF
[DEFAULT]
state_path = /var/lib/neutron
lock_path = \$state_path/lock
core_plugin = neutron.plugins.openvswitch.ovs_neutron_plugin.OVSNeutronPluginV2
allow_overlapping_ips = False
rabbit_host = $HOSTNAME_CONTROLLER
rabbit_password = guest
rabbit_userid = guest
notification_driver = neutron.openstack.common.notifier.rpc_notifier
[quotas]
[agent]
root_helper = sudo /usr/bin/neutron-rootwrap /etc/neutron/rootwrap.conf
[keystone_authtoken]
auth_host = $HOSTNAME_CONTROLLER
auth_port = 35357
auth_protocol = http
admin_tenant_name = service
admin_user = neutron
admin_password = $NEUTRON_ADMIN_PASSWORD
signing_dir = \$state_path/keystone-signing
[database]
connection = mysql://neutron:$NEUTRON_DB_PASSWORD@$HOSTNAME_CONTROLLER/neutron
[service_providers]
service_provider=LOADBALANCER:Haproxy:neutron.services.loadbalancer.drivers.haproxy.plugin_driver.HaproxyOnHostPluginDriver:default
EOF

    if ! egrep -qs "^auth_host=" /etc/neutron/api-paste.ini; then
        sed -i "/keystoneclient\.middleware\.auth_token:filter_factory/a auth_host=$HOSTNAME_CONTROLLER\nauth_uri=http://$HOSTNAME_CONTROLLER:5000\nadmin_user=neutron\nadmin_tenant_name=service\nadmin_password=$NEUTRON_ADMIN_PASSWORD" /etc/neutron/api-paste.ini
    fi

    service openvswitch-switch restart

    # OVS agent on "dedicated network node" and "compute node"
    if ! ovs-vsctl br-exists br-int; then
        ovs-vsctl add-br br-int
    fi


    # OVS agent on "dedicated network node" and "compute node"

    keep_stock_conf /etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini
    cat > /etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini <<EOF
[ovs]
tenant_network_type = gre
tunnel_id_ranges = 1:1000
enable_tunneling = True
integration_bridge = br-int
tunnel_bridge = br-tun
local_ip = $DATA_IP
[agent]
[securitygroup]
firewall_driver = neutron.agent.firewall.NoopFirewallDriver
EOF

    service neutron-plugin-openvswitch-agent restart; sleep 1

}


# Execution starts here

configure_network
install_extra_packages
install_nova_compute
install_neutron_on_compute_node
